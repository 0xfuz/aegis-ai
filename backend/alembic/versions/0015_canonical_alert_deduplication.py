"""add auditable canonical alert deduplication decisions

Revision ID: 0015
Revises: 0014
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "alert_deduplication_decisions",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("org_id", uuid, nullable=False),
        sa.Column("representative_alert_id", uuid, nullable=False),
        sa.Column("duplicate_alert_id", uuid),
        sa.Column("duplicate_occurrence_id", uuid),
        sa.Column("decision_type", sa.String(20), nullable=False),
        sa.Column("decision_version", sa.String(100), nullable=False),
        sa.Column("subject_key", sa.String(160), nullable=False),
        sa.Column("reasons", postgresql.JSONB(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["representative_alert_id"], ["canonical_alerts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["duplicate_alert_id"], ["canonical_alerts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["duplicate_occurrence_id"], ["canonical_alert_occurrences.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("org_id", "decision_version", "subject_key", name="uq_alert_dedupe_decisions_subject"),
        sa.CheckConstraint("decision_type IN ('EXACT_REPLAY', 'SEMANTIC')", name="ck_alert_dedupe_decisions_type"),
        sa.CheckConstraint("(duplicate_alert_id IS NOT NULL AND duplicate_occurrence_id IS NULL) OR (duplicate_alert_id IS NULL AND duplicate_occurrence_id IS NOT NULL)", name="ck_alert_dedupe_decisions_one_subject"),
    )
    op.create_index("ix_alert_deduplication_decisions_org_id", "alert_deduplication_decisions", ["org_id"])
    op.create_index("ix_alert_deduplication_decisions_representative_alert_id", "alert_deduplication_decisions", ["representative_alert_id"])
    op.create_index("ix_alert_dedupe_decisions_representative", "alert_deduplication_decisions", ["org_id", "representative_alert_id"])
    op.create_index("ix_alert_dedupe_decisions_duplicate_alert", "alert_deduplication_decisions", ["org_id", "duplicate_alert_id"])


def downgrade():
    op.drop_table("alert_deduplication_decisions")
