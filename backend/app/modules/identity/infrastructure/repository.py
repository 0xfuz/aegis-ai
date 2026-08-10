"""
Repository pattern: all direct SQLAlchemy querying for the identity module
lives here. The service layer never touches `Session.query`/`select`
directly — it calls this repository, which keeps persistence concerns
swappable (e.g. if the org later needs a read replica or a different ORM).
"""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.modules.identity.infrastructure.models import (
    Organization,
    Permission,
    RevokedToken,
    Role,
    User,
)


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: UUID) -> User | None:
        stmt = (
            select(User)
            .options(joinedload(User.role).joinedload(Role.permissions))
            .where(User.id == user_id)
        )
        return self.db.execute(stmt).unique().scalar_one_or_none()

    def get_by_email(self, org_id: UUID, email: str) -> User | None:
        stmt = (
            select(User)
            .options(joinedload(User.role).joinedload(Role.permissions))
            .where(User.org_id == org_id, User.email == email.lower())
        )
        return self.db.execute(stmt).unique().scalar_one_or_none()

    def get_by_email_any_org(self, email: str) -> User | None:
        """Used at login when the org isn't known up front — the client
        only has an email/password, not an org slug."""
        stmt = (
            select(User)
            .options(joinedload(User.role).joinedload(Role.permissions))
            .where(User.email == email.lower())
        )
        return self.db.execute(stmt).unique().scalar_one_or_none()

    def list_by_org(self, org_id: UUID) -> list[User]:
        stmt = (
            select(User)
            .options(joinedload(User.role).joinedload(Role.permissions))
            .where(User.org_id == org_id)
            .order_by(User.created_at.desc())
        )
        return list(self.db.execute(stmt).unique().scalars().all())

    def create(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        return user

    def save(self, user: User) -> User:
        self.db.flush()
        return user


class RoleRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_name(self, name: str) -> Role | None:
        stmt = select(Role).options(joinedload(Role.permissions)).where(Role.name == name)
        return self.db.execute(stmt).unique().scalar_one_or_none()

    def list_all(self) -> list[Role]:
        stmt = select(Role).options(joinedload(Role.permissions))
        return list(self.db.execute(stmt).unique().scalars().all())


class OrganizationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, org_id: UUID) -> Organization | None:
        return self.db.get(Organization, org_id)

    def get_by_slug(self, slug: str) -> Organization | None:
        stmt = select(Organization).where(Organization.slug == slug)
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, org: Organization) -> Organization:
        self.db.add(org)
        self.db.flush()
        return org


class TokenRevocationRepository:
    def __init__(self, db: Session):
        self.db = db

    def is_revoked(self, jti: str) -> bool:
        return self.db.get(RevokedToken, jti) is not None

    def revoke(self, jti: str, expires_at: datetime) -> None:
        self.db.merge(
            RevokedToken(jti=jti, revoked_at=datetime.now(timezone.utc), expires_at=expires_at)
        )
        self.db.flush()
