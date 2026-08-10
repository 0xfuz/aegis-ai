"""add immutable analyst-controlled alert cluster promotions

Revision ID: 0018
Revises: 0017
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    uuid = postgresql.UUID(as_uuid=True)
    op.drop_constraint("ck_alert_clusters_status", "alert_clusters", type_="check")
    op.create_check_constraint("ck_alert_clusters_status", "alert_clusters", "status IN ('OPEN', 'CLOSED', 'PROMOTED')")
    op.create_table(
        "alert_cluster_promotions",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("org_id", uuid, nullable=False),
        sa.Column("cluster_id", uuid, nullable=False), sa.Column("investigation_id", uuid, nullable=False),
        sa.Column("evidence_id", uuid, nullable=False), sa.Column("actor_id", uuid, nullable=False),
        sa.Column("triage_assessment_id", uuid, nullable=False),
        sa.Column("export_version", sa.String(100), nullable=False), sa.Column("export_fingerprint", sa.String(64), nullable=False),
        sa.Column("manifest", postgresql.JSONB(), nullable=False), sa.Column("status", sa.String(20), nullable=False, server_default="COMPLETED"),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["cluster_id"], ["alert_clusters.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["investigation_id"], ["investigations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["triage_assessment_id"], ["alert_cluster_assessments.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("cluster_id", name="uq_alert_cluster_promotions_cluster"),
        sa.UniqueConstraint("investigation_id", name="uq_alert_cluster_promotions_investigation"),
        sa.CheckConstraint("status = 'COMPLETED'", name="ck_alert_cluster_promotions_status"),
    )
    op.create_index("ix_alert_cluster_promotions_org_id", "alert_cluster_promotions", ["org_id"])
    op.create_index("ix_alert_cluster_promotions_org_promoted", "alert_cluster_promotions", ["org_id", "promoted_at"])


def downgrade():
    op.drop_table("alert_cluster_promotions")
    op.drop_constraint("ck_alert_clusters_status", "alert_clusters", type_="check")
    op.create_check_constraint("ck_alert_clusters_status", "alert_clusters", "status IN ('OPEN', 'CLOSED')")
