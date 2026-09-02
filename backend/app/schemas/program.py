"""Exercise plan and session payloads."""
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.clinical import RiskFlagRead


class PlanCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    starts_on: date
    ends_on: Optional[date] = None
    sessions_per_week: int = Field(default=3, ge=1, le=14)
    minutes_per_session: int = Field(default=30, ge=5, le=180)
    target_exertion_max: Optional[int] = Field(
        default=None, ge=6, le=20, description="Borg RPE ceiling (6-20)."
    )
    instructions: Optional[str] = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def _dates_ordered(self) -> "PlanCreate":
        if self.ends_on and self.ends_on < self.starts_on:
            raise ValueError("ends_on cannot be before starts_on.")
        return self


class PlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    patient_id: str
    prescribed_by_id: Optional[str] = None
    title: str
    starts_on: date
    ends_on: Optional[date] = None
    sessions_per_week: int
    minutes_per_session: int
    target_exertion_max: Optional[int] = None
    instructions: Optional[str] = None
    is_active: bool
    created_at: datetime


class SessionCreate(BaseModel):
    performed_at: Optional[datetime] = None
    activity: str = Field(min_length=1, max_length=120)
    duration_minutes: int = Field(ge=1, le=600)
    perceived_exertion: Optional[int] = Field(
        default=None, ge=6, le=20, description="Borg rating of perceived exertion."
    )
    completed: bool = True
    notes: Optional[str] = Field(default=None, max_length=2000)


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    patient_id: str
    plan_id: Optional[str] = None
    performed_at: datetime
    activity: str
    duration_minutes: int
    perceived_exertion: Optional[int] = None
    completed: bool
    notes: Optional[str] = None


class SessionCreateResponse(BaseModel):
    session: SessionRead
    flags_raised: List[RiskFlagRead] = []


class AdherenceSummary(BaseModel):
    """Adherence over a rolling window, measured against the active plan."""

    patient_id: str
    plan_id: Optional[str] = None
    window_days: int
    sessions_expected: float = Field(description="Prorated from the plan's weekly target.")
    sessions_completed: int
    minutes_expected: float
    minutes_completed: int
    adherence_pct: Optional[float] = Field(
        default=None, description="completed/expected as a percentage; null with no active plan."
    )
