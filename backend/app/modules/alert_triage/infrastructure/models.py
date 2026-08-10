"""Immutable, connector-provenanced canonical alerts (Phase 7.1 only)."""
from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base import Base, OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class CanonicalAlert(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    """A source alert. Its original content remains in connector_raw_events."""

    __tablename__ = "canonical_alerts"
    __table_args__ = (
        UniqueConstraint("org_id", "connector_id", "source", "source_alert_id", name="uq_canonical_alerts_source_identity"),
        UniqueConstraint("raw_event_id", name="uq_canonical_alerts_raw_event"),
        CheckConstraint("severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO')", name="ck_canonical_alerts_severity"),
        CheckConstraint("lifecycle IN ('NEW', 'DEDUPLICATED', 'CORRELATED', 'PROMOTED', 'SUPPRESSED')", name="ck_canonical_alerts_lifecycle"),
        Index("ix_canonical_alerts_org_observed_at", "org_id", "observed_at"),
        Index("ix_canonical_alerts_org_lifecycle", "org_id", "lifecycle"),
    )

    connector_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("connectors.id", ondelete="RESTRICT"), nullable=False, index=True)
    raw_event_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("connector_raw_events.id", ondelete="RESTRICT"), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    source_alert_id: Mapped[str] = mapped_column(String(255), nullable=False)
    observed_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))
    rule_id: Mapped[str | None] = mapped_column(String(255))
    rule_name: Mapped[str | None] = mapped_column(String(255))
    signature: Mapped[str | None] = mapped_column(String(255))
    normalized_observables: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    source_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    normalizer_version: Mapped[str] = mapped_column(String(100), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(20), nullable=False, default="NEW")


class CanonicalAlertOccurrence(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    """Every receipt of an exact source identity, including safe replays."""

    __tablename__ = "canonical_alert_occurrences"
    __table_args__ = (
        UniqueConstraint("raw_event_id", name="uq_canonical_alert_occurrences_raw_event"),
        Index("ix_canonical_alert_occurrences_alert_received", "canonical_alert_id", "received_at"),
    )

    canonical_alert_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("canonical_alerts.id", ondelete="RESTRICT"), nullable=False, index=True)
    raw_event_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("connector_raw_events.id", ondelete="RESTRICT"), nullable=False)
    received_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    disposition: Mapped[str] = mapped_column(String(20), nullable=False)


class AlertDeduplicationDecision(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    """Append-only deterministic exact-replay or semantic-duplicate decision."""

    __tablename__ = "alert_deduplication_decisions"
    __table_args__ = (
        UniqueConstraint("org_id", "decision_version", "subject_key", name="uq_alert_dedupe_decisions_subject"),
        CheckConstraint("decision_type IN ('EXACT_REPLAY', 'SEMANTIC')", name="ck_alert_dedupe_decisions_type"),
        CheckConstraint(
            "(duplicate_alert_id IS NOT NULL AND duplicate_occurrence_id IS NULL) OR "
            "(duplicate_alert_id IS NULL AND duplicate_occurrence_id IS NOT NULL)",
            name="ck_alert_dedupe_decisions_one_subject",
        ),
        Index("ix_alert_dedupe_decisions_representative", "org_id", "representative_alert_id"),
        Index("ix_alert_dedupe_decisions_duplicate_alert", "org_id", "duplicate_alert_id"),
    )

    representative_alert_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("canonical_alerts.id", ondelete="RESTRICT"), nullable=False, index=True)
    duplicate_alert_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("canonical_alerts.id", ondelete="RESTRICT"), nullable=True)
    duplicate_occurrence_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("canonical_alert_occurrences.id", ondelete="RESTRICT"), nullable=True)
    decision_type: Mapped[str] = mapped_column(String(20), nullable=False)
    decision_version: Mapped[str] = mapped_column(String(100), nullable=False)
    subject_key: Mapped[str] = mapped_column(String(160), nullable=False)
    reasons: Mapped[list] = mapped_column(JSONB, nullable=False)
    decided_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), nullable=False)


