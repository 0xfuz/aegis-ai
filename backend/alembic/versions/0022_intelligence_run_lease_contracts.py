"""add intelligence execution lease contracts

Revision ID: 0022
Revises: 0021
"""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

_TABLE = "intelligence_analyses"
_LEASE_COLUMNS = ("lease_owner_id", "lease_acquired_at", "lease_expires_at", "lease_heartbeat_at")

def upgrade():
    # A legacy RUNNING row has no trustworthy worker owner. Requeue it rather
    # than fabricating lease authority; all other existing rows retain status.
    op.execute("UPDATE intelligence_analyses SET status = 'QUEUED' WHERE status = 'RUNNING'")
    op.add_column(_TABLE, sa.Column("lease_owner_id", sa.String(128)))
    op.add_column(_TABLE, sa.Column("lease_generation", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(_TABLE, sa.Column("lease_acquired_at", sa.DateTime(timezone=True)))
    op.add_column(_TABLE, sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
    op.add_column(_TABLE, sa.Column("lease_heartbeat_at", sa.DateTime(timezone=True)))
    op.add_column(_TABLE, sa.Column("execution_attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(_TABLE, sa.Column("execution_started_at", sa.DateTime(timezone=True)))
    op.add_column(_TABLE, sa.Column("execution_finished_at", sa.DateTime(timezone=True)))
    op.create_check_constraint("ck_intelligence_analyses_lease_generation", _TABLE, "lease_generation >= 0")
    op.create_check_constraint("ck_intelligence_analyses_execution_attempt_count", _TABLE, "execution_attempt_count >= 0")
    op.create_check_constraint("ck_intelligence_analyses_lease_tuple", _TABLE, "(lease_owner_id IS NULL AND lease_acquired_at IS NULL AND lease_expires_at IS NULL AND lease_heartbeat_at IS NULL) OR (lease_owner_id IS NOT NULL AND lease_acquired_at IS NOT NULL AND lease_expires_at IS NOT NULL AND lease_heartbeat_at IS NOT NULL)")
    op.create_check_constraint("ck_intelligence_analyses_lease_expiry", _TABLE, "lease_expires_at IS NULL OR lease_expires_at > lease_acquired_at")
    op.create_check_constraint("ck_intelligence_analyses_execution_finish", _TABLE, "execution_finished_at IS NULL OR execution_started_at IS NOT NULL")
    op.create_index("ix_intelligence_analyses_status_created_id", _TABLE, ["status", "created_at", "id"])
    op.create_index("ix_intelligence_analyses_status_lease_expiry_id", _TABLE, ["status", "lease_expires_at", "id"])
    op.create_index("ix_intelligence_analyses_lease_owner_status", _TABLE, ["lease_owner_id", "status"])

def downgrade():
    op.drop_index("ix_intelligence_analyses_lease_owner_status", table_name=_TABLE)
    op.drop_index("ix_intelligence_analyses_status_lease_expiry_id", table_name=_TABLE)
    op.drop_index("ix_intelligence_analyses_status_created_id", table_name=_TABLE)
    for name in ("ck_intelligence_analyses_execution_finish", "ck_intelligence_analyses_lease_expiry", "ck_intelligence_analyses_lease_tuple", "ck_intelligence_analyses_execution_attempt_count", "ck_intelligence_analyses_lease_generation"):
        op.drop_constraint(name, _TABLE, type_="check")
    for column in ("execution_finished_at", "execution_started_at", "execution_attempt_count", "lease_heartbeat_at", "lease_expires_at", "lease_acquired_at", "lease_generation", "lease_owner_id"):
        op.drop_column(_TABLE, column)
