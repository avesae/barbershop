"""Сообщения в Telegram через Bot API. Нужны API-серверу (записи с сайта) и боту."""

import logging

import httpx

from .config import get_settings
from .models import Booking

log = logging.getLogger(__name__)

WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]


def human_dt(dt) -> str:
    return f"{dt.day} {MONTHS[dt.month - 1]} ({WEEKDAYS[dt.weekday()]}), {dt:%H:%M}"


def booking_summary(b: Booking) -> str:
    return (
        f"{b.service.name} — {b.price} ₽\n"
        f"Мастер: {b.master.name}\n"
        f"Когда: {human_dt(b.start_at)}"
    )


def owner_text(event: str, b: Booking) -> str:
    client = b.client
    who = f"{client.name or '—'}, {client.phone or 'без телефона'}" if client else "данные удалены"
    source = "сайт" if b.source == "site" else "бот"
    return f"{event} #{b.id} ({source})\n{booking_summary(b)}\nКлиент: {who}"


async def send(chat_id: int | str, text: str) -> bool:
    token = get_settings().bot_token
    if not token or not chat_id:
        log.info("Telegram не настроен, сообщение не отправлено: %s", text.splitlines()[0])
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
            r.raise_for_status()
        return True
    except httpx.HTTPError as e:
        log.warning("Не удалось отправить сообщение в Telegram: %s", e)
        return False


async def notify_owner(event: str, b: Booking) -> None:
    """Владельцу и самому мастеру, если он подключил кабинет в боте."""
    text = owner_text(event, b)
    await send(get_settings().admin_chat_id, text)
    if b.master and b.master.tg_user_id and str(b.master.tg_user_id) != str(get_settings().admin_chat_id):
        await send(b.master.tg_user_id, text)
