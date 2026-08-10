"""add immutable canonical alert foundation

Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "canonical_alerts",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("org_id", uuid, nullable=False),
        sa.Column("connector_id", uuid, nullable=False),
        sa.Column("raw_event_id", uuid, nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("source_alert_id", sa.String(255), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("category", sa.String(100)),
        sa.Column("rule_id", sa.String(255)),
        sa.Column("rule_name", sa.String(255)),
        sa.Column("signature", sa.String(255)),
        sa.Column("normalized_observables", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source_metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("normalizer_version", sa.String(100), nullable=False),
        sa.Column("lifecycle", sa.String(20), nullable=False, server_default="NEW"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["connector_id"], ["connectors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["raw_event_id"], ["connector_raw_events.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("org_id", "connector_id", "source", "source_alert_id", name="uq_canonical_alerts_source_identity"),
        sa.UniqueConstraint("raw_event_id", name="uq_canonical_alerts_raw_event"),
        sa.CheckConstraint("severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO')", name="ck_canonical_alerts_severity"),
        sa.CheckConstraint("lifecycle IN ('NEW', 'DEDUPLICATED', 'CORRELATED', 'PROMOTED', 'SUPPRESSED')", name="ck_canonical_alerts_lifecycle"),
    )
    op.create_index("ix_canonical_alerts_org_id", "canonical_alerts", ["org_id"])
    op.create_index("ix_canonical_alerts_connector_id", "canonical_alerts", ["connector_id"])
    op.create_index("ix_canonical_alerts_org_observed_at", "canonical_alerts", ["org_id", "observed_at"])
    op.create_index("ix_canonical_alerts_org_lifecycle", "canonical_alerts", ["org_id", "lifecycle"])
    op.create_table(
        "canonical_alert_occurrences",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("org_id", uuid, nullable=False),
        sa.Column("canonical_alert_id", uuid, nullable=False),
        sa.Column("raw_event_id", uuid, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("disposition", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["canonical_alert_id"], ["canonical_alerts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["raw_event_id"], ["connector_raw_events.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("raw_event_id", name="uq_canonical_alert_occurrences_raw_event"),
    )
    op.create_index("ix_canonical_alert_occurrences_org_id", "canonical_alert_occurrences", ["org_id"])
    op.create_index("ix_canonical_alert_occurrences_canonical_alert_id", "canonical_alert_occurrences", ["canonical_alert_id"])
    op.create_index("ix_canonical_alert_occurrences_alert_received", "canonical_alert_occurrences", ["canonical_alert_id", "received_at"])


def downgrade():
    op.drop_table("canonical_alert_occurrences")
    op.drop_table("canonical_alerts")
