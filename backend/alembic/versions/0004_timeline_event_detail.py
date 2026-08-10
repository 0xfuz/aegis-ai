"""timeline event forensic detail

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-26
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# create_type=False: the 'severity' enum type already exists (created in
# 0001... actually 0002) — this migration only adds a column that
# references it, it must not try to CREATE TYPE a second time.
severity_enum = postgresql.ENUM(
    "critical", "high", "medium", "low", "info", name="severity", create_type=False
)


def upgrade() -> None:
    op.add_column("investigation_timeline_events", sa.Column("severity", severity_enum, nullable=True))
    op.add_column("investigation_timeline_events", sa.Column("mitre_technique", sa.String(20), nullable=True))
    op.add_column("investigation_timeline_events", sa.Column("source", sa.String(100), nullable=True))
    op.add_column("investigation_timeline_events", sa.Column("affected_asset", sa.String(255), nullable=True))
    op.add_column("investigation_timeline_events", sa.Column("actor", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("investigation_timeline_events", "actor")
    op.drop_column("investigation_timeline_events", "affected_asset")
    op.drop_column("investigation_timeline_events", "source")
    op.drop_column("investigation_timeline_events", "mitre_technique")
    op.drop_column("investigation_timeline_events", "severity")
