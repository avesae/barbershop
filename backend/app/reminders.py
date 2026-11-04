"""Когда отправлять напоминания. Чистые функции без базы данных."""

from datetime import datetime, timedelta

DAY_BEFORE = timedelta(hours=24)
HOURS_BEFORE = timedelta(hours=2)


def initial_flags(start_at: datetime, now: datetime) -> tuple[bool, bool]:
    """Флаги (24ч отправлено, 2ч отправлено) для новой или перенесённой записи.

    Если до визита уже меньше суток, напоминание «за день» не нужно:
    клиент только что записался. То же для «за 2 часа».
    """
    left = start_at - now
    return left <= DAY_BEFORE, left <= HOURS_BEFORE


def reminder_due(start_at: datetime, now: datetime, sent_24h: bool, sent_2h: bool) -> str | None:
    """Какое напоминание пора отправить: "24h", "2h" или None.

    Если бот простоял и подошли оба срока, отправляется только ближайшее — "2h".
    """
    if start_at <= now:
        return None
    left = start_at - now
    if not sent_2h and left <= HOURS_BEFORE:
        return "2h"
    if not sent_24h and left <= DAY_BEFORE:
        return "24h"
    return None
