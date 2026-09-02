"""Import every model so Alembic autogenerate and Base.metadata see them all."""
from app.db.base import Base
from app.models.chat import Conversation, Message
from app.models.clinical import RiskFlag, SymptomReport, VitalsRecord
from app.models.enums import (
    FlagSource, FlagStatus, MessageRole, Severity, UserRole,
)
from app.models.program import ExercisePlan, ExerciseSession
from app.models.user import PatientProfile, User

__all__ = [
    "Base",
    "Conversation",
    "ExercisePlan",
    "ExerciseSession",
    "FlagSource",
    "FlagStatus",
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
