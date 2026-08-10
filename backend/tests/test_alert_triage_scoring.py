"""Phase 7.4 bounded deterministic cluster scoring contracts."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis
from app.modules.alert_triage.domain.correlation_service import AlertCorrelationService
from app.modules.alert_triage.domain.deduplication_service import AlertDeduplicationService
from app.modules.alert_triage.domain.service import CanonicalAlertCreate, CanonicalAlertService
from app.modules.alert_triage.domain.triage_service import AlertClusterTriageService, priority_band
from app.modules.alert_triage.infrastructure.models import AlertClusterAssessment
from app.modules.assets.infrastructure.models import Asset
from app.modules.connectors.infrastructure.models import Connector, RawEvent
from app.modules.evidence.infrastructure.models import Entity, EntityRelationship, Event, EvidenceItem, Indicator, RawRecord
from app.modules.identity.infrastructure.models import Organization
from app.modules.investigations.infrastructure.models import EvidenceType, Finding, IOC, MitreMapping
from app.shared.database import SessionLocal
from app.shared.exceptions import NotFoundError


@pytest.fixture()
def db():
    session = SessionLocal()
    try: yield session
    finally: session.rollback(); session.close()


def setup(db, suffix=None):
    suffix = suffix or uuid4().hex
    org = Organization(name=f"Triage {suffix}", slug=f"triage-{suffix}"); db.add(org); db.flush()
    connector = Connector(org_id=org.id, name=f"source-{suffix}", type="webhook", secret_hash="x"); db.add(connector); db.commit()
    return org, connector


def connector(db, org, name):
    value = Connector(org_id=org.id, name=name, type="webhook", secret_hash="x"); db.add(value); db.commit(); return value


def alert(db, org, connector_row, identity, observed, *, severity="HIGH", category="network", observables=None, source="suricata", metadata=None):
    raw = RawEvent(connector_id=connector_row.id, received_at=datetime.now(timezone.utc), payload={"identity": identity}); db.add(raw); db.commit()
    item = CanonicalAlertCreate(source=source, source_alert_id=identity, observed_at=observed, title="detection", description="untrusted", severity=severity, category=category, rule_id="rule", observables=observables or {}, source_metadata=metadata or {})
    return CanonicalAlertService(db).create(org.id, connector_row.id, raw.id, item)[0]


def clustered(db, org, alerts):
    service = AlertCorrelationService(db); result = None
    for item in alerts: result = service.process(org.id, item.id)
    return result


def ledger(assessment, factor):
    return next(item for item in assessment.ledger if item["factor"] == factor)


def test_low_medium_high_and_critical_priority_bands(db):
    start = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    # LOW: info singleton, no trusted context.
    org, source = setup(db); low_cluster = clustered(db, org, [alert(db, org, source, "low", start, severity="INFO")]); low = AlertClusterTriageService(db).assess(org.id, low_cluster.id, start + timedelta(minutes=30))
    # MEDIUM: two high, strongly correlated alerts.
    org2, source2 = setup(db); medium_cluster = clustered(db, org2, [alert(db, org2, source2, "m1", start, observables={"hostname": "web-01"}), alert(db, org2, source2, "m2", start + timedelta(seconds=10), observables={"hostname": "web-01"})]); medium = AlertClusterTriageService(db).assess(org2.id, medium_cluster.id, start + timedelta(minutes=30))
    # HIGH: critical source severity plus trusted critical asset.
    org3, source3 = setup(db); high_cluster = clustered(db, org3, [alert(db, org3, source3, "h", start, severity="CRITICAL", observables={"hostname": "db-01"})]); db.add(Asset(org_id=org3.id, name="db-01", criticality="critical", last_seen=start)); db.commit(); high = AlertClusterTriageService(db).assess(org3.id, high_cluster.id, start + timedelta(minutes=30))
    # CRITICAL: distinct sources, critical asset, watchlisted IOC, and deterministic sequence.
    org4, first_source = setup(db); second_source = connector(db, org4, "source-two"); third_source = connector(db, org4, "source-three")
    critical_alerts = [alert(db, org4, first_source, "c1", start, severity="CRITICAL", category="authentication_failed", observables={"hostname": "core-01", "source_ip": "198.51.100.44"}), alert(db, org4, second_source, "c2", start + timedelta(seconds=10), severity="CRITICAL", category="authentication_success", observables={"hostname": "core-01", "source_ip": "198.51.100.44"}, source="elastic"), alert(db, org4, third_source, "c3", start + timedelta(seconds=20), severity="CRITICAL", category="process_execution", observables={"hostname": "core-01", "source_ip": "198.51.100.44"}, source="defender")]
    critical_cluster = clustered(db, org4, critical_alerts); db.add_all([Asset(org_id=org4.id, name="core-01", criticality="critical", last_seen=start), IOC(org_id=org4.id, type=EvidenceType.IP, value="198.51.100.44", verdict="malicious", provenance="internal", is_watched=True, first_seen=start, last_seen=start)]); db.commit(); critical = AlertClusterTriageService(db).assess(org4.id, critical_cluster.id, start + timedelta(minutes=30))

    assert (low.priority, medium.priority, high.priority, critical.priority) == ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert sum(item["points"] for item in critical.ledger) == critical.score <= 100


@pytest.mark.parametrize("score,band", [(0, "LOW"), (24, "LOW"), (25, "MEDIUM"), (49, "MEDIUM"), (50, "HIGH"), (74, "HIGH"), (75, "CRITICAL"), (100, "CRITICAL")])
def test_priority_band_boundaries(score, band):
    assert priority_band(score) == band


def test_assessment_is_idempotent_and_duplicate_replay_semantic_alerts_do_not_inflate(db):
    org, source = setup(db); start = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    primary = alert(db, org, source, "a", start, observables={"hostname": "web-01"})
    replay_raw = RawEvent(connector_id=source.id, received_at=datetime.now(timezone.utc), payload={"identity": "a-replay"}); db.add(replay_raw); db.commit()
    replayed, exact_replay = CanonicalAlertService(db).create(org.id, source.id, replay_raw.id, CanonicalAlertCreate(source="suricata", source_alert_id="a", observed_at=start, title="changed source text", description="untrusted", severity="HIGH", category="network", rule_id="rule", observables={"hostname": "web-01"}))
    semantic = alert(db, org, source, "b", start + timedelta(seconds=10), observables={"hostname": "web-01"})
    AlertDeduplicationService(db).process(org.id, semantic.id)
    cluster = clustered(db, org, [primary]); correlation = AlertCorrelationService(db)
    assert correlation.process(org.id, semantic.id) is None
    service = AlertClusterTriageService(db); first = service.assess(org.id, cluster.id, start + timedelta(minutes=30)); repeated = service.assess(org.id, cluster.id, start + timedelta(minutes=30))
    assert exact_replay and replayed.id == primary.id and first.id == repeated.id and ledger(first, "member_count")["points"] == 0
    assert db.scalar(select(func.count()).select_from(AlertClusterAssessment).where(AlertClusterAssessment.cluster_id == cluster.id)) == 1


def test_source_diversity_member_bound_and_missing_asset_context(db):
    org, first = setup(db); second = connector(db, org, "second"); third = connector(db, org, "third"); start = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    alerts = [alert(db, org, first, "a", start, observables={"hostname": "unknown"}), alert(db, org, second, "b", start + timedelta(seconds=10), observables={"hostname": "unknown"}, source="elastic"), alert(db, org, third, "c", start + timedelta(seconds=20), observables={"hostname": "unknown"}, source="defender")]
    cluster = clustered(db, org, alerts); assessment = AlertClusterTriageService(db).assess(org.id, cluster.id, start + timedelta(minutes=30))
    assert ledger(assessment, "source_diversity")["points"] == 10
    assert ledger(assessment, "member_count")["points"] == 4
    assert ledger(assessment, "asset_criticality")["points"] == 0 and "Unavailable" in ledger(assessment, "asset_criticality")["reason"]


def test_member_count_contribution_is_bounded_at_eight_or_more_distinct_alerts(db):
    org, source = setup(db); start = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    alerts = [alert(db, org, source, f"many-{index}", start + timedelta(seconds=index), observables={"hostname": "web-01"}) for index in range(8)]
    cluster = clustered(db, org, alerts)
    assessment = AlertClusterTriageService(db).assess(org.id, cluster.id, start + timedelta(minutes=30))
    assert cluster.member_count == 8 and ledger(assessment, "member_count")["points"] == 10 and assessment.score <= 100


def test_only_trusted_ioc_context_scores_and_sequence_is_deterministic(db):
    org, source = setup(db); start = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    alerts = [alert(db, org, source, "a", start, category="authentication_failed", observables={"hostname": "web-01", "source_ip": "198.51.100.8"}, metadata={"malicious": True, "mitre_techniques": ["T1059"]}), alert(db, org, source, "b", start + timedelta(seconds=10), category="authentication_success", observables={"hostname": "web-01", "source_ip": "198.51.100.8"}), alert(db, org, source, "c", start + timedelta(seconds=20), category="process_execution", observables={"hostname": "web-01", "source_ip": "198.51.100.8"})]
    cluster = clustered(db, org, alerts); service = AlertClusterTriageService(db)
    untrusted = service.assess(org.id, cluster.id, start + timedelta(minutes=30))
    external_ioc = IOC(org_id=org.id, type=EvidenceType.IP, value="198.51.100.8", verdict="malicious", provenance="external", is_watched=False, first_seen=start, last_seen=start)
    db.add(external_ioc); db.commit()
    external = service.assess(org.id, cluster.id, start + timedelta(minutes=31))
    external_ioc.provenance = "internal"; external_ioc.is_watched = True; db.commit()
    trusted = service.assess(org.id, cluster.id, start + timedelta(minutes=32))
    assert ledger(untrusted, "trusted_ioc_context")["points"] == 0 and ledger(external, "trusted_ioc_context")["points"] == 0
    assert ledger(trusted, "trusted_ioc_context")["points"] == 10 and ledger(trusted, "behavior_sequence")["points"] == 10


def test_recency_boundaries_cross_org_and_merged_cluster_rescoring(db):
    org, source = setup(db); other_org, other_source = setup(db); start = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    left = alert(db, org, source, "left", start, observables={"hostname": "web-01"}); right = alert(db, org, source, "right", start + timedelta(seconds=10), observables={"domain": "example.test"}); bridge = alert(db, org, source, "bridge", start + timedelta(seconds=20), observables={"hostname": "web-01", "domain": "example.test"})
    cluster = clustered(db, org, [left, right, bridge]); service = AlertClusterTriageService(db)
    at_hour = service.assess(org.id, cluster.id, start + timedelta(seconds=20, hours=1)); after_hour = service.assess(org.id, cluster.id, start + timedelta(seconds=21, hours=1))
    assert ledger(at_hour, "recency")["points"] == 5 and ledger(after_hour, "recency")["points"] == 3
    assert at_hour.cluster_id == cluster.id and AlertCorrelationService(db).get_cluster(org.id, cluster.id).member_count == 3
    isolated = clustered(db, other_org, [alert(db, other_org, other_source, "x", start, observables={"hostname": "web-01"})])
    with pytest.raises(NotFoundError): service.assess(other_org.id, cluster.id, start + timedelta(minutes=30))
    assert service.assess(other_org.id, isolated.id, start + timedelta(minutes=30)).cluster_id == isolated.id


def test_scoring_never_mutates_fact_ai_or_creates_investigations(db):
    org, source = setup(db); start = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    cluster = clustered(db, org, [alert(db, org, source, "a", start, observables={"hostname": "web-01"}), alert(db, org, source, "b", start + timedelta(seconds=10), observables={"hostname": "web-01"})])
    models = [EvidenceItem, RawRecord, Event, Indicator, Entity, EntityRelationship, IntelligenceAnalysis, Finding, MitreMapping]
    before = {model.__name__: db.scalar(select(func.count()).select_from(model).where(model.org_id == org.id)) for model in models}
    assessment = AlertClusterTriageService(db).assess(org.id, cluster.id, start + timedelta(minutes=30))
    after = {model.__name__: db.scalar(select(func.count()).select_from(model).where(model.org_id == org.id)) for model in models}
    assert assessment.score >= 0 and before == after
