"""Version-aware triage membership reads without changing triage-v1 scoring."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import event, select

from app.modules.alert_triage.domain.correlation_service import CORRELATION_VERSION
from app.modules.alert_triage.domain.correlation_v2_service import CORRELATION_V2_VERSION
from app.modules.alert_triage.domain.service import CanonicalAlertCreate, CanonicalAlertService
from app.modules.alert_triage.domain.triage_service import AlertClusterTriageService
from app.modules.alert_triage.infrastructure.models import AlertCluster, AlertClusterMembership
from app.modules.connectors.infrastructure.models import Connector, RawEvent
from app.modules.identity.infrastructure.models import Organization
from app.shared.database import SessionLocal
from app.shared.exceptions import NotFoundError, ValidationError


NOW = datetime(2026, 8, 10, 12, tzinfo=timezone.utc)


@pytest.fixture()
def db():
    session = SessionLocal()
    try: yield session
    finally: session.rollback(); session.close()


def context(db, suffix=None):
    suffix = suffix or uuid4().hex
    org = Organization(name=f"Triage versions {suffix}", slug=f"triage-versions-{suffix}")
    db.add(org); db.flush()
    connector = Connector(org_id=org.id, name=f"connector-{suffix}", type="webhook", secret_hash="x")
    db.add(connector); db.commit()
    return org, connector


def alert(db, org, connector, identity, severity="HIGH"):
    raw = RawEvent(connector_id=connector.id, received_at=NOW, payload={"id": identity}); db.add(raw); db.commit()
    return CanonicalAlertService(db).create(org.id, connector.id, raw.id, CanonicalAlertCreate(
        source="test", source_alert_id=identity, observed_at=NOW, title=identity, severity=severity,
        category="network", rule_id="rule", observables={"hostname": "shared-host"},
    ))[0]


def cluster(db, org, version, alerts, score=80):
    row = AlertCluster(org_id=org.id, identity_key=f"{version}:{uuid4().hex}", correlation_version=version,
        status="OPEN", first_seen=NOW, last_seen=NOW, member_count=len(alerts), source_diversity=1)
    db.add(row); db.flush()
    for item in alerts:
        db.add(AlertClusterMembership(org_id=org.id, cluster_id=row.id, alert_id=item.id, candidate_alert_id=None,
            correlation_version=version, score=score, reasons=[{"code": "TEST"}], added_at=NOW))
    db.commit()
    return row


def factor(assessment, name):
    return next(item for item in assessment.ledger if item["factor"] == name)


def test_v1_and_v2_triage_read_only_their_own_memberships_without_score_contamination(db):
    org, source = context(db)
    shared = alert(db, org, source, "shared", "HIGH")
    v1_only = alert(db, org, source, "v1-only", "LOW")
    v2_only = alert(db, org, source, "v2-only", "CRITICAL")
    v1 = cluster(db, org, CORRELATION_VERSION, [shared, v1_only])
    v2 = cluster(db, org, CORRELATION_V2_VERSION, [shared, v2_only])
    service = AlertClusterTriageService(db)
    one = service.assess(org.id, v1.id, NOW + timedelta(minutes=1))
    two = service.assess(org.id, v2.id, NOW + timedelta(minutes=1))
    assert factor(one, "source_severity")["points"] == 18
    assert factor(two, "source_severity")["points"] == 25
    assert factor(one, "member_count")["reason"].startswith("2 distinct")
    assert factor(two, "member_count")["reason"].startswith("2 distinct")
    versions = set(db.scalars(select(AlertClusterMembership.correlation_version).where(AlertClusterMembership.alert_id == shared.id)))
    assert versions == {CORRELATION_VERSION, CORRELATION_V2_VERSION}


def test_equivalent_member_sets_have_identical_triage_score_across_versions(db):
    org, source = context(db)
    alerts = [alert(db, org, source, "a"), alert(db, org, source, "b")]
    v1 = cluster(db, org, CORRELATION_VERSION, alerts, score=80)
    v2 = cluster(db, org, CORRELATION_V2_VERSION, alerts, score=80)
    service = AlertClusterTriageService(db)
    one = service.assess(org.id, v1.id, NOW + timedelta(minutes=1))
    two = service.assess(org.id, v2.id, NOW + timedelta(minutes=1))
    assert one.score == two.score and one.priority == two.priority
    assert factor(one, "correlation_strength")["points"] == factor(two, "correlation_strength")["points"]


def test_v1_behavior_and_cross_org_scope_remain_intact(db):
    org, source = context(db); other, other_source = context(db)
    v1 = cluster(db, org, CORRELATION_VERSION, [alert(db, org, source, "a")])
    isolated = cluster(db, other, CORRELATION_V2_VERSION, [alert(db, other, other_source, "a")])
    service = AlertClusterTriageService(db)
    assert service.assess(org.id, v1.id, NOW + timedelta(minutes=1)).priority == "MEDIUM"
    assert service.assess(other.id, isolated.id, NOW + timedelta(minutes=1)).cluster_id == isolated.id
    with pytest.raises(NotFoundError):
        service.assess(other.id, v1.id, NOW + timedelta(minutes=1))


@pytest.mark.parametrize("member_count", [1, 5, 10])
def test_assessment_input_materialization_uses_a_bounded_select_shape(db, member_count):
    org, source = context(db)
    alerts = [alert(db, org, source, f"bounded-{index}") for index in range(member_count)]
    row = cluster(db, org, CORRELATION_V2_VERSION, alerts)
    service = AlertClusterTriageService(db)
    org_id, cluster_id = org.id, row.id
    observed = []

    def count_select(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            observed.append(1)

    db.expire_all()
    materialized_cluster = db.get(AlertCluster, cluster_id)
    event.listen(db.get_bind(), "before_cursor_execute", count_select)
    try:
        members, materialized = service._materialize_assessment_inputs(org_id, materialized_cluster)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", count_select)
    assert len(observed) == 3  # lineage, version-scoped members, same-org alerts
    assert [member.alert_id for member in members] == [item.id for item in materialized]


def test_bulk_materialization_fails_closed_for_empty_unsupported_or_foreign_inputs(db):
    org, source = context(db)
    service = AlertClusterTriageService(db)
    empty = cluster(db, org, CORRELATION_V2_VERSION, [])
    assert service._materialize_assessment_inputs(org.id, empty) == ([], [])

    unsupported = cluster(db, org, CORRELATION_V2_VERSION, [alert(db, org, source, "unsupported")])
    unsupported.correlation_version = "unknown-version"; db.commit()
    with pytest.raises(ValidationError):
        service._materialize_assessment_inputs(org.id, unsupported)

    other, other_source = context(db)
    foreign = alert(db, other, other_source, "foreign")
    owned = cluster(db, org, CORRELATION_V2_VERSION, [])
    db.add(AlertClusterMembership(
        org_id=org.id, cluster_id=owned.id, alert_id=foreign.id, candidate_alert_id=None,
        correlation_version=CORRELATION_V2_VERSION, score=0, reasons=[], added_at=NOW,
    )); db.commit()
    with pytest.raises(NotFoundError):
        service._materialize_assessment_inputs(org.id, owned)
