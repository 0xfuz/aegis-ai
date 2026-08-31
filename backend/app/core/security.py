"""
Security primitives: password hashing and JWT issuance/verification.

Kept deliberately framework-agnostic (no FastAPI imports here) so it can be
unit-tested in isolation and reused by any module, not just `identity`.
"""
import uuid as uuid_lib
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


def hash_password(plain_password: str) -> str:
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def _create_token(
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    now = datetime.now(timezone.utc)
    to_encode: dict[str, Any] = {
        "sub": subject,
        "type": token_type.value,
        "jti": str(uuid_lib.uuid4()),
        "iat": now,
        "exp": now + expires_delta,
    }
    if extra_claims:
        to_encode.update(extra_claims)
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: UUID, org_id: UUID, role: str, permissions: list[str], *, password_rotation_required: bool = False) -> str:
    return _create_token(
        subject=str(user_id),
        token_type=TokenType.ACCESS,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        extra_claims={
            "org_id": str(org_id),
            "role": role,
            "permissions": permissions,
            "password_rotation_required": password_rotation_required,
        },
    )


def create_refresh_token(user_id: UUID) -> str:
    return _create_token(
        subject=str(user_id),
        token_type=TokenType.REFRESH,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


class TokenPayload:
    def __init__(self, payload: dict[str, Any]):
        self.user_id: str = payload["sub"]
        self.token_type: str = payload["type"]
        self.jti: str = payload["jti"]
        self.exp: int = payload["exp"]
        self.org_id: Optional[str] = payload.get("org_id")
        self.role: Optional[str] = payload.get("role")
        self.permissions: list[str] = payload.get("permissions", [])
        self.password_rotation_required: bool = payload.get("password_rotation_required", False) is True


class InvalidTokenError(Exception):
    pass


def decode_token(token: str, expected_type: TokenType) -> TokenPayload:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise InvalidTokenError("Token is invalid or expired") from exc

    if payload.get("type") != expected_type.value:
        raise InvalidTokenError(f"Expected a {expected_type.value} token")

    return TokenPayload(payload)
