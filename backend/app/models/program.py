"""Prescribed exercise programme and the patient's logged sessions."""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean, Date, ForeignKey, Index, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamped, UUIDPrimaryKey, utcnow
from app.db.types import UtcDateTime

if TYPE_CHECKING:
    from app.models.user import PatientProfile, User


class ExercisePlan(UUIDPrimaryKey, Timestamped, Base):
    """A clinician-prescribed weekly target.

    Plans are versioned by keeping old rows with is_active=False rather than
    updating in place, so a logged session can always be compared against the
    plan that was in force when it happened.
    """

    __tablename__ = "exercise_plans"
    __table_args__ = (Index("ix_plans_patient_active", "patient_id", "is_active"),)

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False
    )
    prescribed_by_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(160), nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    sessions_per_week: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    minutes_per_session: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    target_exertion_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    patient: Mapped["PatientProfile"] = relationship(back_populates="plans")
    prescribed_by: Mapped[Optional["User"]] = relationship(foreign_keys=[prescribed_by_id])
    sessions: Mapped[List["ExerciseSession"]] = relationship(back_populates="plan")


class ExerciseSession(UUIDPrimaryKey, Timestamped, Base):
    """One completed (or abandoned) exercise session logged by the patient."""

    __tablename__ = "exercise_sessions"
    __table_args__ = (
        Index("ix_sessions_patient_performed", "patient_id", "performed_at"),
    )

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("exercise_plans.id", ondelete="SET NULL"), nullable=True
    )

    performed_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), default=utcnow, nullable=False
    )
    activity: Mapped[str] = mapped_column(String(120), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    # Borg rating of perceived exertion, 6-20.
    perceived_exertion: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    patient: Mapped["PatientProfile"] = relationship(back_populates="sessions")
    plan: Mapped[Optional["ExercisePlan"]] = relationship(back_populates="sessions")
