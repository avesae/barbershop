from datetime import date, datetime, time

import pytest

from app.slots import free_slots, overlaps

DAY = date(2026, 11, 9)


def at(h, m=0):
    return datetime(2026, 11, 9, h, m)


def hm(slots):
    return [s.strftime("%H:%M") for s in slots]


def test_grid_with_step():
    assert hm(free_slots(DAY, 60, [(time(10), time(12))], [])) == ["10:00", "10:30", "11:00"]


def test_service_longer_than_working_day():
    assert free_slots(DAY, 90, [(time(10), time(11))], []) == []


def test_day_off_has_no_slots():
    assert free_slots(DAY, 30, [], []) == []


def test_busy_interval_removes_overlapping_slots():
    busy = [(at(10, 30), at(11, 30))]
    assert hm(free_slots(DAY, 60, [(time(10), time(13))], busy)) == ["11:30", "12:00"]


def test_touching_edges_is_not_overlap():
    busy = [(at(10), at(11))]
    assert hm(free_slots(DAY, 60, [(time(10), time(12))], busy)) == ["11:00"]


def test_lunch_break_splits_day():
    lunch = [(at(13), at(14))]
    slots = hm(free_slots(DAY, 60, [(time(12), time(15))], lunch))
    assert slots == ["12:00", "14:00"]


def test_several_working_intervals():
    work = [(time(14), time(15)), (time(10), time(11))]
    assert hm(free_slots(DAY, 60, work, [])) == ["10:00", "14:00"]


def test_past_and_lead_time_are_skipped():
    slots = free_slots(DAY, 30, [(time(10), time(13))], [], now=at(10, 20), min_lead_min=60)
    assert hm(slots)[0] == "11:30"


def test_now_on_previous_day_does_not_limit():
    slots = free_slots(DAY, 60, [(time(10), time(11))], [], now=datetime(2026, 11, 8, 23, 0), min_lead_min=60)
    assert hm(slots) == ["10:00"]


def test_step_does_not_have_to_match_duration():
    assert hm(free_slots(DAY, 45, [(time(10), time(11, 30))], [], step_min=15)) == [
        "10:00", "10:15", "10:30", "10:45",
    ]


@pytest.mark.parametrize("duration,step", [(0, 30), (30, 0), (-15, 30)])
def test_invalid_params(duration, step):
    with pytest.raises(ValueError):
        free_slots(DAY, duration, [(time(10), time(12))], [], step_min=step)


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ((at(10), at(11)), (at(10, 30), at(11, 30)), True),
        ((at(10), at(11)), (at(11), at(12)), False),
        ((at(10), at(12)), (at(10, 30), at(11)), True),
        ((at(10), at(11)), (at(9), at(10)), False),
    ],
)
def test_overlaps(a, b, expected):
    assert overlaps(*a, *b) is expected
    assert overlaps(*b, *a) is expected
