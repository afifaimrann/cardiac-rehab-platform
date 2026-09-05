"""Patient-reported clinical data and the flags raised from it."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamped, UUIDPrimaryKey, utcnow
from app.db.types import UtcDateTime
from app.models.enums import FlagSource, FlagStatus, Severity

if TYPE_CHECKING:
    from app.models.user import PatientProfile, User


class VitalsRecord(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "vitals_records"
    # Every listing is "this patient's readings, newest first" -- a composite
    # index on (patient, recorded_at) serves both the filter and the sort.
    __table_args__ = (
        Index("ix_vitals_patient_recorded", "patient_id", "recorded_at"),
    )

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), default=utcnow, nullable=False
    )

    systolic: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    diastolic: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    heart_rate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    spo2: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    weight_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    patient: Mapped["PatientProfile"] = relationship(back_populates="vitals")


class SymptomReport(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "symptom_reports"
    __table_args__ = (
        Index("ix_symptoms_patient_recorded", "patient_id", "recorded_at"),
    )

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), default=utcnow, nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[Severity] = mapped_column(
        Enum(Severity, native_enum=False, length=20), default=Severity.MILD, nullable=False
    )

    patient: Mapped["PatientProfile"] = relationship(back_populates="symptoms")


class RiskFlag(UUIDPrimaryKey, Timestamped, Base):
    """A rule-raised concern awaiting clinician review.

    The flag stores the rule code and a human-readable message rather than a
    reference to live rule logic, so a flag raised last month still reads
    correctly after the thresholds are tuned.
    """

    __tablename__ = "risk_flags"
    __table_args__ = (
        Index("ix_flags_patient_status", "patient_id", "status"),
        Index("ix_flags_status_created", "status", "created_at"),
    )

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[FlagSource] = mapped_column(
        Enum(FlagSource, native_enum=False, length=20), nullable=False
    )
    source_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    rule_code: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    severity: Mapped[Severity] = mapped_column(
        Enum(Severity, native_enum=False, length=20), nullable=False
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[FlagStatus] = mapped_column(
        Enum(FlagStatus, native_enum=False, length=20),
        default=FlagStatus.OPEN,
        nullable=False,
    )
    resolved_by_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        UtcDateTime(), nullable=True
    )
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    patient: Mapped["PatientProfile"] = relationship(back_populates="risk_flags")
    resolved_by: Mapped[Optional["User"]] = relationship(foreign_keys=[resolved_by_id])
