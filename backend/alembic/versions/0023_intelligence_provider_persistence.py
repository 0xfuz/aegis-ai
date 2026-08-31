"""add bounded intelligence provider persistence metadata

Revision ID: 0023
Revises: 0022
"""
from alembic import op
import sqlalchemy as sa
revision="0023";down_revision="0022";branch_labels=None;depends_on=None
def upgrade():
 t="intelligence_analyses"
 op.add_column(t,sa.Column("provider_execution_version",sa.String(64)))
 op.add_column(t,sa.Column("provider_request_fingerprint",sa.String(64)))
 op.add_column(t,sa.Column("candidate_output_schema_version",sa.String(64)))
 op.add_column(t,sa.Column("candidate_output_fingerprint",sa.String(64)))
 op.add_column(t,sa.Column("provider_attempt_count",sa.Integer(),nullable=False,server_default="0"))
 op.add_column(t,sa.Column("provider_call_started_at",sa.DateTime(timezone=True)))
 op.add_column(t,sa.Column("provider_call_finished_at",sa.DateTime(timezone=True)))
 op.create_check_constraint("ck_intelligence_analyses_provider_attempt_count",t,"provider_attempt_count >= 0")
 op.create_check_constraint("ck_intelligence_analyses_provider_request_fingerprint",t,"provider_request_fingerprint IS NULL OR provider_request_fingerprint ~ '^[0-9a-f]{64}$'")
 op.create_check_constraint("ck_intelligence_analyses_candidate_output_fingerprint",t,"candidate_output_fingerprint IS NULL OR candidate_output_fingerprint ~ '^[0-9a-f]{64}$'")
 op.create_check_constraint("ck_intelligence_analyses_provider_call_finish",t,"provider_call_finished_at IS NULL OR provider_call_started_at IS NOT NULL")
def downgrade():
 t="intelligence_analyses"
 for name in ("ck_intelligence_analyses_provider_call_finish","ck_intelligence_analyses_candidate_output_fingerprint","ck_intelligence_analyses_provider_request_fingerprint","ck_intelligence_analyses_provider_attempt_count"):op.drop_constraint(name,t,type_="check")
 for name in ("provider_call_finished_at","provider_call_started_at","provider_attempt_count","candidate_output_fingerprint","candidate_output_schema_version","provider_request_fingerprint","provider_execution_version"):op.drop_column(t,name)
