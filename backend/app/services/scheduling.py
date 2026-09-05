"""Turning a clinician's weekly rota into bookable slots.

The rota is stored as weekly rules (see AvailabilityRule). Everything a patient
sees is derived here: candidate slots are generated from the rules for a date
window, then anything already taken, too soon, or outside the rule's validity
is removed. Nothing is written until a patient books.

All arithmetic is in UTC. The rota is authored in local clinic time and stored
as naive `time` values against a weekday; `CLINIC_TIMEZONE_OFFSET_MINUTES`
converts. Doing this in one place is deliberate -- a scheduling bug that puts a
consultation six hours out is invisible in tests written in the same wrong
timezone as the code.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, List, Optional, Sequence

from app.core.config import settings
from app.models.care import AvailabilityRule
from app.models.enums import AppointmentMode

# A patient cannot book a slot starting sooner than this. Without it, someone
# can book a consultation that began four minutes ago.
MIN_NOTICE = timedelta(hours=2)
# How far ahead the rota is offered. Longer windows generate slots that a rota
# change will invalidate.
MAX_HORIZON_DAYS = 60
DEFAULT_HORIZON_DAYS = 14


@dataclass(frozen=True)
class Slot:
    """A bookable time. `key` is what a booking is made against."""

    starts_at: datetime
    ends_at: datetime
    mode: AppointmentMode
    location: Optional[str]
    clinician_id: str

    @property
    def key(self) -> str:
        return slot_key(self.clinician_id, self.starts_at)


def slot_key(clinician_id: str, starts_at: datetime) -> str:
    """The value the unique index is built on.

    Seconds are truncated so that two representations of the same minute cannot
    both be booked.
    """
    stamp = starts_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M")
    return f"{clinician_id}:{stamp}"


def _clinic_offset() -> timedelta:
    return timedelta(minutes=settings.CLINIC_TIMEZONE_OFFSET_MINUTES)


def _to_utc(day: date, local: time) -> datetime:
    """A local clinic wall-clock time on a given day, as an aware UTC instant."""
    naive_local = datetime.combine(day, local)
    return (naive_local - _clinic_offset()).replace(tzinfo=timezone.utc)


def _rule_applies(rule: AvailabilityRule, day: date) -> bool:
    if not rule.is_active:
        return False
    if rule.valid_from and day < rule.valid_from:
        return False
    if rule.valid_until and day > rule.valid_until:
        return False
    return True


def generate_slots(
    rules: Sequence[AvailabilityRule],
    *,
    days: int = DEFAULT_HORIZON_DAYS,
    taken_keys: Iterable[str] = (),
    now: Optional[datetime] = None,
) -> List[Slot]:
    """Every slot a patient may book, soonest first.

    `taken_keys` are the slot keys of appointments that are still standing;
    passing them in rather than querying here keeps this function pure and
    directly testable.
    """
    now = now or datetime.now(timezone.utc)
    days = max(1, min(days, MAX_HORIZON_DAYS))
    earliest = now + MIN_NOTICE
    taken = set(taken_keys)

    slots: List[Slot] = []
    # The window is walked in clinic-local days, because a rule says "Tuesday
    # afternoon" in the clinic's calendar, not in UTC's.
    first_local_day = (now + _clinic_offset()).date()

    for offset in range(days + 1):
        day = first_local_day + timedelta(days=offset)
        for rule in rules:
            if rule.weekday != day.weekday() or not _rule_applies(rule, day):
                continue

            cursor = _to_utc(day, rule.start_time)
            window_end = _to_utc(day, rule.end_time)
            length = timedelta(minutes=rule.slot_minutes)
            if length <= timedelta(0):
                continue

            while cursor + length <= window_end:
                slot = Slot(
                    starts_at=cursor,
                    ends_at=cursor + length,
                    mode=rule.mode,
                    location=rule.location,
                    clinician_id=rule.clinician_id,
                )
                if cursor >= earliest and slot.key not in taken:
                    slots.append(slot)
                cursor += length

    slots.sort(key=lambda s: s.starts_at)
    return slots


def find_slot(slots: Sequence[Slot], starts_at: datetime) -> Optional[Slot]:
    """The offered slot matching a requested start, to the minute.

    A booking names a time, not an id, because slots are generated rather than
    stored. Matching here means a patient can only ever book something the rota
    actually offers -- an arbitrary timestamp posted to the endpoint finds
    nothing and is refused.
    """
    wanted = starts_at.astimezone(timezone.utc).replace(second=0, microsecond=0)
    for slot in slots:
        if slot.starts_at.replace(second=0, microsecond=0) == wanted:
            return slot
    return None
