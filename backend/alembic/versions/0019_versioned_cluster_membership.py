"""allow versioned correlation memberships

Revision ID: 0019
Revises: 0018
"""
from alembic import op
revision="0019";down_revision="0018";branch_labels=None;depends_on=None
def upgrade():
 op.drop_constraint("uq_alert_cluster_memberships_alert","alert_cluster_memberships",type_="unique")
 op.create_unique_constraint("uq_alert_cluster_memberships_alert_version","alert_cluster_memberships",["alert_id","correlation_version"])
def downgrade():
 op.drop_constraint("uq_alert_cluster_memberships_alert_version","alert_cluster_memberships",type_="unique")
 op.create_unique_constraint("uq_alert_cluster_memberships_alert","alert_cluster_memberships",["alert_id"])
