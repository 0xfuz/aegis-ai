"""PostgreSQL coverage for the bounded Phase 8.3.3-A reconstruction contract."""
from datetime import datetime, timezone
import json
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.modules.alert_triage.infrastructure.models import AlertCluster, AlertClusterAssessment, AlertClusterMembership, AlertClusterPromotion, CanonicalAlert
from app.modules.ai_reasoning.domain.reconstruction_read_service import ReconstructionReadPolicy, ReconstructionReadService
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis, IntelligenceClaimEvidenceLink, IntelligenceEvidenceReference, IntelligenceFactLink, IntelligenceItem
from app.modules.connectors.infrastructure.models import Connector, RawEvent
from app.modules.evidence.infrastructure.models import EvidenceItem, EvidenceParseRun, Event, RawRecord
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.infrastructure.models import Finding, Investigation, InvestigationStatus, MitreMapping, Severity
from app.shared.database import SessionLocal


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def scope(db, version="correlation-v2", members=True, matching_assessment=True):
    token = uuid4().hex
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    org = Organization(name=token, slug=f"reconstruct-contract-{token}")
    role = Role(name=f"rc-{token}")
    db.add_all((org, role)); db.flush()
    user = User(org_id=org.id, role_id=role.id, email=f"{token}@test", hashed_password="x", full_name="reader")
    investigation = Investigation(org_id=org.id, title="contract", source="test", severity=Severity.MEDIUM, status=InvestigationStatus.NEW)
    db.add_all((user, investigation)); db.flush()
    evidence = EvidenceItem(org_id=org.id, investigation_id=investigation.id, original_filename="safe.log", storage_key=token, sha256="a" * 64, byte_size=0, detected_mime="text/plain", extension=".log", acquisition_source="test", imported_at=now, parsing_status="complete")
    analysis = IntelligenceAnalysis(org_id=org.id, investigation_id=investigation.id, provider="test", model="test", prompt_template_version="v1", input_snapshot={}, input_hash="b" * 64, request_key=f"request-{token}", output_schema_version="v1", status="COMPLETED")
    db.add_all((evidence, analysis)); db.flush()
    parse = EvidenceParseRun(org_id=org.id, evidence_id=evidence.id, parser_name="test", parser_version="1", run_sequence=1, status="complete", started_at=now)
    db.add(parse); db.flush()
    raw = RawRecord(org_id=org.id, evidence_id=evidence.id, parse_run_id=parse.id, ordinal=1, content="safe", content_type="text/plain")
    db.add(raw); db.flush()
    event = Event(org_id=org.id, investigation_id=investigation.id, evidence_id=evidence.id, raw_record_id=raw.id, normalizer_name="test", normalizer_version="1", ordinal=1, timestamp=now, normalized={})
    db.add(event); db.flush()
    connector = Connector(org_id=org.id, name=f"connector-{token}", type="webhook", status="CONNECTED", secret_hash="x", is_active=True)
    db.add(connector); db.flush()
    received = RawEvent(connector_id=connector.id, received_at=now, payload={"safe": True}, investigation_id=investigation.id)
    db.add(received); db.flush()
    alert = CanonicalAlert(org_id=org.id, connector_id=connector.id, raw_event_id=received.id, source="test", source_alert_id=f"alert-{token}", observed_at=now, ingested_at=now, title="safe", description="", severity="MEDIUM", normalized_observables={}, source_metadata={}, payload_digest="c" * 64, normalizer_version="v1", lifecycle="CORRELATED")
    db.add(alert); db.flush()
    cluster = AlertCluster(org_id=org.id, identity_key=f"cluster-{token}", correlation_version=version, status="PROMOTED", first_seen=now, last_seen=now, member_count=1 if members else 0, source_diversity=1)
    db.add(cluster); db.flush()
    if members:
        db.add(AlertClusterMembership(org_id=org.id, cluster_id=cluster.id, alert_id=alert.id, candidate_alert_id=None, correlation_version=version, score=87, reasons=[{"authorization":"Bearer synthetic-secret-value", "observable":"198.51.100.42"}], added_at=now))
    assessment_cluster_id = cluster.id
    if not matching_assessment:
        other = AlertCluster(org_id=org.id, identity_key=f"other-{token}", correlation_version="correlation-v2", status="OPEN", first_seen=now, last_seen=now, member_count=0, source_diversity=0)
        db.add(other); db.flush(); assessment_cluster_id = other.id
    assessment = AlertClusterAssessment(org_id=org.id, cluster_id=assessment_cluster_id, scoring_version="triage-v1", input_hash="d" * 64, score=73, priority="HIGH", ledger=[], reference_at=now, evaluated_at=now)
    db.add(assessment); db.flush()
    promotion = AlertClusterPromotion(org_id=org.id, cluster_id=cluster.id, investigation_id=investigation.id, evidence_id=evidence.id, actor_id=user.id, triage_assessment_id=assessment.id, export_version="v1", export_fingerprint="e" * 64, manifest={"correlation_version": version}, status="COMPLETED", promoted_at=now)
    db.add(promotion); db.commit()
    return org, investigation, analysis, evidence, event, promotion, cluster


