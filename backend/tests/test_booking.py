from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app import booking as bk
from app.models import Booking, Client, Consent, TimeOff

from .conftest import NOW

ARTEM, TIMUR, DANIIL = 1, 2, 3
HAIRCUT = 1  # 60 минут
MON = date(2026, 11, 9)


def at(day: date, h: int, m: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, h, m)


async def site_client(session, phone="+7 900 111-22-33"):
    c = await bk.get_or_create_phone_client(session, "Иван", phone)
    await bk.record_consent(session, c, "site")
    return c


async def book(session, client, start, master=ARTEM, service=HAIRCUT, source="site"):
    return await bk.create_booking(
        session, client=client, master_id=master, service_id=service, start_at=start, source=source
    )


async def test_slots_follow_working_hours_and_lead_time(session):
    slots = await bk.slots_for_day(session, ARTEM, HAIRCUT, MON)
    assert slots[0] == at(MON, 10) and slots[-1] == at(MON, 19)
    # Сейчас 9:00, минимальный отступ 60 минут: 9:30 уже недоступно бы, но день начинается в 10.
    assert await bk.slots_for_day(session, ARTEM, HAIRCUT, MON - timedelta(days=1)) == []


async def test_master_day_off(session):
    sunday = MON + timedelta(days=6)
    assert await bk.slots_for_day(session, ARTEM, HAIRCUT, sunday) == []


async def test_booking_beyond_horizon_has_no_slots(session):
    assert await bk.slots_for_day(session, ARTEM, HAIRCUT, MON + timedelta(days=30)) == []


async def test_booking_takes_slot(session):
    c = await site_client(session)
    b = await book(session, c, at(MON, 12))
    assert b.end_at == at(MON, 13) and b.price == 1800 and b.link_code
    slots = await bk.slots_for_day(session, ARTEM, HAIRCUT, MON)
    assert at(MON, 12) not in slots
    assert at(MON, 11, 30) not in slots  # 11:30–12:30 пересекается
    assert at(MON, 11) in slots and at(MON, 13) in slots


async def test_double_booking_rejected(session):
    c = await site_client(session)
    await book(session, c, at(MON, 12))
    with pytest.raises(bk.SlotTaken):
        await book(session, c, at(MON, 12))
    with pytest.raises(bk.SlotTaken):
        await book(session, c, at(MON, 12, 30))
    other = await book(session, c, at(MON, 12), master=DANIIL)
    assert other.master_id == DANIIL


async def test_off_grid_and_past_times_rejected(session):
    c = await site_client(session)
    with pytest.raises(bk.SlotTaken):
        await book(session, c, at(MON, 12, 10))
    with pytest.raises(bk.SlotTaken):
        await book(session, c, at(MON, 9))
    with pytest.raises(bk.SlotTaken):
        await book(session, c, at(MON, 19, 30))  # не успеет закончить до 20:00


async def test_master_without_service(session):
    c = await site_client(session)
    with pytest.raises(bk.BookingError):
        await book(session, c, at(MON, 12), master=TIMUR, service=3)  # Тимур не делает фейд


async def test_time_off_blocks_slots(session):
    session.add(TimeOff(master_id=ARTEM, start_at=at(MON, 14), end_at=at(MON, 15), reason="Обед"))
    await session.commit()
    slots = await bk.slots_for_day(session, ARTEM, HAIRCUT, MON)
    assert at(MON, 13, 30) not in slots and at(MON, 14) not in slots and at(MON, 15) in slots


async def test_cancel_frees_slot(session):
    c = await site_client(session)
    b = await book(session, c, at(MON, 12))
    await bk.cancel_booking(session, b)
    assert at(MON, 12) in await bk.slots_for_day(session, ARTEM, HAIRCUT, MON)
    with pytest.raises(bk.BookingError):
        await bk.cancel_booking(session, b)


