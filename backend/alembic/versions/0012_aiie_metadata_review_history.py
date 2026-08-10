"""add AIIE execution metadata and review history
Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="0012"; down_revision="0011"; branch_labels=None; depends_on=None
def upgrade():
 op.add_column("intelligence_analyses",sa.Column("model_version",sa.String(255)));op.add_column("intelligence_analyses",sa.Column("generation_duration_ms",sa.Integer()));op.add_column("intelligence_analyses",sa.Column("input_tokens",sa.Integer()));op.add_column("intelligence_analyses",sa.Column("output_tokens",sa.Integer()));op.add_column("intelligence_analyses",sa.Column("total_tokens",sa.Integer()))
 u=postgresql.UUID(as_uuid=True);op.create_table("intelligence_review_events",sa.Column("id",u,primary_key=True),sa.Column("org_id",u,nullable=False),sa.Column("item_id",u,nullable=False),sa.Column("from_status",sa.String(20),nullable=False),sa.Column("to_status",sa.String(20),nullable=False),sa.Column("reviewer_id",u,nullable=False),sa.Column("rationale",sa.Text(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.ForeignKeyConstraint(["item_id"],["intelligence_items.id"],ondelete="RESTRICT"),sa.ForeignKeyConstraint(["reviewer_id"],["users.id"],ondelete="RESTRICT"));op.create_index("ix_intelligence_review_events_org_id","intelligence_review_events",["org_id"]);op.create_index("ix_intelligence_review_events_item_id","intelligence_review_events",["item_id"])
def downgrade():
 op.drop_table("intelligence_review_events");op.drop_column("intelligence_analyses","total_tokens");op.drop_column("intelligence_analyses","output_tokens");op.drop_column("intelligence_analyses","input_tokens");op.drop_column("intelligence_analyses","generation_duration_ms");op.drop_column("intelligence_analyses","model_version")
