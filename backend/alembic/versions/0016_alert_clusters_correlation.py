"""add deterministic alert correlation and cluster persistence

Revision ID: 0016
Revises: 0015
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "alert_clusters",
        sa.Column("id", uuid, primary_key=True), sa.Column("org_id", uuid, nullable=False),
        sa.Column("identity_key", sa.String(180), nullable=False), sa.Column("correlation_version", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"), sa.Column("merged_into_cluster_id", uuid),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False), sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("member_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("source_diversity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["merged_into_cluster_id"], ["alert_clusters.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("org_id", "correlation_version", "identity_key", name="uq_alert_clusters_identity"),
        sa.CheckConstraint("status IN ('OPEN', 'CLOSED')", name="ck_alert_clusters_status"),
    )
    op.create_index("ix_alert_clusters_org_id", "alert_clusters", ["org_id"])
    op.create_index("ix_alert_clusters_merged_into_cluster_id", "alert_clusters", ["merged_into_cluster_id"])
    op.create_index("ix_alert_clusters_org_status", "alert_clusters", ["org_id", "status"])
    op.create_index("ix_alert_clusters_org_seen", "alert_clusters", ["org_id", "first_seen", "last_seen"])
    op.create_table(
        "alert_cluster_memberships",
        sa.Column("id", uuid, primary_key=True), sa.Column("org_id", uuid, nullable=False), sa.Column("cluster_id", uuid, nullable=False),
        sa.Column("alert_id", uuid, nullable=False), sa.Column("candidate_alert_id", uuid), sa.Column("correlation_version", sa.String(100), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False), sa.Column("reasons", postgresql.JSONB(), nullable=False), sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["cluster_id"], ["alert_clusters.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["alert_id"], ["canonical_alerts.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["candidate_alert_id"], ["canonical_alerts.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("alert_id", name="uq_alert_cluster_memberships_alert"),
    )
    op.create_index("ix_alert_cluster_memberships_org_id", "alert_cluster_memberships", ["org_id"])
    op.create_index("ix_alert_cluster_memberships_cluster_id", "alert_cluster_memberships", ["cluster_id"])
    op.create_index("ix_alert_cluster_memberships_cluster_added", "alert_cluster_memberships", ["cluster_id", "added_at"])
    op.create_table(
        "alert_cluster_merges",
        sa.Column("id", uuid, primary_key=True), sa.Column("org_id", uuid, nullable=False), sa.Column("survivor_cluster_id", uuid, nullable=False), sa.Column("absorbed_cluster_id", uuid, nullable=False), sa.Column("trigger_alert_id", uuid, nullable=False),
        sa.Column("correlation_version", sa.String(100), nullable=False), sa.Column("reasons", postgresql.JSONB(), nullable=False), sa.Column("merged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["survivor_cluster_id"], ["alert_clusters.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["absorbed_cluster_id"], ["alert_clusters.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["trigger_alert_id"], ["canonical_alerts.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("absorbed_cluster_id", name="uq_alert_cluster_merges_absorbed"),
    )
    op.create_index("ix_alert_cluster_merges_org_id", "alert_cluster_merges", ["org_id"])
    op.create_index("ix_alert_cluster_merges_survivor_cluster_id", "alert_cluster_merges", ["survivor_cluster_id"])
    op.create_index("ix_alert_cluster_merges_survivor", "alert_cluster_merges", ["org_id", "survivor_cluster_id"])


def downgrade():
    op.drop_table("alert_cluster_merges")
    op.drop_table("alert_cluster_memberships")
    op.drop_table("alert_clusters")
