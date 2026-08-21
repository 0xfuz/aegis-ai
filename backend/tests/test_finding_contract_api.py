"""PostgreSQL-backed contracts for bounded, analyst-owned Findings."""
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.main import app
from app.modules.ai_reasoning.domain.intelligence_service import InvestigationIntelligenceService
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis, IntelligenceClaimEvidenceLink, IntelligenceEvidenceReference, IntelligenceItem
from app.modules.evidence.infrastructure.models import AuditEvent
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.domain.finding_service import FindingService
from app.modules.investigations.infrastructure.models import Finding, Investigation, InvestigationStatus, MitreMapping, RecommendedAction, Severity
from app.shared.database import SessionLocal
from app.shared.exceptions import ValidationError


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def scope(db, label="finding"):
    suffix = uuid4().hex
    compact = label[:8]
    org = Organization(name=f"{compact} {suffix}", slug=f"{compact}-{suffix}")
    role = Role(name=f"{compact}-{suffix[:12]}")
    db.add_all((org, role)); db.flush()
    user = User(org_id=org.id, role_id=role.id, email=f"{suffix}@finding.test", hashed_password="x", full_name="Analyst")
    inv = Investigation(org_id=org.id, title=f"{label} case", source="test", severity=Severity.LOW, status=InvestigationStatus.NEW)
    db.add_all((user, inv)); db.commit()
    return org, user, inv


def headers(user, org, permissions):
    return {"Authorization": f"Bearer {create_access_token(user.id, org.id, 'analyst', permissions)}"}


def list_path(inv, suffix=""):
    return f"/api/v1/investigations/{inv.id}/findings{suffix}"


def status_path(finding):
    return f"/api/v1/investigations/findings/{finding.id}/status"


def add_finding(db, org, inv, user, title, created_at, status="OPEN"):
    row = Finding(org_id=org.id, investigation_id=inv.id, analyst_id=user.id, title=title, description=f"{title} detail", severity="medium", confidence=70, status=status, created_at=created_at, updated_at=created_at)
    db.add(row); db.flush()
    return row


def test_list_is_scoped_paginated_deterministic_and_safe(db):
    org, user, inv = scope(db)
    other_org, _other_user, other_inv = scope(db, "other-finding")
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = add_finding(db, org, inv, user, "first", timestamp)
    second = add_finding(db, org, inv, user, "<img src=x onerror=alert(1)>", timestamp)
    confirmed = add_finding(db, org, inv, user, "confirmed", timestamp, "CONFIRMED")
    add_finding(db, other_org, other_inv, user, "foreign", timestamp)
    db.commit()

    client = TestClient(app)
    read = headers(user, org, ["investigation:read"])
    response = client.get(list_path(inv, "?limit=2&offset=0"), headers=read)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3 and body["returned_count"] == 2 and body["limit"] == 2 and body["offset"] == 0
    expected = [str(row.id) for row in sorted((first, second, confirmed), key=lambda row: str(row.id), reverse=True)[:2]]
    assert [item["id"] for item in body["items"]] == expected
    assert set(body["items"][0]) == {"id", "title", "description", "severity", "confidence", "status", "created_at", "updated_at", "provenance", "fact_links"}
    full_body = client.get(list_path(inv, "?limit=3"), headers=read).json()
    assert "<img" in str(full_body) and "raw_record" not in str(full_body).lower()
    assert client.get(list_path(inv, "?status=CONFIRMED"), headers=read).json()["total"] == 1
    assert client.get(list_path(other_inv), headers=read).status_code == 404
    for suffix in ("?limit=0", "?offset=-1", "?status=UNKNOWN", "?org_id=forged", "?limit=1&actor_id=forged"):
        assert client.get(list_path(inv, suffix), headers=read).status_code == 422
    assert client.get("/api/v1/investigations/not-a-uuid/findings", headers=read).status_code == 422


def test_list_and_review_enforce_active_principal_and_permissions(db):
    org, user, inv = scope(db)
    other_org, other_user, other_inv = scope(db, "foreign")
    finding = add_finding(db, org, inv, user, "reviewable", datetime.now(timezone.utc)); db.commit()
    foreign = add_finding(db, other_org, other_inv, other_user, "foreign", datetime.now(timezone.utc)); db.commit()
    client = TestClient(app)
    assert client.get(list_path(inv), headers=headers(user, org, [])).status_code == 403
    assert client.post(status_path(finding), json={"status": "CONFIRMED"}, headers=headers(user, org, ["investigation:read"])).status_code == 403
    assert client.post(status_path(finding), json={"status": "CONFIRMED"}, headers=headers(user, org, ["investigation:write"])).status_code == 200
    assert client.post(status_path(foreign), json={"status": "CONFIRMED"}, headers=headers(user, org, ["investigation:write"])).status_code == 404
    user.is_active = False; db.commit()
    assert client.get(list_path(inv), headers=headers(user, org, ["investigation:read"])).status_code == 404
    assert client.post(status_path(finding), json={"status": "RESOLVED"}, headers=headers(user, org, ["investigation:write"])).status_code == 404


