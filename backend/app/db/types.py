"""Column types that behave the same on SQLite and Postgres.

`DateTime(timezone=True)` is a promise SQLite does not keep. Postgres stores an
instant and hands back an aware datetime; SQLite stores the string it was given
and hands back a naive one, so the same code returns `2026-09-08T04:00:00+00:00`
on one database and `2026-09-08T04:00:00` on the other.

That difference is invisible in Python — until it reaches a browser, which
parses a timestamp with no offset as *local* time. A consultation stored at
04:00 UTC then displays at 04:00 in Dhaka and 05:00 in London, and neither is
right. The bug never shows up in tests written in the same timezone as the
data, which is what makes it worth fixing in the type rather than at each call
site.

`UtcDateTime` normalises both directions: everything is stored as UTC, and
everything comes back aware.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator):
    """An aware UTC datetime, on any backend."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self, value: Optional[datetime], dialect
    ) -> Optional[datetime]:
        if value is None:
            return None
        if not isinstance(value, datetime):  # pragma: no cover - defensive
            raise TypeError(f"Expected a datetime, got {type(value).__name__}")
        if value.tzinfo is None:
            # A naive value reaching the database is a bug upstream, but
            # rejecting it would fail a write over something we can interpret
            # unambiguously: everything in this system is UTC.
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(
        self, value: Optional[datetime], dialect
    ) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
