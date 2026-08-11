"""Append-only AIIE inference records. FACT models are never imported or mutated here."""
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
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

class IntelligenceEvidenceReference(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    """Immutable typed citation; legacy IntelligenceFactLink remains untouched."""
    __tablename__ = "intelligence_evidence_references"
    __table_args__ = (
        UniqueConstraint("analysis_id", "snapshot_alias", name="uq_intelligence_evidence_references_analysis_alias"),
        CheckConstraint("reference_type IN ('EVIDENCE_ITEM','RAW_RECORD','EVENT','ENTITY_OBSERVATION','INDICATOR_OCCURRENCE','ENTITY_RELATIONSHIP','CANONICAL_ALERT','ALERT_CLUSTER_MEMBERSHIP','ALERT_CLUSTER_ASSESSMENT','ALERT_CLUSTER_PROMOTION','FINDING','MITRE_MAPPING')", name="ck_intelligence_evidence_references_type"),
        CheckConstraint("(reference_type='EVIDENCE_ITEM' AND evidence_item_id IS NOT NULL AND raw_record_id IS NULL AND event_id IS NULL AND entity_observation_id IS NULL AND indicator_occurrence_id IS NULL AND entity_relationship_id IS NULL AND canonical_alert_id IS NULL AND alert_cluster_membership_id IS NULL AND alert_cluster_assessment_id IS NULL AND alert_cluster_promotion_id IS NULL AND finding_id IS NULL AND mitre_mapping_id IS NULL) OR (reference_type='RAW_RECORD' AND evidence_item_id IS NULL AND raw_record_id IS NOT NULL AND event_id IS NULL AND entity_observation_id IS NULL AND indicator_occurrence_id IS NULL AND entity_relationship_id IS NULL AND canonical_alert_id IS NULL AND alert_cluster_membership_id IS NULL AND alert_cluster_assessment_id IS NULL AND alert_cluster_promotion_id IS NULL AND finding_id IS NULL AND mitre_mapping_id IS NULL) OR (reference_type='EVENT' AND evidence_item_id IS NULL AND raw_record_id IS NULL AND event_id IS NOT NULL AND entity_observation_id IS NULL AND indicator_occurrence_id IS NULL AND entity_relationship_id IS NULL AND canonical_alert_id IS NULL AND alert_cluster_membership_id IS NULL AND alert_cluster_assessment_id IS NULL AND alert_cluster_promotion_id IS NULL AND finding_id IS NULL AND mitre_mapping_id IS NULL) OR (reference_type='ENTITY_OBSERVATION' AND evidence_item_id IS NULL AND raw_record_id IS NULL AND event_id IS NULL AND entity_observation_id IS NOT NULL AND indicator_occurrence_id IS NULL AND entity_relationship_id IS NULL AND canonical_alert_id IS NULL AND alert_cluster_membership_id IS NULL AND alert_cluster_assessment_id IS NULL AND alert_cluster_promotion_id IS NULL AND finding_id IS NULL AND mitre_mapping_id IS NULL) OR (reference_type='INDICATOR_OCCURRENCE' AND evidence_item_id IS NULL AND raw_record_id IS NULL AND event_id IS NULL AND entity_observation_id IS NULL AND indicator_occurrence_id IS NOT NULL AND entity_relationship_id IS NULL AND canonical_alert_id IS NULL AND alert_cluster_membership_id IS NULL AND alert_cluster_assessment_id IS NULL AND alert_cluster_promotion_id IS NULL AND finding_id IS NULL AND mitre_mapping_id IS NULL) OR (reference_type='ENTITY_RELATIONSHIP' AND evidence_item_id IS NULL AND raw_record_id IS NULL AND event_id IS NULL AND entity_observation_id IS NULL AND indicator_occurrence_id IS NULL AND entity_relationship_id IS NOT NULL AND canonical_alert_id IS NULL AND alert_cluster_membership_id IS NULL AND alert_cluster_assessment_id IS NULL AND alert_cluster_promotion_id IS NULL AND finding_id IS NULL AND mitre_mapping_id IS NULL) OR (reference_type='CANONICAL_ALERT' AND evidence_item_id IS NULL AND raw_record_id IS NULL AND event_id IS NULL AND entity_observation_id IS NULL AND indicator_occurrence_id IS NULL AND entity_relationship_id IS NULL AND canonical_alert_id IS NOT NULL AND alert_cluster_membership_id IS NULL AND alert_cluster_assessment_id IS NULL AND alert_cluster_promotion_id IS NULL AND finding_id IS NULL AND mitre_mapping_id IS NULL) OR (reference_type='ALERT_CLUSTER_MEMBERSHIP' AND evidence_item_id IS NULL AND raw_record_id IS NULL AND event_id IS NULL AND entity_observation_id IS NULL AND indicator_occurrence_id IS NULL AND entity_relationship_id IS NULL AND canonical_alert_id IS NULL AND alert_cluster_membership_id IS NOT NULL AND alert_cluster_assessment_id IS NULL AND alert_cluster_promotion_id IS NULL AND finding_id IS NULL AND mitre_mapping_id IS NULL) OR (reference_type='ALERT_CLUSTER_ASSESSMENT' AND evidence_item_id IS NULL AND raw_record_id IS NULL AND event_id IS NULL AND entity_observation_id IS NULL AND indicator_occurrence_id IS NULL AND entity_relationship_id IS NULL AND canonical_alert_id IS NULL AND alert_cluster_membership_id IS NULL AND alert_cluster_assessment_id IS NOT NULL AND alert_cluster_promotion_id IS NULL AND finding_id IS NULL AND mitre_mapping_id IS NULL) OR (reference_type='ALERT_CLUSTER_PROMOTION' AND evidence_item_id IS NULL AND raw_record_id IS NULL AND event_id IS NULL AND entity_observation_id IS NULL AND indicator_occurrence_id IS NULL AND entity_relationship_id IS NULL AND canonical_alert_id IS NULL AND alert_cluster_membership_id IS NULL AND alert_cluster_assessment_id IS NULL AND alert_cluster_promotion_id IS NOT NULL AND finding_id IS NULL AND mitre_mapping_id IS NULL) OR (reference_type='FINDING' AND evidence_item_id IS NULL AND raw_record_id IS NULL AND event_id IS NULL AND entity_observation_id IS NULL AND indicator_occurrence_id IS NULL AND entity_relationship_id IS NULL AND canonical_alert_id IS NULL AND alert_cluster_membership_id IS NULL AND alert_cluster_assessment_id IS NULL AND alert_cluster_promotion_id IS NULL AND finding_id IS NOT NULL AND mitre_mapping_id IS NULL) OR (reference_type='MITRE_MAPPING' AND evidence_item_id IS NULL AND raw_record_id IS NULL AND event_id IS NULL AND entity_observation_id IS NULL AND indicator_occurrence_id IS NULL AND entity_relationship_id IS NULL AND canonical_alert_id IS NULL AND alert_cluster_membership_id IS NULL AND alert_cluster_assessment_id IS NULL AND alert_cluster_promotion_id IS NULL AND finding_id IS NULL AND mitre_mapping_id IS NOT NULL)", name="ck_intelligence_evidence_references_pair"),
        CheckConstraint("locator_metadata IS NULL OR jsonb_typeof(locator_metadata) = 'object'", name="ck_intelligence_evidence_references_locator_object"),
        CheckConstraint("provenance_fingerprint ~ '^[0-9a-f]{64}$'", name="ck_intelligence_evidence_references_provenance_hash"),
        CheckConstraint("evidence_sha256 IS NULL OR evidence_sha256 ~ '^[0-9a-f]{64}$'", name="ck_intelligence_evidence_references_evidence_hash"),
        CheckConstraint("locator_hash IS NULL OR locator_hash ~ '^[0-9a-f]{64}$'", name="ck_intelligence_evidence_references_locator_hash"),
        Index("ix_intelligence_evidence_references_scope", "org_id", "investigation_id", "analysis_id"),
        Index("ix_intelligence_evidence_references_type", "reference_type"),
        *tuple(Index(f"uq_ier_analysis_target_{index}", "analysis_id", column, unique=True, postgresql_where=text(f"{column} IS NOT NULL")) for index,column in enumerate(("evidence_item_id","raw_record_id","event_id","entity_observation_id","indicator_occurrence_id","entity_relationship_id","canonical_alert_id","alert_cluster_membership_id","alert_cluster_assessment_id","alert_cluster_promotion_id","finding_id","mitre_mapping_id"), start=1)),
    )
    org_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    investigation_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="RESTRICT"), nullable=False, index=True)
    analysis_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("intelligence_analyses.id", ondelete="RESTRICT"), nullable=False, index=True)
    snapshot_alias: Mapped[str] = mapped_column(String(64), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(32), nullable=False)
    context_version: Mapped[str] = mapped_column(String(64), nullable=False)
    builder_version: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    provenance_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    locator_metadata: Mapped[dict | None] = mapped_column(JSONB)
    locator_hash: Mapped[str | None] = mapped_column(String(64))
    producer_name: Mapped[str | None] = mapped_column(String(100))
    producer_version: Mapped[str | None] = mapped_column(String(100))
    evidence_sha256: Mapped[str | None] = mapped_column(String(64))
    evidence_item_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("evidence_items.id", ondelete="RESTRICT"), index=True)
    raw_record_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("raw_records.id", ondelete="RESTRICT"), index=True)
    event_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("events.id", ondelete="RESTRICT"), index=True)
    entity_observation_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("entity_observations.id", ondelete="RESTRICT"), index=True)
    indicator_occurrence_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("indicator_occurrences.id", ondelete="RESTRICT"), index=True)
    entity_relationship_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("entity_relationships.id", ondelete="RESTRICT"), index=True)
    canonical_alert_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("canonical_alerts.id", ondelete="RESTRICT"), index=True)
    alert_cluster_membership_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("alert_cluster_memberships.id", ondelete="RESTRICT"), index=True)
    alert_cluster_assessment_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("alert_cluster_assessments.id", ondelete="RESTRICT"), index=True)
    alert_cluster_promotion_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("alert_cluster_promotions.id", ondelete="RESTRICT"), index=True)
    finding_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("findings.id", ondelete="RESTRICT"), index=True)
    mitre_mapping_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("mitre_mappings.id", ondelete="RESTRICT"), index=True)

class IntelligenceClaimEvidenceLink(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "intelligence_claim_evidence_links"
    __table_args__ = (UniqueConstraint("item_id", "evidence_reference_id", "role", name="uq_intelligence_claim_evidence_links_item_reference_role"), CheckConstraint("role IN ('SUPPORTS','CONTRADICTS','CONTEXT')", name="ck_intelligence_claim_evidence_links_role"), Index("ix_intelligence_claim_evidence_links_scope", "org_id", "investigation_id"))
    org_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    investigation_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="RESTRICT"), nullable=False, index=True)
    item_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("intelligence_items.id", ondelete="RESTRICT"), nullable=False, index=True)
    evidence_reference_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("intelligence_evidence_references.id", ondelete="RESTRICT"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)

class IntelligenceReviewEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "intelligence_review_events"
    item_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("intelligence_items.id", ondelete="RESTRICT"), nullable=False, index=True)
    from_status: Mapped[str] = mapped_column(String(20), nullable=False)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
