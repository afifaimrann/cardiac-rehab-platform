"""Slot generation: the arithmetic behind every bookable time.

Tested directly rather than only through the API, because these are the
calculations where an off-by-one produces a consultation at the wrong hour and
still looks plausible in a response body.
"""
from datetime import date, datetime, time, timedelta, timezone

from app.core.config import settings
from app.models.care import AvailabilityRule
from app.models.enums import AppointmentMode
from app.services import scheduling


def rule(**kw) -> AvailabilityRule:
    defaults = dict(
        clinician_id="doc-1", weekday=0, start_time=time(9, 0), end_time=time(12, 0),
        slot_minutes=30, mode=AppointmentMode.ONLINE, location=None,
        valid_from=None, valid_until=None, is_active=True,
    )
    defaults.update(kw)
    return AvailabilityRule(**defaults)


# A Monday, well clear of any boundary.
MONDAY = datetime(2026, 9, 7, 0, 30, tzinfo=timezone.utc)


def test_generates_one_slot_per_interval():
    slots = scheduling.generate_slots([rule()], days=0, now=MONDAY)
    # 09:00-12:00 in half hours is six slots.
    assert len(slots) == 6
    assert slots[0].ends_at - slots[0].starts_at == timedelta(minutes=30)


def test_slots_are_in_clinic_local_time():
    """A rota that says 09:00 must not produce a 09:00 UTC slot."""
    slots = scheduling.generate_slots([rule()], days=0, now=MONDAY)
    offset = timedelta(minutes=settings.CLINIC_TIMEZONE_OFFSET_MINUTES)
    local_first = slots[0].starts_at + offset
    assert local_first.hour == 9 and local_first.minute == 0


def test_trailing_partial_interval_is_not_offered():
    """A 09:00-10:20 window at 30 minutes yields two slots, not a 20-minute third."""
    slots = scheduling.generate_slots(
        [rule(end_time=time(10, 20))], days=0, now=MONDAY
    )
    assert len(slots) == 2


def test_minimum_notice_excludes_imminent_slots():
    # Stand at 09:00 clinic-local on the Monday itself; the 09:00 and 09:30
    # slots are inside the two-hour notice period, the 11:00 one is not.
    offset = timedelta(minutes=settings.CLINIC_TIMEZONE_OFFSET_MINUTES)
    now = datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc) - offset
    slots = scheduling.generate_slots([rule()], days=0, now=now)
    assert all(s.starts_at >= now + scheduling.MIN_NOTICE for s in slots)
    assert len(slots) == 2  # 11:00 and 11:30


def test_taken_slots_are_removed():
    all_slots = scheduling.generate_slots([rule()], days=0, now=MONDAY)
    taken = {all_slots[2].key}
    remaining = scheduling.generate_slots([rule()], days=0, now=MONDAY, taken_keys=taken)
    assert len(remaining) == len(all_slots) - 1
    assert all_slots[2].key not in {s.key for s in remaining}


def test_inactive_rule_offers_nothing():
    assert scheduling.generate_slots([rule(is_active=False)], days=7, now=MONDAY) == []


def test_validity_window_is_respected():
    slots = scheduling.generate_slots(
        [rule(valid_from=date(2026, 12, 1))], days=14, now=MONDAY
    )
    assert slots == []


def test_slots_only_fall_on_the_rule_weekday():
    offset = timedelta(minutes=settings.CLINIC_TIMEZONE_OFFSET_MINUTES)
    slots = scheduling.generate_slots([rule(weekday=1)], days=21, now=MONDAY)
    assert slots, "a Tuesday rule should offer Tuesdays within three weeks"
    # Checked in clinic-local time: a 09:00 Tuesday clinic is 03:00 UTC Tuesday
    # here, but a clinic six hours the other way would be Monday in UTC, and
    # asserting on the UTC weekday would pass for the wrong reason.
    assert all((s.starts_at + offset).weekday() == 1 for s in slots)


def test_horizon_is_capped():
    slots = scheduling.generate_slots([rule()], days=9999, now=MONDAY)
    horizon = MONDAY + timedelta(days=scheduling.MAX_HORIZON_DAYS + 1)
    assert all(s.starts_at <= horizon for s in slots)


def test_zero_length_slot_does_not_loop_forever():
    assert scheduling.generate_slots([rule(slot_minutes=0)], days=0, now=MONDAY) == []


def test_slot_key_ignores_seconds():
    a = scheduling.slot_key("doc", datetime(2026, 9, 7, 9, 0, 0, tzinfo=timezone.utc))
    b = scheduling.slot_key("doc", datetime(2026, 9, 7, 9, 0, 59, tzinfo=timezone.utc))
    assert a == b


def test_slot_key_separates_clinicians():
    when = datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc)
    assert scheduling.slot_key("a", when) != scheduling.slot_key("b", when)


def test_find_slot_matches_to_the_minute():
    slots = scheduling.generate_slots([rule()], days=0, now=MONDAY)
    wanted = slots[3].starts_at
    assert scheduling.find_slot(slots, wanted) is slots[3]
    assert scheduling.find_slot(slots, wanted + timedelta(minutes=1)) is None


def test_slots_are_sorted_soonest_first():
    rules = [rule(weekday=2), rule(weekday=0), rule(weekday=1)]
    slots = scheduling.generate_slots(rules, days=7, now=MONDAY)
    assert slots == sorted(slots, key=lambda s: s.starts_at)
