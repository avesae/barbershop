"""Метрики для админки. Чистые функции над списками записей."""

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from .slots import Interval

VISITED = "visited"


def outcome(status: str, start_at: datetime, now: datetime) -> str:
    """Итог записи: visited, no_show, cancelled или upcoming.

    Прошедшая запись, которую никто не отметил, считается состоявшейся:
    на практике мастера отмечают только неявки.
    """
    if status == "cancelled":
        return "cancelled"
    if status == "no_show":
        return "no_show"
    if status == "done" or start_at <= now:
        return VISITED
    return "upcoming"


def working_minutes(hours: list[tuple[int, time, time]], off: list[Interval], start: date, days: int) -> int:
    """Рабочие минуты мастера за период за вычетом закрытого времени."""
    total = 0
    for i in range(days):
        d = start + timedelta(days=i)
        for weekday, a, b in hours:
            if weekday != d.weekday():
                continue
            w0, w1 = datetime.combine(d, a), datetime.combine(d, b)
            minutes = (w1 - w0).total_seconds() / 60
            for o0, o1 in off:
                lo, hi = max(w0, o0), min(w1, o1)
                if lo < hi:
                    minutes -= (hi - lo).total_seconds() / 60
            total += max(0, minutes)
    return int(total)


@dataclass
class BookingRow:
    master: str
    service: str
    source: str
    status: str
    start_at: datetime
    end_at: datetime
    price: int


def summarize(rows: list[BookingRow], now: datetime) -> dict:
    outcomes = [outcome(r.status, r.start_at, now) for r in rows]
    visited = [r for r, o in zip(rows, outcomes) if o == VISITED]
    no_show = outcomes.count("no_show")
    finished = len(visited) + no_show
    sources = Counter(r.source for r, o in zip(rows, outcomes) if o != "cancelled")
    return {
        "total": len(rows) - outcomes.count("cancelled"),
        "visited": len(visited),
        "no_show": no_show,
        "cancelled": outcomes.count("cancelled"),
        "upcoming": outcomes.count("upcoming"),
        "revenue": sum(r.price for r in visited),
        "no_show_rate": round(no_show / finished * 100, 1) if finished else 0.0,
        "sources": {"site": sources.get("site", 0), "bot": sources.get("bot", 0)},
    }


def master_load(booked_minutes: int, work_minutes: int) -> float:
    return round(min(booked_minutes / work_minutes, 1) * 100, 1) if work_minutes else 0.0
