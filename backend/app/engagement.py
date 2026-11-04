"""Кабинет мастера, отзывы, повторная запись и лист ожидания."""

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import booking as bk
from .models import Booking, Client, Master, Review, Service, TimeOff, WaitlistEntry

REVIEW_DELAY = timedelta(hours=3)
REVIEW_WINDOW = timedelta(days=3)  # старые визиты не тревожим


# --- кабинет мастера -------------------------------------------------------


async def master_by_tg(session: AsyncSession, tg_user_id: int) -> Master | None:
    return (await session.execute(select(Master).where(Master.tg_user_id == tg_user_id))).scalar_one_or_none()


async def link_master(session: AsyncSession, code: str, tg_user_id: int) -> Master | None:
    master = (await session.execute(select(Master).where(Master.invite_code == code))).scalar_one_or_none()
    if not master:
        return None
    other = await master_by_tg(session, tg_user_id)
    if other and other.id != master.id:
        other.tg_user_id = None
        await session.flush()
    master.tg_user_id = tg_user_id
    master.invite_code = None
    await session.commit()
    return master


async def master_day(session: AsyncSession, master_id: int, day: date) -> list[Booking]:
    start = datetime.combine(day, time.min)
    q = (
        select(Booking)
        .where(
            Booking.master_id == master_id,
            Booking.status != "cancelled",
            Booking.start_at >= start,
            Booking.start_at < start + timedelta(days=1),
        )
        .order_by(Booking.start_at)
    )
    return list((await session.execute(q)).scalars())


def parse_range(text: str) -> tuple[time, time] | None:
    """«14:00-15:00», «14-15», «14.00–15.30» → (start, end). None — непонятно."""
    cleaned = text.replace("–", "-").replace("—", "-").replace(".", ":").replace(" ", "")
    parts = cleaned.split("-")
    if len(parts) != 2:
        return None
    try:
        a, b = (time.fromisoformat(p if ":" in p else f"{int(p):02d}:00") for p in parts)
    except ValueError:
        return None
    return (a, b) if a < b else None


async def close_time(
    session: AsyncSession, master_id: int, start: datetime, end: datetime, reason: str
) -> tuple[TimeOff, list[Booking]]:
    """Закрыть время. Возвращает и записи, которые попали в закрытый интервал."""
    if end <= start:
        raise bk.BookingError("Конец должен быть позже начала")
    t = TimeOff(master_id=master_id, start_at=start, end_at=end, reason=reason)
    session.add(t)
    await session.commit()
    conflicts = [b for b in await master_day(session, master_id, start.date()) if b.start_at < end and b.end_at > start]
    return t, conflicts


# --- отзывы ----------------------------------------------------------------


async def due_review_requests(session: AsyncSession, now: datetime | None = None) -> list[Booking]:
    now = now or bk.now_local()
    q = (
        select(Booking)
        .join(Client, Booking.client_id == Client.id)
        .where(
            Booking.status.in_(["active", "done"]),
            Booking.review_asked.is_(False),
            Booking.end_at <= now - REVIEW_DELAY,
            Booking.end_at >= now - REVIEW_WINDOW,
            Client.tg_user_id.is_not(None),
        )
    )
    return list((await session.execute(q)).scalars())


async def save_rating(session: AsyncSession, booking: Booking, rating: int) -> Review:
    if not 1 <= rating <= 5:
        raise bk.BookingError("Оценка от 1 до 5")
    review = (await session.execute(select(Review).where(Review.booking_id == booking.id))).scalar_one_or_none()
    if review is None:
        review = Review(
            booking_id=booking.id,
            client_id=booking.client_id,
            master_id=booking.master_id,
            author=(booking.client.name or "Клиент") if booking.client else "Клиент",
            created_at=bk.now_local(),
            rating=rating,
        )
        session.add(review)
    review.rating = rating
    await session.commit()
    return review


async def save_review_text(session: AsyncSession, review_id: int, text: str) -> Review | None:
    review = await session.get(Review, review_id)
    if review:
        review.text = text.strip()[:1000]
        await session.commit()
    return review


# --- повторная запись -------------------------------------------------------


