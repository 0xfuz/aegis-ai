"""Phase 7.8.2 Wazuh HTTP boundary: provenance, v2-only orchestration, safety."""
import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis
from app.modules.alert_triage.domain.correlation_service import CORRELATION_VERSION
from app.modules.alert_triage.domain.correlation_v2_service import CORRELATION_V2_VERSION
from app.modules.alert_triage.infrastructure.models import AlertClusterAssessment, AlertClusterMembership, CanonicalAlert, CanonicalAlertOccurrence
from app.modules.connectors.domain.service import ConnectorService
from app.modules.connectors.infrastructure.models import Connector, RawEvent
from app.modules.evidence.infrastructure.models import Entity, EntityRelationship, Event, EvidenceItem, Indicator, RawRecord
from app.modules.identity.infrastructure.models import Organization
from app.modules.investigations.infrastructure.models import Finding, Investigation, MitreMapping
from app.shared.database import SessionLocal

FIXTURES = Path(__file__).parent / "fixtures" / "wazuh"

@pytest.fixture()
def db():
    session = SessionLocal()
    try: yield session
    finally: session.rollback(); session.close()

def setup(db):
    suffix = uuid4().hex; org = Organization(name=f"Wazuh {suffix}", slug=f"wazuh-{suffix}"); db.add(org); db.commit()
    created = ConnectorService(db).create_webhook_connector(org.id, f"wazuh-{suffix}", "http://testserver"); db.commit()
    return org, created.connector, created.ingest_secret

def payload(name): return json.loads((FIXTURES / name).read_text())
def post(client, connector, secret, body, **kwargs):
    return client.post(f"/api/v1/ingest/wazuh/v1/{connector.id}", json=body, headers={"X-Ingest-Secret": secret}, **kwargs)

@pytest.mark.parametrize("name", ["windows_authentication.json", "linux_process.json", "network_event.json", "file_integrity.json", "sparse_valid.json"])
def test_supported_wazuh_fixtures_ingest_to_v2_and_triage(db, name):
    org, connector, secret = setup(db); response = post(TestClient(app), connector, secret, payload(name))
    assert response.status_code == 201 and response.json()["correlation_version"] == CORRELATION_V2_VERSION and response.json()["priority"]
    assert db.scalar(select(func.count()).select_from(AlertClusterMembership).where(AlertClusterMembership.org_id == org.id, AlertClusterMembership.correlation_version == CORRELATION_V2_VERSION)) == 1
    assert db.scalar(select(func.count()).select_from(AlertClusterMembership).where(AlertClusterMembership.org_id == org.id, AlertClusterMembership.correlation_version == CORRELATION_VERSION)) == 0

def test_raw_provenance_mitre_replay_and_no_authority_side_effects(db):
    org, connector, secret = setup(db); client = TestClient(app); body = payload("mitre_metadata.json")
    models = [Investigation, EvidenceItem, RawRecord, Event, Indicator, Entity, EntityRelationship, IntelligenceAnalysis, Finding, MitreMapping]
    before = {m.__name__: db.scalar(select(func.count()).select_from(m).where(m.org_id == org.id)) for m in models}
    first = post(client, connector, secret, body); replay = post(client, connector, secret, body)
    alert = db.get(CanonicalAlert, first.json()["canonical_alert_id"]); raw = db.get(RawEvent, alert.raw_event_id)
    after = {m.__name__: db.scalar(select(func.count()).select_from(m).where(m.org_id == org.id)) for m in models}
    assert first.status_code == 201 and replay.status_code == 200 and replay.json()["status"] == "replayed"
    assert raw.payload == body and alert.source_metadata["wazuh"]["mitre"]["id"] == ["T1543.003"] and after == before
    assert db.scalar(select(func.count()).select_from(CanonicalAlertOccurrence).where(CanonicalAlertOccurrence.canonical_alert_id == alert.id)) == 2
    assert db.scalar(select(func.count()).select_from(AlertClusterAssessment).where(AlertClusterAssessment.org_id == org.id)) == 1

def test_auth_tenant_boundary_and_invalid_requests(db):
    org, connector, secret = setup(db); other, other_connector, other_secret = setup(db); client = TestClient(app)
    body = payload("sparse_valid.json"); body["organization_id"] = str(other.id)
    assert post(client, connector, secret, body).status_code == 201
    assert post(client, connector, other_secret, {**body, "id": "second"}).status_code == 401
    assert db.scalar(select(func.count()).select_from(CanonicalAlert).where(CanonicalAlert.org_id == org.id)) == 1
    assert post(client, connector, "wrong", body).status_code == 401
    assert client.post(f"/api/v1/ingest/wazuh/v1/{connector.id}", content=b"{bad", headers={"X-Ingest-Secret": secret, "content-type": "application/json"}).status_code == 422
    assert client.post(f"/api/v1/ingest/wazuh/v1/{connector.id}", content=b"plain", headers={"X-Ingest-Secret": secret, "content-type": "text/plain"}).status_code == 422
    bad = payload("sparse_valid.json"); bad.pop("id"); assert post(client, connector, secret, bad).status_code == 422
    bad = payload("sparse_valid.json"); bad["timestamp"] = "bad"; assert post(client, connector, secret, bad).status_code == 422

def test_oversize_inactive_and_semantic_duplicate(db):
    org, connector, secret = setup(db); client = TestClient(app)
    assert client.post(f"/api/v1/ingest/wazuh/v1/{connector.id}", content=b"x" * (256 * 1024 + 1), headers={"X-Ingest-Secret": secret, "content-type": "application/json"}).status_code == 422
    db.get(Connector, connector.id).is_active = False; db.commit(); assert post(client, connector, secret, payload("sparse_valid.json")).status_code == 401
