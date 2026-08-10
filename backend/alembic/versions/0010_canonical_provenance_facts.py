"""add canonical provenance fact tables

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-07

This revision is additive. All foreign keys intentionally use RESTRICT so
canonical evidence-derived facts cannot be cascade-deleted with an
investigation or parent fact.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "evidence_items",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("org_id", _uuid(), nullable=False),
        sa.Column("investigation_id", _uuid(), nullable=False),
        sa.Column("original_filename", sa.String(1024), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("detected_mime", sa.String(255), nullable=False),
        sa.Column("extension", sa.String(32), nullable=False),
        sa.Column("source_description", sa.Text(), nullable=False, server_default=""),
        sa.Column("acquisition_source", sa.String(100), nullable=False),
        sa.Column("imported_by_id", _uuid(), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("parsing_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["imported_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("investigation_id", "sha256", name="uq_evidence_items_investigation_sha256"),
        sa.UniqueConstraint("storage_key", name="uq_evidence_items_storage_key"),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_evidence_items_sha256_lower_hex"),
        sa.CheckConstraint("byte_size >= 0", name="ck_evidence_items_byte_size_nonnegative"),
    )
    op.create_index("ix_evidence_items_org_id", "evidence_items", ["org_id"])
    op.create_index("ix_evidence_items_investigation_id", "evidence_items", ["investigation_id"])
    op.create_index("ix_evidence_items_storage_key", "evidence_items", ["storage_key"])
    op.create_index("ix_evidence_items_sha256", "evidence_items", ["sha256"])
    op.create_index("ix_evidence_items_investigation_imported_at", "evidence_items", ["investigation_id", "imported_at"])

    op.create_table(
        "evidence_parse_runs",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("org_id", _uuid(), nullable=False),
        sa.Column("evidence_id", _uuid(), nullable=False),
        sa.Column("parser_name", sa.String(100), nullable=False),
        sa.Column("parser_version", sa.String(100), nullable=False),
        sa.Column("run_sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("warnings", postgresql.JSONB(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("config_fingerprint", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("evidence_id", "parser_name", "parser_version", "run_sequence", name="uq_evidence_parse_runs_evidence_parser_sequence"),
        sa.CheckConstraint("status IN ('pending', 'parsing', 'complete', 'failed', 'rejected')", name="ck_evidence_parse_runs_status"),
    )
    op.create_index("ix_evidence_parse_runs_org_id", "evidence_parse_runs", ["org_id"])
    op.create_index("ix_evidence_parse_runs_evidence_id", "evidence_parse_runs", ["evidence_id"])
    op.create_index("ix_evidence_parse_runs_evidence_started_at", "evidence_parse_runs", ["evidence_id", "started_at"])
    op.create_index("ix_evidence_parse_runs_status", "evidence_parse_runs", ["status"])

    op.create_table(
        "raw_records",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("org_id", _uuid(), nullable=False),
        sa.Column("evidence_id", _uuid(), nullable=False),
        sa.Column("parse_run_id", _uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("content_locator", postgresql.JSONB(), nullable=True),
        sa.Column("content_type", sa.String(255), nullable=False),
        sa.Column("byte_offset", sa.BigInteger(), nullable=True),
        sa.Column("line_start", sa.Integer(), nullable=True),
        sa.Column("line_end", sa.Integer(), nullable=True),
        sa.Column("encoding", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parse_run_id"], ["evidence_parse_runs.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("parse_run_id", "ordinal", name="uq_raw_records_parse_run_ordinal"),
        sa.CheckConstraint("content IS NOT NULL OR content_locator IS NOT NULL", name="ck_raw_records_content_or_locator"),
    )
    op.create_index("ix_raw_records_org_id", "raw_records", ["org_id"])
    op.create_index("ix_raw_records_evidence_id", "raw_records", ["evidence_id"])
    op.create_index("ix_raw_records_parse_run_id", "raw_records", ["parse_run_id"])
    op.create_index("ix_raw_records_evidence_parse_run_ordinal", "raw_records", ["evidence_id", "parse_run_id", "ordinal"])

    op.create_table(
        "events",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("org_id", _uuid(), nullable=False),
        sa.Column("investigation_id", _uuid(), nullable=False),
        sa.Column("evidence_id", _uuid(), nullable=False),
        sa.Column("raw_record_id", _uuid(), nullable=False),
        sa.Column("normalizer_name", sa.String(100), nullable=False),
        sa.Column("normalizer_version", sa.String(100), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("host", sa.String(255), nullable=True),
        sa.Column("user", sa.String(255), nullable=True),
        sa.Column("process", sa.String(1024), nullable=True),
        sa.Column("source_ip", sa.String(64), nullable=True),
        sa.Column("destination_ip", sa.String(64), nullable=True),
        sa.Column("source_port", sa.Integer(), nullable=True),
        sa.Column("destination_port", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(100), nullable=True),
        sa.Column("action", sa.String(255), nullable=True),
        sa.Column("deterministic_severity", sa.String(20), nullable=True),
        sa.Column("normalized", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["raw_record_id"], ["raw_records.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("raw_record_id", "normalizer_name", "normalizer_version", "ordinal", name="uq_events_raw_record_normalizer_ordinal"),
    )
    for name, columns in (
        ("ix_events_org_id", ["org_id"]), ("ix_events_investigation_id", ["investigation_id"]),
        ("ix_events_evidence_id", ["evidence_id"]), ("ix_events_raw_record_id", ["raw_record_id"]),
        ("ix_events_source_ip", ["source_ip"]), ("ix_events_destination_ip", ["destination_ip"]),
        ("ix_events_investigation_timestamp", ["investigation_id", "timestamp"]),
        ("ix_events_investigation_event_type", ["investigation_id", "event_type"]),
        ("ix_events_investigation_host", ["investigation_id", "host"]),
        ("ix_events_investigation_user", ["investigation_id", "user"]),
    ):
        op.create_index(name, "events", columns)

    op.create_table(
        "indicators",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("org_id", _uuid(), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("normalized_value", sa.String(2048), nullable=False),
        sa.Column("display_value", sa.String(2048), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("org_id", "type", "normalized_value", name="uq_indicators_org_type_normalized_value"),
    )
    op.create_index("ix_indicators_org_id", "indicators", ["org_id"])
    op.create_index("ix_indicators_org_normalized_value", "indicators", ["org_id", "normalized_value"])

    op.create_table(
        "entities",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("org_id", _uuid(), nullable=False),
        sa.Column("investigation_id", _uuid(), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("canonical_value", sa.String(2048), nullable=False),
        sa.Column("display_name", sa.String(2048), nullable=False),
        sa.Column("attributes", postgresql.JSONB(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("investigation_id", "type", "canonical_value", name="uq_entities_investigation_type_canonical"),
    )
    op.create_index("ix_entities_org_id", "entities", ["org_id"])
    op.create_index("ix_entities_investigation_id", "entities", ["investigation_id"])
    op.create_index("ix_entities_investigation_type_canonical", "entities", ["investigation_id", "type", "canonical_value"])

    op.create_table(
        "indicator_occurrences",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("org_id", _uuid(), nullable=False),
        sa.Column("investigation_id", _uuid(), nullable=False),
        sa.Column("indicator_id", _uuid(), nullable=False),
        sa.Column("evidence_id", _uuid(), nullable=False),
        sa.Column("raw_record_id", _uuid(), nullable=False),
        sa.Column("event_id", _uuid(), nullable=True),
        sa.Column("extractor_name", sa.String(100), nullable=False),
        sa.Column("extractor_version", sa.String(100), nullable=False),
        sa.Column("occurrence_ordinal", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_locator", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["indicator_id"], ["indicators.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["raw_record_id"], ["raw_records.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("indicator_id", "raw_record_id", "extractor_name", "extractor_version", "occurrence_ordinal", name="uq_indicator_occurrences_indicator_record_extractor_ordinal"),
    )
    for name, columns in (
        ("ix_indicator_occurrences_org_id", ["org_id"]), ("ix_indicator_occurrences_investigation_id", ["investigation_id"]),
        ("ix_indicator_occurrences_indicator_id", ["indicator_id"]), ("ix_indicator_occurrences_evidence_id", ["evidence_id"]),
        ("ix_indicator_occurrences_raw_record_id", ["raw_record_id"]), ("ix_indicator_occurrences_event_id", ["event_id"]),
        ("ix_indicator_occurrences_investigation_observed_at", ["investigation_id", "observed_at"]),
    ):
        op.create_index(name, "indicator_occurrences", columns)

    op.create_table(
        "entity_observations",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("org_id", _uuid(), nullable=False),
        sa.Column("investigation_id", _uuid(), nullable=False),
        sa.Column("entity_id", _uuid(), nullable=False),
        sa.Column("evidence_id", _uuid(), nullable=False),
        sa.Column("raw_record_id", _uuid(), nullable=False),
        sa.Column("event_id", _uuid(), nullable=True),
        sa.Column("extractor_name", sa.String(100), nullable=False),
        sa.Column("extractor_version", sa.String(100), nullable=False),
        sa.Column("occurrence_ordinal", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_locator", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["raw_record_id"], ["raw_records.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("entity_id", "raw_record_id", "extractor_name", "extractor_version", "occurrence_ordinal", name="uq_entity_observations_entity_record_extractor_ordinal"),
    )
    for name, columns in (
        ("ix_entity_observations_org_id", ["org_id"]), ("ix_entity_observations_investigation_id", ["investigation_id"]),
        ("ix_entity_observations_entity_id", ["entity_id"]), ("ix_entity_observations_evidence_id", ["evidence_id"]),
        ("ix_entity_observations_raw_record_id", ["raw_record_id"]), ("ix_entity_observations_event_id", ["event_id"]),
        ("ix_entity_observations_investigation_observed_at", ["investigation_id", "observed_at"]),
    ):
        op.create_index(name, "entity_observations", columns)

    op.create_table(
        "entity_relationships",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("org_id", _uuid(), nullable=False),
        sa.Column("investigation_id", _uuid(), nullable=False),
        sa.Column("source_entity_id", _uuid(), nullable=False),
        sa.Column("target_entity_id", _uuid(), nullable=False),
        sa.Column("relationship_type", sa.String(100), nullable=False),
        sa.Column("derivation_name", sa.String(100), nullable=False),
        sa.Column("derivation_version", sa.String(100), nullable=False),
        sa.Column("evidence_id", _uuid(), nullable=True),
        sa.Column("raw_record_id", _uuid(), nullable=True),
        sa.Column("event_id", _uuid(), nullable=True),
        sa.Column("source_observation_id", _uuid(), nullable=True),
        sa.Column("target_observation_id", _uuid(), nullable=True),
        sa.Column("source_locator", postgresql.JSONB(), nullable=True),
        sa.Column("source_locator_hash", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_entity_id"], ["entities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["target_entity_id"], ["entities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["raw_record_id"], ["raw_records.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_observation_id"], ["entity_observations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["target_observation_id"], ["entity_observations.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("source_entity_id <> target_entity_id", name="ck_entity_relationships_distinct_entities"),
        sa.CheckConstraint("evidence_id IS NOT NULL OR raw_record_id IS NOT NULL OR event_id IS NOT NULL OR source_observation_id IS NOT NULL OR target_observation_id IS NOT NULL", name="ck_entity_relationships_has_factual_support"),
        sa.UniqueConstraint("source_entity_id", "target_entity_id", "relationship_type", "derivation_name", "derivation_version", "source_locator_hash", name="uq_entity_relationships_derivation_locator"),
    )
    for name, columns in (
        ("ix_entity_relationships_org_id", ["org_id"]), ("ix_entity_relationships_investigation_id", ["investigation_id"]),
        ("ix_entity_relationships_event_id", ["event_id"]),
        ("ix_entity_relationships_investigation_source", ["investigation_id", "source_entity_id"]),
        ("ix_entity_relationships_investigation_target", ["investigation_id", "target_entity_id"]),
        ("ix_entity_relationships_observed_at", ["observed_at"]),
    ):
        op.create_index(name, "entity_relationships", columns)

    op.create_table(
        "audit_events",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("org_id", _uuid(), nullable=False),
        sa.Column("investigation_id", _uuid(), nullable=True),
        sa.Column("actor_id", _uuid(), nullable=True),
        sa.Column("actor_type", sa.String(50), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(100), nullable=False),
        sa.Column("target_id", _uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("correlation_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_audit_events_org_id", "audit_events", ["org_id"])
    op.create_index("ix_audit_events_investigation_id", "audit_events", ["investigation_id"])
    op.create_index("ix_audit_events_org_occurred_at", "audit_events", ["org_id", "occurred_at"])
    op.create_index("ix_audit_events_investigation_occurred_at", "audit_events", ["investigation_id", "occurred_at"])
    op.create_index("ix_audit_events_target", "audit_events", ["target_type", "target_id"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("entity_relationships")
    op.drop_table("entity_observations")
    op.drop_table("indicator_occurrences")
    op.drop_table("entities")
    op.drop_table("indicators")
    op.drop_table("events")
    op.drop_table("raw_records")
    op.drop_table("evidence_parse_runs")
    op.drop_table("evidence_items")
