"""PostgreSQL contracts for bounded, analyst-controlled MITRE mappings."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from app.core.security import create_access_token
from app.main import app
from app.modules.ai_reasoning.domain.context_builder import ContextBuilder
from app.modules.ai_reasoning.domain.intelligence_service import InvestigationIntelligenceService
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis, IntelligenceClaimEvidenceLink, IntelligenceEvidenceReference, IntelligenceItem
from app.modules.evidence.infrastructure.models import AuditEvent
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.domain.finding_service import FindingService
from app.modules.investigations.infrastructure.models import Finding, Investigation, InvestigationStatus, MitreMapping, MitreMappingFactLink, RecommendedAction, Severity
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


def scope(db, label="mitre"):
    suffix = uuid4().hex
    org = Organization(name=f"{label} {suffix}", slug=f"{label[:8]}-{suffix}")
    role = Role(name=f"{label[:8]}-{suffix[:12]}")
    db.add_all((org, role)); db.flush()
    user = User(org_id=org.id, role_id=role.id, email=f"{suffix}@mitre.test", hashed_password="x", full_name="Analyst")
    inv = Investigation(org_id=org.id, title=f"{label} case", source="test", severity=Severity.LOW, status=InvestigationStatus.NEW)
    db.add_all((user, inv)); db.commit()
    return org, user, inv


def headers(user, org, permissions):
    return {"Authorization": f"Bearer {create_access_token(user.id, org.id, 'analyst', permissions)}"}


def path(inv, suffix=""):
    return f"/api/v1/investigations/{inv.id}/mitre{suffix}"


def review_path(mapping):
    return f"/api/v1/investigations/mitre-mappings/{mapping.id}/review"


def add_mapping(db, org, inv, technique, timestamp, status="PROPOSED", rationale=""):
    row = MitreMapping(
        org_id=org.id, investigation_id=inv.id, technique_id=technique,
        technique_name="Command execution", tactic="execution", confidence=73,
        ai_rationale="not exposed by the bounded contract", status=status,
        review_rationale=rationale or None, created_at=timestamp, updated_at=timestamp,
    )
    db.add(row); db.flush()
    return row


def test_bounded_mitre_list_is_scoped_deterministic_paginated_and_safe(db):
    org, user, inv = scope(db)
    other_org, _other_user, other_inv = scope(db, "foreign-mitre")
    moment = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = add_mapping(db, org, inv, "T1059", moment, "CONFIRMED", "<img src=x onerror=alert(1)>")
    second = add_mapping(db, org, inv, "T1003", moment, "PROPOSED")
    rejected = add_mapping(db, org, inv, "T1078", moment, "REJECTED", "not supported")
    add_mapping(db, other_org, other_inv, "T9999", moment)
    for index in range(51):
        db.add(MitreMappingFactLink(org_id=org.id, mapping_id=first.id, fact_type="EVENT", fact_id=uuid4(), role="SUPPORTS"))
    db.commit()

    client = TestClient(app)
    read = headers(user, org, ["investigation:read"])
    response = client.get(path(inv, "?limit=2&offset=0"), headers=read)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3 and body["returned_count"] == 2 and body["limit"] == 2 and body["offset"] == 0
    expected = [str(row.id) for row in sorted((first, second, rejected), key=lambda row: str(row.id), reverse=True)[:2]]
    assert [row["id"] for row in body["items"]] == expected
    assert set(body["items"][0]) == {"id", "technique_id", "technique_name", "tactic", "status", "confidence", "review_rationale", "created_at", "reviewed_at", "provenance", "fact_links"}
    first_page = client.get(path(inv, "?limit=3"), headers=read).json()
    first_read = next(row for row in first_page["items"] if row["id"] == str(first.id))
    assert first_read["provenance"] == {"available": True, "omitted": 1} and len(first_read["fact_links"]) == 50
    assert "<img" in str(first_page) and "ai_rationale" not in str(first_page) and "source_intelligence_item_id" not in str(first_page)
    assert client.get(path(inv, "?status=CONFIRMED"), headers=read).json()["total"] == 1
    assert client.get(path(other_inv), headers=read).status_code == 404
    for suffix in ("?limit=0", "?offset=-1", "?status=UNKNOWN", "?org_id=forged", "?technique_id=T1059", "?limit=1&actor_id=forged"):
        assert client.get(path(inv, suffix), headers=read).status_code == 422
    assert client.get("/api/v1/investigations/not-a-uuid/mitre", headers=read).status_code == 422


def test_bounded_mitre_list_uses_constant_queries_not_one_query_per_mapping(db):
    org, user, inv = scope(db, "query-bound")
    now = datetime.now(timezone.utc)
    for index in range(12):
        mapping = add_mapping(db, org, inv, f"T10{index:02d}", now)
        db.add(MitreMappingFactLink(org_id=org.id, mapping_id=mapping.id, fact_type="EVENT", fact_id=uuid4(), role="SUPPORTS"))
    db.commit()
    statements = []

    def observe(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(db.bind, "before_cursor_execute", observe)
    try:
        result = FindingService(db).list_mitre_page(org.id, inv.id, limit=12)
    finally:
        event.remove(db.bind, "before_cursor_execute", observe)
    # Two identity refreshes can occur after the fixture commit; the remaining
    # five reads are the fixed investigation/count/page/link-count/link-page
    # plan. The budget stays constant as the page grows, unlike an N+1 plan.
    assert result["returned_count"] == 12 and len(statements) <= 7


def test_list_and_review_enforce_principal_scope_and_strict_transition_contract(db, monkeypatch):
    org, user, inv = scope(db)
    other_org, other_user, other_inv = scope(db, "foreign-review")
    mapping = add_mapping(db, org, inv, "T1059", datetime.now(timezone.utc))
    foreign = add_mapping(db, other_org, other_inv, "T1003", datetime.now(timezone.utc))
    db.commit()
    client = TestClient(app)
    assert client.get(path(inv), headers=headers(user, org, [])).status_code == 403
    assert client.get(path(inv), headers=headers(user, org, ["investigation:read"])).status_code == 200
    assert client.post(review_path(mapping), json={"status": "CONFIRMED"}, headers=headers(user, org, ["investigation:read"])).status_code == 403
    write = headers(user, org, ["investigation:write"])
    for body in (
        {"status": "CONFIRMED", "org_id": str(uuid4())}, {"status": "CONFIRMED", "actor_id": str(uuid4())},
        {"status": "CONFIRMED", "origin": "AI"}, {"status": "CONFIRMED", "provenance": {}},
        {"status": "CONFIRMED", "technique_id": "T1003"}, {"status": "CONFIRMED", "reviewed_by_id": str(uuid4())},
    ):
        assert client.post(review_path(mapping), json=body, headers=write).status_code == 422
    assert client.post(review_path(mapping), json={"status": "REJECTED"}, headers=write).status_code == 422
    assert client.post(review_path(foreign), json={"status": "CONFIRMED"}, headers=write).status_code == 404
    protected = (Finding, IntelligenceAnalysis, IntelligenceItem, IntelligenceEvidenceReference, IntelligenceClaimEvidenceLink, RecommendedAction)
    scope_filter = lambda model: model.investigation_id == inv.id if model is RecommendedAction else model.org_id == org.id
    before = {model.__name__: db.scalar(select(func.count()).select_from(model).where(scope_filter(model))) or 0 for model in protected}
    original = (mapping.technique_id, mapping.tactic, mapping.ai_rationale)
    changed = client.post(review_path(mapping), json={"status": "CONFIRMED", "rationale": "reviewed"}, headers=write)
    assert changed.status_code == 200 and changed.json()["status"] == "CONFIRMED" and "ai_rationale" not in changed.json()
    db.refresh(mapping)
    assert (mapping.technique_id, mapping.tactic, mapping.ai_rationale) == original
    assert client.post(review_path(mapping), json={"status": "CONFIRMED", "rationale": "again"}, headers=write).status_code == 422
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.target_id == mapping.id, AuditEvent.action == "MITRE_CONFIRMED")) == 1
    after = {model.__name__: db.scalar(select(func.count()).select_from(model).where(scope_filter(model))) or 0 for model in protected}
    assert after == before
    user.is_active = False; db.commit()
    assert client.get(path(inv), headers=headers(user, org, ["investigation:read"])).status_code == 404

    rollback = add_mapping(db, org, inv, "T1078", datetime.now(timezone.utc)); db.commit()
    service = FindingService(db); original_audit = service._audit
    monkeypatch.setattr(service, "_audit", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("database failure")))
    with pytest.raises(ValidationError, match="Unable to save MITRE mapping review"):
        service.review_mapping(org.id, rollback.id, user.id, "CONFIRMED", "")
    db.refresh(rollback)
    assert rollback.status == "PROPOSED"
    monkeypatch.setattr(service, "_audit", original_audit)


def test_confirmed_mitre_is_distinct_analyst_authority_and_context_only(db):
    org, user, inv = scope(db)
    confirmed = add_mapping(db, org, inv, "T1059", datetime.now(timezone.utc), "CONFIRMED")
    proposed = add_mapping(db, org, inv, "T1003", datetime.now(timezone.utc), "PROPOSED")
    rejected = add_mapping(db, org, inv, "T1078", datetime.now(timezone.utc), "REJECTED")
    db.commit()
    snapshot = ContextBuilder(db).build(org.id, inv.id).snapshot
    assert [row["technique_id"] for row in snapshot["mitre"]] == [confirmed.technique_id]
    assert {proposed.status, rejected.status} == {"PROPOSED", "REJECTED"}
    intelligence = InvestigationIntelligenceService(db)
    run = intelligence.create_run(org.id, inv.id, provider="test", model="test", prompt_template_version="v1", input_snapshot={}, input_hash="a" * 64, request_key=f"mitre-authority-{uuid4().hex}")
    claim = intelligence.create_claim(org.id, run.id, inv.id, kind="OBSERVATION", origin="AI", statement="Claim remains separate")
    db.commit(); intelligence.review(org.id, claim.id, user.id, "CONFIRMED", "reviewed")
    assert db.scalar(select(func.count()).select_from(MitreMapping).where(MitreMapping.org_id == org.id)) == 3


def test_only_approved_analyst_mitre_routes_are_registered_and_legacy_analyze_is_absent(db):
    org, user, inv = scope(db)
    client = TestClient(app)
    write = headers(user, org, ["investigation:write"])
    automatic = f"/api/v1/investigations/{inv.id}/analyze"
    protected = (MitreMapping, Finding, AuditEvent, IntelligenceAnalysis, IntelligenceItem, IntelligenceEvidenceReference, IntelligenceClaimEvidenceLink, RecommendedAction)
    before = {model.__name__: db.scalar(select(func.count()).select_from(model)) or 0 for model in protected}
    response = client.post(automatic, headers=write)
    assert response.status_code == 404 and automatic not in app.openapi()["paths"]
    assert not any(route.path.endswith("/analyze") for route in app.routes)
    assert all("intelligence/items/{item_id}/mitre" not in route.path for route in app.routes)
    after = {model.__name__: db.scalar(select(func.count()).select_from(model)) or 0 for model in protected}
    assert after == before
