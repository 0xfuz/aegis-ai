from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.modules.alert_triage.infrastructure.models import AlertCluster, AlertClusterAssessment, AlertClusterMembership, AlertClusterPromotion, CanonicalAlert
from app.modules.ai_reasoning.domain.activity_window import ActivityWindowReader
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis, IntelligenceClaimEvidenceLink, IntelligenceEvidenceReference, IntelligenceItem
from app.modules.connectors.infrastructure.models import Connector, RawEvent
from app.modules.evidence.infrastructure.models import EvidenceItem, EvidenceParseRun, Event, RawRecord
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.infrastructure.models import Investigation, InvestigationStatus, Severity, TimelineEvent
from app.shared.database import SessionLocal

UTC = timezone.utc

@pytest.fixture()
def db():
    session = SessionLocal()
    try: yield session
    finally: session.rollback(); session.close()

def scoped(db):
    token = uuid4().hex; now = datetime(2026, 1, 1, 12, tzinfo=UTC)
    org = Organization(name=token, slug=f"aw-{token}"); role = Role(name=f"aw-role-{token}")
    db.add_all((org, role)); db.flush()
    user = User(org_id=org.id, role_id=role.id, email=f"{token}@test", hashed_password="x", full_name="test")
    inv = Investigation(org_id=org.id, title="activity", source="test", severity=Severity.MEDIUM, status=InvestigationStatus.NEW)
    db.add_all((user, inv)); db.flush()
    evidence = EvidenceItem(org_id=org.id, investigation_id=inv.id, original_filename="test.log", storage_key=f"aw-{token}", sha256="a" * 64, byte_size=0, detected_mime="text/plain", extension=".log", acquisition_source="test", imported_at=now, parsing_status="complete")
    db.add(evidence); db.flush()
    return org, inv, user, evidence, now

def promoted_v2(db):
    org, inv, user, evidence, now = scoped(db)
    connector = Connector(org_id=org.id, name="test", type="webhook", status="CONNECTED", secret_hash="x", is_active=True)
    db.add(connector); db.flush()
    alerts=[]
    for offset in (0, 10):
        raw = RawEvent(connector_id=connector.id, received_at=now + timedelta(minutes=offset), payload={"safe": True}, investigation_id=inv.id)
        db.add(raw); db.flush()
        alert = CanonicalAlert(org_id=org.id, connector_id=connector.id, raw_event_id=raw.id, source="test", source_alert_id=f"{offset}-{uuid4().hex}", observed_at=now + timedelta(minutes=offset), ingested_at=now + timedelta(minutes=offset), title="test", description="", severity="MEDIUM", normalized_observables={}, source_metadata={}, payload_digest="b" * 64, normalizer_version="v1", lifecycle="CORRELATED")
        db.add(alert); db.flush(); alerts.append(alert)
    cluster = AlertCluster(org_id=org.id, identity_key=f"v2-{uuid4().hex}", correlation_version="correlation-v2", status="PROMOTED", first_seen=now, last_seen=now + timedelta(minutes=10), member_count=2, source_diversity=1)
    db.add(cluster); db.flush()
    for alert in alerts: db.add(AlertClusterMembership(org_id=org.id, cluster_id=cluster.id, alert_id=alert.id, correlation_version="correlation-v2", score=1, reasons=[], added_at=alert.observed_at))
    assessment = AlertClusterAssessment(org_id=org.id, cluster_id=cluster.id, scoring_version="triage-v1", input_hash="c" * 64, score=50, priority="MEDIUM", ledger=[], reference_at=now, evaluated_at=now)
    db.add(assessment); db.flush()
    promotion = AlertClusterPromotion(org_id=org.id, cluster_id=cluster.id, investigation_id=inv.id, evidence_id=evidence.id, actor_id=user.id, triage_assessment_id=assessment.id, export_version="v1", export_fingerprint="d" * 64, manifest={"correlation_version": "correlation-v2"}, status="COMPLETED", promoted_at=now)
    db.add(promotion); db.commit()
    return org, inv, evidence, now, alerts, cluster

