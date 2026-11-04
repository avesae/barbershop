from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import booking as bk
from ..config import get_settings
from ..consent import CONSENT_VERSION, consent_text
from ..deps import get_session
from ..models import Master, Service
from ..notify import booking_summary, notify_owner
from ..schemas import BookingCreated, BookingIn, MasterOut, ServiceOut

router = APIRouter(prefix="/api", tags=["public"])


@router.get("/health")
async def health() -> dict:
    return {"ok": True}


@router.get("/info")
async def info() -> dict:
    s = get_settings()
    return {
        "name": s.shop_name,
        "address": s.shop_address,
        "phone": s.shop_phone,
        "bot_username": s.bot_username,
        "consent_version": CONSENT_VERSION,
        "consent_text": consent_text(),
    }


@router.get("/services", response_model=list[ServiceOut])
async def services(session: AsyncSession = Depends(get_session)):
    rows = await session.execute(select(Service).where(Service.is_active).order_by(Service.sort, Service.id))
    return [
        ServiceOut.model_validate(s).model_copy(update={"master_ids": sorted(m.id for m in s.masters if m.is_active)})
        for s in rows.scalars()
    ]


@router.get("/masters", response_model=list[MasterOut])
async def masters(session: AsyncSession = Depends(get_session)):
    rows = await session.execute(select(Master).where(Master.is_active).order_by(Master.id))
    return [
        MasterOut.model_validate(m).model_copy(update={"service_ids": sorted(s.id for s in m.services if s.is_active)})
        for m in rows.scalars()
    ]


@router.get("/dates")
async def dates(master_id: int, service_id: int, session: AsyncSession = Depends(get_session)) -> list[date]:
    try:
        return await bk.available_dates(session, master_id, service_id)
    except bk.BookingError as e:
        raise HTTPException(400, str(e))


@router.get("/slots")
async def slots(master_id: int, service_id: int, day: date, session: AsyncSession = Depends(get_session)) -> list[str]:
    try:
        return [t.strftime("%H:%M") for t in await bk.slots_for_day(session, master_id, service_id, day)]
    except bk.BookingError as e:
        raise HTTPException(400, str(e))


@router.post("/bookings", response_model=BookingCreated, status_code=201)
async def create_booking(data: BookingIn, session: AsyncSession = Depends(get_session)):
    if not data.consent:
        raise HTTPException(400, "Нужно согласие на обработку персональных данных")
    try:
        client = await bk.get_or_create_phone_client(session, data.name.strip(), data.phone)
        await bk.record_consent(session, client, "site")
        booking = await bk.create_booking(
            session,
            client=client,
            master_id=data.master_id,
            service_id=data.service_id,
            start_at=data.start_at.replace(tzinfo=None, second=0, microsecond=0),
            source="site",
        )
    except bk.BookingError as e:
        raise HTTPException(409 if isinstance(e, bk.SlotTaken) else 400, str(e))
    await notify_owner("🆕 Новая запись", booking)
    username = get_settings().bot_username
    return BookingCreated(
        id=booking.id,
        summary=booking_summary(booking),
        bot_link=f"https://t.me/{username}?start={booking.link_code}" if username else None,
    )
