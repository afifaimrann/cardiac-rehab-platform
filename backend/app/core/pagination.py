"""Keyset (cursor) pagination helpers.

A cursor encodes the sort key of the last row returned -- here the timestamp
plus the row id as a tie-breaker, since two readings can share a timestamp.
Encoding both makes the ordering total, so no row is ever skipped or repeated
when rows are inserted between page fetches.
"""
from __future__ import annotations

import base64
import binascii
from datetime import datetime
from typing import Optional, Tuple

from fastapi import HTTPException, status


def encode_cursor(ts: datetime, row_id: str) -> str:
    raw = f"{ts.isoformat()}|{row_id}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> Tuple[datetime, str]:
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(cursor + padding).decode("utf-8")
        ts_str, row_id = raw.split("|", 1)
        return datetime.fromisoformat(ts_str), row_id
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed pagination cursor"
        )


def next_cursor_for(items: list, limit: int, ts_attr: str) -> Optional[str]:
    """Cursor for the following page, or None when this was the last page."""
    if len(items) < limit:
        return None
    last = items[-1]
    return encode_cursor(getattr(last, ts_attr), last.id)
