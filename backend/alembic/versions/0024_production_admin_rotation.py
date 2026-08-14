"""add forced initial credential rotation

Revision ID: 0024
Revises: 0023
"""
from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("must_rotate_password", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM users WHERE must_rotate_password)
      THEN RAISE EXCEPTION 'cannot safely downgrade users with pending credential rotation'; END IF;
    END $$;""")
    op.drop_column("users", "must_rotate_password")
