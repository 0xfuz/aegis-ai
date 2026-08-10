"""ai reasoning restructure: attack chain, hypotheses, decision center

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-29
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "investigations",
        sa.Column("attack_chain", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "investigations",
        sa.Column("alternative_hypotheses", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "investigations",
        sa.Column("reasoning_chain", postgresql.JSONB(), nullable=False, server_default="[]"),
    )

    op.add_column("investigation_recommended_actions", sa.Column("confidence", sa.Integer(), nullable=True))
    op.add_column("investigation_recommended_actions", sa.Column("business_impact", sa.String(20), nullable=True))
    op.add_column("investigation_recommended_actions", sa.Column("side_effects", sa.Text(), nullable=True))
    op.add_column("investigation_recommended_actions", sa.Column("rollback", sa.Text(), nullable=True))
    op.add_column(
        "investigation_recommended_actions", sa.Column("estimated_time_to_contain", sa.String(100), nullable=True)
    )
    op.add_column("investigation_recommended_actions", sa.Column("approval_tier", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("investigation_recommended_actions", "approval_tier")
    op.drop_column("investigation_recommended_actions", "estimated_time_to_contain")
    op.drop_column("investigation_recommended_actions", "rollback")
    op.drop_column("investigation_recommended_actions", "side_effects")
    op.drop_column("investigation_recommended_actions", "business_impact")
    op.drop_column("investigation_recommended_actions", "confidence")

    op.drop_column("investigations", "reasoning_chain")
    op.drop_column("investigations", "alternative_hypotheses")
    op.drop_column("investigations", "attack_chain")
