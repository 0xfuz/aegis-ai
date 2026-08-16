"""PostgreSQL-backed contracts for bounded Investigation notes."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import create_access_token
from app.main import app
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis, IntelligenceItem
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.infrastructure.models import Finding, Investigation, InvestigationStatus, MitreMapping, Note, RecommendedAction, Severity
from app.shared.database import SessionLocal


@pytest.fixture()
def db():
    session = SessionLocal()
    try: yield session
    finally: session.rollback(); session.close()


def scope(db):
    suffix = uuid4().hex
    org = Organization(name=f"Notes {suffix}", slug=f"notes-{suffix}")
    role = Role(name=f"notes-role-{suffix}")
    db.add_all((org, role)); db.flush()
    user = User(org_id=org.id, role_id=role.id, email=f"{suffix}@notes.test", hashed_password="x", full_name="Analyst")
    inv = Investigation(org_id=org.id, title="Notes", source="test", severity=Severity.LOW, status=InvestigationStatus.NEW)
    db.add_all((user, inv)); db.commit()
    return org, user, inv


def auth(user, org, permissions):
    return {"Authorization": f"Bearer {create_access_token(user.id, org.id, 'analyst', permissions)}"}


def path(inv, suffix=""):
    return f"/api/v1/investigations/{inv.id}/notes{suffix}"


def test_notes_list_is_scoped_bounded_and_deterministic(db):
    org, user, inv = scope(db); other_org, other_user, other_inv = scope(db)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = Note(investigation_id=inv.id, author_id=user.id, body="first", created_at=now, updated_at=now)
    second = Note(investigation_id=inv.id, author_id=user.id, body="<img src=x onerror=alert(1)>", created_at=now, updated_at=now)
    db.add_all((first, second)); db.commit()
    client = TestClient(app); read = auth(user, org, ["investigation:read"])
    response = client.get(path(inv, "?limit=1&offset=0"), headers=read)
    assert response.status_code == 200
    body = response.json(); assert body["total"] == 2 and body["limit"] == 1 and body["offset"] == 0
    assert body["items"][0]["id"] == str(max((first.id, second.id), key=str))
    assert set(body["items"][0]) == {"id", "author_id", "body", "created_at", "updated_at"}
    assert client.get(path(other_inv), headers=read).status_code == 404
    assert client.get(path(inv, "?limit=0"), headers=read).status_code == 422
    assert client.get(path(inv, "?offset=-1"), headers=read).status_code == 422
    assert client.get(path(inv, f"?org_id={org.id}"), headers=read).status_code == 422
    assert client.get("/api/v1/investigations/not-a-uuid/notes", headers=read).status_code == 422


def test_notes_create_uses_principal_and_rejects_unsafe_requests(db):
    org, user, inv = scope(db); client = TestClient(app)
    read = auth(user, org, ["investigation:read"]); write = auth(user, org, ["investigation:write"])
    assert client.post(path(inv), json={"body": "note"}, headers=read).status_code == 403
    created = client.post(path(inv), json={"body": "  persisted note\nsecond line  "}, headers=write)
    assert created.status_code == 200
    assert set(created.json()) == {"id", "author_id", "body", "created_at", "updated_at"}
    note = db.scalar(select(Note).where(Note.investigation_id == inv.id))
    assert note.author_id == user.id and note.body == "persisted note\nsecond line"
    for payload in ({"body": "   "}, {"body": "x" * 4001}, {"body": "note", "org_id": str(uuid4())}, {"body": "note", "actor_id": str(uuid4())}):
        assert client.post(path(inv), json=payload, headers=write).status_code == 422
    user.is_active = False; db.commit()
    assert client.post(path(inv), json={"body": "blocked"}, headers=write).status_code == 404


def test_notes_are_the_only_persisted_effect(db):
    org, user, inv = scope(db)
    response = TestClient(app).post(path(inv), json={"body": "safe"}, headers=auth(user, org, ["investigation:write"]))
    assert response.status_code == 200
    assert len(db.scalars(select(Note).where(Note.investigation_id == inv.id)).all()) == 1
    assert db.scalars(select(IntelligenceAnalysis).where(IntelligenceAnalysis.org_id == org.id)).first() is None
    assert db.scalars(select(IntelligenceItem).where(IntelligenceItem.org_id == org.id)).first() is None
    assert db.scalars(select(Finding).where(Finding.org_id == org.id)).first() is None
    assert db.scalars(select(MitreMapping).where(MitreMapping.org_id == org.id)).first() is None
    assert db.scalars(select(RecommendedAction).where(RecommendedAction.investigation_id == inv.id)).first() is None
