"""
Application services for the identity module. This is the only layer that
orchestrates repositories + security primitives — API routers call these
methods and never touch the database or JWT internals directly.
"""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.modules.identity.infrastructure.models import User
from app.modules.identity.infrastructure.repository import (
    OrganizationRepository,
    RoleRepository,
    TokenRevocationRepository,
    UserRepository,
)
from app.shared.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)


class AuthService:
    """Login, token refresh, logout."""

    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db)
        self.revocations = TokenRevocationRepository(db)

    def authenticate(self, email: str, password: str) -> tuple[str, str]:
        user = self.users.get_by_email_any_org(email)
        if user is None or not verify_password(password, user.hashed_password):
            # Deliberately identical error for "no such user" and "wrong
            # password" — don't leak which one it was.
            raise AuthenticationError("Incorrect email or password.")
        if not user.is_active:
            raise AuthenticationError("This account has been deactivated.")

        return self._issue_tokens(user)

    def refresh(self, refresh_token: str) -> tuple[str, str]:
        try:
            payload = decode_token(refresh_token, expected_type=TokenType.REFRESH)
        except InvalidTokenError as exc:
            raise AuthenticationError("Refresh token is invalid or expired.") from exc

        if self.revocations.is_revoked(payload.jti):
            raise AuthenticationError("This session has been signed out.")

        user = self.users.get_by_id(UUID(payload.user_id))
        if user is None or not user.is_active:
            raise AuthenticationError("Account is no longer active.")

        # Rotate: revoke the old refresh token, issue a fresh pair. Prevents
        # a leaked refresh token from being replayed indefinitely.
        self.revocations.revoke(
            payload.jti, datetime.fromtimestamp(payload.exp, tz=timezone.utc)
        )
        return self._issue_tokens(user)

    def logout(self, refresh_token: str) -> None:
        try:
            payload = decode_token(refresh_token, expected_type=TokenType.REFRESH)
        except InvalidTokenError:
            return  # already invalid/expired — logout is idempotent
        self.revocations.revoke(
            payload.jti, datetime.fromtimestamp(payload.exp, tz=timezone.utc)
        )

    def _issue_tokens(self, user: User) -> tuple[str, str]:
        permission_codes = [p.code for p in user.role.permissions]
        access = create_access_token(user.id, user.org_id, user.role.name, permission_codes)
        refresh = create_refresh_token(user.id)
        return access, refresh


class UserService:
    """User CRUD + role assignment, scoped to the caller's organization."""

    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db)
        self.roles = RoleRepository(db)
        self.orgs = OrganizationRepository(db)

    def get_current_user(self, user_id: UUID) -> User:
        user = self.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found.")
        return user

    def list_org_users(self, org_id: UUID) -> list[User]:
        return self.users.list_by_org(org_id)

    def invite_user(self, org_id: UUID, email: str, full_name: str, role_name: str, temporary_password: str) -> User:
        if self.users.get_by_email(org_id, email):
            raise ConflictError("A user with this email already exists in your organization.")

        role = self.roles.get_by_name(role_name)
        if role is None:
            raise ValidationError(f"Unknown role: {role_name}")

        user = User(
            org_id=org_id,
            role_id=role.id,
            email=email.lower(),
            hashed_password=hash_password(temporary_password),
            full_name=full_name,
            is_active=True,
        )
        return self.users.create(user)

    def update_role(self, org_id: UUID, user_id: UUID, role_name: str) -> User:
        user = self.users.get_by_id(user_id)
        if user is None or user.org_id != org_id:
            raise NotFoundError("User not found.")

        role = self.roles.get_by_name(role_name)
        if role is None:
            raise ValidationError(f"Unknown role: {role_name}")

        user.role_id = role.id
        return self.users.save(user)

    def deactivate(self, org_id: UUID, user_id: UUID) -> User:
        user = self.users.get_by_id(user_id)
        if user is None or user.org_id != org_id:
            raise NotFoundError("User not found.")
        user.is_active = False
        return self.users.save(user)

    def reactivate(self, org_id: UUID, user_id: UUID) -> User:
        user = self.users.get_by_id(user_id)
        if user is None or user.org_id != org_id:
            raise NotFoundError("User not found.")
        user.is_active = True
        return self.users.save(user)
