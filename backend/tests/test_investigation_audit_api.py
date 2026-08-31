"""PostgreSQL-backed contract tests for the bounded Investigation audit feed."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from app.modules.evidence.infrastructure.models import AuditEvent
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.infrastructure.models import Investigation, InvestigationStatus, Severity
from app.shared.database import SessionLocal


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def scope(db):
    suffix = uuid4().hex
    org = Organization(name=f"Audit {suffix}", slug=f"audit-{suffix}")
    role = Role(name=f"audit-role-{suffix}")
    db.add_all((org, role)); db.flush()
    user = User(org_id=org.id, role_id=role.id, email=f"{suffix}@audit.test", hashed_password="x", full_name="Audit analyst")
    investigation = Investigation(org_id=org.id, title="Audit case", source="test", severity=Severity.LOW, status=InvestigationStatus.NEW)
    db.add_all((user, investigation)); db.commit()
    return org, user, investigation


def headers(user, org, permissions=("investigation:read",)):
    return {"Authorization": f"Bearer {create_access_token(user.id, org.id, 'analyst', permissions)}"}


def add_event(db, org, investigation, actor, action, occurred_at, metadata=None, rationale=None):
    row = AuditEvent(org_id=org.id, investigation_id=investigation.id, actor_id=actor.id, actor_type="user", action=action, target_type="IntelligenceItem", target_id=uuid4(), occurred_at=occurred_at, metadata_=metadata, rationale=rationale)
    db.add(row); db.flush()
    return row


def endpoint(investigation, suffix=""):
    return f"/api/v1/investigations/{investigation.id}/audit{suffix}"


def test_audit_is_bounded_deterministic_and_safe(db):
    org, user, investigation = scope(db)
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    older = add_event(db, org, investigation, user, "INTELLIGENCE_ITEM_REVIEWED", timestamp, {"previous": "PENDING", "status": "UNRESOLVED", "secret": "never-return"}, "do not return this")
    newer = add_event(db, org, investigation, user, "INTELLIGENCE_RUN_COMPLETED", timestamp + timedelta(seconds=1), {"status": "COMPLETED", "candidate_fingerprint": "not-returned"}, "also private")
    db.commit()
    response = TestClient(app).get(endpoint(investigation, "?limit=1&offset=0"), headers=headers(user, org))
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2 and body["limit"] == 1 and body["offset"] == 0
    assert body["items"][0]["id"] == str(newer.id)
    assert set(body["items"][0]) == {"id", "event_type", "occurred_at", "actor", "target", "transition"}
    assert body["items"][0]["transition"] == {"from": None, "to": "COMPLETED"}
    assert "private" not in str(body) and "never-return" not in str(body) and "candidate_fingerprint" not in str(body)
    second = TestClient(app).get(endpoint(investigation, "?limit=1&offset=1"), headers=headers(user, org)).json()
    assert second["items"][0]["id"] == str(older.id)
    assert second["items"][0]["transition"] == {"from": "PENDING", "to": "UNRESOLVED"}


def test_audit_enforces_active_read_scope_and_anti_enumeration(db):
    org, user, investigation = scope(db)
    other_org, other_user, other_investigation = scope(db)
    client = TestClient(app)
    assert client.get(endpoint(investigation), headers=headers(user, org, ())).status_code == 403
    assert client.get(endpoint(other_investigation), headers=headers(user, org)).status_code == 404
    user.is_active = False; db.commit()
    assert client.get(endpoint(investigation), headers=headers(user, org)).status_code == 404
    assert client.get("/api/v1/investigations/not-a-uuid/audit", headers=headers(other_user, other_org)).status_code == 422
    assert client.get(endpoint(other_investigation, "?limit=0"), headers=headers(other_user, other_org)).status_code == 422
    assert client.get(endpoint(other_investigation, "?offset=-1"), headers=headers(other_user, other_org)).status_code == 422
