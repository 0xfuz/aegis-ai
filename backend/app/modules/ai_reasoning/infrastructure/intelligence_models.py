"""Append-only AIIE inference records. FACT models are never imported or mutated here."""
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.shared.base import Base, OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin

class IntelligenceAnalysis(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "intelligence_analyses"
    __table_args__ = (CheckConstraint("status IN ('QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED')", name="ck_intelligence_analyses_status"), Index("ix_intelligence_analyses_investigation_generated", "investigation_id", "generated_at"), Index("ix_intelligence_analyses_org_investigation_status", "org_id", "investigation_id", "status"), Index("uq_intelligence_analyses_request", "org_id", "investigation_id", "request_key", unique=True))
    investigation_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="RESTRICT"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_template_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_key: Mapped[str] = mapped_column(String(128), nullable=False)
    output_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    predecessor_analysis_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("intelligence_analyses.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    model_version: Mapped[str | None] = mapped_column(String(255))
    generation_duration_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    error_summary: Mapped[str | None] = mapped_column(Text)

class IntelligenceItem(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "intelligence_items"
    __table_args__ = (CheckConstraint("kind IN ('SUMMARY','OBSERVATION','HYPOTHESIS','RECOMMENDATION','QUESTION','REASONING','FACT','INFERENCE')", name="ck_intelligence_items_kind"), CheckConstraint("review_status IN ('PENDING','CONFIRMED','REJECTED','UNRESOLVED','SUPERSEDED')", name="ck_intelligence_items_review"), CheckConstraint("supersedes_item_id IS NULL OR supersedes_item_id <> id", name="ck_intelligence_items_not_self_superseding"), Index("ix_intelligence_items_analysis_kind", "analysis_id", "kind"), Index("ix_intelligence_items_org_investigation_supersedes", "org_id", "investigation_id", "supersedes_item_id"))
    analysis_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("intelligence_analyses.id", ondelete="RESTRICT"), nullable=False, index=True)
    investigation_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="RESTRICT"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    origin: Mapped[str] = mapped_column(String(32), nullable=False)
    supersedes_item_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("intelligence_items.id", ondelete="RESTRICT"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[int | None] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_rationale: Mapped[str | None] = mapped_column(Text)

class IntelligenceFactLink(Base, UUIDPrimaryKeyMixin, OrgScopedMixin):
    __tablename__ = "intelligence_fact_links"
    __table_args__ = (CheckConstraint("role IN ('SUPPORTS','CONTRADICTS','CONTEXT')", name="ck_intelligence_fact_links_role"), Index("ix_intelligence_fact_links_item", "item_id"))
    item_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("intelligence_items.id", ondelete="RESTRICT"), nullable=False)
    fact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    fact_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)

class IntelligenceReviewEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "intelligence_review_events"
    item_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("intelligence_items.id", ondelete="RESTRICT"), nullable=False, index=True)
    from_status: Mapped[str] = mapped_column(String(20), nullable=False)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
