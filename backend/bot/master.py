"""Кабинет мастера: расписание, отметки о визитах, закрытие времени."""

from datetime import date, datetime, time, timedelta

from aiogram import F, Router
from aiogram.filters import Filter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, TelegramObject

from app import booking as bk
from app import db
from app import engagement as eg

from . import keyboards as kb

router = Router()


class IsMaster(Filter):
    async def __call__(self, event: TelegramObject) -> bool | dict:
        async with db.SessionLocal() as session:
            master = await eg.master_by_tg(session, event.from_user.id)
        return {"master": master} if master else False


router.message.filter(IsMaster())
router.callback_query.filter(IsMaster())


class CloseTime(StatesGroup):
    range = State()


STATUS = {"done": "✅", "no_show": "🚫", "active": ""}


async def day_view(master, day: date) -> tuple[str, object]:
    async with db.SessionLocal() as session:
        items = await eg.master_day(session, master.id, day)
    now = bk.now_local()
    if not items:
        return f"{kb.short_date(day)}: записей нет", None
    lines = [f"{kb.short_date(day)} — {len(items)} зап."]
    for b in items:
        who = f"{b.client.name}, {b.client.phone}" if b.client else "данные удалены"
        notes = f"\n   📝 {b.client.notes}" if b.client and b.client.notes else ""
        lines.append(f"{STATUS.get(b.status, '')} {b.start_at:%H:%M}–{b.end_at:%H:%M} {b.service.name}\n   {who}{notes}")
    return "\n".join(lines), kb.master_day(items, now)


@router.message(F.text.in_({kb.M_TODAY, kb.M_TOMORROW}))
async def schedule(message: Message, state: FSMContext, master) -> None:
    await state.clear()
    day = bk.now_local().date() + timedelta(days=1 if message.text == kb.M_TOMORROW else 0)
    text, markup = await day_view(master, day)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("ms:"))
async def mark_visit(call: CallbackQuery, master) -> None:
    _, booking_id, status = call.data.split(":")
    async with db.SessionLocal() as session:
        b = await bk.get_booking(session, int(booking_id))
        if not b or b.master_id != master.id:
            await call.answer("Запись не найдена", show_alert=True)
            return
        try:
            await bk.set_visit_status(session, b, status)
        except bk.BookingError as e:
            await call.answer(str(e), show_alert=True)
            return
    await call.answer("Отмечено")
    text, markup = await day_view(master, b.start_at.date())
    await call.message.edit_text(text, reply_markup=markup)


@router.message(F.text == kb.M_CLOSE)
async def close_pick_day(message: Message, state: FSMContext, master) -> None:
    await state.clear()
    today = bk.now_local().date()
    await message.answer("Какой день?", reply_markup=kb.master_close_days([today + timedelta(days=i) for i in range(9)]))


@router.callback_query(F.data.startswith("mo:") & (F.data != "mo:all"))
async def close_pick_range(call: CallbackQuery, state: FSMContext, master) -> None:
    await state.set_state(CloseTime.range)
    await state.update_data(off_day=call.data.split(":", 1)[1])
    await call.message.edit_text(
        "Напишите время, например «14:00-15:00» или «14-15», либо закройте весь день.",
        reply_markup=kb.master_close_range(),
    )


async def _close(answer, master, day: date, start: datetime, end: datetime, reason: str) -> None:
    async with db.SessionLocal() as session:
        _, conflicts = await eg.close_time(session, master.id, start, end, reason)
    span = "весь день" if (start.time(), end.time()) == (time.min, time.min) else f"{start:%H:%M}–{end:%H:%M}"
    text = f"⛔ Закрыто: {kb.short_date(day)}, {span}."
    if conflicts:
        text += "\nВнимание: на это время уже есть записи — " + ", ".join(f"{b.start_at:%H:%M}" for b in conflicts) + ". Предупредите клиентов или администратора."
    await answer(text)


@router.callback_query(CloseTime.range, F.data == "mo:all")
async def close_whole_day(call: CallbackQuery, state: FSMContext, master) -> None:
    day = date.fromisoformat((await state.get_data())["off_day"])
    await state.clear()
    start = datetime.combine(day, time.min)
    await _close(call.message.edit_text, master, day, start, start + timedelta(days=1), "Выходной")


@router.message(CloseTime.range, F.text)
async def close_range(message: Message, state: FSMContext, master) -> None:
    parsed = eg.parse_range(message.text)
    if not parsed:
        await message.answer("Не понял интервал. Пример: 14:00-15:00")
        return
    day = date.fromisoformat((await state.get_data())["off_day"])
    await state.clear()
    a, b = parsed
    await _close(message.answer, master, day, datetime.combine(day, a), datetime.combine(day, b), "Закрыто мастером")
