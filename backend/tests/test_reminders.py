from datetime import datetime, timedelta

from app.reminders import initial_flags, reminder_due

START = datetime(2026, 11, 10, 15, 0)


def before(**kw):
    return START - timedelta(**kw)


def test_far_booking_needs_both():
    assert initial_flags(START, before(days=3)) == (False, False)


def test_booking_within_a_day_skips_day_before():
    assert initial_flags(START, before(hours=10)) == (True, False)


def test_booking_within_two_hours_skips_both():
    assert initial_flags(START, before(hours=1)) == (True, True)


def test_due_sequence():
    assert reminder_due(START, before(hours=30), False, False) is None
    assert reminder_due(START, before(hours=24), False, False) == "24h"
    assert reminder_due(START, before(hours=5), True, False) is None
    assert reminder_due(START, before(hours=2), True, False) == "2h"
    assert reminder_due(START, before(hours=1), True, True) is None


def test_missed_both_sends_only_nearest():
    assert reminder_due(START, before(hours=1), False, False) == "2h"


def test_no_reminder_after_start():
    assert reminder_due(START, START, False, False) is None
    assert reminder_due(START, START + timedelta(minutes=5), False, False) is None