def reference(org, investigation, analysis, alias, reference_type, **target):
    return IntelligenceEvidenceReference(org_id=org.id, investigation_id=investigation.id, analysis_id=analysis.id, snapshot_alias=alias, reference_type=reference_type, context_version="phase8-context-v1", builder_version="8.1.2", policy_version="v1", provenance_fingerprint="f" * 64, **target)


def test_citation_projection_preserves_many_to_many_links_and_is_bounded(db):
    org, investigation, analysis, evidence, event, _promotion, _cluster = scope(db)
    item_a = IntelligenceItem(org_id=org.id, investigation_id=investigation.id, analysis_id=analysis.id, kind="OBSERVATION", origin="AI", ordinal=1, statement="safe", payload={}, review_status="PENDING")
    item_b = IntelligenceItem(org_id=org.id, investigation_id=investigation.id, analysis_id=analysis.id, kind="HYPOTHESIS", origin="AI", ordinal=2, statement="safe", payload={}, review_status="PENDING")
    evidence_reference = reference(org, investigation, analysis, "E1", "EVIDENCE_ITEM", evidence_item_id=evidence.id)
    event_reference = reference(org, investigation, analysis, "EV1", "EVENT", event_id=event.id)
    db.add_all((item_a, item_b, evidence_reference, event_reference)); db.flush()
    db.add_all((
        IntelligenceClaimEvidenceLink(org_id=org.id, investigation_id=investigation.id, item_id=item_a.id, evidence_reference_id=evidence_reference.id, role="SUPPORTS"),
        IntelligenceClaimEvidenceLink(org_id=org.id, investigation_id=investigation.id, item_id=item_b.id, evidence_reference_id=evidence_reference.id, role="CONTRADICTS"),
        IntelligenceClaimEvidenceLink(org_id=org.id, investigation_id=investigation.id, item_id=item_a.id, evidence_reference_id=event_reference.id, role="CONTEXT"),
        IntelligenceFactLink(org_id=org.id, item_id=item_a.id, fact_type="EVENT", fact_id=event.id, role="SUPPORTS"),
    )); db.commit()
    complete = ReconstructionReadService(db).read(org.id, investigation.id)
    assert {link["role"] for link in next(citation for citation in complete["sections"]["citations"] if citation["alias"] == "E1")["claim_links"]} == {"SUPPORTS", "CONTRADICTS"}
    first = ReconstructionReadService(db, ReconstructionReadPolicy(per_citation_links=1)).read(org.id, investigation.id)
    with SessionLocal() as fresh:
        second = ReconstructionReadService(fresh, ReconstructionReadPolicy(per_citation_links=1)).read(org.id, investigation.id)
    assert json.dumps(first, sort_keys=True, separators=(",", ":")) == json.dumps(second, sort_keys=True, separators=(",", ":"))
    citations = {citation["alias"]: citation for citation in first["sections"]["citations"]}
    assert citations["E1"]["claim_links_omitted"] == 1
    assert citations["E1"]["claim_links"] == sorted(citations["E1"]["claim_links"], key=lambda link: (link["claim_id"], link["role"]))
    assert citations["EV1"]["claim_links"] == [{"claim_id": str(item_a.id), "role": "CONTEXT"}]
    assert "claim_role" not in citations["E1"] and str(event.id) not in json.dumps(citations)


