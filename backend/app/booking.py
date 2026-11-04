"""Бизнес-логика записи. Используется и API, и ботом."""

import re
import secrets
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from . import reminders
from .config import get_settings
from .consent import CONSENT_VERSION
from .models import Booking, Client, Consent, Master, Review, Service, TimeOff, WaitlistEntry, WorkingHours
from .slots import Interval, free_slots


class BookingError(Exception):
    """Ошибка, текст которой можно показать клиенту."""


class SlotTaken(BookingError):
    def __init__(self) -> None:
        super().__init__("Это время уже занято, выберите другое")


def now_local() -> datetime:
    tz = ZoneInfo(get_settings().shop_tz)
    return datetime.now(tz).replace(tzinfo=None, second=0, microsecond=0)


def normalize_phone(raw: str) -> str:
    """Российский номер в формате +7XXXXXXXXXX."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 10 and digits.startswith("9"):
        digits = "7" + digits
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    raise BookingError("Укажите номер телефона в формате +7 900 000-00-00")


# --- слоты ---------------------------------------------------------------


async def _bookable(session: AsyncSession, master_id: int, service_id: int) -> tuple[Master, Service]:
    # populate_existing: после rollback связи в identity map сброшены, а ленивая
    # подгрузка в async-сессии невозможна.
    master = await session.get(
        Master,
        master_id,
        options=[selectinload(Master.services), selectinload(Master.working_hours)],
        populate_existing=True,
    )
    service = await session.get(Service, service_id, populate_existing=True)
    if not master or not master.is_active or not service or not service.is_active:
        raise BookingError("Мастер или услуга недоступны")
    if service not in master.services:
        raise BookingError("Этот мастер не оказывает выбранную услугу")
    return master, service


async def _busy(
    session: AsyncSession,
    master_id: int,
    start: datetime,
    end: datetime,
    exclude_booking_id: int | None = None,
) -> list[Interval]:
    q = select(Booking.start_at, Booking.end_at).where(
        Booking.master_id == master_id,
        Booking.status == "active",
        Booking.start_at < end,
        Booking.end_at > start,
    )
    if exclude_booking_id:
        q = q.where(Booking.id != exclude_booking_id)
    busy = [(r.start_at, r.end_at) for r in await session.execute(q)]
    off = await session.execute(
        select(TimeOff.start_at, TimeOff.end_at).where(
            TimeOff.master_id == master_id, TimeOff.start_at < end, TimeOff.end_at > start
        )
    )
    busy += [(r.start_at, r.end_at) for r in off]
    return busy


def _work(master: Master, day: date) -> list[tuple[time, time]]:
    return [(w.start, w.end) for w in master.working_hours if w.weekday == day.weekday()]


async def slots_for_day(
    session: AsyncSession,
    master_id: int,
    service_id: int,
    day: date,
    *,
    now: datetime | None = None,
    exclude_booking_id: int | None = None,
) -> list[datetime]:
    s = get_settings()
    now = now or now_local()
    if day < now.date() or day > now.date() + timedelta(days=s.booking_days_ahead):
        return []
    master, service = await _bookable(session, master_id, service_id)
    day_start = datetime.combine(day, time.min)
    busy = await _busy(session, master_id, day_start, day_start + timedelta(days=1), exclude_booking_id)
    return free_slots(
        day,
        service.duration_min,
        _work(master, day),
        busy,
        now=now,
        step_min=s.slot_step_min,
        min_lead_min=s.min_lead_min,
    )


async def available_dates(
    session: AsyncSession,
    master_id: int,
    service_id: int,
    *,
    now: datetime | None = None,
    exclude_booking_id: int | None = None,
) -> list[date]:
    now = now or now_local()
    days = [now.date() + timedelta(days=i) for i in range(get_settings().booking_days_ahead + 1)]
    result = []
    for d in days:
        if await slots_for_day(
            session, master_id, service_id, d, now=now, exclude_booking_id=exclude_booking_id
        ):
            result.append(d)
    return result


# --- клиенты и согласие --------------------------------------------------


async def client_by_tg(session: AsyncSession, tg_user_id: int) -> Client | None:
    return (await session.execute(select(Client).where(Client.tg_user_id == tg_user_id))).scalar_one_or_none()


async def get_or_create_tg_client(session: AsyncSession, tg_user_id: int) -> Client:
    client = await client_by_tg(session, tg_user_id)
    if not client:
        client = Client(tg_user_id=tg_user_id)
        session.add(client)
        await session.flush()
    return client


async def get_or_create_phone_client(session: AsyncSession, name: str, phone: str) -> Client:
    phone = normalize_phone(phone)
    client = (
        await session.execute(select(Client).where(Client.phone == phone).order_by(Client.id).limit(1))
    ).scalar_one_or_none()
    if not client:
        client = Client(phone=phone)
        session.add(client)
    client.name = name
    await session.flush()
    return client


async def set_tg_client_contacts(session: AsyncSession, client: Client, name: str, phone: str) -> Client:
    """Имя и телефон для клиента из бота. Если этот номер уже записывался
    через сайт, его записи переходят к Telegram-клиенту."""
    phone = normalize_phone(phone)
    others = (
        await session.execute(
            select(Client).where(Client.phone == phone, Client.id != client.id, Client.tg_user_id.is_(None))
        )
    ).scalars()
    for other in others:
        await session.execute(update(Booking).where(Booking.client_id == other.id).values(client_id=client.id))
        await session.execute(update(Consent).where(Consent.client_id == other.id).values(client_id=client.id))
        await session.delete(other)
    client.name = name
    client.phone = phone
    await session.flush()
    return client


async def record_consent(session: AsyncSession, client: Client, source: str) -> Consent:
    consent = Consent(client_id=client.id, version=CONSENT_VERSION, source=source, accepted_at=now_local())
    session.add(consent)
    await session.flush()
    return consent


async def has_current_consent(session: AsyncSession, client: Client) -> bool:
    q = select(func.count()).where(Consent.client_id == client.id, Consent.version == CONSENT_VERSION)
    return (await session.scalar(q)) > 0


async def delete_client_data(session: AsyncSession, client: Client) -> int:
    """Отзыв согласия: будущие записи отменяются, прошлые обезличиваются,
    клиент и его согласия удаляются. Возвращает число отменённых записей."""
    now = now_local()
    cancelled = await session.execute(
        update(Booking)
        .where(Booking.client_id == client.id, Booking.status == "active", Booking.start_at > now)
        .values(status="cancelled")
    )
    await session.execute(
        update(Booking).where(Booking.client_id == client.id).values(client_id=None, link_code=None)
    )
    await session.execute(delete(Consent).where(Consent.client_id == client.id))
    await session.execute(delete(Review).where(Review.client_id == client.id))
    await session.execute(delete(WaitlistEntry).where(WaitlistEntry.client_id == client.id))
    await session.delete(client)
    await session.commit()
    return cancelled.rowcount or 0


# --- записи --------------------------------------------------------------


async def _lock_master(session: AsyncSession, master_id: int) -> None:
    # В PostgreSQL параллельные записи к одному мастеру выстраиваются в очередь.
    await session.execute(select(Master.id).where(Master.id == master_id).with_for_update())


async def _save(session: AsyncSession) -> None:
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise SlotTaken() from None


async def create_booking(
    session: AsyncSession,
    *,
    client: Client,
    master_id: int,
    service_id: int,
    start_at: datetime,
    source: str,
    now: datetime | None = None,
) -> Booking:
    now = now or now_local()
    await _lock_master(session, master_id)
    _, service = await _bookable(session, master_id, service_id)
    if start_at not in await slots_for_day(session, master_id, service_id, start_at.date(), now=now):
        raise SlotTaken()
    r24, r2 = reminders.initial_flags(start_at, now)
    booking = Booking(
        client_id=client.id,
        master_id=master_id,
        service_id=service_id,
        start_at=start_at,
        end_at=start_at + timedelta(minutes=service.duration_min),
        price=service.price,
        status="active",
        source=source,
        reminded_24h=r24,
        reminded_2h=r2,
        link_code=secrets.token_urlsafe(9) if source == "site" else None,
    )
    session.add(booking)
    await _save(session)
    return await get_booking(session, booking.id)


async def get_booking(session: AsyncSession, booking_id: int) -> Booking | None:
    return (
        await session.execute(select(Booking).where(Booking.id == booking_id).execution_options(populate_existing=True))
    ).scalar_one_or_none()


async def reschedule_booking(
    session: AsyncSession, booking: Booking, new_start: datetime, *, now: datetime | None = None
) -> Booking:
    now = now or now_local()
    if booking.status != "active" or booking.start_at <= now:
        raise BookingError("Эту запись уже нельзя перенести")
    await _lock_master(session, booking.master_id)
    slots = await slots_for_day(
        session, booking.master_id, booking.service_id, new_start.date(), now=now, exclude_booking_id=booking.id
    )
    if new_start not in slots:
        raise SlotTaken()
    booking.end_at = new_start + (booking.end_at - booking.start_at)
    booking.start_at = new_start
    booking.reminded_24h, booking.reminded_2h = reminders.initial_flags(new_start, now)
    await _save(session)
    return await get_booking(session, booking.id)


async def cancel_booking(session: AsyncSession, booking: Booking) -> Booking:
    if booking.status != "active":
        raise BookingError("Запись уже отменена")
    booking.status = "cancelled"
    await session.commit()
    return booking


async def set_visit_status(session: AsyncSession, booking: Booking, status: str) -> Booking:
    """Отметка «пришёл» / «не пришёл» (или сброс отметки) для начавшейся записи."""
    if booking.status == "cancelled":
        raise BookingError("Запись отменена")
    if booking.start_at > now_local():
        raise BookingError("Визит ещё не начался")
    booking.status = status
    await session.commit()
    return booking


async def upcoming_for_client(session: AsyncSession, client: Client) -> list[Booking]:
    q = (
        select(Booking)
        .where(Booking.client_id == client.id, Booking.status == "active", Booking.start_at > now_local())
        .order_by(Booking.start_at)
    )
    return list((await session.execute(q)).scalars())


async def link_booking_to_tg(session: AsyncSession, code: str, tg_user_id: int) -> Booking | None:
    """Привязать запись с сайта к Telegram, чтобы приходили напоминания."""
    booking = (await session.execute(select(Booking).where(Booking.link_code == code))).scalar_one_or_none()
    if not booking or not booking.client:
        return None
    site_client = booking.client
    tg_client = await client_by_tg(session, tg_user_id)
    if tg_client and tg_client.id != site_client.id:
        await set_tg_client_contacts(session, tg_client, site_client.name or "", site_client.phone or "")
    else:
        site_client.tg_user_id = tg_user_id
    booking.link_code = None
    await session.commit()
    return await get_booking(session, booking.id)


# --- напоминания ---------------------------------------------------------


async def due_reminders(session: AsyncSession, now: datetime | None = None) -> list[tuple[Booking, str]]:
    now = now or now_local()
    q = (
        select(Booking)
        .join(Client, Booking.client_id == Client.id)
        .where(
            Booking.status == "active",
            Booking.start_at > now,
            Booking.start_at <= now + reminders.DAY_BEFORE,
            Client.tg_user_id.is_not(None),
            (Booking.reminded_24h.is_(False)) | (Booking.reminded_2h.is_(False)),
        )
    )
    due = []
    for b in (await session.execute(q)).scalars():
        kind = reminders.reminder_due(b.start_at, now, b.reminded_24h, b.reminded_2h)
        if kind:
            due.append((b, kind))
    return due


async def mark_reminded(session: AsyncSession, booking: Booking, kind: str) -> None:
    booking.reminded_24h = True
    if kind == "2h":
        booking.reminded_2h = True
    await session.commit()
