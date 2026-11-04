from datetime import date, datetime

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.models import Booking, Master, Service
from app.notify import MONTHS, WEEKDAYS

BOOK = "✂️ Записаться"
MY = "📋 Мои записи"
ABOUT = "📍 Контакты"
DELETE = "🗑 Удалить мои данные"

ABORT = InlineKeyboardButton(text="✖️ Отмена", callback_data="abort")


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BOOK), KeyboardButton(text=MY)],
            [KeyboardButton(text=ABOUT), KeyboardButton(text=DELETE)],
        ],
        resize_keyboard=True,
    )


def share_phone() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить мой номер", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def services(items: list[Service]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for s in items:
        kb.button(text=f"{s.name} · {s.price} ₽ · {s.duration_min} мин", callback_data=f"svc:{s.id}")
    kb.adjust(1)
    kb.row(ABORT)
    return kb.as_markup()


def masters(items: list[Master]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for m in items:
        kb.button(text=f"{m.name} — {m.title}", callback_data=f"mst:{m.id}")
    kb.adjust(1)
    kb.row(ABORT)
    return kb.as_markup()


def short_date(d: date) -> str:
    return f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1][:3]}"


def dates(items: list[date], waitlist: bool = True) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for d in items:
        kb.button(text=short_date(d), callback_data=f"day:{d.isoformat()}")
    kb.adjust(3)
    if waitlist:
        kb.row(InlineKeyboardButton(text="📝 Нет удобного дня — в лист ожидания", callback_data="wl:pick"))
    kb.row(ABORT)
    return kb.as_markup()


def times(items: list[datetime]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for t in items:
        kb.button(text=t.strftime("%H:%M"), callback_data=f"tm:{t.isoformat(timespec='minutes')}")
    kb.adjust(4)
    kb.row(InlineKeyboardButton(text="« Другая дата", callback_data="back:dates"), ABORT)
    return kb.as_markup()


def consent() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Согласен", callback_data="consent:yes")], [ABORT]]
    )


def confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Подтвердить запись", callback_data="confirm")], [ABORT]]
    )


def booking_actions(b: Booking) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔁 Перенести", callback_data=f"rs:{b.id}"),
                InlineKeyboardButton(text="❌ Отменить", callback_data=f"cx:{b.id}"),
            ]
        ]
    )


def confirm_cancel(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да, отменить", callback_data=f"cxok:{booking_id}")],
            [InlineKeyboardButton(text="Нет", callback_data="abort")],
        ]
    )


def confirm_delete() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да, удалить всё", callback_data="del:yes")],
            [InlineKeyboardButton(text="Нет", callback_data="abort")],
        ]
    )


# --- кабинет мастера -------------------------------------------------------

M_TODAY = "📅 Сегодня"
M_TOMORROW = "📅 Завтра"
M_CLOSE = "⛔ Закрыть время"


def master_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=M_TODAY), KeyboardButton(text=M_TOMORROW)], [KeyboardButton(text=M_CLOSE)]],
        resize_keyboard=True,
    )


def master_day(bookings: list[Booking], now: datetime) -> InlineKeyboardMarkup | None:
    kb = InlineKeyboardBuilder()
    for b in bookings:
        if b.start_at > now:
            continue
        t = b.start_at.strftime("%H:%M")
        mark = {"done": "✅ ", "no_show": "🚫 "}.get(b.status, "")
        kb.row(
            InlineKeyboardButton(text=f"{mark}{t} пришёл", callback_data=f"ms:{b.id}:done"),
            InlineKeyboardButton(text=f"{t} не пришёл", callback_data=f"ms:{b.id}:no_show"),
        )
    return kb.as_markup() if kb.export() else None


def master_close_days(days: list[date]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for d in days:
        kb.button(text=short_date(d), callback_data=f"mo:{d.isoformat()}")
    kb.adjust(3)
    kb.row(ABORT)
    return kb.as_markup()


def master_close_range() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Весь день", callback_data="mo:all")], [ABORT]]
    )


# --- отзывы, повторная запись, лист ожидания -------------------------------


def stars(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="★" * n, callback_data=f"rv:{booking_id}:{n}") for n in range(1, 6)]]
    )


def skip() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Пропустить", callback_data="rvskip")]])


def rebook(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🗓 Выбрать время", callback_data=f"rb:{booking_id}")]]
    )


def waitlist_days(days: list[date]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for d in days:
        kb.button(text=short_date(d), callback_data=f"wl:{d.isoformat()}")
    kb.adjust(3)
    kb.row(ABORT)
    return kb.as_markup()


def waitlist_offer(master_id: int, service_id: int, slots: list[datetime]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for t in slots[:12]:
        kb.button(text=t.strftime("%H:%M"), callback_data=f"wlt:{master_id}:{service_id}:{t.isoformat(timespec='minutes')}")
    kb.adjust(4)
    return kb.as_markup()
