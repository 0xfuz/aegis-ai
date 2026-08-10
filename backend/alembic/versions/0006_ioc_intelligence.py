"""ioc intelligence registry

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-29
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

# create_type=False: 'evidence_type' already exists (created in 0002) —
# this migration only adds a column referencing it, must not recreate it.
evidence_type_enum = postgresql.ENUM(
    "ip", "hash", "domain", "url", "asset", name="evidence_type", create_type=False
)


def upgrade() -> None:
    op.create_table(
        "iocs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", evidence_type_enum, nullable=False),
        sa.Column("value", sa.String(255), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.String(50)), nullable=False, server_default="{}"),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("enrichment", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sightings_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("org_id", "type", "value", name="uq_iocs_org_type_value"),
    )
    op.create_index("ix_iocs_org_id", "iocs", ["org_id"])
    op.create_index("ix_iocs_value", "iocs", ["value"])


def downgrade() -> None:
    op.drop_index("ix_iocs_value", table_name="iocs")
    op.drop_index("ix_iocs_org_id", table_name="iocs")
    op.drop_table("iocs")
