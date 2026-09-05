"""Voice/text Q&A transcripts."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional

from sqlalchemy import Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base, Timestamped, UUIDPrimaryKey, utcnow
from app.models.enums import MessageRole

if TYPE_CHECKING:
    from app.models.user import PatientProfile

# JSONB on Postgres, plain JSON on SQLite.
JSONVariant = JSON().with_variant(JSONB(), "postgresql")


class Conversation(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_patient_created", "patient_id", "created_at"),)

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    patient: Mapped["PatientProfile"] = relationship()
    messages: Mapped[List["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "messages"
    # Cursor pagination walks (conversation_id, created_at) backwards.
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, native_enum=False, length=20), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Retrieved guideline passages backing an assistant answer.
    citations: Mapped[Optional[Any]] = mapped_column(JSONVariant, nullable=True)
    # Set when the message originated from an uploaded audio clip.
    transcribed_from_audio: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
