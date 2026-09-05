"""Declarative base and shared column mixins."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.types import UtcDateTime


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class UUIDPrimaryKey:
    """String UUID primary keys: portable across SQLite and Postgres, and safe to
    expose in URLs (sequential integer ids leak record counts and invite probing)."""

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), default=utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), default=utcnow, onupdate=utcnow, nullable=False
    )
