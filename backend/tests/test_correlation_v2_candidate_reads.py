"""Query-shape and fail-closed coverage for correlation-v2 candidate reads."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event, select

from app.modules.alert_triage.domain.correlation_v2_service import (
    AlertCorrelationV2Service,
    CORRELATION_V2_VERSION,
)
from app.modules.alert_triage.domain.service import CanonicalAlertCreate, CanonicalAlertService
from app.modules.alert_triage.infrastructure.models import AlertCluster, AlertClusterMembership
from app.modules.connectors.infrastructure.models import Connector, RawEvent
from app.modules.identity.infrastructure.models import Organization
from app.shared.database import SessionLocal
from app.shared.exceptions import NotFoundError


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _scope(db, suffix=None):
    suffix = suffix or uuid4().hex
    org = Organization(name=f"Candidate {suffix}", slug=f"candidate-{suffix}")
    db.add(org)
    db.flush()
    connector = Connector(org_id=org.id, name=f"source-{suffix}", type="webhook", secret_hash="x")
    db.add(connector)
    db.commit()
    return org, connector


def _alert(db, org, connector, sequence):
    observed = datetime(2026, 8, 9, 12, tzinfo=timezone.utc) + timedelta(seconds=sequence * 30)
    raw = RawEvent(connector_id=connector.id, received_at=observed, payload={"synthetic": sequence})
    db.add(raw)
    db.commit()
    return CanonicalAlertService(db).create(org.id, connector.id, raw.id, CanonicalAlertCreate(
        source="candidate-read", source_alert_id=f"candidate-{sequence}", observed_at=observed,
        title="candidate read", description="synthetic", severity="HIGH", category="network",
        rule_id="candidate-rule", observables={"hostname": f"host-{sequence}.example.com"},
    ))[0]


def _open_roots(db, org, connector, count):
    service = AlertCorrelationV2Service(db)
    for sequence in range(1, count + 1):
        service.process(org.id, _alert(db, org, connector, sequence).id)
    return service, list(db.scalars(select(AlertCluster).where(
        AlertCluster.org_id == org.id,
        AlertCluster.correlation_version == CORRELATION_V2_VERSION,
        AlertCluster.status == "OPEN",
    )))


def _legacy_candidate_ids(db, service, org_id, roots):
    result = {}
    for root in roots:
        members = list(db.scalars(select(AlertClusterMembership).where(
            AlertClusterMembership.cluster_id == root.id,
            AlertClusterMembership.correlation_version == CORRELATION_V2_VERSION,
        )))
        result[root.id] = ([member.id for member in members], [service._alert(org_id, member.alert_id).id for member in members])
    return result


def test_candidate_bulk_read_matches_certified_per_cluster_traversal(db):
    org, connector = _scope(db)
    service, roots = _open_roots(db, org, connector, 4)
    expected = _legacy_candidate_ids(db, service, org.id, roots)
    members, alerts = service._candidate_read_maps(org.id, roots)
    actual = {
        root.id: ([member.id for member in members[root.id]], [alerts[member.alert_id].id for member in members[root.id]])
        for root in roots
    }
    assert actual == expected


@pytest.mark.parametrize("count", [1, 5, 10])
def test_candidate_bulk_read_has_constant_select_boundary(db, count):
    org, connector = _scope(db)
    service, roots = _open_roots(db, org, connector, count)
    statements = []
    engine = db.get_bind()

    def observe(_conn, _cursor, statement, _params, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(1)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        members, alerts = service._candidate_read_maps(org.id, roots)
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert len(statements) == 2
    assert sum(len(value) for value in members.values()) == count
    assert len(alerts) == count


def test_candidate_bulk_read_handles_no_open_cluster_without_querying(db):
    org, _connector = _scope(db)
    assert AlertCorrelationV2Service(db)._candidate_read_maps(org.id, []) == ({}, {})


def test_candidate_bulk_read_rejects_cross_org_alert_reference(db):
    org, connector = _scope(db)
    other_org, other_connector = _scope(db)
    foreign_alert = _alert(db, other_org, other_connector, 1)
    cluster = AlertCluster(
        org_id=org.id, identity_key=f"cross-org-{uuid4().hex}", correlation_version=CORRELATION_V2_VERSION,
        status="OPEN", first_seen=foreign_alert.observed_at, last_seen=foreign_alert.observed_at,
        member_count=1, source_diversity=1,
    )
    db.add(cluster)
    db.flush()
    db.add(AlertClusterMembership(
        org_id=org.id, cluster_id=cluster.id, alert_id=foreign_alert.id,
        correlation_version=CORRELATION_V2_VERSION, score=0, reasons=[], added_at=foreign_alert.observed_at,
    ))
    db.commit()
    with pytest.raises(NotFoundError, match="Canonical alert not found"):
        AlertCorrelationV2Service(db)._candidate_read_maps(org.id, [cluster])


def test_candidate_bulk_read_fails_closed_for_unavailable_alert_without_persisting_invalid_rows():
    org_id = uuid4()
    root = SimpleNamespace(id=uuid4())
    membership = SimpleNamespace(org_id=org_id, cluster_id=root.id, correlation_version=CORRELATION_V2_VERSION, alert_id=uuid4())

    class FakeDatabase:
        def __init__(self):
            self.rows = iter(([membership], []))

        def scalars(self, _statement):
            return next(self.rows)

    with pytest.raises(NotFoundError, match="Canonical alert not found"):
        AlertCorrelationV2Service(FakeDatabase())._candidate_read_maps(org_id, [root])
