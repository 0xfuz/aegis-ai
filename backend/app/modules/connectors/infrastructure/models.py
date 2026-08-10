"""
ORM models for the `connectors` module — the plug-in ingestion layer the
architecture doc promises: every external data source (Sentinel, Splunk,
Elastic, CrowdStrike, cloud audit logs, ...) is meant to become a
`Connector` row plus a small adapter that turns its native event format
into the same normalized shape. This module ships the framework plus the
first real adapter: a generic webhook receiver. Vendor-specific adapters
(a Sentinel poller, a Splunk poller, etc.) are new `connector_type`
values and new ingestion functions in domain/service.py — they don't
change this schema or the investigations schema at all, which is exactly
the point of building the framework first.

v1's mock data (seed_data.py) intentionally bypasses this layer entirely
— it writes Investigation rows directly, standing in for "a connector
already ran". Real connectors, from v2 on, always go through
RawEvent -> normalize -> Investigation, so there is always an audit
trail of exactly what an external system sent before Aegis interpreted it.
"""
import enum
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base import Base, OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ConnectorType(str, enum.Enum):
    WEBHOOK = "webhook"
    # Future adapters register here: SENTINEL = "sentinel", SPLUNK = "splunk", etc.
    # Adding one means a new value here, a new normalize_* function in
    # domain/service.py, and (for polling-style sources) a Celery beat
    # schedule — never a schema change.


class ConnectorStatus(str, enum.Enum):
    CONNECTED = "connected"
    ERROR = "error"


class Connector(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "connectors"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(
        # Stored as plain text rather than a DB enum: unlike investigation
        # severity/status (a small, stable, domain-modeled set), connector
        # types are expected to grow steadily as real vendor adapters are
        # added — a DB enum would mean a migration for every new vendor.
        String(50),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ConnectorStatus.CONNECTED.value)

    # Only the bcrypt hash of the ingest secret is ever stored — same
    # pattern as user passwords. The plaintext secret is shown to the
    # admin exactly once, at creation time, and never again.
    secret_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    last_event_at: Mapped["DateTime | None"] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    raw_events: Mapped[list["RawEvent"]] = relationship(back_populates="connector", cascade="all, delete-orphan")


class RawEvent(Base, UUIDPrimaryKeyMixin):
    """Exactly what an external system sent, before Aegis interpreted it —
    the audit trail a real security product needs: if the AI got
    something wrong, you can always see the original input."""

    __tablename__ = "connector_raw_events"

    connector_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    received_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="SET NULL"), nullable=True
    )

    connector: Mapped["Connector"] = relationship(back_populates="raw_events")
