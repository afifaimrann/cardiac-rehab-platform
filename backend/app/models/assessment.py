"""Six-minute walk test records.

The 6MWT is the standard submaximal measure of functional capacity in cardiac
rehabilitation: distance walked on a flat course in six minutes, with heart
rate, oxygen saturation and perceived exertion recorded before and after.

Every field the protocol calls for is stored, including the ones a shortcut
would drop -- lowest SpO2 during the walk rather than only the final value,
rests taken, and why a test was stopped. Those are the fields a clinician reads
when a distance looks worse than last time.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean, Enum, Float, ForeignKey, Index, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamped, UUIDPrimaryKey, utcnow
from app.db.types import UtcDateTime
from app.models.enums import WalkTestStatus

if TYPE_CHECKING:
    from app.models.user import PatientProfile, User


class WalkTest(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "walk_tests"
    __table_args__ = (Index("ix_walk_tests_patient_performed", "patient_id", "performed_at"),)

    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False
    )
    # Null when a patient self-recorded; set when a clinician supervised.
    conducted_by_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    performed_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), default=utcnow, nullable=False
    )

    # --- screening as answered on the day ----------------------------------
    # Stored because the record must show why this test was allowed to proceed,
    # and because the next test can offer these answers back for confirmation
    # instead of asking the same four questions every fortnight.
    screen_acs_within_30_days: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    screen_unstable_angina: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    screen_syncope_history: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    screen_acute_respiratory_failure: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # --- course and result -------------------------------------------------
    course_length_m: Mapped[float] = mapped_column(Float, default=30.0, nullable=False)
    laps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    partial_lap_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    distance_m: Mapped[float] = mapped_column(Float, nullable=False)

    # --- before ------------------------------------------------------------
    pre_heart_rate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pre_spo2: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pre_systolic: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pre_diastolic: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pre_borg_dyspnoea: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pre_borg_fatigue: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # --- during ------------------------------------------------------------
    # The nadir matters more than the endpoint: desaturation often recovers
    # before the six minutes are up, and recording only the final value hides it.
    lowest_spo2: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rest_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rest_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # --- after -------------------------------------------------------------
    post_heart_rate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    post_spo2: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    post_systolic: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    post_diastolic: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    post_borg_dyspnoea: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    post_borg_fatigue: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # --- outcome -----------------------------------------------------------
    status: Mapped[WalkTestStatus] = mapped_column(
        Enum(WalkTestStatus, native_enum=False, length=20),
        default=WalkTestStatus.COMPLETED, nullable=False,
    )
    stop_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    symptoms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    used_oxygen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Stored rather than recomputed: the equation inputs (height, weight, age)
    # change over time, and a past result must stay comparable to what the
    # clinician saw on the day.
    predicted_distance_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    percent_predicted: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    below_lower_limit: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    patient: Mapped["PatientProfile"] = relationship(back_populates="walk_tests")
    conducted_by: Mapped[Optional["User"]] = relationship(foreign_keys=[conducted_by_id])
