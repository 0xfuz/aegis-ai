"""connectors module schema

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-25
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connectors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="connected"),
        sa.Column("secret_hash", sa.String(255), nullable=False),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_connectors_org_id", "connectors", ["org_id"])

    op.create_table(
        "connector_raw_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("connector_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("investigations.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_connector_raw_events_connector_id", "connector_raw_events", ["connector_id"])


def downgrade() -> None:
    op.drop_table("connector_raw_events")
    op.drop_index("ix_connectors_org_id", table_name="connectors")
    op.drop_table("connectors")
