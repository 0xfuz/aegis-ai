"""Phase 7.5 promotion contract: analyst-only, atomic FACT-pipeline entry."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.config import Settings
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis
from app.modules.alert_triage.domain.correlation_service import AlertCorrelationService
from app.modules.alert_triage.domain.promotion_service import AlertClusterPromotionService, PROMOTION_EXPORT_VERSION
from app.modules.alert_triage.domain.service import CanonicalAlertCreate, CanonicalAlertService
from app.modules.alert_triage.domain.triage_service import AlertClusterTriageService
from app.modules.alert_triage.infrastructure.models import AlertCluster, AlertClusterPromotion, CanonicalAlertOccurrence, AlertDeduplicationDecision
from app.modules.connectors.infrastructure.models import Connector, RawEvent
from app.modules.evidence.infrastructure.models import AuditEvent, Entity, EntityRelationship, Event, EvidenceItem, Indicator, RawRecord
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.infrastructure.models import Finding, Investigation, MitreMapping
from app.shared.database import SessionLocal
from app.shared.exceptions import NotFoundError, ValidationError


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback(); session.close()


def context(db, suffix=None):
    suffix = suffix or uuid4().hex
    org = Organization(name=f"Promotion {suffix}", slug=f"promotion-{suffix}")
    role = Role(name=f"promotion-role-{suffix}")
    db.add_all([org, role]); db.flush()
    user = User(org_id=org.id, role_id=role.id, email=f"{suffix}@test.invalid", hashed_password="x", full_name="Analyst")
    connector = Connector(org_id=org.id, name=f"sensor-{suffix}", type="webhook", secret_hash="x")
    db.add_all([user, connector]); db.commit()
    return org, user, connector


def add_alert(db, org, connector, identity, observed, observables=None):
    raw = RawEvent(connector_id=connector.id, received_at=datetime.now(timezone.utc), payload={"source": identity})
    db.add(raw); db.commit()
    payload = CanonicalAlertCreate(source="suricata", source_alert_id=identity, observed_at=observed,
        title="detection", description="untrusted", severity="HIGH", category="network",
        rule_id="rule-1", observables=observables or {"hostname": "web-01", "source_ip": "198.51.100.9", "destination_ip": "203.0.113.12"}, source_metadata={})
    return CanonicalAlertService(db).create(org.id, connector.id, raw.id, payload)[0]


def promotable(db):
    org, user, connector = context(db); now = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    first = add_alert(db, org, connector, "one", now)
    second = add_alert(db, org, connector, "two", now + timedelta(seconds=10))
    correlation = AlertCorrelationService(db); cluster = correlation.process(org.id, first.id); cluster = correlation.process(org.id, second.id)
    assessment = AlertClusterTriageService(db).assess(org.id, cluster.id, now + timedelta(minutes=30))
    return org, user, cluster, assessment, (first, second)


def service(db, tmp_path):
    return AlertClusterPromotionService(db, Settings(EVIDENCE_STORAGE_DIR=str(tmp_path)))


def test_promotion_creates_normal_investigation_and_complete_fact_provenance(db, tmp_path):
    org, user, cluster, assessment, alerts = promotable(db)
    result = service(db, tmp_path).promote(org.id, cluster.id, user.id)
    promotion = db.get(AlertClusterPromotion, result.id); investigation = db.get(Investigation, result.investigation_id)
    evidence = db.get(EvidenceItem, result.evidence_id)
    raw = db.scalar(select(RawRecord).where(RawRecord.evidence_id == evidence.id))
    event = db.scalar(select(Event).where(Event.evidence_id == evidence.id))
    assert result.created and promotion.cluster_id == cluster.id and promotion.triage_assessment_id == assessment.id
    assert investigation.source == "Alert Cluster Promotion" and evidence.acquisition_source == "alert_cluster_promotion"
    assert evidence.parsing_status == "complete" and raw is not None and event is not None
    assert raw.content.find(str(alerts[0].id)) >= 0 and raw.content.find(str(alerts[0].raw_event_id)) >= 0 and event.raw_record_id == raw.id
    assert db.get(AlertCluster, cluster.id).status == "PROMOTED"
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.investigation_id == investigation.id, AuditEvent.action == "ALERT_CLUSTER_PROMOTED")) == 1


def test_promotion_is_idempotent_and_export_snapshot_is_deterministic(db, tmp_path):
    org, user, cluster, _assessment, _alerts = promotable(db); promotion_service = service(db, tmp_path)
    first = promotion_service.promote(org.id, cluster.id, user.id); second = promotion_service.promote(org.id, cluster.id, user.id)
    row = db.get(AlertClusterPromotion, first.id)
    assert second.created is False and second.id == first.id and first.export_version == PROMOTION_EXPORT_VERSION
    assert row.export_fingerprint == __import__("hashlib").sha256(
        __import__("json").dumps({"format": "aegis.alert-promotion.export", "version": "1.0", "cluster_id": str(cluster.id), "manifest_fingerprint": __import__("hashlib").sha256(__import__("json").dumps(row.manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest(), "alerts": row.manifest["members"]}, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    assert db.scalar(select(func.count()).select_from(AlertClusterPromotion).where(AlertClusterPromotion.cluster_id == cluster.id)) == 1


def test_promotion_requires_open_cluster_current_assessment_and_same_org_actor(db, tmp_path):
    org, user, cluster, _assessment, _alerts = promotable(db); other_org, other_user, _connector = context(db)
    with pytest.raises(NotFoundError): service(db, tmp_path).promote(other_org.id, cluster.id, other_user.id)
    # A new cluster without assessment cannot be promoted.
    now = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    # Deliberately use a fresh cluster in the correct tenant.
    own_connector = db.scalar(select(Connector).where(Connector.org_id == org.id))
    lonely = add_alert(db, org, own_connector, "lonely-2", now + timedelta(minutes=10), {"hostname": "isolated"})
    no_assessment = AlertCorrelationService(db).process(org.id, lonely.id)
    with pytest.raises(ValidationError, match="assessment"): service(db, tmp_path).promote(org.id, no_assessment.id, user.id)
    with pytest.raises(NotFoundError): service(db, tmp_path).promote(org.id, cluster.id, other_user.id)


def test_promotion_failure_is_atomic_and_does_not_mark_cluster_promoted(db, tmp_path, monkeypatch):
    org, user, cluster, _assessment, _alerts = promotable(db); promotion_service = service(db, tmp_path)
    monkeypatch.setattr(promotion_service, "_audit", lambda *args: (_ for _ in ()).throw(RuntimeError("audit failure")))
    before = db.scalar(select(func.count()).select_from(Investigation).where(Investigation.org_id == org.id))
    with pytest.raises(RuntimeError, match="audit failure"): promotion_service.promote(org.id, cluster.id, user.id)
    assert db.scalar(select(func.count()).select_from(Investigation).where(Investigation.org_id == org.id)) == before
    assert db.scalar(select(func.count()).select_from(AlertClusterPromotion).where(AlertClusterPromotion.cluster_id == cluster.id)) == 0
    assert db.get(AlertCluster, cluster.id).status == "OPEN" and list(tmp_path.iterdir()) == []


def test_promotion_does_not_create_ai_findings_or_mitre_and_only_parser_writes_facts(db, tmp_path):
    org, user, cluster, _assessment, _alerts = promotable(db)
    models = (IntelligenceAnalysis, Finding, MitreMapping)
    before = {model.__name__: db.scalar(select(func.count()).select_from(model).where(model.org_id == org.id)) for model in models}
    result = service(db, tmp_path).promote(org.id, cluster.id, user.id)
    after = {model.__name__: db.scalar(select(func.count()).select_from(model).where(model.org_id == org.id)) for model in models}
    assert before == after
    assert db.scalar(select(func.count()).select_from(EvidenceItem).where(EvidenceItem.id == result.evidence_id)) == 1
    assert db.scalar(select(func.count()).select_from(Indicator).where(Indicator.org_id == org.id)) >= 1
    assert db.scalar(select(func.count()).select_from(Entity).where(Entity.investigation_id == result.investigation_id)) >= 1
    assert db.scalar(select(func.count()).select_from(EntityRelationship).where(EntityRelationship.investigation_id == result.investigation_id)) >= 1


def test_exact_alert_replays_remain_source_history_but_export_once(db, tmp_path):
    org, user, cluster, _assessment, alerts = promotable(db)
    replay_raw = RawEvent(connector_id=alerts[0].connector_id, received_at=datetime.now(timezone.utc), payload={"replay": True})
    db.add(replay_raw); db.commit()
    replay, exact = CanonicalAlertService(db).create(org.id, alerts[0].connector_id, replay_raw.id, CanonicalAlertCreate(
        source=alerts[0].source, source_alert_id=alerts[0].source_alert_id, observed_at=alerts[0].observed_at,
        title="changed", description="untrusted", severity=alerts[0].severity, category=alerts[0].category,
        rule_id=alerts[0].rule_id, observables=alerts[0].normalized_observables, source_metadata={},
    ))
    result = service(db, tmp_path).promote(org.id, cluster.id, user.id)
    assert exact and replay.id == alerts[0].id
    assert db.scalar(select(func.count()).select_from(CanonicalAlertOccurrence).where(CanonicalAlertOccurrence.canonical_alert_id == replay.id)) == 2
    assert len(db.get(AlertClusterPromotion, result.id).manifest["members"]) == 2


def test_semantic_duplicate_member_is_rejected_without_partial_promotion(db, tmp_path):
    org, user, cluster, _assessment, alerts = promotable(db)
    db.add(AlertDeduplicationDecision(org_id=org.id, representative_alert_id=alerts[1].id, duplicate_alert_id=alerts[0].id,
        duplicate_occurrence_id=None, decision_type="SEMANTIC", decision_version="test-v1", subject_key="semantic-test",
        reasons=[{"code": "TEST"}], decided_at=datetime.now(timezone.utc)))
    db.commit()
    with pytest.raises(ValidationError, match="Semantic duplicate"):
        service(db, tmp_path).promote(org.id, cluster.id, user.id)
    assert db.scalar(select(func.count()).select_from(AlertClusterPromotion).where(AlertClusterPromotion.cluster_id == cluster.id)) == 0
    assert db.get(AlertCluster, cluster.id).status == "OPEN"