def test_review_transitions_are_strict_atomic_and_audited_once(db, monkeypatch):
    org, user, inv = scope(db)
    finding = add_finding(db, org, inv, user, "reviewable", datetime.now(timezone.utc)); db.commit()
    client = TestClient(app); write = headers(user, org, ["investigation:write"])
    for body in (
        {"status": "CONFIRMED", "org_id": str(uuid4())},
        {"status": "CONFIRMED", "actor_id": str(uuid4())},
        {"status": "CONFIRMED", "origin": "AI"},
        {"status": "CONFIRMED", "provenance": {}},
        {"status": "CONFIRMED", "source_intelligence_item_id": str(uuid4())},
    ):
        assert client.post(status_path(finding), json=body, headers=write).status_code == 422
    assert client.post(status_path(finding), json={"status": "INVALID"}, headers=write).status_code == 422
    prohibited = (IntelligenceAnalysis, IntelligenceItem, IntelligenceEvidenceReference, IntelligenceClaimEvidenceLink, MitreMapping, RecommendedAction)
    scope_filter = lambda model: model.investigation_id == inv.id if model is RecommendedAction else model.org_id == org.id
    before = {model.__name__: db.scalar(select(func.count()).select_from(model).where(scope_filter(model))) or 0 for model in prohibited}
    original_title, original_description = finding.title, finding.description
    changed = client.post(status_path(finding), json={"status": "CONFIRMED"}, headers=write)
    assert changed.status_code == 200 and changed.json()["status"] == "CONFIRMED"
    db.refresh(finding)
    assert (finding.title, finding.description) == (original_title, original_description)
    after = {model.__name__: db.scalar(select(func.count()).select_from(model).where(scope_filter(model))) or 0 for model in prohibited}
    assert after == before
    assert client.post(status_path(finding), json={"status": "CONFIRMED"}, headers=write).status_code == 422
    assert client.post(status_path(finding), json={"status": "RESOLVED"}, headers=write).status_code == 200
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.target_id == finding.id, AuditEvent.action == "FINDING_STATUS_CHANGED")) == 2

    rollback_finding = add_finding(db, org, inv, user, "rollback", datetime.now(timezone.utc)); db.commit()
    service = FindingService(db)
    original = service._audit
    monkeypatch.setattr(service, "_audit", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("database failure")))
    with pytest.raises(ValidationError, match="Unable to save finding review"):
        service.status(org.id, rollback_finding.id, user.id, "CONFIRMED")
    db.refresh(rollback_finding)
    assert rollback_finding.status == "OPEN"
    monkeypatch.setattr(service, "_audit", original)


def test_retired_claim_to_finding_route_is_unregistered_and_side_effect_free(db):
    org, user, inv = scope(db)
    item_id = uuid4()
    client = TestClient(app)
    write = headers(user, org, ["investigation:write"])
    before = {model.__name__: db.scalar(select(func.count()).select_from(model)) or 0 for model in (Finding, AuditEvent, MitreMapping, IntelligenceAnalysis, IntelligenceItem, IntelligenceEvidenceReference, IntelligenceClaimEvidenceLink, RecommendedAction)}
    path = f"/api/v1/investigations/intelligence/items/{item_id}/finding"
    response = client.post(path, json={}, headers=write)
    assert response.status_code == 404
    assert path not in app.openapi()["paths"]
    assert not any("intelligence/items/{item_id}/finding" in route.path for route in app.routes)
    after = {model.__name__: db.scalar(select(func.count()).select_from(model)) or 0 for model in (Finding, AuditEvent, MitreMapping, IntelligenceAnalysis, IntelligenceItem, IntelligenceEvidenceReference, IntelligenceClaimEvidenceLink, RecommendedAction)}
    assert after == before


def test_findings_remain_manual_authority_and_context_is_confirmed_only(db):
    org, user, inv = scope(db)
    pending = add_finding(db, org, inv, user, "pending", datetime.now(timezone.utc), "OPEN")
    confirmed = add_finding(db, org, inv, user, "confirmed", datetime.now(timezone.utc), "CONFIRMED")
    rejected = add_finding(db, org, inv, user, "rejected", datetime.now(timezone.utc), "DISMISSED")
    db.commit()
    from app.modules.ai_reasoning.domain.context_builder import ContextBuilder
    snapshot = ContextBuilder(db).build(org.id, inv.id).snapshot
    assert [row["title"] for row in snapshot["findings"]] == [confirmed.title]
    assert {pending.status, rejected.status} == {"OPEN", "DISMISSED"}
    assert db.scalar(select(func.count()).select_from(IntelligenceItem).where(IntelligenceItem.org_id == org.id)) == 0


def test_confirming_an_intelligence_claim_never_creates_a_finding(db):
    org, user, inv = scope(db)
    intelligence = InvestigationIntelligenceService(db)
    run = intelligence.create_run(
        org.id,
        inv.id,
        provider="test",
        model="test",
        prompt_template_version="v1",
        input_snapshot={},
        input_hash="a" * 64,
        request_key=f"finding-authority-{uuid4().hex}",
    )
    claim = intelligence.create_claim(org.id, run.id, inv.id, kind="OBSERVATION", origin="AI", statement="Analyst-reviewed claim")
    db.commit()
    intelligence.review(org.id, claim.id, user.id, "CONFIRMED", "reviewed")
    assert db.scalar(select(func.count()).select_from(Finding).where(Finding.org_id == org.id)) == 0
