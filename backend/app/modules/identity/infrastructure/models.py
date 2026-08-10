"""
ORM models for the `identity` module. This module owns: organizations,
users, roles, permissions, and the token-revocation list. No other module
may declare a foreign key into these tables' internals beyond storing a
plain `org_id` / `user_id` UUID column (that's the DDD boundary).
"""
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Table, UniqueConstraint, Column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# --- Association table: role <-> permission (many-to-many) ---
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", PG_UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", PG_UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class Organization(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)

    users: Mapped[list["User"]] = relationship(back_populates="organization")


class Permission(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "permissions"

    # e.g. "investigation:read", "investigation:approve_remediation", "reports:generate_executive"
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class Role(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "roles"

    # soc_analyst | incident_responder | security_architect | ciso | ai_engineer | admin
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    permissions: Mapped[list["Permission"]] = relationship(secondary=role_permissions)
    users: Mapped[list["User"]] = relationship(back_populates="role")


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("org_id", "email", name="uq_users_org_email"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False
    )

    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    organization: Mapped["Organization"] = relationship(back_populates="users")
    role: Mapped["Role"] = relationship(back_populates="users")


class RevokedToken(Base):
    """Tracks revoked refresh-token JTIs (logout, forced sign-out) so a
    stolen-but-logged-out refresh token can't mint new access tokens.
    Access tokens are short-lived (30 min default) and are not individually
    revocable by design — that trade-off is documented in the README."""

    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    revoked_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), nullable=False)
