"""Сценарий записи: услуга → мастер → дата → время → согласие → имя → телефон."""

from datetime import date, datetime

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy import select

from app import booking as bk
from app import db
from app.config import get_settings
from app.consent import consent_text
from app.models import Master, Service
from app.notify import booking_summary, notify_owner

from . import keyboards as kb

router = Router()


class Book(StatesGroup):
    name = State()
    phone = State()


def contacts_text() -> str:
    s = get_settings()
    return (
        f"💈 {s.shop_name}\n📍 {s.shop_address}\n☎️ {s.shop_phone}\n\n"
        f"Сайт: {s.site_url}\nПолитика конфиденциальности: {s.site_url}/privacy.html"
    )


# --- старт и меню --------------------------------------------------------


@router.message(CommandStart())
async def start(message: Message, command: CommandObject, state: FSMContext) -> None:
    await state.clear()
    if command.args:
        async with db.SessionLocal() as session:
            b = await bk.link_booking_to_tg(session, command.args, message.from_user.id)
        if b:
            await message.answer(
                "✅ Запись с сайта привязана к Telegram. Напоминания придут сюда за день и за 2 часа.\n\n"
                + booking_summary(b),
                reply_markup=kb.main_menu(),
            )
            return
    await message.answer(
        f"Привет! Это бот барбершопа «{get_settings().shop_name}».\n"
        "Здесь можно записаться на стрижку, перенести или отменить визит.",
        reply_markup=kb.main_menu(),
    )


@router.message(F.text == kb.ABOUT)
async def about(message: Message) -> None:
    await message.answer(contacts_text())


