"""Internal, transactional production-admin bootstrap boundary."""
from __future__ import annotations

from datetime import datetime, timezone
import re
from uuid import UUID

from pydantic import EmailStr, TypeAdapter, ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.modules.evidence.infrastructure.models import AuditEvent
from app.modules.identity.infrastructure.models import Organization, Permission, Role, User
from app.modules.identity.infrastructure.repository import OrganizationRepository, UserRepository
from app.seed.seed_data import PERMISSIONS, ROLES
from app.shared.exceptions import ConflictError, NotFoundError, ValidationError

_DEFAULT_EMAILS = {"admin@aegis.demo"}
_DEFAULT_PASSWORDS = {"changeme123!", "aegis_dev_password", "change_me_dev_only_insecure_secret", "password", "password123", "admin"}
_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,98}[a-z0-9])?$")
_EMAIL_ADAPTER = TypeAdapter(EmailStr)


def _normalize_bootstrap_email(value: str) -> str | None:
    """Apply the same deliverability-aware email contract as login requests."""
    try:
        return str(_EMAIL_ADAPTER.validate_python(value.strip())).casefold()
    except PydanticValidationError:
        return None


def validate_bootstrap_password(password: str) -> None:
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise ValidationError("Bootstrap credentials are invalid.")
    if password.casefold() in _DEFAULT_PASSWORDS:
        raise ValidationError("Bootstrap credentials are invalid.")
    categories = sum((any(char.islower() for char in password), any(char.isupper() for char in password), any(char.isdigit() for char in password), any(not char.isalnum() for char in password)))
    if categories < 3:
        raise ValidationError("Bootstrap credentials are invalid.")


def _ensure_baseline_roles(db: Session) -> dict[str, Role]:
    permissions = {item.code: item for item in db.query(Permission).all()}
    for code, description in PERMISSIONS.items():
        if code not in permissions:
            permissions[code] = Permission(code=code, description=description)
            db.add(permissions[code])
    db.flush()
    roles = {item.name: item for item in db.query(Role).all()}
    for name, (description, permission_codes) in ROLES.items():
        role = roles.get(name)
        if role is None:
            role = Role(name=name, description=description)
            db.add(role)
            db.flush()
            roles[name] = role
        role.permissions = [permissions[code] for code in permission_codes]
    db.flush()
    return roles


class ProductionAdminBootstrapService:
    """Creates one scoped admin and never retains plaintext credentials."""
    def __init__(self, db: Session, *, environment: str, demo_seed_enabled: bool):
        self.db, self.environment, self.demo_seed_enabled = db, environment.casefold(), demo_seed_enabled
        self.users, self.organizations = UserRepository(db), OrganizationRepository(db)

    def bootstrap(self, *, organization_name: str, organization_slug: str, email: str, full_name: str, password: str) -> UUID:
        if self.environment == "production" and self.demo_seed_enabled:
            raise ValidationError("Production bootstrap configuration is invalid.")
        normalized_email, normalized_slug = _normalize_bootstrap_email(email), organization_slug.strip().casefold()
        if (not normalized_email or normalized_email in _DEFAULT_EMAILS or not 1 <= len(organization_name.strip()) <= 255 or not 1 <= len(full_name.strip()) <= 255 or not _SLUG.fullmatch(normalized_slug)):
            raise ValidationError("Bootstrap identity is invalid.")
        validate_bootstrap_password(password)
        try:
            if self.organizations.get_by_slug(normalized_slug) is not None:
                raise ConflictError("Bootstrap state already exists.")
            roles = _ensure_baseline_roles(self.db)
            organization = Organization(name=organization_name.strip(), slug=normalized_slug)
            self.db.add(organization)
            self.db.flush()
            user = User(org_id=organization.id, role_id=roles["admin"].id, email=normalized_email, full_name=full_name.strip(), hashed_password=hash_password(password), is_active=True, must_rotate_password=True)
            self.users.create(user)
            self.db.add(AuditEvent(org_id=organization.id, investigation_id=None, actor_id=None, actor_type="operator", action="PRODUCTION_ADMIN_BOOTSTRAPPED", target_type="User", target_id=user.id, occurred_at=datetime.now(timezone.utc), metadata_={"password_rotation_required": True}))
            self.db.commit()
            return user.id
        except (ConflictError, ValidationError):
            self.db.rollback()
            raise
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError("Bootstrap state already exists.") from exc
        except Exception:
            self.db.rollback()
            raise ValidationError("Bootstrap could not be completed.") from None


class ProductionAdminPasswordRecoveryService:
    """Internal operator recovery boundary; plaintext never leaves the caller."""

    def __init__(self, db: Session, *, environment: str, demo_seed_enabled: bool):
        self.db, self.environment, self.demo_seed_enabled = db, environment.casefold(), demo_seed_enabled

    def reset(self, *, organization_slug: str, email: str, password: str) -> UUID:
        if self.environment != "production" or self.demo_seed_enabled:
            raise ValidationError("Production recovery configuration is invalid.")
        normalized_email = _normalize_bootstrap_email(email)
        normalized_slug = organization_slug.strip().casefold()
        if not normalized_email or normalized_email in _DEFAULT_EMAILS or not _SLUG.fullmatch(normalized_slug):
            raise ValidationError("Recovery identity is invalid.")
        validate_bootstrap_password(password)
        try:
            organization = self.db.scalar(select(Organization).where(Organization.slug == normalized_slug))
            if organization is None:
                raise NotFoundError("Administrator not found.")
            users = list(self.db.scalars(
                select(User).join(Role).where(
                    User.org_id == organization.id,
                    User.email == normalized_email,
                    User.is_active.is_(True),
                    Role.name == "admin",
                )
            ))
            if len(users) != 1:
                raise NotFoundError("Administrator not found.")
            user = users[0]
            user.hashed_password = hash_password(password)
            user.must_rotate_password = True
            self.db.add(AuditEvent(
                org_id=organization.id, investigation_id=None, actor_id=None,
                actor_type="operator", action="OPERATOR_ADMIN_PASSWORD_RESET",
                target_type="User", target_id=user.id, occurred_at=datetime.now(timezone.utc),
                metadata_={"password_rotation_required": True},
            ))
            self.db.commit()
            return user.id
        except (NotFoundError, ValidationError):
            self.db.rollback()
            raise
        except Exception:
            self.db.rollback()
            raise ValidationError("Administrator recovery could not be completed.") from None
