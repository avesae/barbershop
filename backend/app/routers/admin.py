from collections import Counter
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import booking as bk
from ..deps import get_session, require_admin
from ..models import Booking, Master, Service, TimeOff
from ..notify import booking_summary, send
from ..schemas import AdminBooking, ServiceIn, ServiceOut, TimeOffIn, TimeOffOut

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _admin_booking(b: Booking) -> AdminBooking:
    return AdminBooking(
        id=b.id,
        master_id=b.master_id,
        master=b.master.name,
        service=b.service.name,
        start_at=b.start_at,
        end_at=b.end_at,
        price=b.price,
        status=b.status,
        source=b.source,
        client_name=b.client.name if b.client else None,
        client_phone=b.client.phone if b.client else None,
        telegram=bool(b.client and b.client.tg_user_id),
    )


async def _bookings(session: AsyncSession, start: datetime, end: datetime, status: str | None = None):
    q = select(Booking).where(Booking.start_at >= start, Booking.start_at < end).order_by(Booking.start_at)
    if status:
        q = q.where(Booking.status == status)
    return list((await session.execute(q)).scalars())


@router.get("/check")
async def check() -> dict:
    return {"ok": True}


@router.get("/schedule")
async def schedule(
    day: date,
    days: int = Query(1, ge=1, le=7),
    session: AsyncSession = Depends(get_session),
) -> dict:
    start = datetime.combine(day, time.min)
    end = start + timedelta(days=days)
    masters = list((await session.execute(select(Master).where(Master.is_active).order_by(Master.id))).scalars())
    off = await session.execute(
        select(TimeOff).where(TimeOff.start_at < end, TimeOff.end_at > start).order_by(TimeOff.start_at)
    )
    return {
        "masters": [
            {
                "id": m.id,
                "name": m.name,
                "hours": [
                    {"weekday": w.weekday, "start": w.start.strftime("%H:%M"), "end": w.end.strftime("%H:%M")}
                    for w in m.working_hours
                ],
            }
            for m in masters
        ],
        "bookings": [_admin_booking(b) for b in await _bookings(session, start, end, "active")],
        "time_off": [TimeOffOut.model_validate(t) for t in off.scalars()],
    }


@router.get("/bookings", response_model=list[AdminBooking])
async def bookings(
    date_from: date | None = None,
    date_to: date | None = None,
    status: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    today = bk.now_local().date()
    start = datetime.combine(date_from or today, time.min)
    end = datetime.combine(date_to or today + timedelta(days=14), time.min) + timedelta(days=1)
    return [_admin_booking(b) for b in await _bookings(session, start, end, status)]


@router.post("/bookings/{booking_id}/cancel", response_model=AdminBooking)
async def cancel(booking_id: int, session: AsyncSession = Depends(get_session)):
    b = await bk.get_booking(session, booking_id)
    if not b:
        raise HTTPException(404, "Запись не найдена")
    try:
        await bk.cancel_booking(session, b)
    except bk.BookingError as e:
        raise HTTPException(400, str(e))
    if b.client and b.client.tg_user_id:
        await send(b.client.tg_user_id, f"❌ Ваша запись отменена барбершопом.\n{booking_summary(b)}")
    return _admin_booking(b)


# --- услуги --------------------------------------------------------------


def _service_out(s: Service) -> ServiceOut:
    return ServiceOut.model_validate(s).model_copy(update={"master_ids": sorted(m.id for m in s.masters)})


@router.get("/masters")
async def masters(session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = await session.execute(select(Master).order_by(Master.id))
    return [{"id": m.id, "name": m.name, "is_active": m.is_active} for m in rows.scalars()]


@router.get("/services", response_model=list[ServiceOut])
async def services(session: AsyncSession = Depends(get_session)):
    rows = await session.execute(select(Service).order_by(Service.sort, Service.id))
    return [_service_out(s) for s in rows.scalars()]


async def _apply(session: AsyncSession, s: Service, data: ServiceIn) -> Service:
    q = select(Master).where(Master.id.in_(data.master_ids)).options(selectinload(Master.services))
    masters = list((await session.execute(q)).scalars())
    s.name, s.description, s.price = data.name, data.description, data.price
    s.duration_min, s.is_active = data.duration_min, data.is_active
    s.masters = masters
    session.add(s)
    await session.commit()
    await session.refresh(s)
    return s


@router.post("/services", response_model=ServiceOut, status_code=201)
async def create_service(data: ServiceIn, session: AsyncSession = Depends(get_session)):
    s = Service(sort=100, masters=[])
    return _service_out(await _apply(session, s, data))


@router.put("/services/{service_id}", response_model=ServiceOut)
async def update_service(service_id: int, data: ServiceIn, session: AsyncSession = Depends(get_session)):
    s = await session.get(Service, service_id)
    if not s:
        raise HTTPException(404, "Услуга не найдена")
    return _service_out(await _apply(session, s, data))


# --- закрытое время ------------------------------------------------------


@router.get("/time-off", response_model=list[TimeOffOut])
async def time_off(session: AsyncSession = Depends(get_session)):
    start = datetime.combine(bk.now_local().date(), time.min)
    rows = await session.execute(select(TimeOff).where(TimeOff.end_at > start).order_by(TimeOff.start_at))
    return list(rows.scalars())


@router.post("/time-off", response_model=TimeOffOut, status_code=201)
async def add_time_off(data: TimeOffIn, session: AsyncSession = Depends(get_session)):
    if not await session.get(Master, data.master_id):
        raise HTTPException(404, "Мастер не найден")
    start = datetime.combine(data.day, data.start or time.min)
    end = datetime.combine(data.day, data.end) if data.end else datetime.combine(data.day + timedelta(days=1), time.min)
    if end <= start:
        raise HTTPException(400, "Конец должен быть позже начала")
    t = TimeOff(master_id=data.master_id, start_at=start, end_at=end, reason=data.reason or "Закрыто")
    session.add(t)
    await session.commit()
    return t


@router.delete("/time-off/{time_off_id}", status_code=204)
async def delete_time_off(time_off_id: int, session: AsyncSession = Depends(get_session)):
    t = await session.get(TimeOff, time_off_id)
    if not t:
        raise HTTPException(404, "Не найдено")
    await session.delete(t)
    await session.commit()


# --- статистика ----------------------------------------------------------


@router.get("/stats")
async def stats(session: AsyncSession = Depends(get_session)) -> dict:
    today = bk.now_local().date()
    week_start = datetime.combine(today - timedelta(days=6), time.min)
    week_end = datetime.combine(today + timedelta(days=1), time.min)
    week = await _bookings(session, week_start, week_end)
    active = [b for b in week if b.status == "active"]
    per_day = Counter(b.start_at.date() for b in active)

    month = await _bookings(session, week_end - timedelta(days=30), week_end, "active")
    popular = Counter(b.service.name for b in month)
    by_master = Counter(b.master.name for b in active)

    return {
        "week": [
            {"day": (today - timedelta(days=i)).isoformat(), "count": per_day[today - timedelta(days=i)]}
            for i in range(6, -1, -1)
        ],
        "week_total": len(active),
        "week_cancelled": len(week) - len(active),
        "week_revenue": sum(b.price for b in active),
        "services_30d": [{"name": n, "count": c} for n, c in popular.most_common()],
        "masters_week": [{"name": n, "count": c} for n, c in by_master.most_common()],
    }
