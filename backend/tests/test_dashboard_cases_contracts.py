"""PostgreSQL contracts for bounded organization-scoped Dashboard and Cases reads."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.main import app
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis, IntelligenceItem
from app.modules.alert_triage.infrastructure.models import AlertClusterMembership
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.infrastructure.models import Finding, Investigation, InvestigationStatus, MitreMapping, Note, RecommendedAction, Severity
from app.shared.database import SessionLocal


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def make_scope(db):
    suffix = uuid4().hex
    org = Organization(name=f"Operations {suffix}", slug=f"operations-{suffix}")
    role = Role(name=f"operations-role-{suffix}")
    db.add_all((org, role))
    db.flush()
    user = User(org_id=org.id, role_id=role.id, email=f"{suffix}@operations.test", hashed_password="x", full_name="Analyst")
    db.add(user)
    db.commit()
    return org, user


def create_case(db, org, title, created_at, status=InvestigationStatus.NEW, severity=Severity.LOW, fp=0):
    case = Investigation(
        org_id=org.id, title=title, source="contract", severity=severity, status=status,
        confidence=0, false_positive_probability=fp, created_at=created_at, updated_at=created_at,
    )
    db.add(case)
    db.flush()
    return case


def headers(user, org, permissions=("investigation:read",)):
    return {"Authorization": f"Bearer {create_access_token(user.id, org.id, 'analyst', list(permissions))}"}


def test_dashboard_scopes_all_aggregates_to_inclusive_exclusive_utc_window(db):
    org, user = make_scope(db)
    foreign_org, _ = make_scope(db)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    create_case(db, org, "at-start", start, severity=Severity.CRITICAL, fp=10)
    create_case(db, org, "inside", start + timedelta(hours=1), status=InvestigationStatus.RESOLVED, fp=30)
    create_case(db, org, "at-end", start + timedelta(days=1), severity=Severity.CRITICAL, fp=90)
    create_case(db, foreign_org, "foreign", start + timedelta(hours=1), severity=Severity.CRITICAL, fp=100)
    db.commit()
    client = TestClient(app)
    response = client.get(
        "/api/v1/investigations/dashboard-summary?from=2026-01-01T00:00:00%2B00:00&to=2026-01-02T00:00:00%2B00:00",
        headers=headers(user, org),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_investigations"] == 2
    assert body["open_investigations"] == 1
    assert body["critical_open"] == 1
    assert body["avg_false_positive_probability"] == 20.0
    assert body["window"] == {"preset": None, "from_at": "2026-01-01T00:00:00Z", "to_at": "2026-01-02T00:00:00Z"}
    assert client.get("/api/v1/investigations/dashboard-summary?window=24h", headers=headers(user, org)).status_code == 200
    for query in ("window=bad", "from=2026-01-01T00:00:00", "from=2026-01-02T00:00:00%2B00:00&to=2026-01-01T00:00:00%2B00:00", "from=2026-01-01T00:00:00%2B00:00", "window=24h&from=2026-01-01T00:00:00%2B00:00&to=2026-01-02T00:00:00%2B00:00", "from=2026-01-01T00:00:00%2B00:00&to=2026-04-02T00:00:01%2B00:00", "org_id=x"):
        assert client.get(f"/api/v1/investigations/dashboard-summary?{query}", headers=headers(user, org)).status_code == 422
    empty = client.get("/api/v1/investigations/dashboard-summary?from=2025-01-01T00:00:00%2B00:00&to=2025-01-02T00:00:00%2B00:00", headers=headers(user, org))
    assert empty.status_code == 200 and empty.json()["total_investigations"] == 0
    assert response.json() == client.get("/api/v1/investigations/dashboard-summary?from=2026-01-01T00:00:00%2B00:00&to=2026-01-02T00:00:00%2B00:00", headers=headers(user, org)).json()


def test_cases_are_deterministic_bounded_scoped_and_read_only(db):
    org, user = make_scope(db)
    foreign_org, foreign_user = make_scope(db)
    now = datetime(2026, 2, 1, tzinfo=timezone.utc)
    first = create_case(db, org, "first", now)
    second = create_case(db, org, "second", now)
    resolved = create_case(db, org, "resolved", now - timedelta(seconds=1), status=InvestigationStatus.RESOLVED)
    foreign = create_case(db, foreign_org, "foreign", now + timedelta(days=1))
    db.commit()
    client = TestClient(app)
    response = client.get("/api/v1/investigations?limit=1&offset=0", headers=headers(user, org))
    assert response.status_code == 200
    page = response.json()
    assert page["total"] == 3 and page["returned_count"] == 1 and page["limit"] == 1 and page["offset"] == 0
    assert page["items"][0]["id"] == str(max((first.id, second.id), key=str))
    following = client.get("/api/v1/investigations?limit=1&offset=1", headers=headers(user, org)).json()
    assert following["items"][0]["id"] != page["items"][0]["id"]
    filtered = client.get("/api/v1/investigations?status=resolved", headers=headers(user, org)).json()
    assert [item["id"] for item in filtered["items"]] == [str(resolved.id)]
    assert client.get("/api/v1/investigations?status=unknown", headers=headers(user, org)).status_code == 422
    for query in ("limit=0", "limit=201", "offset=-1", "status=", "org_id=x", "actor_id=x"):
        assert client.get(f"/api/v1/investigations?{query}", headers=headers(user, org)).status_code == 422
    assert client.get("/api/v1/investigations", headers=headers(foreign_user, foreign_org)).json()["total"] == 1
    assert foreign.id not in {item["id"] for item in page["items"]}
    user.is_active = False
    db.commit()
    assert client.get("/api/v1/investigations", headers=headers(user, org)).status_code == 404


def test_dashboard_and_cases_reads_create_no_authority_side_effects(db):
    org, user = make_scope(db)
    create_case(db, org, "only", datetime(2026, 1, 1, tzinfo=timezone.utc))
    db.commit()
    client = TestClient(app)
    before = {
        "investigations": db.scalar(select(func.count()).select_from(Investigation).where(Investigation.org_id == org.id)),
        "notes": db.scalar(select(func.count()).select_from(Note)),
        "analyses": db.scalar(select(func.count()).select_from(IntelligenceAnalysis).where(IntelligenceAnalysis.org_id == org.id)),
        "items": db.scalar(select(func.count()).select_from(IntelligenceItem).where(IntelligenceItem.org_id == org.id)),
        "findings": db.scalar(select(func.count()).select_from(Finding).where(Finding.org_id == org.id)),
        "mitre": db.scalar(select(func.count()).select_from(MitreMapping).where(MitreMapping.org_id == org.id)),
        "memberships": db.scalar(select(func.count()).select_from(AlertClusterMembership)),
        "actions": db.scalar(select(func.count()).select_from(RecommendedAction)),
    }
    assert client.get("/api/v1/investigations", headers=headers(user, org)).status_code == 200
    assert client.get("/api/v1/investigations/dashboard-summary", headers=headers(user, org)).status_code == 200
    after = {
        "investigations": db.scalar(select(func.count()).select_from(Investigation).where(Investigation.org_id == org.id)),
        "notes": db.scalar(select(func.count()).select_from(Note)),
        "analyses": db.scalar(select(func.count()).select_from(IntelligenceAnalysis).where(IntelligenceAnalysis.org_id == org.id)),
        "items": db.scalar(select(func.count()).select_from(IntelligenceItem).where(IntelligenceItem.org_id == org.id)),
        "findings": db.scalar(select(func.count()).select_from(Finding).where(Finding.org_id == org.id)),
        "mitre": db.scalar(select(func.count()).select_from(MitreMapping).where(MitreMapping.org_id == org.id)),
        "memberships": db.scalar(select(func.count()).select_from(AlertClusterMembership)),
        "actions": db.scalar(select(func.count()).select_from(RecommendedAction)),
    }
    assert after == before
