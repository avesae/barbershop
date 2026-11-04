"""Админка: клиенты и карточка клиента."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import booking as bk
from ..deps import get_session, require_admin
from ..models import Booking, Client, Consent, Review
from ..stats import VISITED, outcome

router = APIRouter(prefix="/api/admin/clients", tags=["admin"], dependencies=[Depends(require_admin)])


def _metrics(bookings: list[Booking], now: datetime) -> dict:
    visits = sorted(b.start_at for b in bookings if outcome(b.status, b.start_at, now) == VISITED)
    gaps = [(b - a).days for a, b in zip(visits, visits[1:])]
    upcoming = sorted(b.start_at for b in bookings if outcome(b.status, b.start_at, now) == "upcoming")
    return {
        "visits": len(visits),
        "no_shows": sum(1 for b in bookings if b.status == "no_show"),
        "spent": sum(b.price for b in bookings if outcome(b.status, b.start_at, now) == VISITED),
        "last_visit": visits[-1] if visits else None,
        "next_visit": upcoming[0] if upcoming else None,
        "avg_interval_days": round(sum(gaps) / len(gaps)) if gaps else None,
    }


async def _bookings_by_client(session: AsyncSession, client_ids: list[int]) -> dict[int, list[Booking]]:
    rows = await session.execute(select(Booking).where(Booking.client_id.in_(client_ids)).order_by(Booking.start_at))
    result: dict[int, list[Booking]] = {cid: [] for cid in client_ids}
    for b in rows.scalars():
        result[b.client_id].append(b)
    return result


@router.get("")
async def clients(q: str = "", session: AsyncSession = Depends(get_session)) -> list[dict]:
    query = select(Client).where(Client.phone.is_not(None)).order_by(Client.id.desc()).limit(200)
    if q.strip():
        like = f"%{q.strip()}%"
        digits = "".join(ch for ch in q if ch.isdigit())
        conds = [Client.name.ilike(like)]
        if digits:
            conds.append(Client.phone.like(f"%{digits}%"))
        query = query.where(or_(*conds))
    items = list((await session.execute(query)).scalars())
    by_client = await _bookings_by_client(session, [c.id for c in items])
    now = bk.now_local()
    return [
        {"id": c.id, "name": c.name, "phone": c.phone, "telegram": c.tg_user_id is not None,
         **_metrics(by_client[c.id], now)}
        for c in items
    ]


@router.get("/{client_id}")
async def client_card(client_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    c = await session.get(Client, client_id)
    if not c:
        raise HTTPException(404, "Клиент не найден")
    bookings = (await _bookings_by_client(session, [c.id]))[c.id]
    consent = (
        await session.execute(select(Consent).where(Consent.client_id == c.id).order_by(Consent.accepted_at.desc()).limit(1))
    ).scalar_one_or_none()
    reviews = (await session.execute(select(Review).where(Review.client_id == c.id))).scalars()
    rating = {r.booking_id: r.rating for r in reviews}
    return {
        "id": c.id,
        "name": c.name,
        "phone": c.phone,
        "telegram": c.tg_user_id is not None,
        "notes": c.notes,
        "created_at": c.created_at,
        "consent": {"version": consent.version, "accepted_at": consent.accepted_at, "source": consent.source}
        if consent else None,
        **_metrics(bookings, bk.now_local()),
        "history": [
            {"id": b.id, "start_at": b.start_at, "service": b.service.name, "master": b.master.name,
             "price": b.price, "status": b.status, "source": b.source, "rating": rating.get(b.id)}
            for b in reversed(bookings)
        ],
    }


class NotesIn(BaseModel):
    notes: str = Field(max_length=2000)


@router.put("/{client_id}/notes")
async def set_notes(client_id: int, data: NotesIn, session: AsyncSession = Depends(get_session)) -> dict:
    c = await session.get(Client, client_id)
    if not c:
        raise HTTPException(404, "Клиент не найден")
    c.notes = data.notes
    await session.commit()
    return {"notes": c.notes}
