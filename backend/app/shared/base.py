"""
Shared kernel: the declarative Base and cross-cutting mixins every module's
models inherit from. This is the ONLY thing modules are allowed to share at
the ORM level — a module must never import another module's models directly
(import the other module's service/repository interface instead).
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class OrgScopedMixin:
    """Every tenant-owned row carries org_id — enforced at the application
    layer in the MVP (row-level security policies are a documented v2
    hardening step once the schema has settled)."""

    org_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True
    )
