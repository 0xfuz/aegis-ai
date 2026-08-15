"""PostgreSQL contract tests for the bounded alert-triage read/promotion API."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.main import app
from app.modules.alert_triage.domain.correlation_service import AlertCorrelationService, CORRELATION_VERSION
from app.modules.alert_triage.domain.correlation_v2_service import AlertCorrelationV2Service, CORRELATION_V2_VERSION
from app.modules.alert_triage.domain.read_service import AlertClusterTriageReadService
from app.modules.alert_triage.domain.service import CanonicalAlertCreate, CanonicalAlertService
from app.modules.alert_triage.domain.triage_service import AlertClusterTriageService
from app.modules.alert_triage.infrastructure.models import AlertCluster, AlertClusterMembership, AlertClusterPromotion
from app.modules.connectors.infrastructure.models import Connector, RawEvent
from app.modules.identity.infrastructure.models import Organization, Role, User
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
    org = Organization(name=f"Triage {suffix}", slug=f"triage-{suffix}")
    role = Role(name=f"triage-role-{suffix}")
    db.add_all([org, role]); db.flush()
    user = User(org_id=org.id, role_id=role.id, email=f"{suffix}@test.invalid", hashed_password="x", full_name="Analyst")
    connector = Connector(org_id=org.id, name=f"sensor-{suffix}", type="webhook", secret_hash="x")
    db.add_all([user, connector]); db.commit()
    return org, user, connector


def add_alert(db, org, connector, source_id, observed):
    raw = RawEvent(connector_id=connector.id, received_at=datetime.now(timezone.utc), payload={"source": source_id})
    db.add(raw); db.commit()
    return CanonicalAlertService(db).create(org.id, connector.id, raw.id, CanonicalAlertCreate(
        source="test", source_alert_id=source_id, observed_at=observed, title="safe title", description="<script>inert</script>",
        severity="HIGH", category="network", rule_id="rule", observables={"hostname": "host-a", "source_ip": "198.51.100.4"}, source_metadata={},
    ))[0]


def triaged_v2(db):
    org, user, connector = setup(db); now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = add_alert(db, org, connector, "one", now); second = add_alert(db, org, connector, "two", now + timedelta(seconds=1))
    cluster = AlertCorrelationV2Service(db).process(org.id, first.id)
    cluster = AlertCorrelationV2Service(db).process(org.id, second.id)
    assessment = AlertClusterTriageService(db).assess(org.id, cluster.id, now + timedelta(minutes=10))
    return org, user, connector, cluster, assessment, first


def auth(user, org, permissions=("investigation:read",)):
    token = create_access_token(user.id, org.id, "analyst", list(permissions))
    return {"Authorization": f"Bearer {token}"}


def test_read_service_is_tenant_scoped_version_exact_and_stably_paginated(db):
    org, user, connector, cluster, assessment, alert = triaged_v2(db)
    # A malformed historical row is deliberately not projected because the
    # cluster's authoritative version is v2.
    db.add(AlertClusterMembership(org_id=org.id, cluster_id=cluster.id, alert_id=alert.id, candidate_alert_id=None,
        correlation_version=CORRELATION_VERSION, score=1, reasons=[], added_at=datetime.now(timezone.utc)))
    db.commit()
    detail = AlertClusterTriageReadService(db).get(org.id, cluster.id)
    assert detail["correlation_version"] == CORRELATION_V2_VERSION
    assert detail["triage"] == {"id": str(assessment.id), "priority": assessment.priority, "score": assessment.score, "version": assessment.scoring_version}
    assert detail["promotion_eligible"] and detail["promotion_reason"] == "ELIGIBLE"
    assert detail["members"] and {row["score"] for row in detail["members"]} != {1}
    assert AlertClusterTriageReadService(db).list(org.id, 1, 0) == AlertClusterTriageReadService(db).list(org.id, 1, 0)
    other_org, _other_user, _other_connector = setup(db)
    assert AlertClusterTriageReadService(db).list(other_org.id, 100, 0) == []


def test_api_enforces_permissions_scope_pagination_and_strict_body(db):
    org, user, _connector, cluster, _assessment, _alert = triaged_v2(db)
    other_org, other_user, _ = setup(db)
    client = TestClient(app)
    assert client.get("/api/v1/alert-triage/clusters?limit=1&offset=0", headers=auth(user, org)).status_code == 200
    assert client.get(f"/api/v1/alert-triage/clusters/{cluster.id}", headers=auth(user, org)).json()["id"] == str(cluster.id)
    assert client.get(f"/api/v1/alert-triage/clusters/{cluster.id}", headers=auth(other_user, other_org)).status_code == 404
    assert client.get("/api/v1/alert-triage/clusters?limit=101", headers=auth(user, org)).status_code == 422
    assert client.get("/api/v1/alert-triage/clusters/not-a-uuid", headers=auth(user, org)).status_code == 422
    assert client.get("/api/v1/alert-triage/clusters", headers=auth(user, org, ())).status_code == 403
    injected = {"org_id": str(other_org.id), "actor_id": str(other_user.id), "investigation_id": str(uuid4()), "correlation_version": "anything", "triage": {}, "status": "COMPLETED", "membership_id": str(uuid4())}
    assert client.post(f"/api/v1/alert-triage/clusters/{cluster.id}/promote", json=injected, headers=auth(user, org, ("investigation:write",))).status_code == 422


def test_api_promotion_is_idempotent_and_principal_derived(db):
    org, user, _connector, cluster, _assessment, _alert = triaged_v2(db)
    client = TestClient(app)
    headers = auth(user, org, ("investigation:read", "investigation:write"))
    first = client.post(f"/api/v1/alert-triage/clusters/{cluster.id}/promote", json={}, headers=headers)
    second = client.post(f"/api/v1/alert-triage/clusters/{cluster.id}/promote", json={}, headers=headers)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["created"] is True and second.json()["created"] is False
    assert first.json()["promotion_id"] == second.json()["promotion_id"]
    assert db.scalar(select(func.count()).select_from(AlertClusterPromotion).where(AlertClusterPromotion.org_id == org.id, AlertClusterPromotion.cluster_id == cluster.id)) == 1


def test_unsupported_version_is_read_only_and_route_surface_is_bounded(db):
    org, user, connector = setup(db); now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    alert = add_alert(db, org, connector, "unsupported", now)
    cluster_read = AlertCorrelationService(db).process(org.id, alert.id)
    cluster = db.get(AlertCluster, cluster_read.id)
    cluster.correlation_version = "correlation-unknown"; db.commit()
    projection = AlertClusterTriageReadService(db).get(org.id, cluster.id)
    assert projection["promotion_eligible"] is False and projection["promotion_reason"] == "CORRELATION_VERSION_UNSUPPORTED"
    paths = {route.path for route in app.routes}
    assert "/api/v1/alert-triage/clusters" in paths
    assert "/api/v1/alert-triage/clusters/{cluster_id}" in paths
    assert "/api/v1/alert-triage/clusters/{cluster_id}/promote" in paths
    assert not any("alert-triage" in path and any(word in path for word in ("acquire", "heartbeat", "complete", "provider")) for path in paths)
    assert db.scalar(select(func.count()).select_from(AlertClusterPromotion).where(AlertClusterPromotion.org_id == org.id)) == 0