async def test_reschedule(session):
    c = await site_client(session)
    b = await book(session, c, at(MON, 12))
    # Сдвиг на полчаса пересекается только с самой записью — это разрешено.
    b = await bk.reschedule_booking(session, b, at(MON, 12, 30))
    assert (b.start_at, b.end_at) == (at(MON, 12, 30), at(MON, 13, 30))
    assert at(MON, 11) in await bk.slots_for_day(session, ARTEM, HAIRCUT, MON)
    other = await book(session, c, at(MON, 15))
    with pytest.raises(bk.SlotTaken):
        await bk.reschedule_booking(session, other, at(MON, 13))


async def test_phone_normalization():
    assert bk.normalize_phone("8 (900) 111-22-33") == "+79001112233"
    assert bk.normalize_phone("+7 900 111 22 33") == "+79001112233"
    assert bk.normalize_phone("9001112233") == "+79001112233"
    for bad in ["123", "+1 202 555 0100", ""]:
        with pytest.raises(bk.BookingError):
            bk.normalize_phone(bad)


async def test_same_phone_reuses_client(session):
    a = await site_client(session, "89001112233")
    b = await site_client(session, "+7 900 111-22-33")
    assert a.id == b.id


async def test_delete_client_data(session):
    c = await site_client(session)
    past = Booking(client_id=c.id, master_id=ARTEM, service_id=HAIRCUT, start_at=NOW - timedelta(days=2),
                   end_at=NOW - timedelta(days=2, hours=-1), price=1800, status="active", source="site")
    session.add(past)
    future = await book(session, c, at(MON, 12))
    cancelled = await bk.delete_client_data(session, c)
    assert cancelled == 1
    assert await session.scalar(select(func.count()).select_from(Client)) == 0
    assert await session.scalar(select(func.count()).select_from(Consent)) == 0
    rows = {b.id: b for b in (await session.execute(select(Booking).execution_options(populate_existing=True))).scalars()}
    assert all(b.client_id is None for b in rows.values())
    assert rows[future.id].status == "cancelled"
    assert rows[past.id].status == "active"  # прошлый визит остаётся в статистике обезличенным


async def test_link_site_booking_to_telegram(session):
    c = await site_client(session)
    b = await book(session, c, at(MON, 12))
    linked = await bk.link_booking_to_tg(session, b.link_code, 555)
    assert linked.client.tg_user_id == 555 and linked.link_code is None
    assert await bk.link_booking_to_tg(session, "nope", 555) is None


async def test_bot_contacts_merge_site_client(session):
    site = await site_client(session)
    b = await book(session, site, at(MON, 12))
    tg = await bk.get_or_create_tg_client(session, 777)
    await bk.set_tg_client_contacts(session, tg, "Иван", "8 900 111 22 33")
    await session.commit()
    b = await bk.get_booking(session, b.id)
    assert b.client_id == tg.id


async def test_due_reminders(session):
    tg = await bk.get_or_create_tg_client(session, 42)
    await bk.set_tg_client_contacts(session, tg, "Пётр", "+79005556677")
    await bk.record_consent(session, tg, "bot")
    tue = MON + timedelta(days=1)
    b = await book(session, tg, at(tue, 15), source="bot")
    assert (b.reminded_24h, b.reminded_2h) == (False, False)
    site = await site_client(session)  # без Telegram: напоминаний нет
    await book(session, site, at(tue, 12))

    assert await bk.due_reminders(session, at(MON, 9)) == []
    due = await bk.due_reminders(session, at(MON, 15))
    assert [(x.id, k) for x, k in due] == [(b.id, "24h")]
    await bk.mark_reminded(session, b, "24h")
    assert await bk.due_reminders(session, at(tue, 10)) == []
    due = await bk.due_reminders(session, at(tue, 13))
    assert [(x.id, k) for x, k in due] == [(b.id, "2h")]
    await bk.mark_reminded(session, b, "2h")
    assert await bk.due_reminders(session, at(tue, 14)) == []


async def test_consent_version_check(session):
    tg = await bk.get_or_create_tg_client(session, 1)
    assert not await bk.has_current_consent(session, tg)
    await bk.record_consent(session, tg, "bot")
    assert await bk.has_current_consent(session, tg)
