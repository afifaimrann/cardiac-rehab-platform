"""Scheduling and direct messaging between a patient and their clinician.

Two things live here because they are the same relationship seen twice: a
patient talks to the clinician they are assigned to, and books time with that
same clinician. Neither table carries a free-floating "recipient" -- the
counterparty is always derived from the assignment, so a message or a booking
can never be addressed to a clinician who does not have this patient.
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean, Date, Enum, ForeignKey, Index, Integer, String, Text, Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamped, UUIDPrimaryKey, utcnow
from app.db.types import UtcDateTime
from app.models.enums import AppointmentMode, AppointmentStatus, MeetingProvider

if TYPE_CHECKING:
    from app.models.user import PatientProfile, User


class AvailabilityRule(UUIDPrimaryKey, Timestamped, Base):
    """A weekly window in which a clinician sees patients.

    Stored as a rule rather than as pre-generated slot rows. A clinic that
    publishes twelve weeks of half-hour slots is writing four hundred rows that
    exist only to be mostly unused, and every change to the rota has to rewrite
    them. Generating candidate slots on read costs microseconds and cannot
    drift from the rule that produced it.
    """

    __tablename__ = "availability_rules"
    __table_args__ = (Index("ix_availability_clinician_weekday", "clinician_id", "weekday"),)

    clinician_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # 0 = Monday, matching datetime.weekday().
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    slot_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)

    mode: Mapped[AppointmentMode] = mapped_column(
        Enum(AppointmentMode, native_enum=False, length=20),
        default=AppointmentMode.ONLINE, nullable=False,
    )
    location: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # A rota changes; old appointments must stay readable against the rule that
    # was in force, so rules are retired by date rather than deleted.
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    clinician: Mapped["User"] = relationship(foreign_keys=[clinician_id])


class Appointment(UUIDPrimaryKey, Timestamped, Base):
    """A booked consultation, online or in person."""

    __tablename__ = "appointments"
    __table_args__ = (
        Index("ix_appointments_patient_start", "patient_id", "starts_at"),
        Index("ix_appointments_clinician_start", "clinician_id", "starts_at"),
        # Double-booking is prevented in the database rather than by a check in
        # the handler, because two patients can call the same endpoint in the
        # same millisecond. slot_key is cleared on cancellation, and NULLs do
        # not collide under a unique index on either SQLite or Postgres, so a
        # cancelled time becomes bookable again without a partial index.
        UniqueConstraint("slot_key", name="uq_appointments_slot"),
    )

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False
    )
    clinician_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    slot_key: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)

    starts_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)

    mode: Mapped[AppointmentMode] = mapped_column(
        Enum(AppointmentMode, native_enum=False, length=20), nullable=False
    )
    location: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    # --- online meeting ----------------------------------------------------
    meeting_provider: Mapped[Optional[MeetingProvider]] = mapped_column(
        Enum(MeetingProvider, native_enum=False, length=20), nullable=True
    )
    meeting_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Kept separately from the URL so a room can be reused or reported without
    # parsing a link.
    meeting_room: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    # --- lifecycle ---------------------------------------------------------
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, native_enum=False, length=20),
        default=AppointmentStatus.SCHEDULED, nullable=False,
    )
    cancelled_by_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        UtcDateTime(), nullable=True
    )
    cancellation_reason: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    clinician_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    patient: Mapped["PatientProfile"] = relationship(back_populates="appointments")
    clinician: Mapped["User"] = relationship(foreign_keys=[clinician_id])


class DirectMessage(UUIDPrimaryKey, Timestamped, Base):
    """One message in the thread between a patient and their care team.

    There is one thread per patient rather than per pair of users: if a
    patient's clinician changes, the history the new clinician needs is the
    patient's, not the departing colleague's. sender_id records who wrote it.
    """

    __tablename__ = "direct_messages"
    __table_args__ = (Index("ix_direct_messages_patient_sent", "patient_id", "sent_at"),)

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False
    )
    sender_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), default=utcnow, nullable=False
    )
    # Null until the other party opens the thread.
    read_at: Mapped[Optional[datetime]] = mapped_column(
        UtcDateTime(), nullable=True
    )

    patient: Mapped["PatientProfile"] = relationship(back_populates="direct_messages")
    sender: Mapped["User"] = relationship(foreign_keys=[sender_id])


class ClinicianAssistantMessage(UUIDPrimaryKey, Timestamped, Base):
    """A turn in a clinician's private assistant thread about one patient.

    Scoped to (clinician, patient) so that opening a different patient starts a
    clean thread -- context bleeding between two patients' records is the one
    failure mode of this feature that would be genuinely dangerous.
    """

    __tablename__ = "clinician_assistant_messages"
    __table_args__ = (
        Index("ix_assistant_clinician_patient", "clinician_id", "patient_id", "created_at"),
    )

    clinician_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Names of the record lookups that produced this answer, so a clinician can
    # see what the assistant actually read rather than trusting the prose.
    tools_used: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
