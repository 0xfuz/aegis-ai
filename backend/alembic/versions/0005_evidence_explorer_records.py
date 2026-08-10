"""evidence explorer records

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-29
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigation_evidence_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_investigation_evidence_records_investigation_id", "investigation_evidence_records", ["investigation_id"])
    op.create_index("ix_investigation_evidence_records_category", "investigation_evidence_records", ["category"])


def downgrade() -> None:
    op.drop_index("ix_investigation_evidence_records_category", table_name="investigation_evidence_records")
    op.drop_index("ix_investigation_evidence_records_investigation_id", table_name="investigation_evidence_records")
    op.drop_table("investigation_evidence_records")
