"""Clinician caseload and queue payloads."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.enums import Severity


class CaseloadRow(BaseModel):
    """One patient as they appear in the clinician's roster."""

    patient_id: str
    full_name: str
    email: str
    primary_condition: Optional[str] = None

    open_flags: int = 0
    highest_open_severity: Optional[Severity] = None
    last_vitals_at: Optional[datetime] = None

    sessions_completed: int = 0
    adherence_pct: Optional[float] = Field(
        default=None, description="Null when the patient has no active plan."
    )


class Caseload(BaseModel):
    window_days: int
    patients: List[CaseloadRow]


class PatientAssign(BaseModel):
    clinician_id: Optional[str] = Field(
        default=None, description="Clinician to assign; null unassigns the patient."
    )
