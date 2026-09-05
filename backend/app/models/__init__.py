"""Import every model so Alembic autogenerate and Base.metadata see them all."""
from app.db.base import Base
from app.models.assessment import WalkTest
from app.models.care import (
    Appointment, AvailabilityRule, ClinicianAssistantMessage, DirectMessage,
)
from app.models.chat import Conversation, Message
from app.models.clinical import RiskFlag, SymptomReport, VitalsRecord
from app.models.knowledge import KnowledgePassage
from app.models.enums import (
    AppointmentMode, AppointmentStatus, FlagSource, FlagStatus, MeetingProvider,
    MessageRole, Severity, SexAtBirth, UserRole, WalkTestStatus,
)
from app.models.program import ExercisePlan, ExerciseSession
from app.models.user import PatientProfile, User

__all__ = [
    "Appointment",
    "AppointmentMode",
    "AppointmentStatus",
    "AvailabilityRule",
    "Base",
    "ClinicianAssistantMessage",
    "DirectMessage",
    "MeetingProvider",
    "Conversation",
    "SexAtBirth",
    "WalkTest",
    "WalkTestStatus",
    "ExercisePlan",
    "ExerciseSession",
    "FlagSource",
    "FlagStatus",
    "KnowledgePassage",
    "Message",
    "MessageRole",
    "PatientProfile",
    "RiskFlag",
    "Severity",
    "SymptomReport",
    "User",
    "UserRole",
    "VitalsRecord",
]
