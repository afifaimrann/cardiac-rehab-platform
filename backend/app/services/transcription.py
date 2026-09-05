"""Speech-to-text for patient voice questions.

Thin wrapper over Whisper. Kept separate from the chat service so the transport
(audio) and the reasoning (retrieval and generation) can be tested and replaced
independently -- the browser can also send text directly, and that path must not
depend on any of this.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger("cardiac.transcription")

MAX_AUDIO_BYTES = 25 * 1024 * 1024  # Whisper's documented request ceiling
ALLOWED_CONTENT_TYPES = {
    "audio/webm", "audio/ogg", "audio/wav", "audio/x-wav",
    "audio/mpeg", "audio/mp4", "audio/m4a", "audio/mpga",
}


class TranscriptionUnavailable(RuntimeError):
    """Raised when speech-to-text is not configured."""


async def transcribe(audio: bytes, filename: str) -> Optional[str]:
    if not settings.voice_enabled:
        raise TranscriptionUnavailable(
            "Speech-to-text is not configured on this server. Set OPENAI_API_KEY "
            "to enable it, or type the question instead."
        )

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=60.0)
    try:
        result = await client.audio.transcriptions.create(
            model=settings.WHISPER_MODEL,
            file=(filename, audio),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Transcription failed: %s", exc)
        return None
    return (getattr(result, "text", "") or "").strip() or None
