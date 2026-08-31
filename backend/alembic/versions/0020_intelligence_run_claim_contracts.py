"""add intelligence run and claim contracts

Revision ID: 0020
Revises: 0019
"""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("intelligence_analyses", sa.Column("request_key", sa.String(length=128), nullable=True))
    op.add_column("intelligence_analyses", sa.Column("output_schema_version", sa.String(length=64), nullable=True))
    op.add_column("intelligence_analyses", sa.Column("predecessor_analysis_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_intelligence_analyses_predecessor", "intelligence_analyses", "intelligence_analyses", ["predecessor_analysis_id"], ["id"], ondelete="RESTRICT")
    op.execute("UPDATE intelligence_analyses SET request_key = 'legacy:' || id::text, output_schema_version = 'aiie-output-v1'")
    op.alter_column("intelligence_analyses", "request_key", nullable=False)
    op.alter_column("intelligence_analyses", "output_schema_version", nullable=False)
    op.drop_constraint("ck_intelligence_analyses_status", "intelligence_analyses", type_="check")
    op.create_check_constraint("ck_intelligence_analyses_status", "intelligence_analyses", "status IN ('QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED')")
    op.create_index("ix_intelligence_analyses_org_investigation_status", "intelligence_analyses", ["org_id", "investigation_id", "status"])
    op.create_index("uq_intelligence_analyses_request", "intelligence_analyses", ["org_id", "investigation_id", "request_key"], unique=True)

    op.add_column("intelligence_items", sa.Column("origin", sa.String(length=32), nullable=True))
    op.add_column("intelligence_items", sa.Column("supersedes_item_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_intelligence_items_supersedes", "intelligence_items", "intelligence_items", ["supersedes_item_id"], ["id"], ondelete="RESTRICT")
    op.execute("UPDATE intelligence_items SET origin = 'AI'")
    op.alter_column("intelligence_items", "origin", nullable=False)
    op.drop_constraint("ck_intelligence_items_kind", "intelligence_items", type_="check")
    op.create_check_constraint("ck_intelligence_items_kind", "intelligence_items", "kind IN ('SUMMARY','OBSERVATION','HYPOTHESIS','RECOMMENDATION','QUESTION','REASONING','FACT','INFERENCE')")
    op.drop_constraint("ck_intelligence_items_review", "intelligence_items", type_="check")
    op.execute("UPDATE intelligence_items SET review_status = CASE review_status WHEN 'UNREVIEWED' THEN 'PENDING' WHEN 'APPROVED' THEN 'CONFIRMED' ELSE review_status END")
    op.create_check_constraint("ck_intelligence_items_review", "intelligence_items", "review_status IN ('PENDING','CONFIRMED','REJECTED','UNRESOLVED','SUPERSEDED')")
    op.create_check_constraint("ck_intelligence_items_not_self_superseding", "intelligence_items", "supersedes_item_id IS NULL OR supersedes_item_id <> id")
    op.create_index("ix_intelligence_items_org_investigation_supersedes", "intelligence_items", ["org_id", "investigation_id", "supersedes_item_id"])
    op.execute("UPDATE intelligence_review_events SET from_status = CASE from_status WHEN 'UNREVIEWED' THEN 'PENDING' WHEN 'APPROVED' THEN 'CONFIRMED' ELSE from_status END, to_status = CASE to_status WHEN 'UNREVIEWED' THEN 'PENDING' WHEN 'APPROVED' THEN 'CONFIRMED' ELSE to_status END")


def downgrade():
    # Do not silently discard Phase 8-only state on a downgrade.
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM intelligence_analyses WHERE status IN ('QUEUED','CANCELLED') OR predecessor_analysis_id IS NOT NULL)
         OR EXISTS (SELECT 1 FROM intelligence_items WHERE kind IN ('FACT','INFERENCE') OR origin <> 'AI' OR review_status = 'UNRESOLVED' OR supersedes_item_id IS NOT NULL)
      THEN RAISE EXCEPTION 'cannot safely downgrade intelligence run and claim contracts with Phase 8 data'; END IF;
    END $$;""")
    op.drop_index("ix_intelligence_items_org_investigation_supersedes", table_name="intelligence_items")
    op.drop_constraint("ck_intelligence_items_not_self_superseding", "intelligence_items", type_="check")
    op.drop_constraint("ck_intelligence_items_review", "intelligence_items", type_="check")
    op.execute("UPDATE intelligence_items SET review_status = CASE review_status WHEN 'PENDING' THEN 'UNREVIEWED' WHEN 'CONFIRMED' THEN 'APPROVED' ELSE review_status END")
    op.create_check_constraint("ck_intelligence_items_review", "intelligence_items", "review_status IN ('UNREVIEWED','APPROVED','REJECTED','SUPERSEDED')")
    op.drop_constraint("ck_intelligence_items_kind", "intelligence_items", type_="check")
    op.create_check_constraint("ck_intelligence_items_kind", "intelligence_items", "kind IN ('SUMMARY','OBSERVATION','HYPOTHESIS','RECOMMENDATION','QUESTION','REASONING')")
    op.drop_constraint("fk_intelligence_items_supersedes", "intelligence_items", type_="foreignkey")
    op.drop_column("intelligence_items", "supersedes_item_id")
    op.drop_column("intelligence_items", "origin")
    op.execute("UPDATE intelligence_review_events SET from_status = CASE from_status WHEN 'PENDING' THEN 'UNREVIEWED' WHEN 'CONFIRMED' THEN 'APPROVED' ELSE from_status END, to_status = CASE to_status WHEN 'PENDING' THEN 'UNREVIEWED' WHEN 'CONFIRMED' THEN 'APPROVED' ELSE to_status END")
    op.drop_index("uq_intelligence_analyses_request", table_name="intelligence_analyses")
    op.drop_index("ix_intelligence_analyses_org_investigation_status", table_name="intelligence_analyses")
    op.drop_constraint("ck_intelligence_analyses_status", "intelligence_analyses", type_="check")
    op.create_check_constraint("ck_intelligence_analyses_status", "intelligence_analyses", "status IN ('RUNNING','COMPLETED','FAILED')")
    op.drop_constraint("fk_intelligence_analyses_predecessor", "intelligence_analyses", type_="foreignkey")
    op.drop_column("intelligence_analyses", "predecessor_analysis_id")
    op.drop_column("intelligence_analyses", "output_schema_version")
    op.drop_column("intelligence_analyses", "request_key")
