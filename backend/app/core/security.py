"""
Password hashing and JWT access/refresh token helpers.

Uses argon2id (via `argon2-cffi` directly, OWASP's recommended default)
for password hashing, and short-lived HS256 JWTs for access tokens,
delivered to the browser as an HttpOnly, SameSite=Lax cookie (see
app/api/auth.py) rather than being exposed to JavaScript.

Note: we call `argon2-cffi` directly rather than through `passlib` --
passlib has seen no real release in years and its argon2 backend triggers
Python 3.13 deprecation warnings (it still imports the stdlib `crypt`
module). `argon2-cffi` is the actively maintained library passlib itself
wraps for argon2, so this removes a layer without changing the algorithm.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()

_hasher = PasswordHasher()


def hash_password(plain_password: str) -> str:
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return _hasher.verify(hashed_password, plain_password)
    except VerifyMismatchError:
        return False
    except Exception:
        # Malformed/unknown hash format -- treat as a failed verification
        # rather than raising, so a bad row in the DB can't 500 the login
        # endpoint.
        return False


def _create_token(
    subject: str, expires_delta: timedelta, token_type: Literal["access", "refresh"]
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: str) -> str:
    return _create_token(user_id, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES), "access")


def create_refresh_token(user_id: str) -> str:
    return _create_token(
        user_id, timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES), "refresh"
    )


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None
