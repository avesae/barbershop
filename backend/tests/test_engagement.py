"""Кабинет мастера, отзывы, повторная запись и лист ожидания — через бота."""

from datetime import datetime, time, timedelta

import pytest
from aiogram.types import User
from sqlalchemy import select

from app import booking as bk
from app import db
from app import engagement as eg
from app.models import Booking, Master, Review, TimeOff, WaitlistEntry
from bot import jobs

from .conftest import NOW
from .test_bot import Harness

MASTER_USER = User(id=2002, is_bot=False, first_name="Артём")


@pytest.mark.parametrize("text,expected", [
    ("14:00-15:00", (time(14), time(15))),
    ("14-15", (time(14), time(15))),
    ("14.30 – 15.15", (time(14, 30), time(15, 15))),
    ("15-14", None),
    ("обед", None),
    ("25-26", None),
])
def test_parse_range(text, expected):
    assert eg.parse_range(text) == expected


async def tg_client(s, tg_id=1001, name="Иван", phone="+79001112233"):
    c = await bk.get_or_create_tg_client(s, tg_id)
    await bk.set_tg_client_contacts(s, c, name, phone)
    await bk.record_consent(s, c, "bot")
    await s.commit()
    return c


async def past_booking(s, client, start, status="active"):
    b = Booking(client_id=client.id, master_id=1, service_id=1, start_at=start, end_at=start + timedelta(hours=1),
                price=1800, status=status, source="bot", reminded_24h=True, reminded_2h=True)
    s.add(b)
    await s.commit()
    return b


async def test_master_cabinet(monkeypatch):
    async with db.SessionLocal() as s:
        c = await tg_client(s)
        b = await bk.create_booking(s, client=c, master_id=1, service_id=1, start_at=datetime(2026, 11, 9, 12), source="bot")
        c.notes = "Короче на висках"
        m = await s.get(Master, 1)
        m.invite_code = "INV"
        await s.commit()

    h = Harness(MASTER_USER)
    try:
        await h.text("/start m_INV")
        assert "Кабинет мастера подключён" in h.last()
        await h.text("/start m_INV")
        assert "устарела" in h.last()

        await h.text("📅 Сегодня")
        assert "12:00–13:00 Мужская стрижка" in h.last() and "Короче на висках" in h.last()

        await h.click(f"ms:{b.id}:done")
        assert "ещё не начался" in h.session.alerts()[-1]
        monkeypatch.setattr(bk, "now_local", lambda: NOW.replace(hour=12, minute=30))
        await h.click(f"ms:{b.id}:done")
        async with db.SessionLocal() as s:
            assert (await bk.get_booking(s, b.id)).status == "done"

        await h.text("⛔ Закрыть время")
        await h.click("mo:2026-11-10")
        await h.text("обед")
        assert "Не понял" in h.last()
        await h.text("14-15")
        assert "Закрыто: вт, 10 ноя, 14:00–15:00" in h.last()
        await h.text("⛔ Закрыть время")
        await h.click("mo:2026-11-11")
        await h.click("mo:all")
        assert "весь день" in h.last()
        async with db.SessionLocal() as s:
            assert len((await s.execute(select(TimeOff))).scalars().all()) == 2
            assert await bk.slots_for_day(s, 1, 1, datetime(2026, 11, 11).date()) == []
    finally:
        h.detach()


async def test_client_cannot_use_master_buttons():
    async with db.SessionLocal() as s:
        c = await tg_client(s)
        b = await past_booking(s, c, NOW - timedelta(hours=2))
    h = Harness()
    try:
        await h.click(f"ms:{b.id}:no_show")
        async with db.SessionLocal() as s:
            assert (await bk.get_booking(s, b.id)).status == "active"
    finally:
        h.detach()


