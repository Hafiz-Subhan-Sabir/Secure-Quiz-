from hashlib import sha256
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from jose import JWTError, jwt

from app.core.config import get_settings

Role = Literal["admin", "instructor", "student"]

# Use SHA-256 digests for local/dev auth to avoid bcrypt/passlib version friction.
# Swap to argon2/bcrypt in production deploy configs.
_PWD_PREFIX = "iq$sha256$"


def hash_password(password: str) -> str:
    digest = sha256(password.encode("utf-8")).hexdigest()
    return f"{_PWD_PREFIX}{digest}"


def verify_password(plain: str, hashed: str) -> bool:
    if hashed.startswith(_PWD_PREFIX):
        return hash_password(plain) == hashed
    return False


def create_access_token(
    *,
    subject: str,
    role: Role,
    expires_minutes: int | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )
    payload: dict[str, Any] = {"sub": subject, "role": role, "exp": expire}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("invalid_token") from exc