class AlertCluster(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    """A deterministic candidate-incident container; never a FACT or verdict."""

    __tablename__ = "alert_clusters"
    __table_args__ = (
        UniqueConstraint("org_id", "correlation_version", "identity_key", name="uq_alert_clusters_identity"),
        CheckConstraint("status IN ('OPEN', 'CLOSED', 'PROMOTED')", name="ck_alert_clusters_status"),
        Index("ix_alert_clusters_org_status", "org_id", "status"),
        Index("ix_alert_clusters_org_seen", "org_id", "first_seen", "last_seen"),
    )

    identity_key: Mapped[str] = mapped_column(String(180), nullable=False)
    correlation_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    merged_into_cluster_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("alert_clusters.id", ondelete="RESTRICT"), nullable=True, index=True)
    first_seen: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), nullable=False)
    member_count: Mapped[int] = mapped_column(nullable=False, default=0)
    source_diversity: Mapped[int] = mapped_column(nullable=False, default=0)


class AlertClusterMembership(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    """Append-only alert-to-cluster placement with deterministic explanation."""

    __tablename__ = "alert_cluster_memberships"
    __table_args__ = (
        UniqueConstraint("alert_id", "correlation_version", name="uq_alert_cluster_memberships_alert_version"),
        Index("ix_alert_cluster_memberships_cluster_added", "cluster_id", "added_at"),
    )

    cluster_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("alert_clusters.id", ondelete="RESTRICT"), nullable=False, index=True)
    alert_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("canonical_alerts.id", ondelete="RESTRICT"), nullable=False)
    candidate_alert_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("canonical_alerts.id", ondelete="RESTRICT"), nullable=True)
    correlation_version: Mapped[str] = mapped_column(String(100), nullable=False)
    score: Mapped[int] = mapped_column(nullable=False)
    reasons: Mapped[list] = mapped_column(JSONB, nullable=False)
    added_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), nullable=False)


class AlertClusterMerge(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    """Immutable history for an automatic deterministic cluster merge."""

    __tablename__ = "alert_cluster_merges"
    __table_args__ = (
        UniqueConstraint("absorbed_cluster_id", name="uq_alert_cluster_merges_absorbed"),
        Index("ix_alert_cluster_merges_survivor", "org_id", "survivor_cluster_id"),
    )

    survivor_cluster_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("alert_clusters.id", ondelete="RESTRICT"), nullable=False, index=True)
    absorbed_cluster_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("alert_clusters.id", ondelete="RESTRICT"), nullable=False)
    trigger_alert_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("canonical_alerts.id", ondelete="RESTRICT"), nullable=False)
    correlation_version: Mapped[str] = mapped_column(String(100), nullable=False)
    reasons: Mapped[list] = mapped_column(JSONB, nullable=False)
    merged_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), nullable=False)


class AlertClusterAssessment(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    """Immutable, input-fingerprinted deterministic priority assessment."""

    __tablename__ = "alert_cluster_assessments"
    __table_args__ = (
        UniqueConstraint("cluster_id", "scoring_version", "input_hash", name="uq_alert_cluster_assessments_input"),
        CheckConstraint("score >= 0 AND score <= 100", name="ck_alert_cluster_assessments_score"),
        CheckConstraint("priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')", name="ck_alert_cluster_assessments_priority"),
        Index("ix_alert_cluster_assessments_cluster_evaluated", "cluster_id", "evaluated_at"),
    )

    cluster_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("alert_clusters.id", ondelete="RESTRICT"), nullable=False, index=True)
    scoring_version: Mapped[str] = mapped_column(String(100), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[int] = mapped_column(nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    ledger: Mapped[list] = mapped_column(JSONB, nullable=False)
    reference_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), nullable=False)
    evaluated_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), nullable=False)


class AlertClusterPromotion(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    """One immutable, analyst-created promotion of a root alert cluster."""

    __tablename__ = "alert_cluster_promotions"
    __table_args__ = (
        UniqueConstraint("cluster_id", name="uq_alert_cluster_promotions_cluster"),
        UniqueConstraint("investigation_id", name="uq_alert_cluster_promotions_investigation"),
        CheckConstraint("status = 'COMPLETED'", name="ck_alert_cluster_promotions_status"),
        Index("ix_alert_cluster_promotions_org_promoted", "org_id", "promoted_at"),
    )

    cluster_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("alert_clusters.id", ondelete="RESTRICT"), nullable=False)
    investigation_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="RESTRICT"), nullable=False)
    evidence_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("evidence_items.id", ondelete="RESTRICT"), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    triage_assessment_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("alert_cluster_assessments.id", ondelete="RESTRICT"), nullable=False)
    export_version: Mapped[str] = mapped_column(String(100), nullable=False)
    export_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="COMPLETED")
    promoted_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), nullable=False)