def test_selected_run_citations_are_not_mixed_with_other_completed_runs(db):
    org, investigation, analysis, evidence, _event, _promotion, _cluster = scope(db)
    first_item = IntelligenceItem(org_id=org.id, investigation_id=investigation.id, analysis_id=analysis.id, kind="OBSERVATION", origin="AI", ordinal=1, statement="safe", payload={}, review_status="PENDING")
    first_reference = reference(org, investigation, analysis, "FIRST", "EVIDENCE_ITEM", evidence_item_id=evidence.id)
    db.add_all((first_item, first_reference)); db.flush()
    db.add(IntelligenceClaimEvidenceLink(org_id=org.id, investigation_id=investigation.id, item_id=first_item.id, evidence_reference_id=first_reference.id, role="SUPPORTS"))
    newer = IntelligenceAnalysis(org_id=org.id, investigation_id=investigation.id, provider="test", model="test", prompt_template_version="v1", input_snapshot={}, input_hash="c" * 64, request_key=f"newer-{uuid4().hex}", output_schema_version="v1", status="COMPLETED")
    db.add(newer); db.flush()
    second_item = IntelligenceItem(org_id=org.id, investigation_id=investigation.id, analysis_id=newer.id, kind="OBSERVATION", origin="AI", ordinal=1, statement="safe", payload={}, review_status="PENDING")
    second_reference = reference(org, investigation, newer, "SECOND", "EVIDENCE_ITEM", evidence_item_id=evidence.id)
    db.add_all((second_item, second_reference)); db.flush()
    db.add(IntelligenceClaimEvidenceLink(org_id=org.id, investigation_id=investigation.id, item_id=second_item.id, evidence_reference_id=second_reference.id, role="SUPPORTS")); db.commit()
    selected = ReconstructionReadService(db).read(org.id, investigation.id, analysis.id)
    newer_selected = ReconstructionReadService(db).read(org.id, investigation.id, newer.id)
    assert [citation["alias"] for citation in selected["sections"]["citations"]] == ["FIRST"]
    assert [citation["alias"] for citation in newer_selected["sections"]["citations"]] == ["SECOND"]


def test_promotion_projection_uses_exact_v2_rows_redacts_reasons_and_does_not_write(db):
    org, investigation, analysis, _evidence, _event, promotion, cluster = scope(db)
    models = (IntelligenceAnalysis, IntelligenceItem, IntelligenceEvidenceReference, IntelligenceClaimEvidenceLink, AlertClusterMembership, AlertClusterAssessment, AlertClusterPromotion)
    before = [db.scalar(select(func.count()).select_from(model)) for model in models]
    output = ReconstructionReadService(db).read(org.id, investigation.id)
    promotion_output = output["promotion"]
    assert promotion_output["state"] == "AVAILABLE"
    assert promotion_output["promotion"]["id"] == str(promotion.id)
    assert promotion_output["correlation"]["version"] == "correlation-v2"
    assert promotion_output["correlation"]["membership_count"] == 1
    assert promotion_output["correlation"]["memberships"][0]["score"] == 87
    assert promotion_output["correlation"]["memberships"][0]["reasons"] == [{"authorization": "[REDACTED]", "observable": "198.51.100.42"}]
    assert promotion_output["triage"] == {"id": promotion_output["triage"]["id"], "status": "AVAILABLE", "priority": "HIGH", "score": 73, "version": "triage-v1"}
    assert "synthetic-secret-value" not in json.dumps(output)
    assert before == [db.scalar(select(func.count()).select_from(model)) for model in models]
    assert db.get(AlertCluster, cluster.id).correlation_version == "correlation-v2"


def test_total_response_bound_trims_persisted_membership_summaries_not_authoritative_count(db):
    org, investigation, _analysis, _evidence, _event, _promotion, cluster = scope(db)
    membership = db.scalar(select(AlertClusterMembership).where(AlertClusterMembership.cluster_id == cluster.id))
    membership.reasons = ["x" * 1_000 for _ in range(20)]
    db.commit()
    policy = ReconstructionReadPolicy(max_bytes=8192)
    output = ReconstructionReadService(db, policy).read(org.id, investigation.id)
    assert len(json.dumps(output, sort_keys=True, separators=(",", ":")).encode()) <= policy.max_bytes
    assert output["promotion"]["correlation"]["membership_count"] == 1
    assert output["promotion"]["correlation"]["memberships"] == []
    assert output["promotion"]["correlation"]["memberships_omitted"] == 1


