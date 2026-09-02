"""Vitals, symptoms and risk-flag payloads."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import FlagSource, FlagStatus, Severity


class VitalsCreate(BaseModel):
    recorded_at: Optional[datetime] = Field(
        default=None, description="Defaults to now. Use for back-dated entries."
    )
    systolic: Optional[int] = Field(default=None, ge=50, le=300, description="mmHg")
    diastolic: Optional[int] = Field(default=None, ge=30, le=200, description="mmHg")
    heart_rate: Optional[int] = Field(default=None, ge=20, le=250, description="bpm")
    spo2: Optional[int] = Field(default=None, ge=50, le=100, description="percent")
    weight_kg: Optional[float] = Field(default=None, gt=0, le=500)
    note: Optional[str] = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _at_least_one_measurement(self) -> "VitalsCreate":
        if all(
            v is None
            for v in (self.systolic, self.diastolic, self.heart_rate, self.spo2, self.weight_kg)
        ):
            raise ValueError("Provide at least one measurement.")
        if (
            self.systolic is not None
            and self.diastolic is not None
            and self.diastolic >= self.systolic
        ):
            raise ValueError("Diastolic pressure must be lower than systolic.")
        return self


class VitalsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    patient_id: str
    recorded_at: datetime
    systolic: Optional[int] = None
    diastolic: Optional[int] = None
    heart_rate: Optional[int] = None
    spo2: Optional[int] = None
    weight_kg: Optional[float] = None
    note: Optional[str] = None


class RiskFlagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    patient_id: str
    source_type: FlagSource
    source_id: Optional[str] = None
    rule_code: str
    severity: Severity
    message: str
    status: FlagStatus
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None


class VitalsCreateResponse(BaseModel):
    """The stored reading plus anything it triggered.

    Returning the flags inline means the patient app can warn immediately
    without a second request.
    """

    vitals: VitalsRead
    flags_raised: List[RiskFlagRead] = []


class SymptomCreate(BaseModel):
    recorded_at: Optional[datetime] = None
    description: str = Field(min_length=1, max_length=2000)
    severity: Severity = Severity.MILD


class SymptomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    patient_id: str
    recorded_at: datetime
    description: str
    severity: Severity


class SymptomCreateResponse(BaseModel):
    symptom: SymptomRead
    flags_raised: List[RiskFlagRead] = []


class FlagResolve(BaseModel):
    status: FlagStatus = Field(description="Set to acknowledged or resolved.")
    resolution_note: Optional[str] = Field(default=None, max_length=2000)
