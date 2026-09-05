"""Video rooms for online appointments.

One provider works with no credentials at all (Jitsi Meet, whose rooms are
created by being joined), so booking an online consultation produces a link
that actually opens a call. Zoom and Google Meet are behind the same interface
but need per-clinic OAuth credentials to create a meeting; until those exist,
an appointment can still carry a link a clinician pasted in.

SECURITY -- why the room name is random
    A Jitsi room is created by whoever visits its URL first, and anyone who
    knows the name can walk into the call. Naming rooms after something
    predictable (the appointment id, the patient's name, a date) means a
    stranger who guesses the pattern can sit in on a consultation. Room names
    here come from `secrets`, are long enough not to be brute-forced, and are
    never derived from patient data.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Optional

from app.core.config import settings
from app.models.enums import MeetingProvider

# 128 bits of entropy, base32-ish: unguessable, and still typeable over the
# phone if a patient cannot open the link.
ROOM_TOKEN_BYTES = 16
ROOM_PREFIX = "cardiacrehab"


@dataclass(frozen=True)
class Meeting:
    provider: MeetingProvider
    room: str
    url: str


class MeetingProviderUnavailable(RuntimeError):
    """Raised when a provider is selected that cannot create rooms unattended."""


def _jitsi_room() -> str:
    return f"{ROOM_PREFIX}-{secrets.token_hex(ROOM_TOKEN_BYTES)}"


def create_room(provider: Optional[MeetingProvider] = None) -> Meeting:
    """Create a video room for an online appointment.

    Called once when the appointment is booked rather than on each visit, so
    both parties see the same link and a patient can add it to their calendar.
    """
    provider = provider or MeetingProvider(settings.MEETING_PROVIDER)

    if provider is MeetingProvider.JITSI:
        room = _jitsi_room()
        base = settings.JITSI_BASE_URL.rstrip("/")
        return Meeting(provider=provider, room=room, url=f"{base}/{room}")

    # The seam for a real integration: exchange clinic credentials for a
    # meeting via the provider's API and return its join URL. Deliberately not
    # faked -- returning a plausible-looking Zoom URL that dials nowhere is
    # worse than saying the provider is not configured.
    raise MeetingProviderUnavailable(
        f"{provider.value} meetings require clinic OAuth credentials, which are not "
        "configured. Book this appointment as in-person, or paste an existing "
        "meeting link when confirming it."
    )
