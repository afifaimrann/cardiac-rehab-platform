"""Shared response envelopes."""
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class CursorPage(BaseModel, Generic[T]):
    """Cursor-paginated list.

    Cursor rather than offset pagination: clinical logs are append-heavy and
    frequently read newest-first, where an offset shifts under the reader and
    silently duplicates or skips rows. `next_cursor` is null on the last page.
    """

    items: List[T]
    next_cursor: Optional[str] = Field(
        default=None,
        description="Opaque cursor for the next page; null when no more results.",
    )


class Message(BaseModel):
    detail: str
