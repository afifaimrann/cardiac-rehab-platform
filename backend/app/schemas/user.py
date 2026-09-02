"""Account and authentication payloads."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import UserRole


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)
    # Self-registration is patient-only; clinician accounts are created by an
    # admin, so role is deliberately not accepted from the request body.


class ClinicianCreate(UserRegister):
    """Admin-only clinician provisioning."""


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds.")


class RefreshRequest(BaseModel):
    refresh_token: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class PatientProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    clinician_id: Optional[str] = None
    date_of_birth: Optional[date] = None
    primary_condition: Optional[str] = None
    language: str
    resting_hr_baseline: Optional[int] = None
    target_hr_max: Optional[int] = None


class PatientProfileUpdate(BaseModel):
    date_of_birth: Optional[date] = None
    primary_condition: Optional[str] = Field(default=None, max_length=200)
    language: Optional[str] = Field(default=None, max_length=5)
    resting_hr_baseline: Optional[int] = Field(default=None, ge=30, le=140)
    target_hr_max: Optional[int] = Field(default=None, ge=60, le=220)


class MeResponse(BaseModel):
    user: UserRead
    patient_profile: Optional[PatientProfileRead] = None
