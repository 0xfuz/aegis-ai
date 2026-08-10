"""Phase 7.6 HTTP generic webhook contract over real FastAPI routes."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis
from app.modules.alert_triage.infrastructure.models import AlertClusterAssessment, AlertClusterMembership, CanonicalAlert, CanonicalAlertOccurrence
from app.modules.connectors.infrastructure.models import Connector, RawEvent
from app.modules.evidence.infrastructure.models import Entity, EntityRelationship, Event, EvidenceItem, Indicator, RawRecord
from app.modules.identity.infrastructure.models import Organization
from app.modules.investigations.infrastructure.models import Finding, Investigation, MitreMapping
from app.shared.database import SessionLocal


@pytest.fixture()
def db():
    session = SessionLocal()
    try: yield session
    finally: session.rollback(); session.close()


def connector(db, suffix=None):
    from app.modules.connectors.domain.service import ConnectorService
    suffix = suffix or uuid4().hex
    org = Organization(name=f"Webhook {suffix}", slug=f"webhook-{suffix}"); db.add(org); db.commit()
    created = ConnectorService(db).create_webhook_connector(org.id, f"sensor-{suffix}", "http://testserver")
    db.commit()
    return org, created.connector, created.ingest_secret


def payload(identity="a", **changes):
    value = {"source": "suricata", "source_alert_id": identity, "observed_at": "2026-08-09T12:00:00Z",
        "title": "Suspicious network detection", "description": "untrusted <script>never execute</script>",
        "severity": "high", "category": "network", "rule_id": "rule-1", "source_ip": "198.51.100.22",
        "destination_ip": "203.0.113.20", "hostname": "web-01", "username": "admin", "process": "curl",
        "file": "/tmp/dropper", "domain": "example.test", "url": "https://example.test/path#fragment",
        "source_metadata": {"vendor": "generic", "note": "untrusted"}}
    value.update(changes); return value


def post(client, connector_id, secret, body, source="suricata", **kwargs):
    return client.post(f"/api/v1/ingest/alerts/v1/{connector_id}/{source}", json=body,
        headers={"X-Ingest-Secret": secret}, **kwargs)


def test_http_e2e_related_alerts_replay_and_no_investigation(db):
    org, row, secret = connector(db); client = TestClient(app)
    first = post(client, row.id, secret, payload("a")); second = post(client, row.id, secret, payload("b", rule_id="rule-2", observed_at="2026-08-09T12:00:10Z")); replay = post(client, row.id, secret, payload("a"))
    assert first.status_code == 201 and second.status_code == 201 and replay.status_code == 200
    assert first.json()["status"] == "accepted" and replay.json()["status"] == "replayed"
    assert first.json()["cluster_id"] == second.json()["cluster_id"] and second.json()["priority"] is not None
    assert db.scalar(select(func.count()).select_from(CanonicalAlert).where(CanonicalAlert.org_id == org.id)) == 2
    alert_id = first.json()["canonical_alert_id"]
    assert db.scalar(select(func.count()).select_from(CanonicalAlertOccurrence).where(CanonicalAlertOccurrence.canonical_alert_id == alert_id)) == 2
    assert db.scalar(select(func.count()).select_from(AlertClusterMembership).where(AlertClusterMembership.org_id == org.id)) == 2
    assert db.scalar(select(func.count()).select_from(AlertClusterAssessment).where(AlertClusterAssessment.org_id == org.id)) >= 1
    assert db.scalar(select(func.count()).select_from(Investigation).where(Investigation.org_id == org.id)) == 0


def test_provenance_semantic_dedupe_and_no_fact_or_ai_mutation(db):
    org, row, secret = connector(db); client = TestClient(app)
    models = (EvidenceItem, RawRecord, Event, Indicator, Entity, EntityRelationship, IntelligenceAnalysis, Finding, MitreMapping, Investigation)
    before = {model.__name__: db.scalar(select(func.count()).select_from(model).where(model.org_id == org.id)) for model in models}
    accepted = post(client, row.id, secret, payload("a")); duplicate = post(client, row.id, secret, payload("b", observed_at="2026-08-09T12:00:10Z"))
    after = {model.__name__: db.scalar(select(func.count()).select_from(model).where(model.org_id == org.id)) for model in models}
    alert = db.get(CanonicalAlert, accepted.json()["canonical_alert_id"]); raw = db.get(RawEvent, alert.raw_event_id)
    assert accepted.status_code == 201 and duplicate.status_code == 201 and duplicate.json()["deduplication_status"] == "SEMANTIC_DUPLICATE"
    assert raw.connector_id == row.id and raw.payload["description"] == payload()["description"] and alert.raw_event_id == raw.id
    assert after == before and db.scalar(select(func.count()).select_from(AlertClusterMembership).where(AlertClusterMembership.org_id == org.id)) == 1


@pytest.mark.parametrize("body, headers, expected", [
    (b"{bad", {"content-type": "application/json"}, 422),
    (None, {"content-type": "application/json"}, 422),
    (None, {"content-type": "text/plain"}, 422),
])
def test_rejects_malformed_timestamp_and_unsupported_content_type(db, body, headers, expected):
    _org, row, secret = connector(db); client = TestClient(app)
    if body is not None:
        response = client.post(f"/api/v1/ingest/alerts/v1/{row.id}/suricata", content=body, headers={**headers, "X-Ingest-Secret": secret})
    elif headers["content-type"] == "text/plain":
        response = client.post(f"/api/v1/ingest/alerts/v1/{row.id}/suricata", content=b"plain", headers={**headers, "X-Ingest-Secret": secret})
    else:
        response = post(client, row.id, secret, payload(observed_at="2026-08-09T12:00:00"))
    assert response.status_code == expected


def test_rejects_invalid_severity_oversize_auth_and_source_mismatch(db):
    _org, row, secret = connector(db); client = TestClient(app)
    assert post(client, row.id, secret, payload(severity="urgent")).status_code == 422
    oversized = b"x" * (256 * 1024 + 1)
    response = client.post(f"/api/v1/ingest/alerts/v1/{row.id}/suricata", content=oversized, headers={"X-Ingest-Secret": secret, "content-type": "application/json"})
    assert response.status_code == 422
    assert post(client, row.id, "wrong-secret", payload()).status_code == 401
    assert post(client, row.id, secret, payload(source="other"), source="suricata").status_code == 422
    db.get(Connector, row.id).is_active = False; db.commit()
    assert post(client, row.id, secret, payload()).status_code == 401


def test_connector_secret_scopes_each_organization(db):
    org_a, row_a, secret_a = connector(db); org_b, row_b, secret_b = connector(db); client = TestClient(app)
    assert post(client, row_a.id, secret_b, payload()).status_code == 401
    assert post(client, row_a.id, secret_a, payload()).status_code == 201
    assert post(client, row_b.id, secret_b, payload()).status_code == 201
    assert db.scalar(select(func.count()).select_from(CanonicalAlert).where(CanonicalAlert.org_id == org_a.id)) == 1
    assert db.scalar(select(func.count()).select_from(CanonicalAlert).where(CanonicalAlert.org_id == org_b.id)) == 1
