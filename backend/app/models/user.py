"""Accounts and patient profiles.

A User is an identity with a role. Clinical data hangs off PatientProfile rather
than User so that a clinician account never carries orphan clinical columns, and
so a patient's clinical record can be reassigned without touching credentials.
"""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, Date, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamped, UUIDPrimaryKey
from app.models.enums import SexAtBirth, UserRole

if TYPE_CHECKING:
    from app.models.assessment import WalkTest
    from app.models.care import Appointment, DirectMessage
    from app.models.clinical import RiskFlag, SymptomReport, VitalsRecord
    from app.models.program import ExercisePlan, ExerciseSession


class User(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=20), nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Filename only, never a path or a URL: the storage root is configuration,
    # and a stored absolute path breaks the moment the volume is remounted.
    # Storing a filename also means a stored value can never escape the media
    # directory the way a stored "../.." path could.
    avatar_filename: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    patient_profile: Mapped[Optional["PatientProfile"]] = relationship(
        back_populates="user",
        uselist=False,
        foreign_keys="PatientProfile.user_id",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.email} ({self.role})>"


class PatientProfile(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "patient_profiles"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    # The clinician responsible for this patient. Nullable so a patient can be
    # enrolled before assignment; SET NULL on delete keeps the clinical record.
    clinician_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    primary_condition: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    language: Mapped[str] = mapped_column(String(5), default="en", nullable=False)

    # Baselines used by the risk engine to personalise thresholds.
    resting_hr_baseline: Mapped[Optional[int]] = mapped_column(nullable=True)
    target_hr_max: Mapped[Optional[int]] = mapped_column(nullable=True)

    # Anthropometrics, needed only by the 6MWT predicted-distance equations.
    height_cm: Mapped[Optional[float]] = mapped_column(nullable=True)
    sex_at_birth: Mapped[Optional[SexAtBirth]] = mapped_column(
        Enum(SexAtBirth, native_enum=False, length=20), nullable=True
    )

    user: Mapped["User"] = relationship(
        back_populates="patient_profile", foreign_keys=[user_id]
    )
    clinician: Mapped[Optional["User"]] = relationship(foreign_keys=[clinician_id])

    vitals: Mapped[List["VitalsRecord"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )
    symptoms: Mapped[List["SymptomReport"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )
    risk_flags: Mapped[List["RiskFlag"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )
    plans: Mapped[List["ExercisePlan"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )
    sessions: Mapped[List["ExerciseSession"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )
    walk_tests: Mapped[List["WalkTest"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )
    appointments: Mapped[List["Appointment"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )
    direct_messages: Mapped[List["DirectMessage"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )
