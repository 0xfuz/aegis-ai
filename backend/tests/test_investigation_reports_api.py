"""PostgreSQL-backed authorization and response contracts for reports."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.infrastructure.models import Investigation, InvestigationStatus, Severity
from app.shared.database import SessionLocal


@pytest.fixture()
def db():
    session = SessionLocal()
    try: yield session
    finally: session.rollback(); session.close()


def scope(db):
    value = uuid4().hex
    org = Organization(name=f"Reports {value}", slug=f"reports-{value}")
    role = Role(name=f"reports-role-{value}")
    db.add_all((org, role)); db.flush()
    user = User(org_id=org.id, role_id=role.id, email=f"{value}@reports.test", hashed_password="x", full_name="Reports analyst")
    inv = Investigation(org_id=org.id, title='Hostile / "title" <script>', source="test", severity=Severity.LOW, status=InvestigationStatus.NEW)
    db.add_all((user, inv)); db.commit()
    return org, user, inv


def auth(user, org, permissions):
    return {"Authorization": f"Bearer {create_access_token(user.id, org.id, 'analyst', permissions)}"}


def url(inv, query=""):
    return f"/api/v1/investigations/{inv.id}/report{query}"


def test_authorized_report_is_scoped_and_has_safe_download_headers(db):
    org, user, inv = scope(db)
    response = TestClient(app).get(url(inv, "?type=technical&format=markdown"), headers=auth(user, org, ["reports:generate_technical"]))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    disposition = response.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="technical-report-')
    assert "/" not in disposition and "<" not in disposition and '"title' not in disposition
    assert b"Hostile" in response.content


def test_report_rejects_inactive_foreign_invalid_and_injected_requests(db):
    org, user, inv = scope(db); other_org, other_user, other_inv = scope(db); client = TestClient(app)
    technical = auth(user, org, ["reports:generate_technical"])
    assert client.get(url(other_inv), headers=technical).status_code == 404
    assert client.get(url(inv, "?type=executive"), headers=technical).status_code == 403
    assert client.get(url(inv, "?type=unknown"), headers=technical).status_code == 422
    assert client.get(url(inv, "?format=html"), headers=technical).status_code == 422
    assert client.get(url(inv, "?org_id=forged"), headers=technical).status_code == 422
    assert client.get("/api/v1/investigations/not-a-uuid/report", headers=technical).status_code == 422
    user.is_active = False; db.commit()
    assert client.get(url(inv), headers=technical).status_code == 404
    assert client.get(url(other_inv), headers=auth(other_user, other_org, [])).status_code == 403


def test_report_generation_has_no_authority_side_effects(db):
    org, user, inv = scope(db)
    before = (len(db.identity_map), inv.updated_at)
    response = TestClient(app).get(url(inv, "?type=executive&format=pdf"), headers=auth(user, org, ["reports:generate_executive"]))
    db.refresh(inv)
    assert response.status_code == 200 and response.headers["content-type"].startswith("application/pdf")
    assert inv.updated_at == before[1]
