"""Appointment, availability and messaging payloads."""
from datetime import date, datetime, time
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import AppointmentMode, AppointmentStatus, MeetingProvider


# --- availability ----------------------------------------------------------
class AvailabilityRuleCreate(BaseModel):
    weekday: int = Field(ge=0, le=6, description="0 = Monday, matching datetime.weekday().")
    start_time: time
    end_time: time
    slot_minutes: int = Field(default=30, ge=10, le=120)
    mode: AppointmentMode = AppointmentMode.ONLINE
    location: Optional[str] = Field(default=None, max_length=200)
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None

    @model_validator(mode="after")
    def _check_window(self) -> "AvailabilityRuleCreate":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time.")
        if self.mode is AppointmentMode.IN_PERSON and not self.location:
            raise ValueError("An in-person clinic needs a location.")
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until must not be before valid_from.")
        return self


class AvailabilityRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    weekday: int
    start_time: time
    end_time: time
    slot_minutes: int
    mode: AppointmentMode
    location: Optional[str] = None
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    is_active: bool


class SlotRead(BaseModel):
    """An offered time. Has no id because slots are derived, not stored."""

    starts_at: datetime
    ends_at: datetime
    mode: AppointmentMode
    location: Optional[str] = None
    clinician_id: str
    clinician_name: Optional[str] = None


# --- appointments ----------------------------------------------------------
class AppointmentBook(BaseModel):
    starts_at: datetime = Field(description="Must match a start time the rota offers.")
    mode: Optional[AppointmentMode] = Field(
        default=None,
        description="Defaults to the mode the slot was published as. Only a mode "
        "the slot supports is accepted.",
    )
    reason: Optional[str] = Field(default=None, max_length=300)


class AppointmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    patient_id: str
    clinician_id: str
    starts_at: datetime
    ends_at: datetime
    mode: AppointmentMode
    location: Optional[str] = None
    reason: Optional[str] = None
    meeting_provider: Optional[MeetingProvider] = None
    meeting_url: Optional[str] = None
    status: AppointmentStatus
    cancellation_reason: Optional[str] = None
    clinician_notes: Optional[str] = None
    clinician_name: Optional[str] = None
    patient_name: Optional[str] = None


class AppointmentCancel(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=300)


class AppointmentUpdate(BaseModel):
    """Clinician-side outcome recording."""

    status: Optional[AppointmentStatus] = None
    clinician_notes: Optional[str] = Field(default=None, max_length=4000)
    meeting_url: Optional[str] = Field(default=None, max_length=500)
    meeting_provider: Optional[MeetingProvider] = None


# --- messaging -------------------------------------------------------------
class MessageSend(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class DirectMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    patient_id: str
    sender_id: str
    sender_name: Optional[str] = None
    sender_role: Optional[str] = None
    body: str
    sent_at: datetime
    read_at: Optional[datetime] = None


class MessageThread(BaseModel):
    messages: List[DirectMessageRead]
    unread_count: int
    counterparty_name: Optional[str] = Field(
        default=None, description="Null when a patient has no clinician assigned yet."
    )


# --- clinician assistant ---------------------------------------------------
class AssistantAsk(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class AssistantTurn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    content: str
    tools_used: Optional[str] = None
    created_at: datetime


class AssistantAnswer(BaseModel):
    answer: str
    tools_used: List[str] = []
    generated: bool = Field(
        description="False when no language model is configured and the reply is "
        "a deterministic summary of the record.",
    )
