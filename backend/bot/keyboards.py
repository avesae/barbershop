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


def dates(items: list[date]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for d in items:
        kb.button(text=short_date(d), callback_data=f"day:{d.isoformat()}")
    kb.adjust(3)
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