async def due_rebook_offers(session: AsyncSession, now: datetime | None = None) -> list[Booking]:
    """Последний визит клиента, после которого прошло rebook_days и нет новых записей."""
    now = now or bk.now_local()
    q = (
        select(Booking)
        .join(Client, Booking.client_id == Client.id)
        .join(Service, Booking.service_id == Service.id)
        .where(
            Booking.status.in_(["active", "done"]),
            Booking.rebook_offered.is_(False),
            Booking.end_at <= now,
            Service.rebook_days > 0,
            Client.tg_user_id.is_not(None),
        )
        .order_by(Booking.start_at)
    )
    latest: dict[int, Booking] = {}
    stale: list[Booking] = []
    for b in (await session.execute(q)).scalars():
        if b.client_id in latest:
            stale.append(latest[b.client_id])
        latest[b.client_id] = b
    # Более ранние визиты уже не нужны — помечаем, чтобы не пересчитывать.
    for b in stale:
        b.rebook_offered = True

    due = []
    for b in latest.values():
        if b.end_at + timedelta(days=b.service.rebook_days) > now:
            continue
        later = await session.scalar(
            select(Booking.id).where(
                Booking.client_id == b.client_id,
                Booking.status != "cancelled",
                Booking.start_at > b.start_at,
            ).limit(1)
        )
        if later:
            b.rebook_offered = True
        else:
            due.append(b)
    await session.commit()
    return due


async def mark_rebook_offered(session: AsyncSession, booking: Booking) -> None:
    booking.rebook_offered = True
    await session.commit()


# --- лист ожидания ---------------------------------------------------------


async def join_waitlist(
    session: AsyncSession, client: Client, service_id: int, master_id: int | None, day: date
) -> WaitlistEntry:
    existing = (
        await session.execute(
            select(WaitlistEntry).where(
                WaitlistEntry.client_id == client.id,
                WaitlistEntry.service_id == service_id,
                WaitlistEntry.master_id == master_id if master_id else WaitlistEntry.master_id.is_(None),
                WaitlistEntry.day == day,
                WaitlistEntry.is_active,
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    entry = WaitlistEntry(
        client_id=client.id, service_id=service_id, master_id=master_id, day=day, created_at=bk.now_local()
    )
    session.add(entry)
    await session.commit()
    return entry


async def waitlist_candidates(session: AsyncSession, entry: WaitlistEntry) -> list[Master]:
    """Мастера, к которым можно на эту услугу (все — если клиенту не важно, к кому)."""
    if entry.master_id:
        return [entry.master] if entry.master and entry.master.is_active else []
    service = await session.get(Service, entry.service_id)
    return sorted((m for m in service.masters if m.is_active), key=lambda m: m.id)


async def due_waitlist(
    session: AsyncSession, now: datetime | None = None
) -> list[tuple[WaitlistEntry, Master, list[datetime]]]:
    """Записи листа ожидания, для которых освободилось время. Прошедшие дни закрываются."""
    now = now or bk.now_local()
    q = select(WaitlistEntry).where(WaitlistEntry.is_active).order_by(WaitlistEntry.created_at)
    due = []
    for entry in list((await session.execute(q)).scalars()):
        if entry.day < now.date():
            entry.is_active = False
            continue
        if entry.notified_at or not entry.client.tg_user_id:
            continue
        for master in await waitlist_candidates(session, entry):
            try:
                slots = await bk.slots_for_day(session, master.id, entry.service_id, entry.day, now=now)
            except bk.BookingError:
                continue
            if slots:
                due.append((entry, master, slots))
                break
    await session.commit()
    return due


async def mark_waitlist_notified(session: AsyncSession, entry: WaitlistEntry) -> None:
    entry.notified_at = bk.now_local()
    await session.commit()


async def close_waitlist(session: AsyncSession, client: Client, service_id: int, day: date) -> None:
    """Клиент записался — его ожидание на этот день больше не нужно."""
    rows = await session.execute(
        select(WaitlistEntry).where(
            WaitlistEntry.client_id == client.id,
            WaitlistEntry.service_id == service_id,
            WaitlistEntry.day == day,
            WaitlistEntry.is_active,
        )
    )
    for entry in rows.scalars():
        entry.is_active = False
    await session.commit()
