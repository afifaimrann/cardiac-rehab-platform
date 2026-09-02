"""Domain enumerations.

All enum columns are stored as strings (native_enum=False at the column site) so
the same models run unchanged on SQLite in development and Postgres in
production, and so adding a value never requires an ALTER TYPE migration.
"""
from enum import Enum


class UserRole(str, Enum):
    PATIENT = "patient"
    CLINICIAN = "clinician"
    ADMIN = "admin"


class Severity(str, Enum):
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


class FlagStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class FlagSource(str, Enum):
    VITALS = "vitals"
    SYMPTOM = "symptom"
    SESSION = "session"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
