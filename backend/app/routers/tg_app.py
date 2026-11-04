"""API для Telegram Mini App: пользователь определяется по подписанному initData."""

from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from .. import booking as bk
from .. import engagement as eg
from ..config import get_settings
from ..consent import consent_text
from ..deps import get_session
from ..notify import booking_summary, notify_owner, send
from ..telegram_auth import InitDataError, verify

router = APIRouter(prefix="/api/tg", tags=["mini-app"])


def tg_user(x_telegram_init_data: str = Header(default="")) -> dict:
    try:
        return verify(x_telegram_init_data, get_settings().bot_token)
    except InitDataError as e:
        raise HTTPException(401, str(e))


@router.get("/me")
async def me(user: dict = Depends(tg_user), session: AsyncSession = Depends(get_session)) -> dict:
    client = await bk.client_by_tg(session, user["id"])
    return {
        "name": (client.name if client else None) or user.get("first_name", ""),
        "phone": client.phone if client else None,
        "consent": bool(client and await bk.has_current_consent(session, client)),
        "consent_text": consent_text(),
    }


class TgBookingIn(BaseModel):
    service_id: int
    master_id: int
    start_at: datetime
    name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=5, max_length=30)
    consent: bool


@router.post("/bookings", status_code=201)
async def create(data: TgBookingIn, user: dict = Depends(tg_user), session: AsyncSession = Depends(get_session)) -> dict:
    client = await bk.client_by_tg(session, user["id"])
    has_consent = bool(client and await bk.has_current_consent(session, client))
    if not has_consent and not data.consent:
        raise HTTPException(400, "Нужно согласие на обработку персональных данных")
    try:
        client = await bk.get_or_create_tg_client(session, user["id"])
        if not has_consent:
            await bk.record_consent(session, client, "bot")
        await bk.set_tg_client_contacts(session, client, data.name.strip(), data.phone)
        booking = await bk.create_booking(
            session,
            client=client,
            master_id=data.master_id,
            service_id=data.service_id,
            start_at=data.start_at.replace(tzinfo=None, second=0, microsecond=0),
            source="bot",
        )
        await eg.close_waitlist(session, client, booking.service_id, booking.start_at.date())
    except bk.BookingError as e:
        raise HTTPException(409 if isinstance(e, bk.SlotTaken) else 400, str(e))
    summary = booking_summary(booking)
    await send(user["id"], f"✅ Вы записаны!\n\n{summary}\n\nНапомним за день и за 2 часа. Перенести или отменить — в «Мои записи».")
    await notify_owner("🆕 Новая запись (Mini App)", booking)
    return {"id": booking.id, "summary": summary}
