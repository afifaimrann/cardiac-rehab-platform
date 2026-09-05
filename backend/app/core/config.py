"""Application settings, loaded from the environment.

Everything configurable lives here so that no module reads os.environ directly.
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_JWT_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Application
    APP_NAME: str = "Cardiac Rehab Platform"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"

    # Security
    # The placeholder is usable in development and refused in production by
    # the check at the bottom of this module. A signing key that ships in a
    # public repository lets anyone mint a token for any patient.
    JWT_SECRET_KEY: str = DEFAULT_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./cardiac.db"

    # CORS. Kept as a raw string: pydantic-settings JSON-decodes list-typed
    # fields before validators run, which rejects plain comma-separated values.
    CORS_ORIGINS: str = "http://localhost:5173"

    # Retrieval
    # auto | fastembed | sentence-transformers | openai | hash | none
    EMBEDDING_BACKEND: str = "auto"
    # Must match the model. Bengali queries need a multilingual encoder:
    #   BAAI/bge-m3                    1024  (sentence-transformers; needs torch)
    #   intfloat/multilingual-e5-large 1024  (fastembed; ONNX, no torch)
    #   BAAI/bge-small-en-v1.5          384  (English only)
    # Changing the dimension needs a migration and a full re-ingest; changing
    # between two 1024-dim models needs only a re-ingest.
    # Changing it needs a migration and a full re-ingest.
    EMBEDDING_MODEL: str = "intfloat/multilingual-e5-large"
    EMBEDDING_DIM: int = 1024
    RETRIEVAL_MODE: str = "hybrid"   # hybrid | dense | lexical
    # Cross-encoder reranking of the top candidates. Slower per query, but it
    # is what makes a relevance threshold meaningful across both languages.
    # Disabled: bge-reranker-v2-m3 returns scores far below its documented range
    # on this machine (an exact-match pair scores 0.002), identically through
    # three loaders, two transformers versions, and a freshly downloaded
    # checkpoint. Cause unknown. Run `python -m scripts.rerank_sanity` and
    # require clear separation before setting this to true.
    RERANK_ENABLED: bool = False
    RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"
    # auto | flagembedding | transformers | cross-encoder
    RERANKER_BACKEND: str = "auto"
    RERANK_CANDIDATES: int = 20
    # Threshold on the reranker's 0-1 score. Applied instead of
    # MIN_DENSE_SIMILARITY whenever reranking ran.
    MIN_RERANK_SCORE: float = 0.30

    # Cosine similarity below which a dense hit is treated as "no match".
    # Model-dependent: calibrate with `python -m scripts.retrieval_debug`.
    # Refusing to answer beats answering from an unrelated passage.
    # Measured, not guessed: over the calibration set, relevant queries scored
    # 0.500-0.694 and irrelevant ones peaked at 0.480. The margin is narrow, so
    # this is a floor that errs toward refusing rather than answering wrongly.
    MIN_DENSE_SIMILARITY: float = 0.50

    # Speech / LLM
    OPENAI_API_KEY: str = ""
    WHISPER_MODEL: str = "whisper-1"
    CHAT_MODEL: str = "gpt-4o-mini"

    # Clinician assistant. A larger model than the patient chat: it reasons over
    # a whole record rather than three retrieved passages, and a clinician
    # notices a wrong summary in a way a patient cannot.
    CLINICIAN_ASSISTANT_MODEL: str = "gpt-4o"

    # Scheduling. The rota is authored in clinic-local wall-clock time; this is
    # the offset from UTC in minutes (Bangladesh Standard Time, UTC+6, by
    # default). A fixed offset rather than a zone name because the clinic this
    # is built for does not observe daylight saving; a clinic that does should
    # switch this to a zoneinfo key and convert per date.
    CLINIC_TIMEZONE_OFFSET_MINUTES: int = 360

    # Online consultations. Jitsi needs no credentials, so the booking flow
    # works out of the box; see app/services/meetings.py for the seam where a
    # Zoom or Google Meet integration plugs in.
    MEETING_PROVIDER: str = "jitsi"
    JITSI_BASE_URL: str = "https://meet.jit.si"

    # Uploaded avatars. Served by the API rather than by a CDN so that the same
    # bearer-token rules apply to a patient's photograph as to their record.
    MEDIA_ROOT: str = "media"
    MAX_AVATAR_BYTES: int = 4 * 1024 * 1024
    AVATAR_EDGE_PX: int = 512

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() in {"production", "prod"}

    @property
    def llm_enabled(self) -> bool:
        """Answer generation degrades to extractive when no key is configured."""
        return bool(self.OPENAI_API_KEY)

    @property
    def voice_enabled(self) -> bool:
        """Speech-to-text needs the same key; kept separate so the two can
        diverge if transcription later moves to a different provider."""
        return bool(self.OPENAI_API_KEY)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()

    # Fail at import rather than at the first forged token. A deployment that
    # kept the placeholder is not "insecure later" -- every access token it
    # ever issues is already forgeable by anyone who has read this file.
    if settings.is_production and settings.JWT_SECRET_KEY == DEFAULT_JWT_SECRET:
        raise RuntimeError(
            "JWT_SECRET_KEY is still the development placeholder. Set it before "
            "running in production: "
            'python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    return settings


settings = get_settings()
