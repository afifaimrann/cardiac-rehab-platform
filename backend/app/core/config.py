"""Application settings, loaded from the environment.

Everything configurable lives here so that no module reads os.environ directly.
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Application
    APP_NAME: str = "Cardiac Rehab Platform"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"

    # Security
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./cardiac.db"

    # CORS. Kept as a raw string: pydantic-settings JSON-decodes list-typed
    # fields before validators run, which rejects plain comma-separated values.
    CORS_ORIGINS: str = "http://localhost:5173"

    # Speech / LLM
    OPENAI_API_KEY: str = ""
    WHISPER_MODEL: str = "whisper-1"
    CHAT_MODEL: str = "gpt-4o-mini"

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() in {"production", "prod"}

    @property
    def voice_enabled(self) -> bool:
        """Voice Q&A degrades gracefully when no API key is configured."""
        return bool(self.OPENAI_API_KEY)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
