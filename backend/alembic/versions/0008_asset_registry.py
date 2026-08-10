"""asset registry

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-01
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("asset_type", sa.String(50), nullable=False, server_default="host"),
        sa.Column("os", sa.String(100), nullable=True),
        sa.Column("owner", sa.String(255), nullable=True),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("criticality", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("health", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("risk_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("open_vulnerabilities", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("installed_software", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("running_services", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("security_controls", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("cloud_tags", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("ai_risk_summary", sa.Text(), nullable=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("org_id", "name", name="uq_assets_org_name"),
    )
    op.create_index("ix_assets_org_id", "assets", ["org_id"])
    op.create_index("ix_assets_name", "assets", ["name"])


def downgrade() -> None:
    op.drop_index("ix_assets_name", table_name="assets")
    op.drop_index("ix_assets_org_id", table_name="assets")
    op.drop_table("assets")
