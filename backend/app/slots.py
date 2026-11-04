"""Расчёт свободных слотов. Чистые функции без базы данных."""

from datetime import date, datetime, time, timedelta

Interval = tuple[datetime, datetime]


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """Полуоткрытые интервалы [start, end): касание краями — не пересечение."""
    return a_start < b_end and b_start < a_end


def free_slots(
    day: date,
    duration_min: int,
    work: list[tuple[time, time]],
    busy: list[Interval],
    *,
    now: datetime | None = None,
    step_min: int = 30,
    min_lead_min: int = 0,
) -> list[datetime]:
    """Свободные начала записей на день.

    work — рабочие интервалы мастера в этот день, busy — занятое время
    (записи, обед, выходной). Слот подходит, если услуга целиком помещается
    в рабочий интервал, ни с чем не пересекается и начинается не раньше
    now + min_lead_min.
    """
    if duration_min <= 0 or step_min <= 0:
        raise ValueError("duration_min и step_min должны быть положительными")

    duration = timedelta(minutes=duration_min)
    step = timedelta(minutes=step_min)
    earliest = now + timedelta(minutes=min_lead_min) if now else None

    result: list[datetime] = []
    for w_start, w_end in sorted(work):
        start = datetime.combine(day, w_start)
        end = datetime.combine(day, w_end)
        t = start
        while t + duration <= end:
            fits = earliest is None or t >= earliest
            if fits and not any(overlaps(t, t + duration, b0, b1) for b0, b1 in busy):
                result.append(t)
            t += step
    return result