@router.callback_query(F.data == "abort")
async def abort(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text("Отменено.")
    await call.message.answer("Чем ещё помочь?", reply_markup=kb.main_menu())


@router.message(Command("cancel"))
async def cancel_cmd(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.", reply_markup=kb.main_menu())


# --- выбор услуги, мастера, даты, времени --------------------------------


@router.message(F.text == kb.BOOK)
@router.message(Command("book"))
async def choose_service(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with db.SessionLocal() as session:
        rows = await session.execute(select(Service).where(Service.is_active).order_by(Service.sort, Service.id))
        services = [s for s in rows.scalars() if any(m.is_active for m in s.masters)]
    await message.answer("Выберите услугу:", reply_markup=kb.services(services))


@router.callback_query(F.data.startswith("svc:"))
async def choose_master(call: CallbackQuery, state: FSMContext) -> None:
    service_id = int(call.data.split(":")[1])
    async with db.SessionLocal() as session:
        service = await session.get(Service, service_id)
        masters = sorted((m for m in service.masters if m.is_active), key=lambda m: m.id)
    await state.update_data(mode="new", service_id=service_id)
    await call.message.edit_text(f"{service.name}. Выберите мастера:", reply_markup=kb.masters(masters))


async def _show_dates(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    async with db.SessionLocal() as session:
        days = await bk.available_dates(
            session, data["master_id"], data["service_id"], exclude_booking_id=data.get("booking_id")
        )
    if not days:
        await call.message.edit_text("Свободных дней в ближайшие две недели нет 😔", reply_markup=None)
        return
    await call.message.edit_text("Выберите дату:", reply_markup=kb.dates(days))


@router.callback_query(F.data.startswith("mst:"))
async def choose_date(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(master_id=int(call.data.split(":")[1]))
    await _show_dates(call, state)


@router.callback_query(F.data == "back:dates")
async def back_to_dates(call: CallbackQuery, state: FSMContext) -> None:
    await _show_dates(call, state)


async def _show_times(call: CallbackQuery, state: FSMContext, day: date, prefix: str = "") -> None:
    data = await state.get_data()
    async with db.SessionLocal() as session:
        slots = await bk.slots_for_day(
            session, data["master_id"], data["service_id"], day, exclude_booking_id=data.get("booking_id")
        )
    if not slots:
        await _show_dates(call, state)
        return
    await call.message.edit_text(f"{prefix}{kb.short_date(day)}. Выберите время:", reply_markup=kb.times(slots))


@router.callback_query(F.data.startswith("day:"))
async def choose_time(call: CallbackQuery, state: FSMContext) -> None:
    await _show_times(call, state, date.fromisoformat(call.data.split(":", 1)[1]))


@router.callback_query(F.data.startswith("tm:"))
async def time_chosen(call: CallbackQuery, state: FSMContext) -> None:
    start = call.data.split(":", 1)[1]
    await state.update_data(start_at=start)
    data = await state.get_data()
    if data.get("mode") == "reschedule":
        await _do_reschedule(call, state)
        return
    async with db.SessionLocal() as session:
        client = await bk.client_by_tg(session, call.from_user.id)
        consented = client is not None and await bk.has_current_consent(session, client)
    if not consented:
        # 152-ФЗ: согласие спрашиваем до того, как запросить имя и телефон.
        await call.message.edit_text(consent_text(), reply_markup=kb.consent())
    elif not (client.name and client.phone):
        await _ask_name(call.message, state)
    else:
        await _show_confirm(call.message, state, client.name, client.phone, edit=True)


# --- согласие и контакты -------------------------------------------------


@router.callback_query(F.data == "consent:yes")
async def consent_given(call: CallbackQuery, state: FSMContext) -> None:
    async with db.SessionLocal() as session:
        client = await bk.get_or_create_tg_client(session, call.from_user.id)
        await bk.record_consent(session, client, "bot")
        await session.commit()
        name, phone = client.name, client.phone
    await call.message.edit_text("Спасибо, согласие сохранено ✅")
    if name and phone:
        await _show_confirm(call.message, state, name, phone)
    else:
        await _ask_name(call.message, state)


async def _ask_name(message: Message, state: FSMContext) -> None:
    await state.set_state(Book.name)
    await message.answer("Как к вам обращаться?")


@router.message(Book.name, F.text)
async def name_entered(message: Message, state: FSMContext) -> None:
    name = message.text.strip()[:100]
    if not name or name.startswith("/"):
        await message.answer("Напишите, пожалуйста, имя.")
        return
    await state.update_data(name=name)
    await state.set_state(Book.phone)
    await message.answer("Ваш номер телефона? Нажмите кнопку ниже или напишите вручную.", reply_markup=kb.share_phone())


@router.message(Book.phone, F.contact | F.text)
async def phone_entered(message: Message, state: FSMContext) -> None:
    raw = message.contact.phone_number if message.contact else message.text
    data = await state.get_data()
    try:
        async with db.SessionLocal() as session:
            client = await bk.get_or_create_tg_client(session, message.from_user.id)
            await bk.set_tg_client_contacts(session, client, data["name"], raw)
            await session.commit()
            phone = client.phone
    except bk.BookingError as e:
        await message.answer(str(e))
        return
    await state.set_state(None)
    await message.answer("Записал 👍", reply_markup=ReplyKeyboardRemove())
    await _show_confirm(message, state, data["name"], phone)


async def _show_confirm(message: Message, state: FSMContext, name: str, phone: str, edit: bool = False) -> None:
    data = await state.get_data()
    async with db.SessionLocal() as session:
        service = await session.get(Service, data["service_id"])
        master = await session.get(Master, data["master_id"])
    start = datetime.fromisoformat(data["start_at"])
    text = (
        "Проверьте запись:\n\n"
        f"{service.name} — {service.price} ₽\nМастер: {master.name}\n"
        f"Когда: {kb.short_date(start.date())}, {start:%H:%M}\n"
        f"Имя: {name}\nТелефон: {phone}"
    )
    if edit:
        await message.edit_text(text, reply_markup=kb.confirm())
    else:
        await message.answer(text, reply_markup=kb.confirm())


@router.callback_query(F.data == "confirm")
async def confirm(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if "start_at" not in data:
        await call.answer("Запись устарела, начните заново", show_alert=True)
        return
    start = datetime.fromisoformat(data["start_at"])
    try:
        async with db.SessionLocal() as session:
            client = await bk.client_by_tg(session, call.from_user.id)
            if not client or not await bk.has_current_consent(session, client):
                await call.answer("Нужно согласие на обработку данных", show_alert=True)
                return
            b = await bk.create_booking(
                session,
                client=client,
                master_id=data["master_id"],
                service_id=data["service_id"],
                start_at=start,
                source="bot",
            )
    except bk.BookingError as e:
        await call.answer(str(e), show_alert=True)
        await _show_times(call, state, start.date(), prefix="Время только что заняли. ")
        return
    await state.clear()
    await call.message.edit_text(
        "✅ Вы записаны!\n\n" + booking_summary(b) + f"\n\n📍 {get_settings().shop_address}\n"
        "Напомним за день и за 2 часа. Перенести или отменить — в «Мои записи».",
    )
    await call.message.answer("Ждём вас!", reply_markup=kb.main_menu())
    await notify_owner("🆕 Новая запись", b)


# --- мои записи: перенос и отмена ----------------------------------------


@router.message(F.text == kb.MY)
@router.message(Command("my"))
async def my_bookings(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with db.SessionLocal() as session:
        client = await bk.client_by_tg(session, message.from_user.id)
        items = await bk.upcoming_for_client(session, client) if client else []
    if not items:
        await message.answer("Предстоящих записей нет.", reply_markup=kb.main_menu())
        return
    for b in items:
        await message.answer(booking_summary(b), reply_markup=kb.booking_actions(b))


async def _own_booking(session, booking_id: int, tg_user_id: int):
    b = await bk.get_booking(session, booking_id)
    if not b or not b.client or b.client.tg_user_id != tg_user_id:
        return None
    return b


@router.callback_query(F.data.startswith("cx:"))
async def cancel_ask(call: CallbackQuery) -> None:
    booking_id = int(call.data.split(":")[1])
    await call.message.edit_reply_markup(reply_markup=kb.confirm_cancel(booking_id))


@router.callback_query(F.data.startswith("cxok:"))
async def cancel_booking(call: CallbackQuery) -> None:
    async with db.SessionLocal() as session:
        b = await _own_booking(session, int(call.data.split(":")[1]), call.from_user.id)
        if not b:
            await call.answer("Запись не найдена", show_alert=True)
            return
        try:
            await bk.cancel_booking(session, b)
        except bk.BookingError as e:
            await call.answer(str(e), show_alert=True)
            return
    await call.message.edit_text("❌ Запись отменена.\n\n" + booking_summary(b))
    await notify_owner("❌ Клиент отменил запись", b)


@router.callback_query(F.data.startswith("rs:"))
async def reschedule_start(call: CallbackQuery, state: FSMContext) -> None:
    async with db.SessionLocal() as session:
        b = await _own_booking(session, int(call.data.split(":")[1]), call.from_user.id)
    if not b or b.status != "active":
        await call.answer("Запись не найдена", show_alert=True)
        return
    await state.update_data(mode="reschedule", booking_id=b.id, master_id=b.master_id, service_id=b.service_id)
    await _show_dates(call, state)


async def _do_reschedule(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    start = datetime.fromisoformat(data["start_at"])
    async with db.SessionLocal() as session:
        b = await _own_booking(session, data["booking_id"], call.from_user.id)
        if not b:
            await call.answer("Запись не найдена", show_alert=True)
            return
        old = b.start_at
        try:
            b = await bk.reschedule_booking(session, b, start)
        except bk.BookingError as e:
            await call.answer(str(e), show_alert=True)
            await _show_times(call, state, start.date())
            return
    await state.clear()
    await call.message.edit_text("🔁 Запись перенесена.\n\n" + booking_summary(b))
    await notify_owner(f"🔁 Перенос записи (было {old:%d.%m %H:%M})", b)


# --- удаление данных (отзыв согласия) ------------------------------------


@router.message(F.text == kb.DELETE)
@router.message(Command("delete_me"))
async def delete_ask(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Удалим ваше имя, телефон, Telegram ID и согласие на обработку данных. "
        "Будущие записи будут отменены. Продолжить?",
        reply_markup=kb.confirm_delete(),
    )


@router.callback_query(F.data == "del:yes")
async def delete_confirmed(call: CallbackQuery) -> None:
    async with db.SessionLocal() as session:
        client = await bk.client_by_tg(session, call.from_user.id)
        upcoming = await bk.upcoming_for_client(session, client) if client else []
        if client:
            await bk.delete_client_data(session, client)
    await call.message.edit_text("Готово: ваши персональные данные удалены.")
    for b in upcoming:
        await notify_owner("🗑 Клиент удалил данные, запись отменена", b)
