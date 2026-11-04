from datetime import date, datetime, time

from app.stats import BookingRow, master_load, outcome, summarize, working_minutes

NOW = datetime(2026, 11, 9, 15, 0)


def row(status, h, price=1000, source="site"):
    start = datetime(2026, 11, 9, h)
    return BookingRow("Артём", "Стрижка", source, status, start, start.replace(hour=h + 1), price)


def test_outcome():
    assert outcome("active", datetime(2026, 11, 9, 12), NOW) == "visited"  # прошла без отметки
    assert outcome("active", datetime(2026, 11, 9, 18), NOW) == "upcoming"
    assert outcome("done", datetime(2026, 11, 9, 18), NOW) == "visited"
    assert outcome("no_show", datetime(2026, 11, 9, 12), NOW) == "no_show"
    assert outcome("cancelled", datetime(2026, 11, 9, 12), NOW) == "cancelled"


def test_summarize():
    s = summarize([row("done", 10), row("active", 11, source="bot"), row("no_show", 12),
                   row("cancelled", 13), row("active", 18)], NOW)
    assert (s["total"], s["visited"], s["no_show"], s["cancelled"], s["upcoming"]) == (4, 2, 1, 1, 1)
    assert s["revenue"] == 2000
    assert s["no_show_rate"] == 33.3
    assert s["sources"] == {"site": 3, "bot": 1}


def test_working_minutes_with_time_off():
    hours = [(0, time(10), time(20))]  # только понедельник
    lunch = [(datetime(2026, 11, 9, 14), datetime(2026, 11, 9, 15))]
    assert working_minutes(hours, [], date(2026, 11, 9), 7) == 600
    assert working_minutes(hours, lunch, date(2026, 11, 9), 7) == 540
    assert working_minutes(hours, [], date(2026, 11, 10), 6) == 0


def test_master_load():
    assert master_load(300, 600) == 50.0
    assert master_load(10, 0) == 0.0
    assert master_load(700, 600) == 100.0
