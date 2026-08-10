"""investigations module schema

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-24
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

severity_enum = postgresql.ENUM(
    "critical", "high", "medium", "low", "info", name="severity", create_type=False
)
status_enum = postgresql.ENUM(
    "new", "triaging", "investigating", "contained", "resolved", name="investigation_status", create_type=False
)
evidence_type_enum = postgresql.ENUM(
    "ip", "hash", "domain", "url", "asset", name="evidence_type", create_type=False
)
action_status_enum = postgresql.ENUM(
    "pending", "approved", "dismissed", name="action_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    severity_enum.create(bind, checkfirst=True)
    status_enum.create(bind, checkfirst=True)
    evidence_type_enum.create(bind, checkfirst=True)
    action_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "investigations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("source", sa.String(100), nullable=False, server_default="Mock Data"),
        sa.Column("severity", severity_enum, nullable=False),
        sa.Column("status", status_enum, nullable=False, server_default="new"),
        sa.Column("assignee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("root_cause", sa.Text(), nullable=False, server_default=""),
        sa.Column("mitre_techniques", postgresql.ARRAY(sa.String(20)), nullable=False, server_default="{}"),
        sa.Column("blast_radius_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("false_positive_probability", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_investigations_org_id", "investigations", ["org_id"])

    op.create_table(
        "investigation_timeline_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
    )
    op.create_index("ix_investigation_timeline_events_investigation_id", "investigation_timeline_events", ["investigation_id"])

    op.create_table(
        "investigation_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", evidence_type_enum, nullable=False),
        sa.Column("value", sa.String(255), nullable=False),
    )
    op.create_index("ix_investigation_evidence_investigation_id", "investigation_evidence", ["investigation_id"])

    op.create_table(
        "investigation_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_investigation_notes_investigation_id", "investigation_notes", ["investigation_id"])

    op.create_table(
        "investigation_recommended_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", action_status_enum, nullable=False, server_default="pending"),
    )
    op.create_index("ix_investigation_recommended_actions_investigation_id", "investigation_recommended_actions", ["investigation_id"])


def downgrade() -> None:
    op.drop_table("investigation_recommended_actions")
    op.drop_table("investigation_notes")
    op.drop_table("investigation_evidence")
    op.drop_table("investigation_timeline_events")
    op.drop_table("investigations")

    bind = op.get_bind()
    action_status_enum.drop(bind, checkfirst=True)
    evidence_type_enum.drop(bind, checkfirst=True)
    status_enum.drop(bind, checkfirst=True)
    severity_enum.drop(bind, checkfirst=True)
