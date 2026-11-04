"""Демо-режим для портфолио: правдоподобные данные и сброс каждую ночь.

Включается DEMO_MODE=true. Не включайте его на настоящем барбершопе —
база ежедневно стирается.
"""

import asyncio
import logging
import random
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import booking as bk
from . import db
from .config import get_settings
from .consent import CONSENT_VERSION
from .media import upload_dir
from .models import Base, Booking, Client, Consent, Master, Review, Service, TimeOff, WaitlistEntry
from .seed import seed
from .slots import free_slots

log = logging.getLogger(__name__)

RESET_AT = time(4, 0)

NAMES = ["Алексей", "Дмитрий", "Максим", "Игорь", "Никита", "Павел", "Роман", "Сергей", "Егор", "Кирилл",
         "Андрей", "Михаил", "Владимир", "Константин", "Глеб", "Фёдор", "Марк", "Лев", "Степан", "Илья",
         "Антон", "Олег", "Вадим", "Георгий"]
NOTES = ["Короче на висках", "Не любит воск", "Пьёт эспрессо без сахара", "Аллергия на ментол",
         "Всегда к одному мастеру", ""]
REVIEWS = {
    5: ["Лучший фейд, что у меня был. Мастер своего дела!", "Записался через бота за минуту, пришёл — сразу посадили. Стрижка огонь.",
        "Королевское бритьё — must try. Горячие полотенца, атмосфера, всё на уровне.",
        "Хожу уже полгода, ни разу не разочаровали. Напоминание в Telegram — очень удобно.",
        "Бороду наконец-то привели в форму. Золотые руки у мастера."],
    4: ["Хорошая стрижка, уютно. Немного подождал, но кофе скрасил ожидание.",
        "Всё понравилось, в следующий раз попробую комплекс с бородой."],
}


def _phone(rng: random.Random) -> str:
    return "+79" + "".join(str(rng.randint(0, 9)) for _ in range(9))


async def seed_demo(session: AsyncSession, now: datetime | None = None, *, rng_seed: int = 42) -> None:
    """Клиенты, записи за прошлые 30 дней и ближайшую неделю, отзывы, обеды."""
    now = now or bk.now_local()
    rng = random.Random(rng_seed)
    masters = list((await session.execute(select(Master).order_by(Master.id))).scalars())
    services = list((await session.execute(select(Service).order_by(Service.id))).scalars())

    clients = []
    for i, name in enumerate(NAMES):
        c = Client(name=name, phone=_phone(rng), notes=rng.choice(NOTES), created_at=now - timedelta(days=60))
        session.add(c)
        clients.append(c)
    await session.flush()
    for c in clients:
        session.add(Consent(client_id=c.id, version=CONSENT_VERSION, source=rng.choice(["site", "bot"]),
                            accepted_at=now - timedelta(days=rng.randint(30, 60))))

    # Обед у каждого мастера в будни.
    for d in range(-30, 8):
        day = now.date() + timedelta(days=d)
        for m in masters:
            if day.weekday() < 5 and any(w.weekday == day.weekday() for w in m.working_hours):
                session.add(TimeOff(master_id=m.id, start_at=datetime.combine(day, time(14)),
                                    end_at=datetime.combine(day, time(14, 30)), reason="Обед"))
    await session.flush()

    busy: dict[tuple[int, date], list] = {}
    for d in range(-30, 8):
        day = now.date() + timedelta(days=d)
        for m in masters:
            work = [(w.start, w.end) for w in m.working_hours if w.weekday == day.weekday()]
            if not work:
                continue
            key = (m.id, day)
            busy[key] = [(datetime.combine(day, time(14)), datetime.combine(day, time(14, 30)))]
            # Загрузка 45–80 %: в прошлом плотнее, впереди — свободнее.
            target = rng.randint(5, 8) if d <= 0 else rng.randint(2, 5)
            for _ in range(target):
                service = rng.choice([s for s in services if s in m.services])
                options = free_slots(day, service.duration_min, work, busy[key], step_min=30)
                if d >= 0:  # не занимаем ближайший час — его можно забронировать в демо
                    options = [t for t in options if t + timedelta(minutes=service.duration_min) <= now or t > now + timedelta(hours=1)]
                if not options:
                    break
                start = rng.choice(options)
                end = start + timedelta(minutes=service.duration_min)
                busy[key].append((start, end))
                past = start < now
                roll = rng.random()
                status = ("cancelled" if roll < 0.07 else "no_show" if roll < 0.11 else "done") if past else (
                    "cancelled" if roll < 0.05 else "active")
                session.add(Booking(
                    client_id=rng.choice(clients).id, master_id=m.id, service_id=service.id,
                    start_at=start, end_at=end, price=service.price, status=status,
                    source="bot" if rng.random() < 0.62 else "site",
                    reminded_24h=past, reminded_2h=past, review_asked=past, rebook_offered=past,
                    created_at=start - timedelta(days=rng.randint(1, 10)),
                ))
    await session.flush()

    done = list((await session.execute(select(Booking).where(Booking.status == "done"))).scalars())
    for b in rng.sample(done, min(12, len(done))):
        rating = rng.choices([5, 4, 3], weights=[7, 3, 1])[0]
        texts = REVIEWS.get(rating, [""])
        client = await session.get(Client, b.client_id)
        session.add(Review(booking_id=b.id, client_id=b.client_id, master_id=b.master_id, rating=rating,
                           text=rng.choice(texts) if rating >= 4 else "Долго ждал, хотя пришёл вовремя.",
                           author=client.name, published=rating >= 4, created_at=b.end_at + timedelta(hours=3)))

    # Пара клиентов в листе ожидания на ближайшие дни.
    for c in clients[:2]:
        session.add(WaitlistEntry(client_id=c.id, service_id=services[0].id, master_id=masters[0].id,
                                  day=now.date() + timedelta(days=rng.randint(1, 5)), created_at=now))
    await session.commit()


async def reset_demo() -> None:
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await db.init_db()
    for f in upload_dir().glob("*"):
        f.unlink(missing_ok=True)
    async with db.SessionLocal() as session:
        await seed(session)
        await seed_demo(session)
    log.info("Демо-данные сброшены")


async def demo_loop() -> None:
    """Сбрасывает демо раз в сутки в RESET_AT по времени барбершопа."""
    last_reset: date | None = None
    while True:
        now = bk.now_local()
        if now.time() >= RESET_AT and last_reset != now.date():
            if last_reset is not None:
                await reset_demo()
            last_reset = now.date()
        await asyncio.sleep(60)


async def ensure_demo() -> None:
    """При первом запуске в демо-режиме — сразу наполнить базу."""
    async with db.SessionLocal() as session:
        has_clients = await session.scalar(select(Client.id).limit(1))
    if not has_clients:
        await reset_demo()


def enabled() -> bool:
    return get_settings().demo_mode
