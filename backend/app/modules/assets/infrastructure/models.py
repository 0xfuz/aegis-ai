"""
The asset registry — org-scoped, same design pattern as investigations'
IOC registry: an asset's identity is (org, name), not tied to any one
investigation. When an investigation's timeline event references
"jump-host-03" as `affected_asset`, that's a mention of this same
registry entry, not a separate fact — record_sighting() (see
repository.py) keeps the two in sync exactly the way IOCRepository does.

v1 fields are manually curated (seed data / analyst input). A real CMDB
or cloud-inventory connector would populate the same columns
automatically — this is intentionally the same trade-off as
IOC.enrichment: schema is final, only the population method changes later.
"""
import enum
import uuid

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base import Base, OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AssetCriticality(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AssetHealth(str, enum.Enum):
    HEALTHY = "healthy"
    AT_RISK = "at_risk"
    COMPROMISED = "compromised"
    UNKNOWN = "unknown"


class Asset(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_assets_org_name"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String(50), nullable=False, default="host")  # host | cloud_resource | identity_provider | ...
    os: Mapped[str | None] = mapped_column(String(100), nullable=True)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Stored as plain strings (not DB enums), same rationale as
    # connectors' Connector.type/status: these are simple, low-cardinality
    # classifications an analyst or a future risk-scoring job updates
    # often — a DB enum would mean a migration for every new value.
    criticality: Mapped[str] = mapped_column(String(20), nullable=False, default=AssetCriticality.MEDIUM.value)
    health: Mapped[str] = mapped_column(String(20), nullable=False, default=AssetHealth.UNKNOWN.value)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0-100

    open_vulnerabilities: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    installed_software: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    running_services: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    security_controls: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    cloud_tags: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    ai_risk_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    last_seen: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), nullable=False)