def test_reader_uses_promoted_v2_interval_and_is_fresh_session_deterministic(db):
    org, inv, _evidence, now, alerts, _cluster = promoted_v2(db)
    first = ActivityWindowReader(db).reconstruct(org.id, inv.id, now)
    assert first["anchor"] == {"start": now.isoformat(), "end": (now + timedelta(minutes=10)).isoformat()}
    assert {item["id"] for item in first["activities"] if item["type"] == "CANONICAL_ALERT"} == {str(alert.id) for alert in alerts}
    with SessionLocal() as fresh: second = ActivityWindowReader(fresh).reconstruct(org.id, inv.id, now)
    assert first == second

def test_reader_event_anchor_receipt_fallback_and_org_scope(db):
    org, inv, _user, evidence, now = scoped(db)
    run = EvidenceParseRun(org_id=org.id, evidence_id=evidence.id, parser_name="test", parser_version="1", run_sequence=1, status="complete", started_at=now)
    db.add(run); db.flush()
    raw = RawRecord(org_id=org.id, evidence_id=evidence.id, parse_run_id=run.id, ordinal=1, content="safe", content_type="text/plain")
    db.add(raw); db.flush()
    event = Event(org_id=org.id, investigation_id=inv.id, evidence_id=evidence.id, raw_record_id=raw.id, normalizer_name="test", normalizer_version="1", ordinal=1, timestamp=None, normalized={})
    db.add(event); db.commit()
    output = ActivityWindowReader(db).reconstruct(org.id, inv.id, now)
    assert output["anchor"]["start"] == now.isoformat()
    activity = next(item for item in output["activities"] if item["id"] == str(event.id))
    assert activity["time_basis"] == "RECEIPT" and "SOURCE_TIME_MISSING" in activity["uncertainty"]
    assert ActivityWindowReader(db).reconstruct(uuid4(), inv.id, now)["anchor"] is None

def test_reader_evidence_import_is_final_receipt_anchor(db):
    org, inv, _user, evidence, now = scoped(db)
    output = ActivityWindowReader(db).reconstruct(org.id, inv.id, now)
    assert output["anchor"] == {"start": now.isoformat(), "end": now.isoformat()}
    activity = next(item for item in output["activities"] if item["id"] == str(evidence.id))
    assert activity["time_basis"] == "RECEIPT" and "SOURCE_TIME_MISSING" in activity["uncertainty"]

def test_reader_excludes_v1_history_legacy_timeline_and_has_no_side_effects(db):
    org, inv, _evidence, now, alerts, cluster = promoted_v2(db)
    v1_cluster = AlertCluster(org_id=org.id, identity_key=f"v1-{uuid4().hex}", correlation_version="correlation-v1", status="OPEN", first_seen=now - timedelta(days=1), last_seen=now - timedelta(days=1), member_count=1, source_diversity=1)
    db.add(v1_cluster); db.flush()
    db.add(AlertClusterMembership(org_id=org.id, cluster_id=v1_cluster.id, alert_id=alerts[0].id, correlation_version="correlation-v1", score=1, reasons=[], added_at=now - timedelta(days=1)))
    db.add(TimelineEvent(investigation_id=inv.id, occurred_at=now - timedelta(days=2), description="legacy")); db.commit()
    models = (IntelligenceAnalysis, IntelligenceItem, IntelligenceEvidenceReference, IntelligenceClaimEvidenceLink)
    before = [db.scalar(select(func.count()).select_from(model)) for model in models]
    output = ActivityWindowReader(db).reconstruct(org.id, inv.id, now)
    after = [db.scalar(select(func.count()).select_from(model)) for model in models]
    assert output["anchor"]["start"] == now.isoformat()
    assert before == after