def test_finding_and_mitre_citation_links_project_context_only(db):
    org, investigation, analysis, _evidence, _event, promotion, _cluster = scope(db)
    item = IntelligenceItem(org_id=org.id, investigation_id=investigation.id, analysis_id=analysis.id, kind="OBSERVATION", origin="AI", ordinal=1, statement="safe", payload={}, review_status="CONFIRMED")
    db.add(item); db.flush()
    finding = Finding(org_id=org.id, investigation_id=investigation.id, source_intelligence_item_id=item.id, source_analysis_id=analysis.id, title="confirmed", description="safe", severity="medium", confidence=80, status="CONFIRMED", analyst_id=promotion.actor_id)
    db.add(finding); db.flush()
    mapping = MitreMapping(org_id=org.id, investigation_id=investigation.id, source_intelligence_item_id=item.id, finding_id=finding.id, technique_id="T1059", technique_name="Command", tactic="execution", confidence=80, ai_rationale="safe", status="CONFIRMED", reviewed_by_id=promotion.actor_id, reviewed_at=promotion.promoted_at, review_rationale="safe")
    db.add(mapping); db.flush()
    finding_reference = reference(org, investigation, analysis, "FI1", "FINDING", finding_id=finding.id)
    mapping_reference = reference(org, investigation, analysis, "MT1", "MITRE_MAPPING", mitre_mapping_id=mapping.id)
    db.add_all((finding_reference, mapping_reference)); db.flush()
    for reference_row in (finding_reference, mapping_reference):
        db.add_all((
            IntelligenceClaimEvidenceLink(org_id=org.id, investigation_id=investigation.id, item_id=item.id, evidence_reference_id=reference_row.id, role="CONTEXT"),
            IntelligenceClaimEvidenceLink(org_id=org.id, investigation_id=investigation.id, item_id=item.id, evidence_reference_id=reference_row.id, role="SUPPORTS"),
        ))
    db.commit()
    citations = {citation["alias"]: citation for citation in ReconstructionReadService(db).read(org.id, investigation.id)["sections"]["citations"]}
    assert citations["FI1"]["claim_links"] == [{"claim_id": str(item.id), "role": "CONTEXT"}]
    assert citations["MT1"]["claim_links"] == [{"claim_id": str(item.id), "role": "CONTEXT"}]


@pytest.mark.parametrize(("version", "members", "matching_assessment", "state", "warning"), [
    ("correlation-v1", True, True, "UNSUPPORTED", "CORRELATION_V1_CONTEXT_UNSUPPORTED"),
    ("future-version", True, True, "UNSUPPORTED", "CORRELATION_VERSION_UNSUPPORTED"),
    ("correlation-v2", False, True, "DEGRADED", "CORRELATION_V2_MEMBERSHIP_MISSING"),
    ("correlation-v2", True, False, "DEGRADED", "TRIAGE_LINK_MISSING"),
])
def test_promotion_projection_fails_closed_without_fallback_or_recomputation(db, version, members, matching_assessment, state, warning):
    org, investigation, _analysis, _evidence, _event, _promotion, _cluster = scope(db, version, members, matching_assessment)
    output = ReconstructionReadService(db).read(org.id, investigation.id)["promotion"]
    assert output["state"] == state and output["warning"] == warning
    if output["correlation"]:
        assert output["correlation"]["version"] == version


def test_promotion_projection_distinguishes_no_promotion(db):
    org, investigation, _analysis, _evidence, _event, promotion, _cluster = scope(db)
    db.delete(promotion); db.commit()
    assert ReconstructionReadService(db).read(org.id, investigation.id)["promotion"] == {
        "state": "UNAVAILABLE", "warning": "PROMOTION_LINK_MISSING", "promotion": None, "correlation": None, "triage": None,
    }


def test_citation_projection_excludes_foreign_scope_and_keeps_unlinked_reference(db):
    org, investigation, analysis, evidence, _event, _promotion, _cluster = scope(db)
    local = reference(org, investigation, analysis, "E1", "EVIDENCE_ITEM", evidence_item_id=evidence.id)
    db.add(local); db.commit()
    foreign_org, foreign_investigation, foreign_analysis, foreign_evidence, _event, _promotion, _cluster = scope(db)
    foreign = reference(foreign_org, foreign_investigation, foreign_analysis, "foreign", "EVIDENCE_ITEM", evidence_item_id=foreign_evidence.id)
    foreign_item = IntelligenceItem(org_id=foreign_org.id, investigation_id=foreign_investigation.id, analysis_id=foreign_analysis.id, kind="OBSERVATION", origin="AI", ordinal=1, statement="safe", payload={}, review_status="PENDING")
    db.add_all((foreign, foreign_item)); db.flush()
    db.add(IntelligenceClaimEvidenceLink(org_id=org.id, investigation_id=investigation.id, item_id=foreign_item.id, evidence_reference_id=local.id, role="SUPPORTS")); db.commit()
    output = ReconstructionReadService(db).read(org.id, investigation.id)
    assert {citation["id"] for citation in output["sections"]["citations"]} == {str(local.id)}
    assert output["sections"]["citations"][0]["claim_links"] == []
