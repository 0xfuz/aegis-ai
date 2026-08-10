"""ioc verdict, provenance, and watchlist

Adds columns to the EXISTING `iocs` table from 0006 — no new table, no
second IOC registry. Phase 4 extension: verdict classification, explicit
provenance (internal vs a future external provider), and an org-scoped
watchlist (is_watched/watched_at) directly on the indicator an analyst is
already looking at.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-06
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Plain String columns (not Postgres ENUM types) — same choice already
    # made for Asset.criticality/health in 0008, and for the same reason:
    # low-cardinality, analyst-updated classifications, not structural
    # types. This also sidesteps the enum create_type/values_callable
    # pitfalls noted elsewhere in this project's migrations (0002, 0006).
    op.add_column("iocs", sa.Column("verdict", sa.String(20), nullable=False, server_default="unknown"))
    op.add_column("iocs", sa.Column("provenance", sa.String(20), nullable=False, server_default="internal"))
    op.add_column(
        "iocs", sa.Column("is_watched", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("iocs", sa.Column("watched_at", sa.DateTime(timezone=True), nullable=True))

    # Composite index for the Watchlist tab's query (org_id + is_watched)
    # rather than a bare index on is_watched, which is a low-cardinality
    # boolean and not selective enough to be useful on its own.
    op.create_index("ix_iocs_org_watched", "iocs", ["org_id", "is_watched"])
    op.create_index("ix_iocs_org_verdict", "iocs", ["org_id", "verdict"])


def downgrade() -> None:
    op.drop_index("ix_iocs_org_verdict", table_name="iocs")
    op.drop_index("ix_iocs_org_watched", table_name="iocs")
    op.drop_column("iocs", "watched_at")
    op.drop_column("iocs", "is_watched")
    op.drop_column("iocs", "provenance")
    op.drop_column("iocs", "verdict")
