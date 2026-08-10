"""Additive canonical FACT and audit models.

These models intentionally have no API/service integration in Phase 1. Foreign
keys use RESTRICT rather than cascade deletion so evidence provenance cannot be
silently erased by deleting an investigation or a parent factual record.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base import Base, OrgScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


PARSE_STATUSES = ("pending", "parsing", "complete", "failed", "rejected")


class EvidenceItem(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "evidence_items"
    __table_args__ = (
        UniqueConstraint("investigation_id", "sha256", name="uq_evidence_items_investigation_sha256"),
        UniqueConstraint("storage_key", name="uq_evidence_items_storage_key"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_evidence_items_sha256_lower_hex"),
        CheckConstraint("byte_size >= 0", name="ck_evidence_items_byte_size_nonnegative"),
        Index("ix_evidence_items_investigation_imported_at", "investigation_id", "imported_at"),
    )

    investigation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(1024), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    detected_mime: Mapped[str] = mapped_column(String(255), nullable=False)
    extension: Mapped[str] = mapped_column(String(32), nullable=False)
    source_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    acquisition_source: Mapped[str] = mapped_column(String(100), nullable=False)
    imported_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    parsing_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    investigation = relationship("Investigation")
    imported_by = relationship("User")
    parse_runs: Mapped[list["EvidenceParseRun"]] = relationship(back_populates="evidence_item")
    raw_records: Mapped[list["RawRecord"]] = relationship(back_populates="evidence_item")
    events: Mapped[list["Event"]] = relationship(back_populates="evidence_item")
    indicator_occurrences: Mapped[list["IndicatorOccurrence"]] = relationship(back_populates="evidence_item")
    entity_observations: Mapped[list["EntityObservation"]] = relationship(back_populates="evidence_item")


class EvidenceParseRun(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "evidence_parse_runs"
    __table_args__ = (
        UniqueConstraint(
            "evidence_id", "parser_name", "parser_version", "run_sequence",
            name="uq_evidence_parse_runs_evidence_parser_sequence",
        ),
        CheckConstraint(
            "status IN ('pending', 'parsing', 'complete', 'failed', 'rejected')",
            name="ck_evidence_parse_runs_status",
        ),
        Index("ix_evidence_parse_runs_evidence_started_at", "evidence_id", "started_at"),
        Index("ix_evidence_parse_runs_status", "status"),
    )

    evidence_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("evidence_items.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    parser_name: Mapped[str] = mapped_column(String(100), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(100), nullable=False)
    run_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    warnings: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)

    evidence_item: Mapped["EvidenceItem"] = relationship(back_populates="parse_runs")
    raw_records: Mapped[list["RawRecord"]] = relationship(back_populates="parse_run")


class RawRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "raw_records"
    __table_args__ = (
        UniqueConstraint("parse_run_id", "ordinal", name="uq_raw_records_parse_run_ordinal"),
        CheckConstraint(
            "content IS NOT NULL OR content_locator IS NOT NULL", name="ck_raw_records_content_or_locator"
        ),
        Index("ix_raw_records_evidence_parse_run_ordinal", "evidence_id", "parse_run_id", "ordinal"),
    )

    evidence_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("evidence_items.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    parse_run_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("evidence_parse_runs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_locator: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_offset: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    encoding: Mapped[str | None] = mapped_column(String(64), nullable=True)

    evidence_item: Mapped["EvidenceItem"] = relationship(back_populates="raw_records")
    parse_run: Mapped["EvidenceParseRun"] = relationship(back_populates="raw_records")
    events: Mapped[list["Event"]] = relationship(back_populates="raw_record")
    indicator_occurrences: Mapped[list["IndicatorOccurrence"]] = relationship(back_populates="raw_record")
    entity_observations: Mapped[list["EntityObservation"]] = relationship(back_populates="raw_record")


class Event(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint(
            "raw_record_id", "normalizer_name", "normalizer_version", "ordinal",
            name="uq_events_raw_record_normalizer_ordinal",
        ),
        Index("ix_events_investigation_timestamp", "investigation_id", "timestamp"),
        Index("ix_events_investigation_event_type", "investigation_id", "event_type"),
        Index("ix_events_investigation_host", "investigation_id", "host"),
        Index("ix_events_investigation_user", "investigation_id", "user"),
    )

    investigation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("evidence_items.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    raw_record_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("raw_records.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    normalizer_name: Mapped[str] = mapped_column(String(100), nullable=False)
    normalizer_version: Mapped[str] = mapped_column(String(100), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user: Mapped[str | None] = mapped_column(String(255), nullable=True)
    process: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_ip: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    destination_ip: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    destination_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    action: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deterministic_severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    normalized: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    investigation = relationship("Investigation")
    evidence_item: Mapped["EvidenceItem"] = relationship(back_populates="events")
    raw_record: Mapped["RawRecord"] = relationship(back_populates="events")
    indicator_occurrences: Mapped[list["IndicatorOccurrence"]] = relationship(back_populates="event")
    entity_observations: Mapped[list["EntityObservation"]] = relationship(back_populates="event")


class Indicator(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "indicators"
    __table_args__ = (
        UniqueConstraint("org_id", "type", "normalized_value", name="uq_indicators_org_type_normalized_value"),
        Index("ix_indicators_org_normalized_value", "org_id", "normalized_value"),
    )

    type: Mapped[str] = mapped_column(String(50), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(2048), nullable=False)
    display_value: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    occurrences: Mapped[list["IndicatorOccurrence"]] = relationship(back_populates="indicator")


class IndicatorOccurrence(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "indicator_occurrences"
    __table_args__ = (
        UniqueConstraint(
            "indicator_id", "raw_record_id", "extractor_name", "extractor_version", "occurrence_ordinal",
            name="uq_indicator_occurrences_indicator_record_extractor_ordinal",
        ),
        Index("ix_indicator_occurrences_investigation_observed_at", "investigation_id", "observed_at"),
    )

    investigation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    indicator_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("indicators.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("evidence_items.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    raw_record_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("raw_records.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("events.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    extractor_name: Mapped[str] = mapped_column(String(100), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(100), nullable=False)
    occurrence_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_locator: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    investigation = relationship("Investigation")
    indicator: Mapped["Indicator"] = relationship(back_populates="occurrences")
    evidence_item: Mapped["EvidenceItem"] = relationship(back_populates="indicator_occurrences")
    raw_record: Mapped["RawRecord"] = relationship(back_populates="indicator_occurrences")
    event: Mapped["Event | None"] = relationship(back_populates="indicator_occurrences")


class Entity(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "entities"
    __table_args__ = (
        UniqueConstraint("investigation_id", "type", "canonical_value", name="uq_entities_investigation_type_canonical"),
        Index("ix_entities_investigation_type_canonical", "investigation_id", "type", "canonical_value"),
    )

    investigation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    canonical_value: Mapped[str] = mapped_column(String(2048), nullable=False)
    display_name: Mapped[str] = mapped_column(String(2048), nullable=False)
    attributes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    investigation = relationship("Investigation")
    observations: Mapped[list["EntityObservation"]] = relationship(back_populates="entity")
    outgoing_relationships: Mapped[list["EntityRelationship"]] = relationship(
        back_populates="source_entity", foreign_keys="EntityRelationship.source_entity_id"
    )
    incoming_relationships: Mapped[list["EntityRelationship"]] = relationship(
        back_populates="target_entity", foreign_keys="EntityRelationship.target_entity_id"
    )


class EntityObservation(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "entity_observations"
    __table_args__ = (
        UniqueConstraint(
            "entity_id", "raw_record_id", "extractor_name", "extractor_version", "occurrence_ordinal",
            name="uq_entity_observations_entity_record_extractor_ordinal",
        ),
        Index("ix_entity_observations_investigation_observed_at", "investigation_id", "observed_at"),
    )

    investigation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("entities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("evidence_items.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    raw_record_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("raw_records.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("events.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    extractor_name: Mapped[str] = mapped_column(String(100), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(100), nullable=False)
    occurrence_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_locator: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    investigation = relationship("Investigation")
    entity: Mapped["Entity"] = relationship(back_populates="observations")
    evidence_item: Mapped["EvidenceItem"] = relationship(back_populates="entity_observations")
    raw_record: Mapped["RawRecord"] = relationship(back_populates="entity_observations")
    event: Mapped["Event | None"] = relationship(back_populates="entity_observations")


class EntityRelationship(Base, UUIDPrimaryKeyMixin, TimestampMixin, OrgScopedMixin):
    __tablename__ = "entity_relationships"
    __table_args__ = (
        CheckConstraint("source_entity_id <> target_entity_id", name="ck_entity_relationships_distinct_entities"),
        CheckConstraint(
            "evidence_id IS NOT NULL OR raw_record_id IS NOT NULL OR event_id IS NOT NULL "
            "OR source_observation_id IS NOT NULL OR target_observation_id IS NOT NULL",
            name="ck_entity_relationships_has_factual_support",
        ),
        UniqueConstraint(
            "source_entity_id", "target_entity_id", "relationship_type", "derivation_name",
            "derivation_version", "source_locator_hash",
            name="uq_entity_relationships_derivation_locator",
        ),
        Index("ix_entity_relationships_investigation_source", "investigation_id", "source_entity_id"),
        Index("ix_entity_relationships_investigation_target", "investigation_id", "target_entity_id"),
        Index("ix_entity_relationships_observed_at", "observed_at"),
    )

    investigation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_entity_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("entities.id", ondelete="RESTRICT"), nullable=False
    )
    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("entities.id", ondelete="RESTRICT"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String(100), nullable=False)
    derivation_name: Mapped[str] = mapped_column(String(100), nullable=False)
    derivation_version: Mapped[str] = mapped_column(String(100), nullable=False)
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("evidence_items.id", ondelete="RESTRICT"), nullable=True
    )
    raw_record_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("raw_records.id", ondelete="RESTRICT"), nullable=True
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("events.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    source_observation_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("entity_observations.id", ondelete="RESTRICT"), nullable=True
    )
    target_observation_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("entity_observations.id", ondelete="RESTRICT"), nullable=True
    )
    source_locator: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_locator_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    investigation = relationship("Investigation")
    source_entity: Mapped["Entity"] = relationship(
        back_populates="outgoing_relationships", foreign_keys=[source_entity_id]
    )
    target_entity: Mapped["Entity"] = relationship(
        back_populates="incoming_relationships", foreign_keys=[target_entity_id]
    )
    evidence_item = relationship("EvidenceItem", foreign_keys=[evidence_id])
    raw_record = relationship("RawRecord", foreign_keys=[raw_record_id])
    event = relationship("Event", foreign_keys=[event_id])
    source_observation = relationship("EntityObservation", foreign_keys=[source_observation_id])
    target_observation = relationship("EntityObservation", foreign_keys=[target_observation_id])


class AuditEvent(Base, UUIDPrimaryKeyMixin, OrgScopedMixin):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_org_occurred_at", "org_id", "occurred_at"),
        Index("ix_audit_events_investigation_occurred_at", "investigation_id", "occurred_at"),
        Index("ix_audit_events_target", "target_type", "target_id"),
    )

    investigation_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_type: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    investigation = relationship("Investigation")
    actor = relationship("User")
