"""PostgreSQL schema checks for Phase 8.2 typed evidence references."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DataError, IntegrityError

from app.modules.alert_triage.infrastructure.models import AlertCluster, AlertClusterAssessment, AlertClusterMembership, AlertClusterPromotion, CanonicalAlert
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis, IntelligenceClaimEvidenceLink, IntelligenceEvidenceReference, IntelligenceFactLink, IntelligenceItem
from app.modules.ai_reasoning.domain.evidence_reference_service import IntelligenceEvidenceReferenceService
from app.modules.evidence.infrastructure.models import Entity, EntityObservation, EntityRelationship, Event, EvidenceItem, EvidenceParseRun, Indicator, IndicatorOccurrence, RawRecord
from app.modules.connectors.infrastructure.models import Connector, RawEvent
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.infrastructure.models import Finding, Investigation, InvestigationStatus, MitreMapping, Severity
from app.shared.database import SessionLocal
from app.shared.exceptions import NotFoundError, ValidationError


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback(); session.close()


def scope(db):
    suffix = uuid4().hex
    org = Organization(name=suffix, slug=f"typed-{suffix}")
    role = Role(name=f"typed-role-{suffix}")
    db.add_all([org, role]); db.flush()
    user = User(org_id=org.id, role_id=role.id, email=f"{suffix}@test", hashed_password="x", full_name="typed")
    investigation = Investigation(org_id=org.id, title="typed", source="test", severity=Severity.MEDIUM, status=InvestigationStatus.NEW)
    db.add_all([user, investigation]); db.flush()
    analysis = IntelligenceAnalysis(org_id=org.id, investigation_id=investigation.id, provider="test", model="test", prompt_template_version="v1", input_snapshot={}, input_hash="a" * 64, request_key=f"request-{suffix}", output_schema_version="v1", status="QUEUED")
    db.add(analysis); db.flush()
    item = IntelligenceItem(org_id=org.id, investigation_id=investigation.id, analysis_id=analysis.id, kind="OBSERVATION", origin="AI", ordinal=1, statement="test", payload={}, review_status="PENDING")
    evidence = EvidenceItem(org_id=org.id, investigation_id=investigation.id, original_filename="test.log", storage_key=f"typed-{suffix}", sha256="b" * 64, byte_size=0, detected_mime="text/plain", extension=".log", acquisition_source="test", imported_at=analysis.created_at, parsing_status="complete")
    db.add_all([item, evidence]); db.commit()
    return org, investigation, analysis, item, evidence


def batch_2a_targets(db, rows):
    org, investigation, _analysis, _item, evidence = rows
    run = EvidenceParseRun(org_id=org.id, evidence_id=evidence.id, parser_name="test", parser_version="1", run_sequence=1, status="complete", started_at=evidence.imported_at)
    db.add(run); db.flush()
    raw = RawRecord(org_id=org.id, evidence_id=evidence.id, parse_run_id=run.id, ordinal=1, content="safe", content_type="text/plain")
    db.add(raw); db.flush()
    event = Event(org_id=org.id, investigation_id=investigation.id, evidence_id=evidence.id, raw_record_id=raw.id, normalizer_name="test", normalizer_version="1", ordinal=1, normalized={})
    entity = Entity(org_id=org.id, investigation_id=investigation.id, type="host", canonical_value="host", display_name="host")
    indicator = Indicator(org_id=org.id, type="ip", normalized_value="198.51.100.1", display_value="198.51.100.1", occurrence_count=0)
    db.add_all([event, entity, indicator]); db.flush()
    observation = EntityObservation(org_id=org.id, investigation_id=investigation.id, entity_id=entity.id, evidence_id=evidence.id, raw_record_id=raw.id, event_id=event.id, extractor_name="test", extractor_version="1", occurrence_ordinal=1)
    occurrence = IndicatorOccurrence(org_id=org.id, investigation_id=investigation.id, indicator_id=indicator.id, evidence_id=evidence.id, raw_record_id=raw.id, event_id=event.id, extractor_name="test", extractor_version="1", occurrence_ordinal=1)
    db.add_all([observation, occurrence]); db.flush()
    other = Entity(org_id=org.id, investigation_id=investigation.id, type="user", canonical_value="user", display_name="user")
    db.add(other); db.flush()
    relationship = EntityRelationship(org_id=org.id, investigation_id=investigation.id, source_entity_id=entity.id, target_entity_id=other.id, relationship_type="observed", derivation_name="test", derivation_version="1", raw_record_id=raw.id, source_locator_hash="d" * 64)
    db.add(relationship); db.commit()
    return {"RAW_RECORD": ("raw_record_id", raw.id), "EVENT": ("event_id", event.id), "ENTITY_OBSERVATION": ("entity_observation_id", observation.id), "INDICATOR_OCCURRENCE": ("indicator_occurrence_id", occurrence.id), "ENTITY_RELATIONSHIP": ("entity_relationship_id", relationship.id)}


def batch_2b_targets(db, rows):
    org, investigation, analysis, item, evidence = rows
    now = datetime.now(timezone.utc)
    actor_id = db.scalar(select(User.id).where(User.org_id == org.id))
    connector = Connector(org_id=org.id, name="typed", type="webhook", status="CONNECTED", secret_hash="x", is_active=True)
    db.add(connector); db.flush()
    raw_event = RawEvent(connector_id=connector.id, received_at=now, payload={"event": "typed"}, investigation_id=investigation.id)
    db.add(raw_event); db.flush()
    alert = CanonicalAlert(org_id=org.id, connector_id=connector.id, raw_event_id=raw_event.id, source="typed", source_alert_id=f"alert-{uuid4().hex}", observed_at=now, ingested_at=now, title="typed", description="", severity="MEDIUM", normalized_observables={}, source_metadata={}, payload_digest="e" * 64, normalizer_version="v1", lifecycle="CORRELATED")
    db.add(alert); db.flush()
    cluster = AlertCluster(org_id=org.id, identity_key=f"typed-{uuid4().hex}", correlation_version="correlation-v2", status="PROMOTED", first_seen=now, last_seen=now, member_count=1, source_diversity=1)
    db.add(cluster); db.flush()
    membership = AlertClusterMembership(org_id=org.id, cluster_id=cluster.id, alert_id=alert.id, candidate_alert_id=None, correlation_version="correlation-v2", score=100, reasons=[], added_at=now)
    db.add(membership); db.flush()
    assessment = AlertClusterAssessment(org_id=org.id, cluster_id=cluster.id, scoring_version="triage-v1", input_hash="f" * 64, score=50, priority="MEDIUM", ledger=[], reference_at=now, evaluated_at=now)
    db.add(assessment); db.flush()
    promotion = AlertClusterPromotion(org_id=org.id, cluster_id=cluster.id, investigation_id=investigation.id, evidence_id=evidence.id, actor_id=actor_id, triage_assessment_id=assessment.id, export_version="v1", export_fingerprint="0" * 64, manifest={"correlation_version": "correlation-v2"}, status="COMPLETED", promoted_at=now)
    item.review_status = "CONFIRMED"
    finding = Finding(org_id=org.id, investigation_id=investigation.id, source_intelligence_item_id=item.id, source_analysis_id=analysis.id, title="confirmed", description="confirmed", severity="medium", confidence=80, status="CONFIRMED", analyst_id=promotion.actor_id)
    db.add_all([promotion, finding]); db.flush()
    mapping = MitreMapping(org_id=org.id, investigation_id=investigation.id, source_intelligence_item_id=item.id, finding_id=finding.id, technique_id="T1059", technique_name="Command and Scripting Interpreter", tactic="execution", confidence=80, ai_rationale="confirmed", status="CONFIRMED", reviewed_by_id=promotion.actor_id, reviewed_at=now, review_rationale="confirmed")
    db.add(mapping); db.commit()
    return {"CANONICAL_ALERT": ("canonical_alert_id", alert.id), "ALERT_CLUSTER_MEMBERSHIP": ("alert_cluster_membership_id", membership.id), "ALERT_CLUSTER_ASSESSMENT": ("alert_cluster_assessment_id", assessment.id), "ALERT_CLUSTER_PROMOTION": ("alert_cluster_promotion_id", promotion.id), "FINDING": ("finding_id", finding.id), "MITRE_MAPPING": ("mitre_mapping_id", mapping.id)}


def reference(scope_rows, **target):
    org, investigation, analysis, _item, _evidence = scope_rows
    return IntelligenceEvidenceReference(org_id=org.id, investigation_id=investigation.id, analysis_id=analysis.id, snapshot_alias=target.pop("snapshot_alias", "E1"), reference_type=target.pop("reference_type", "EVIDENCE_ITEM"), context_version="v1", builder_version="v1", policy_version="v1", provenance_fingerprint=target.pop("provenance_fingerprint", "c" * 64), **target)


def test_valid_evidence_item_reference_and_claim_roles(db):
    rows = scope(db); _org, _investigation, _analysis, item, evidence = rows
    row = reference(rows, evidence_item_id=evidence.id)
    db.add(row); db.commit(); db.refresh(row)
    assert row.reference_type == "EVIDENCE_ITEM" and row.evidence_item_id == evidence.id
    for role in ("SUPPORTS", "CONTRADICTS", "CONTEXT"):
        db.add(IntelligenceClaimEvidenceLink(org_id=item.org_id, investigation_id=item.investigation_id, item_id=item.id, evidence_reference_id=row.id, role=role))
    db.commit()
    assert len(db.scalars(select(IntelligenceClaimEvidenceLink).where(IntelligenceClaimEvidenceLink.item_id == item.id)).all()) == 3


@pytest.mark.parametrize("kwargs", [{}, {"evidence_item_id": uuid4(), "raw_record_id": uuid4()}, {"reference_type": "EVENT", "evidence_item_id": uuid4()}, {"reference_type": "UNSUPPORTED", "evidence_item_id": uuid4()}])
def test_pair_constraint_rejects_invalid_combinations(db, kwargs):
    rows = scope(db)
    if kwargs.get("evidence_item_id") and kwargs.get("reference_type") != "UNSUPPORTED":
        kwargs = {**kwargs, "evidence_item_id": rows[-1].id}
    db.add(reference(rows, **kwargs))
    with pytest.raises(IntegrityError): db.commit()
    db.rollback()
    assert db.scalar(select(Organization.id).where(Organization.id == rows[0].id)) == rows[0].id


@pytest.mark.parametrize("reference_type", ["RAW_RECORD", "EVENT", "ENTITY_OBSERVATION", "INDICATOR_OCCURRENCE", "ENTITY_RELATIONSHIP"])
def test_batch_2a_authoritative_targets_persist(db, reference_type):
    rows = scope(db); column, target_id = batch_2a_targets(db, rows)[reference_type]
    row = reference(rows, snapshot_alias=f"{reference_type}-1", reference_type=reference_type, **{column: target_id})
    db.add(row); db.commit()
    with SessionLocal() as verify:
        persisted = verify.get(IntelligenceEvidenceReference, row.id)
        assert persisted.reference_type == reference_type and getattr(persisted, column) == target_id


@pytest.mark.parametrize("reference_type", ["CANONICAL_ALERT", "ALERT_CLUSTER_MEMBERSHIP", "ALERT_CLUSTER_ASSESSMENT", "ALERT_CLUSTER_PROMOTION", "FINDING", "MITRE_MAPPING"])
def test_batch_2b_authoritative_targets_persist(db, reference_type):
    rows = scope(db); column, target_id = batch_2b_targets(db, rows)[reference_type]
    row = reference(rows, snapshot_alias=f"{reference_type}-1", reference_type=reference_type, **{column: target_id})
    db.add(row); db.commit()
    with SessionLocal() as verify:
        persisted = verify.get(IntelligenceEvidenceReference, row.id)
        assert persisted.reference_type == reference_type and getattr(persisted, column) == target_id


def all_targets(db, rows):
    return {"EVIDENCE_ITEM": ("evidence_item_id", rows[-1].id), **batch_2a_targets(db, rows), **batch_2b_targets(db, rows)}


@pytest.mark.parametrize("reference_type", ["EVIDENCE_ITEM", "RAW_RECORD", "EVENT", "ENTITY_OBSERVATION", "INDICATOR_OCCURRENCE", "ENTITY_RELATIONSHIP", "CANONICAL_ALERT", "ALERT_CLUSTER_MEMBERSHIP", "ALERT_CLUSTER_ASSESSMENT", "ALERT_CLUSTER_PROMOTION", "FINDING", "MITRE_MAPPING"])
def test_each_target_partial_unique_index_rejects_duplicate_within_analysis(db, reference_type):
    rows = scope(db); column, target_id = all_targets(db, rows)[reference_type]
    db.add(reference(rows, snapshot_alias="first", reference_type=reference_type, **{column: target_id})); db.commit()
    db.add(reference(rows, snapshot_alias="second", reference_type=reference_type, **{column: target_id}))
    with pytest.raises((DataError, IntegrityError)): db.commit()
    db.rollback()


def test_snapshot_alias_and_target_foreign_key_constraints(db):
    rows = scope(db); evidence = rows[-1]
    db.add(reference(rows, snapshot_alias="same", evidence_item_id=evidence.id)); db.commit()
    db.add(reference(rows, snapshot_alias="same", reference_type="RAW_RECORD", raw_record_id=uuid4()))
    with pytest.raises(IntegrityError): db.commit()
    db.rollback()
    db.add(reference(rows, snapshot_alias="dangling", reference_type="RAW_RECORD", raw_record_id=uuid4()))
    with pytest.raises(IntegrityError): db.commit()
    db.rollback()


def test_all_partial_unique_indexes_exist(db):
    names = set(db.scalars(text("SELECT indexname FROM pg_indexes WHERE tablename = 'intelligence_evidence_references'")))
    assert {f"uq_ier_analysis_target_{number}" for number in range(1, 13)} <= names


def test_claim_link_constraints_scope_foreign_keys_and_restrict(db):
    rows = scope(db); org, investigation, _analysis, item, evidence = rows
    row = reference(rows, evidence_item_id=evidence.id); db.add(row); db.commit()
    db.add(IntelligenceClaimEvidenceLink(org_id=org.id, investigation_id=investigation.id, item_id=item.id, evidence_reference_id=row.id, role="SUPPORTS")); db.commit()
    db.add(IntelligenceClaimEvidenceLink(org_id=org.id, investigation_id=investigation.id, item_id=item.id, evidence_reference_id=row.id, role="SUPPORTS"))
    with pytest.raises(IntegrityError): db.commit()
    db.rollback()
    db.add(IntelligenceClaimEvidenceLink(org_id=org.id, investigation_id=investigation.id, item_id=item.id, evidence_reference_id=row.id, role="INVALID"))
    with pytest.raises(IntegrityError): db.commit()
    db.rollback()
    db.add(IntelligenceClaimEvidenceLink(org_id=uuid4(), investigation_id=investigation.id, item_id=item.id, evidence_reference_id=row.id, role="CONTEXT"))
    with pytest.raises(IntegrityError): db.commit()
    db.rollback()
    db.add(IntelligenceClaimEvidenceLink(org_id=org.id, investigation_id=investigation.id, item_id=uuid4(), evidence_reference_id=row.id, role="CONTEXT"))
    with pytest.raises(IntegrityError): db.commit()
    db.rollback()
    with pytest.raises(IntegrityError):
        db.execute(delete(IntelligenceEvidenceReference).where(IntelligenceEvidenceReference.id == row.id)); db.commit()
    db.rollback()


@pytest.mark.parametrize("field, value", [("provenance_fingerprint", "not-a-sha256"), ("locator_hash", "A" * 64), ("evidence_sha256", "z" * 64)])
def test_locator_metadata_hashes_and_bounded_fields(db, field, value):
    rows = scope(db); kwargs = {field: value, "evidence_item_id": rows[-1].id}
    db.add(reference(rows, **kwargs))
    with pytest.raises(IntegrityError): db.commit()
    db.rollback()
    db.add(reference(rows, locator_metadata=["not", "an", "object"], evidence_item_id=rows[-1].id))
    with pytest.raises(IntegrityError): db.commit()
    db.rollback()
    db.add(reference(rows, producer_name="x" * 101, evidence_item_id=rows[-1].id))
    with pytest.raises((DataError, IntegrityError)): db.commit()
    db.rollback()
    row = reference(rows, locator_metadata={"line": 1}, locator_hash="1" * 64, evidence_sha256="2" * 64, producer_name="parser", producer_version="v1", evidence_item_id=rows[-1].id)
    db.add(row); db.commit()
    assert row.locator_metadata == {"line": 1}


def test_legacy_fact_links_remain_unmodified_without_backfill(db):
    rows = scope(db); org, _investigation, _analysis, item, evidence = rows
    legacy = IntelligenceFactLink(org_id=org.id, item_id=item.id, fact_type="EVIDENCE_ITEM", fact_id=evidence.id, role="SUPPORTS")
    db.add(legacy); db.commit()
    assert db.get(IntelligenceFactLink, legacy.id) is not None
    assert db.scalar(select(IntelligenceEvidenceReference).where(IntelligenceEvidenceReference.analysis_id == item.analysis_id)) is None


def service_aliases(targets):
    return {f"A{ordinal}": {"type": reference_type, "id": str(target_id)} for ordinal, (reference_type, (_column, target_id)) in enumerate(targets.items(), 1)}


def test_service_creates_all_twelve_server_resolved_references(db):
    rows = scope(db); org, investigation, analysis, _item, _evidence = rows
    targets = all_targets(db, rows)
    analysis.input_snapshot = {"context_version": "phase8-context-v1", "builder_version": "8.1.2", "policy": {"max_text": 512}, "aliases": service_aliases(targets)}
    db.commit(); service = IntelligenceEvidenceReferenceService(db)
    created = [service.create(org.id, investigation.id, analysis.id, alias, expected) for alias, expected in ((alias, entry["type"]) for alias, entry in analysis.input_snapshot["aliases"].items())]
    assert len({row.id for row in created}) == 12
    assert db.scalar(select(func.count()).select_from(IntelligenceEvidenceReference).where(IntelligenceEvidenceReference.analysis_id == analysis.id)) == 12
    assert all("content" not in row.locator_metadata for row in created)


def test_service_rejects_forged_scope_stale_type_and_unconfirmed_targets(db):
    rows = scope(db); org, investigation, analysis, _item, evidence = rows
    analysis.input_snapshot = {"aliases": {"E1": {"type": "E", "id": str(evidence.id)}, "bad": {"type": "EVENT", "id": "not-a-uuid"}}}; db.commit()
    service = IntelligenceEvidenceReferenceService(db)
    with pytest.raises(ValidationError): service.create(org.id, investigation.id, analysis.id, "missing")
    with pytest.raises(ValidationError): service.create(org.id, investigation.id, analysis.id, "E1", "EVENT")
    with pytest.raises(ValidationError): service.create(org.id, investigation.id, analysis.id, "bad")
    with pytest.raises(NotFoundError): service.create(uuid4(), investigation.id, analysis.id, "E1")
    finding = Finding(org_id=org.id, investigation_id=investigation.id, title="pending", description="pending", severity="low", status="OPEN", analyst_id=db.scalar(select(User.id).where(User.org_id == org.id)))
    db.add(finding); db.flush(); analysis.input_snapshot["aliases"]["FI1"] = {"type": "FINDING", "id": str(finding.id)}; db.commit()
    with pytest.raises(ValidationError): service.create(org.id, investigation.id, analysis.id, "FI1")


def test_service_idempotency_claim_roles_and_atomic_rollback(db):
    rows = scope(db); org, investigation, analysis, item, evidence = rows
    analysis.input_snapshot = {"aliases": {"E1": {"type": "E", "id": str(evidence.id)}, "bad": {"type": "EVENT", "id": str(uuid4())}}}; db.commit()
    service = IntelligenceEvidenceReferenceService(db)
    row = service.create(org.id, investigation.id, analysis.id, "E1")
    assert service.create(org.id, investigation.id, analysis.id, "E1").id == row.id
    assert service.link_claim(org.id, investigation.id, analysis.id, item.id, row.id, "SUPPORTS").id == service.link_claim(org.id, investigation.id, analysis.id, item.id, row.id, "SUPPORTS").id
    with pytest.raises(ValidationError): service.link_claim(org.id, investigation.id, analysis.id, item.id, row.id, "INVALID")
    before = db.scalar(select(func.count()).select_from(IntelligenceEvidenceReference).where(IntelligenceEvidenceReference.analysis_id == analysis.id))
    with pytest.raises(ValidationError): service.create_many(org.id, investigation.id, analysis.id, [("E1", None), ("bad", None)])
    assert db.scalar(select(func.count()).select_from(IntelligenceEvidenceReference).where(IntelligenceEvidenceReference.analysis_id == analysis.id)) == before
    assert db.scalar(select(func.count()).select_from(IntelligenceFactLink).where(IntelligenceFactLink.item_id == item.id)) == 0
