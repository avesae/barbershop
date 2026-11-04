"""Сценарии бота целиком: апдейты идут через диспетчер aiogram,
запросы к Telegram перехватывает фейковая сессия."""

from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import CallbackQuery, Chat, Contact, Message, Update, User
from sqlalchemy import select

from app import booking as bk
from app import db
from app.models import Booking, Client, Consent
from bot.handlers import router
from bot.master import router as master_router
from bot.main import send_reminders

from .conftest import NOW

USER = User(id=1001, is_bot=False, first_name="Иван")
CHAT = Chat(id=1001, type="private")


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list = []

    async def make_request(self, bot, method, timeout=None):
        self.requests.append(method)
        if isinstance(method, SendMessage):
            return Message(message_id=len(self.requests), date=NOW, chat=CHAT, text=method.text)
        return True

    async def stream_content(self, *args, **kwargs):
        yield b""

    async def close(self) -> None:
        pass

    def texts(self) -> list[str]:
        return [m.text for m in self.requests if isinstance(m, (SendMessage, EditMessageText))]

    def alerts(self) -> list[str]:
        return [m.text for m in self.requests if isinstance(m, AnswerCallbackQuery) and m.text]


class Harness:
    def __init__(self, user: User = USER) -> None:
        self.user = user
        self.chat = Chat(id=user.id, type="private")
        self.session = FakeSession()
        self.bot = Bot("123456:" + "A" * 35, session=self.session)
        self.dp = Dispatcher()
        self.dp.include_router(master_router)
        self.dp.include_router(router)
        self.n = 0

    def _msg(self, **kw) -> Message:
        self.n += 1
        return Message(message_id=self.n, date=NOW, chat=self.chat, from_user=self.user, **kw)

    async def text(self, text: str) -> None:
        await self.dp.feed_update(self.bot, Update(update_id=self.n, message=self._msg(text=text)))

    async def contact(self, phone: str) -> None:
        contact = Contact(phone_number=phone, first_name="Иван", user_id=self.user.id)
        await self.dp.feed_update(self.bot, Update(update_id=self.n, message=self._msg(contact=contact)))

    async def click(self, data: str) -> None:
        call = CallbackQuery(id=str(self.n), from_user=self.user, chat_instance="ci", data=data, message=self._msg(text="…"))
        await self.dp.feed_update(self.bot, Update(update_id=self.n, callback_query=call))

    def last(self) -> str:
        return self.session.texts()[-1]

    def detach(self) -> None:
        # Глобальные роутеры можно подключить только к одному диспетчеру.
        router._parent_router = None
        master_router._parent_router = None


async def bookings():
    async with db.SessionLocal() as s:
        return list((await s.execute(select(Booking).order_by(Booking.id))).scalars())


async def test_full_bot_flow():
    h = Harness()
    try:
        await h.text("/start")
        assert "Fade & Blade" in h.last()

        await h.text("✂️ Записаться")
        assert h.last() == "Выберите услугу:"
        await h.click("svc:1")
        await h.click("mst:1")
        assert h.last() == "Выберите дату:"
        await h.click("day:2026-11-09")
        assert "Выберите время" in h.last()
        await h.click("tm:2026-11-09T12:00")
        # Согласие показывается до запроса имени и телефона.
        assert "согласие" in h.last() and "Версия текста: 1.0" in h.last()

        await h.click("consent:yes")
        assert h.last() == "Как к вам обращаться?"
        async with db.SessionLocal() as s:
            consent = (await s.execute(select(Consent))).scalar_one()
            assert consent.source == "bot" and consent.version == "1.0" and consent.accepted_at == NOW

        await h.text("Иван")
        await h.text("123")
        assert "формате +7" in h.last()
        await h.contact("+7 900 111-22-33")
        assert "Проверьте запись" in h.last() and "+79001112233" in h.last()

        await h.click("confirm")
        assert "Вы записаны" in h.session.texts()[-2]
        [b] = await bookings()
        assert (b.source, b.start_at, b.status) == ("bot", datetime(2026, 11, 9, 12), "active")

        # Повторная запись: согласие и контакты уже есть — сразу подтверждение.
        await h.text("✂️ Записаться")
        await h.click("svc:1")
        await h.click("mst:1")
        await h.click("day:2026-11-09")
        await h.click("tm:2026-11-09T15:00")
        assert "Проверьте запись" in h.last()
        await h.click("confirm")
        assert len(await bookings()) == 2

        # Перенос первой записи.
        await h.text("📋 Мои записи")
        await h.click(f"rs:{b.id}")
        await h.click("day:2026-11-10")
        await h.click("tm:2026-11-10T11:00")
        assert "перенесена" in h.last()
        b = (await bookings())[0]
        assert b.start_at == datetime(2026, 11, 10, 11)

        # Занятое время при переносе — ошибка, запись не меняется.
        await h.click(f"rs:{b.id}")
        await h.click("tm:2026-11-09T15:30")
        assert any("занято" in a for a in h.session.alerts())

        # Отмена второй записи.
        second = (await bookings())[1]
        await h.click(f"cx:{second.id}")
        await h.click(f"cxok:{second.id}")
        assert "отменена" in h.last()
        assert (await bookings())[1].status == "cancelled"

        # Удаление данных.
        await h.text("🗑 Удалить мои данные")
        await h.click("del:yes")
        assert "удалены" in h.last()
        async with db.SessionLocal() as s:
            assert (await s.execute(select(Client))).first() is None
            assert (await s.execute(select(Consent))).first() is None
        assert all(x.client_id is None for x in await bookings())
        assert (await bookings())[0].status == "cancelled"
    finally:
        h.detach()


async def test_foreign_booking_is_not_accessible():
    h = Harness()
    try:
        async with db.SessionLocal() as s:
            other = await bk.get_or_create_phone_client(s, "Чужой", "+79009999999")
            b = await bk.create_booking(s, client=other, master_id=1, service_id=1,
                                        start_at=datetime(2026, 11, 9, 12), source="site")
        await h.click(f"cxok:{b.id}")
        assert "Запись не найдена" in h.session.alerts()
        assert (await bookings())[0].status == "active"
    finally:
        h.detach()


async def test_start_with_site_code_links_booking():
    h = Harness()
    try:
        async with db.SessionLocal() as s:
            c = await bk.get_or_create_phone_client(s, "Иван", "+79001112233")
            b = await bk.create_booking(s, client=c, master_id=1, service_id=1,
                                        start_at=datetime(2026, 11, 9, 12), source="site")
        await h.text(f"/start {b.link_code}")
        assert "привязана" in h.last()
        async with db.SessionLocal() as s:
            assert (await bk.client_by_tg(s, USER.id)).id == c.id
    finally:
        h.detach()


async def test_send_reminders(monkeypatch):
    h = Harness()
    try:
        async with db.SessionLocal() as s:
            c = await bk.get_or_create_tg_client(s, USER.id)
            await bk.set_tg_client_contacts(s, c, "Иван", "+79001112233")
            await bk.create_booking(s, client=c, master_id=1, service_id=1,
                                    start_at=datetime(2026, 11, 10, 15), source="bot")
        monkeypatch.setattr(bk, "now_local", lambda: datetime(2026, 11, 9, 16))
        assert await send_reminders(h.bot) == 1
        assert "завтра" in h.last()
        assert await send_reminders(h.bot) == 0  # повторно не шлём
        monkeypatch.setattr(bk, "now_local", lambda: datetime(2026, 11, 10, 13, 30))
        assert await send_reminders(h.bot) == 1
        assert "через 2 часа" in h.last()
    finally:
        h.detach()
