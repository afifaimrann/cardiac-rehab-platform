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
    CHAT = "chat"
    WALK_TEST = "walk_test"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class SexAtBirth(str, Enum):
    """Recorded only because the 6MWT predicted-distance equations are
    sex-specific. Not used anywhere else in the system."""

    FEMALE = "female"
    MALE = "male"
    UNSPECIFIED = "unspecified"


class WalkTestStatus(str, Enum):
    COMPLETED = "completed"
    STOPPED_EARLY = "stopped_early"
    NOT_ATTEMPTED = "not_attempted"


class AppointmentMode(str, Enum):
    ONLINE = "online"
    IN_PERSON = "in_person"


class AppointmentStatus(str, Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class MeetingProvider(str, Enum):
    """Where an online appointment is held.

    JITSI needs no account or credentials, so the booking flow works end to end
    out of the box. ZOOM and GOOGLE_MEET are recognised so an existing link can
    be stored against an appointment; creating one automatically needs OAuth
    credentials per clinic (see app/services/meetings.py).
    """

    JITSI = "jitsi"
    ZOOM = "zoom"
    GOOGLE_MEET = "google_meet"
    OTHER = "other"
