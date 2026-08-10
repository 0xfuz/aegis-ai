"""Phase 7.3 deterministic correlation and immutable AlertCluster history."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis
from app.modules.alert_triage.domain.correlation_service import AlertCorrelationService, CORRELATION_VERSION
from app.modules.alert_triage.domain.deduplication_service import AlertDeduplicationService
from app.modules.alert_triage.domain.service import CanonicalAlertCreate, CanonicalAlertService
from app.modules.alert_triage.infrastructure.models import AlertCluster, AlertClusterMembership, AlertClusterMerge, CanonicalAlert
from app.modules.connectors.infrastructure.models import Connector, RawEvent
from app.modules.evidence.infrastructure.models import Entity, EntityRelationship, Event, EvidenceItem, Indicator, RawRecord
from app.modules.identity.infrastructure.models import Organization
from app.modules.investigations.infrastructure.models import Finding, MitreMapping
from app.shared.database import SessionLocal


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback(); session.close()


def setup(db, suffix=None):
    suffix = suffix or uuid4().hex
    org = Organization(name=f"Correlation {suffix}", slug=f"correlation-{suffix}")
    db.add(org); db.flush()
    connector = Connector(org_id=org.id, name=f"sensor-{suffix}", type="webhook", secret_hash="x")
    db.add(connector); db.commit()
    return org, connector


def add_alert(db, org, connector, identity, observed, *, observables=None, source="suricata", severity="HIGH", category="network", metadata=None):
    raw = RawEvent(connector_id=connector.id, received_at=datetime.now(timezone.utc), payload={"id": identity})
    db.add(raw); db.commit()
    payload = CanonicalAlertCreate(
        source=source, source_alert_id=identity, observed_at=observed, title="network detection", description="untrusted",
        severity=severity, category=category, rule_id="rule-1", observables=observables or {}, source_metadata=metadata or {},
    )
    return CanonicalAlertService(db).create(org.id, connector.id, raw.id, payload)[0]


def test_two_related_alerts_form_one_explainable_cluster(db):
    org, connector = setup(db); start = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    first = add_alert(db, org, connector, "a", start, observables={"hostname": "web-01"})
    second = add_alert(db, org, connector, "b", start + timedelta(seconds=120), observables={"hostname": "web-01"})
    service = AlertCorrelationService(db)

    initial = service.process(org.id, first.id)
    clustered = service.process(org.id, second.id)
    members = service.list_members(org.id, clustered.id)

    assert initial.id == clustered.id and clustered.member_count == 2 and clustered.source_diversity == 1
    assert len(service.list_clusters(org.id)) == 1 and {member.alert_id for member in members} == {first.id, second.id}
    second_membership = next(member for member in members if member.alert_id == second.id)
    assert second_membership.score >= 50 and {reason["code"] for reason in second_membership.reasons} >= {"SAME_OBSERVABLE", "WITHIN_OBSERVED_TIME_WINDOW"}


def test_unrelated_or_category_severity_only_alerts_remain_separate(db):
    org, connector = setup(db); start = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    first = add_alert(db, org, connector, "a", start, observables={"hostname": "web-01"})
    category_only = add_alert(db, org, connector, "b", start + timedelta(seconds=20), observables={})
    service = AlertCorrelationService(db)

    assert service.process(org.id, first.id).member_count == 1
    assert service.process(org.id, category_only.id).member_count == 1
    assert len(service.list_clusters(org.id)) == 2


def test_same_observable_inside_window_correlates_but_outside_does_not(db):
    org, connector = setup(db); start = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    first = add_alert(db, org, connector, "a", start, observables={"domain": "example.test"})
    inside = add_alert(db, org, connector, "b", start + timedelta(seconds=180), observables={"domain": "example.test"})
    outside = add_alert(db, org, connector, "c", start + timedelta(seconds=361), observables={"domain": "example.test"})
    service = AlertCorrelationService(db)

    service.process(org.id, first.id)
    inside_cluster = service.process(org.id, inside.id)
    outside_cluster = service.process(org.id, outside.id)
    assert inside_cluster.member_count == 2 and outside_cluster.member_count == 1
    assert len(service.list_clusters(org.id)) == 2


def test_exact_replays_and_semantic_duplicates_do_not_inflate_cluster_membership(db):
    org, connector = setup(db); start = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    representative = add_alert(db, org, connector, "a", start, observables={"hostname": "web-01"})
    semantic = add_alert(db, org, connector, "b", start + timedelta(seconds=10), observables={"hostname": "web-01"})
    AlertDeduplicationService(db).process(org.id, semantic.id)
    service = AlertCorrelationService(db)
    cluster = service.process(org.id, representative.id)
    assert service.process(org.id, semantic.id) is None
    assert cluster.member_count == 1 and len(service.list_members(org.id, cluster.id)) == 1


def test_multi_source_correlation_increases_source_diversity_without_cross_org_join(db):
    org, connector = setup(db); other_org, other_connector = setup(db)
    connector_two = Connector(org_id=org.id, name="second-source", type="webhook", secret_hash="x")
    db.add(connector_two); db.commit()
    start = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    first = add_alert(db, org, connector, "a", start, observables={"file": "c:/tmp/dropper.exe"})
    second = add_alert(db, org, connector_two, "b", start + timedelta(seconds=20), observables={"file": "c:/tmp/dropper.exe"}, source="elastic")
    isolated = add_alert(db, other_org, other_connector, "a", start + timedelta(seconds=20), observables={"file": "c:/tmp/dropper.exe"})
    service = AlertCorrelationService(db)

    service.process(org.id, first.id)
    cluster = service.process(org.id, second.id)
    assert cluster.member_count == 2 and cluster.source_diversity == 2
    assert service.process(other_org.id, isolated.id).member_count == 1
    assert len(service.list_clusters(other_org.id)) == 1


def test_common_private_gateway_user_or_mitre_alone_never_correlates(db):
    org, connector = setup(db); start = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    private_a = add_alert(db, org, connector, "a", start, observables={"source_ip": "10.0.0.5"}, metadata={"mitre_techniques": ["T1059"]})
    private_b = add_alert(db, org, connector, "b", start + timedelta(seconds=10), observables={"source_ip": "10.0.0.5"}, metadata={"mitre_techniques": ["T1059"]})
    user_a = add_alert(db, org, connector, "c", start, observables={"username": "admin"})
    user_b = add_alert(db, org, connector, "d", start + timedelta(seconds=10), observables={"username": "admin"})
    service = AlertCorrelationService(db)

    for alert in (private_a, private_b, user_a, user_b): service.process(org.id, alert.id)
    assert len(service.list_clusters(org.id)) == 4


def test_bridge_alert_deterministically_merges_clusters_and_preserves_membership_history(db):
    org, connector = setup(db); start = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    left = add_alert(db, org, connector, "left", start, observables={"hostname": "web-01"})
    right = add_alert(db, org, connector, "right", start + timedelta(seconds=10), observables={"domain": "example.test"})
    bridge = add_alert(db, org, connector, "bridge", start + timedelta(seconds=20), observables={"hostname": "web-01", "domain": "example.test"})
    service = AlertCorrelationService(db)
    left_cluster = service.process(org.id, left.id)
    right_cluster = service.process(org.id, right.id)
    merged = service.process(org.id, bridge.id)

    expected = min((left_cluster, right_cluster), key=lambda item: item.identity_key)
    assert merged.id == expected.id and merged.member_count == 3 and len(service.list_clusters(org.id)) == 1
    merge = db.scalar(select(AlertClusterMerge).where(AlertClusterMerge.survivor_cluster_id == merged.id))
    assert merge.trigger_alert_id == bridge.id and merge.absorbed_cluster_id in {left_cluster.id, right_cluster.id}
    assert {member.alert_id for member in service.list_members(org.id, merged.id)} == {left.id, right.id, bridge.id}
    assert db.get(AlertCluster, merge.absorbed_cluster_id).status == "CLOSED"
    assert service.process(org.id, bridge.id).id == merged.id
    assert db.scalar(select(func.count()).select_from(AlertClusterMerge).where(AlertClusterMerge.org_id == org.id)) == 1


def test_correlation_never_mutates_fact_ai_investigation_or_verdict_data(db):
    org, connector = setup(db); start = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    first = add_alert(db, org, connector, "a", start, observables={"hostname": "web-01"})
    second = add_alert(db, org, connector, "b", start + timedelta(seconds=5), observables={"hostname": "web-01"})
    models = [EvidenceItem, RawRecord, Event, Indicator, Entity, EntityRelationship, IntelligenceAnalysis, Finding, MitreMapping]
    before = {model.__name__: db.scalar(select(func.count()).select_from(model).where(model.org_id == org.id)) for model in models}

    service = AlertCorrelationService(db); service.process(org.id, first.id); service.process(org.id, second.id)
    after = {model.__name__: db.scalar(select(func.count()).select_from(model).where(model.org_id == org.id)) for model in models}
    assert before == after and db.scalar(select(func.count()).select_from(AlertClusterMembership).where(AlertClusterMembership.org_id == org.id)) == 2