async def test_review_flow():
    async with db.SessionLocal() as s:
        c = await tg_client(s)
        recent = await past_booking(s, c, NOW - timedelta(hours=5))
        await past_booking(s, c, NOW - timedelta(days=10))  # слишком старый — не спрашиваем
        await past_booking(s, c, NOW - timedelta(hours=5, minutes=30), status="no_show")
    h = Harness()
    try:
        assert await jobs.ask_reviews(h.bot) == 1
        assert "Как прошёл визит" in h.last()
        assert await jobs.ask_reviews(h.bot) == 0

        await h.click(f"rv:{recent.id}:5")
        assert "опубликуем" in h.last()
        await h.text("Лучший фейд в городе!")
        async with db.SessionLocal() as s:
            r = (await s.execute(select(Review))).scalar_one()
            assert (r.rating, r.text, r.author, r.published) == (5, "Лучший фейд в городе!", "Иван", False)

        await h.click(f"rv:{recent.id}:2")  # передумал — оценка обновилась, отзыв один
        assert "Что пошло не так" in h.last()
        await h.click("rvskip")
        async with db.SessionLocal() as s:
            assert [x.rating for x in (await s.execute(select(Review))).scalars()] == [2]
    finally:
        h.detach()


async def test_rebook_flow():
    async with db.SessionLocal() as s:
        c = await tg_client(s)
        await past_booking(s, c, NOW - timedelta(days=60))
        last = await past_booking(s, c, NOW - timedelta(days=30))
        other = await tg_client(s, 1002, "Пётр", "+79005556677")
        await past_booking(s, other, NOW - timedelta(days=10))  # ещё рано
    h = Harness()
    try:
        assert await jobs.offer_rebooking(h.bot) == 1
        assert "Артём" in h.last() and "Мужская стрижка" in h.last()
        assert await jobs.offer_rebooking(h.bot) == 0
        await h.click(f"rb:{last.id}")
        assert h.last() == "Выберите дату:"
    finally:
        h.detach()


async def test_rebook_skipped_when_client_already_booked():
    async with db.SessionLocal() as s:
        c = await tg_client(s)
        await past_booking(s, c, NOW - timedelta(days=30))
        await bk.create_booking(s, client=c, master_id=1, service_id=1, start_at=datetime(2026, 11, 10, 12), source="bot")
        assert await eg.due_rebook_offers(s) == []


async def test_waitlist_flow():
    tue = datetime(2026, 11, 10)
    async with db.SessionLocal() as s:
        s.add(TimeOff(master_id=1, start_at=tue, end_at=tue + timedelta(days=1), reason="Выходной"))
        await s.commit()
    h = Harness()
    try:
        await h.text("✂️ Записаться")
        await h.click("svc:1")
        await h.click("mst:1")
        await h.click("wl:pick")
        assert "лист ожидания" in h.last()
        await h.click("wl:2026-11-10")
        assert "согласие" in h.last()  # без согласия в лист не ставим
        await h.click("consent:yes")
        await h.text("Иван")
        await h.contact("+79001112233")
        assert "листе ожидания" in h.session.texts()[-1]
        async with db.SessionLocal() as s:
            entry = (await s.execute(select(WaitlistEntry))).scalar_one()
            assert entry.is_active and entry.day == tue.date()

        assert await jobs.notify_waitlist(h.bot) == 0  # время ещё закрыто
        async with db.SessionLocal() as s:
            for t in (await s.execute(select(TimeOff))).scalars():
                await s.delete(t)
            await s.commit()
        assert await jobs.notify_waitlist(h.bot) == 1
        assert "Освободилось время" in h.last()
        assert await jobs.notify_waitlist(h.bot) == 0  # уведомляем один раз

        await h.click("wlt:1:1:2026-11-10T12:00")
        assert "Проверьте запись" in h.last()
        await h.click("confirm")
        async with db.SessionLocal() as s:
            b = (await s.execute(select(Booking))).scalar_one()
            assert b.start_at == datetime(2026, 11, 10, 12)
            assert not (await s.execute(select(WaitlistEntry))).scalar_one().is_active
    finally:
        h.detach()


async def test_waitlist_expires():
    async with db.SessionLocal() as s:
        c = await tg_client(s)
        e = await eg.join_waitlist(s, c, 1, None, NOW.date() - timedelta(days=1))
        assert await eg.due_waitlist(s) == []
        await s.refresh(e)
        assert not e.is_active


async def test_delete_data_removes_reviews_and_waitlist():
    async with db.SessionLocal() as s:
        c = await tg_client(s)
        b = await past_booking(s, c, NOW - timedelta(hours=5))
        await eg.save_rating(s, b, 5)
        await eg.join_waitlist(s, c, 1, 1, NOW.date() + timedelta(days=1))
        await bk.delete_client_data(s, c)
        assert (await s.execute(select(Review))).first() is None
        assert (await s.execute(select(WaitlistEntry))).first() is None
