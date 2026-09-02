"""Password hashing and JWT issuing/verification.

Access tokens are short-lived and carry the user's role so that authorisation
checks never need a database round-trip. Refresh tokens are long-lived, carry a
distinct token type, and are the only tokens accepted by the refresh endpoint --
this prevents an access token from being replayed to mint new credentials.
"""
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional

import bcrypt
import jwt

from app.core.config import settings

# bcrypt directly rather than passlib: passlib 1.7.4 is unmaintained and its
# bcrypt backend warns against bcrypt >= 4. The cost factor is explicit here.
BCRYPT_ROUNDS = 12
# bcrypt silently truncates at 72 bytes; reject longer input instead.
MAX_PASSWORD_BYTES = 72


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


def hash_password(plain_password: str) -> str:
    pw = plain_password.encode("utf-8")
    if len(pw) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes")
    return bcrypt.hashpw(pw, bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8")[:MAX_PASSWORD_BYTES],
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def _create_token(
    subject: str, token_type: TokenType, expires_delta: timedelta, **claims: Any
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "iss": settings.APP_NAME,
        "iat": now,
        "exp": now + expires_delta,
        "type": token_type.value,
        **claims,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: str, role: str) -> str:
    return _create_token(
        subject=user_id,
        token_type=TokenType.ACCESS,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        role=role,
    )


def create_refresh_token(user_id: str) -> str:
    return _create_token(
        subject=user_id,
        token_type=TokenType.REFRESH,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, expected_type: TokenType) -> Optional[dict[str, Any]]:
    """Return the token payload, or None if invalid, expired or the wrong type."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.APP_NAME,
        )
    except jwt.PyJWTError:
        return None
    if payload.get("type") != expected_type.value:
        return None
    return payload
