"""add immutable deterministic alert cluster assessments

Revision ID: 0017
Revises: 0016
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "alert_cluster_assessments",
        sa.Column("id", uuid, primary_key=True), sa.Column("org_id", uuid, nullable=False), sa.Column("cluster_id", uuid, nullable=False),
        sa.Column("scoring_version", sa.String(100), nullable=False), sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False), sa.Column("priority", sa.String(20), nullable=False), sa.Column("ledger", postgresql.JSONB(), nullable=False),
        sa.Column("reference_at", sa.DateTime(timezone=True), nullable=False), sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["cluster_id"], ["alert_clusters.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("cluster_id", "scoring_version", "input_hash", name="uq_alert_cluster_assessments_input"),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_alert_cluster_assessments_score"),
        sa.CheckConstraint("priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')", name="ck_alert_cluster_assessments_priority"),
    )
    op.create_index("ix_alert_cluster_assessments_org_id", "alert_cluster_assessments", ["org_id"])
    op.create_index("ix_alert_cluster_assessments_cluster_id", "alert_cluster_assessments", ["cluster_id"])
    op.create_index("ix_alert_cluster_assessments_cluster_evaluated", "alert_cluster_assessments", ["cluster_id", "evaluated_at"])


def downgrade():
    op.drop_table("alert_cluster_assessments")
