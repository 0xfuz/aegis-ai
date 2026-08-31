"""add typed intelligence evidence references

Revision ID: 0021
Revises: 0020
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

_TARGETS = (
    ("EVIDENCE_ITEM", "evidence_item_id", "evidence_items"), ("RAW_RECORD", "raw_record_id", "raw_records"),
    ("EVENT", "event_id", "events"), ("ENTITY_OBSERVATION", "entity_observation_id", "entity_observations"),
    ("INDICATOR_OCCURRENCE", "indicator_occurrence_id", "indicator_occurrences"), ("ENTITY_RELATIONSHIP", "entity_relationship_id", "entity_relationships"),
    ("CANONICAL_ALERT", "canonical_alert_id", "canonical_alerts"), ("ALERT_CLUSTER_MEMBERSHIP", "alert_cluster_membership_id", "alert_cluster_memberships"),
    ("ALERT_CLUSTER_ASSESSMENT", "alert_cluster_assessment_id", "alert_cluster_assessments"), ("ALERT_CLUSTER_PROMOTION", "alert_cluster_promotion_id", "alert_cluster_promotions"),
    ("FINDING", "finding_id", "findings"), ("MITRE_MAPPING", "mitre_mapping_id", "mitre_mappings"),
)

def _pair_check():
    columns=", ".join(column for _,column,_ in _TARGETS)
    matches=" AND ".join(f"(reference_type = '{kind}') = ({column} IS NOT NULL)" for kind,column,_ in _TARGETS)
    return f"num_nonnulls({columns}) = 1 AND {matches}"

def upgrade():
    op.create_table("intelligence_evidence_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("investigations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("intelligence_analyses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("snapshot_alias", sa.String(64), nullable=False), sa.Column("reference_type", sa.String(32), nullable=False),
        sa.Column("context_version", sa.String(64), nullable=False), sa.Column("builder_version", sa.String(64), nullable=False), sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("provenance_fingerprint", sa.String(64), nullable=False), sa.Column("locator_metadata", postgresql.JSONB()), sa.Column("locator_hash", sa.String(64)),
        sa.Column("producer_name", sa.String(100)), sa.Column("producer_version", sa.String(100)), sa.Column("evidence_sha256", sa.String(64)),
        *(sa.Column(column, postgresql.UUID(as_uuid=True), sa.ForeignKey(f"{table}.id", ondelete="RESTRICT")) for _,column,table in _TARGETS),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("analysis_id","snapshot_alias",name="uq_intelligence_evidence_references_analysis_alias"),
        sa.CheckConstraint("reference_type IN ("+",".join(f"'{kind}'" for kind,_,_ in _TARGETS)+")",name="ck_intelligence_evidence_references_type"),
        sa.CheckConstraint(_pair_check(),name="ck_intelligence_evidence_references_pair"),
        sa.CheckConstraint("locator_metadata IS NULL OR jsonb_typeof(locator_metadata) = 'object'",name="ck_intelligence_evidence_references_locator_object"),
        sa.CheckConstraint("provenance_fingerprint ~ '^[0-9a-f]{64}$'",name="ck_intelligence_evidence_references_provenance_hash"),
        sa.CheckConstraint("evidence_sha256 IS NULL OR evidence_sha256 ~ '^[0-9a-f]{64}$'",name="ck_intelligence_evidence_references_evidence_hash"),
        sa.CheckConstraint("locator_hash IS NULL OR locator_hash ~ '^[0-9a-f]{64}$'",name="ck_intelligence_evidence_references_locator_hash"),
    )
    op.create_index("ix_intelligence_evidence_references_scope","intelligence_evidence_references",["org_id","investigation_id","analysis_id"])
    op.create_index("ix_intelligence_evidence_references_type","intelligence_evidence_references",["reference_type"])
    for index,(_,column,_) in enumerate(_TARGETS, start=1):
        op.create_index(f"ix_intelligence_evidence_references_{column}","intelligence_evidence_references",[column])
        op.create_index(f"uq_ier_analysis_target_{index}","intelligence_evidence_references",["analysis_id",column],unique=True,postgresql_where=sa.text(f"{column} IS NOT NULL"))
    op.create_table("intelligence_claim_evidence_links",
        sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),sa.Column("org_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("organizations.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("investigation_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("investigations.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("item_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("intelligence_items.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("evidence_reference_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("intelligence_evidence_references.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("role",sa.String(20),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.text("now()"),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.text("now()"),nullable=False),
        sa.UniqueConstraint("item_id","evidence_reference_id","role",name="uq_intelligence_claim_evidence_links_item_reference_role"),sa.CheckConstraint("role IN ('SUPPORTS','CONTRADICTS','CONTEXT')",name="ck_intelligence_claim_evidence_links_role"),
    )
    op.create_index("ix_intelligence_claim_evidence_links_scope","intelligence_claim_evidence_links",["org_id","investigation_id"])
    op.create_index("ix_intelligence_claim_evidence_links_item","intelligence_claim_evidence_links",["item_id"])
    op.create_index("ix_intelligence_claim_evidence_links_reference","intelligence_claim_evidence_links",["evidence_reference_id"])

def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM intelligence_evidence_references) OR EXISTS (SELECT 1 FROM intelligence_claim_evidence_links)
      THEN RAISE EXCEPTION 'cannot safely downgrade typed evidence references with Phase 8.2 data'; END IF;
    END $$;""")
    op.drop_table("intelligence_claim_evidence_links")
    op.drop_table("intelligence_evidence_references")
