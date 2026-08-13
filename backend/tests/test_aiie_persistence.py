"""Phase 5.2 AIIE integration contracts against PostgreSQL.

These tests use a deterministic LLM double: they exercise the real AIIE
service, persistence models, review history, FACT rows, and tenant scoping
without downloading or invoking an Ollama model.
"""
import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import create_access_token
from app.main import app
from app.modules.ai_reasoning.domain import intelligence_service
from app.modules.ai_reasoning.domain.intelligence_service import InvestigationIntelligenceService
from app.modules.ai_reasoning.infrastructure.intelligence_models import (
    IntelligenceAnalysis,
    IntelligenceFactLink,
    IntelligenceItem,
    IntelligenceReviewEvent,
)
from app.modules.evidence.infrastructure.models import AuditEvent, Entity
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.infrastructure.models import Investigation, InvestigationStatus, Severity
from app.shared.database import SessionLocal
from app.shared.exceptions import NotFoundError, ValidationError


class DeterministicProvider:
    model = "aiie-test-model"

    def __init__(self, fact_id=None):
        self.fact_id = fact_id

    async def complete_json(self, _system, prompt, **_kwargs):
        fact_id = self.fact_id or json.loads(prompt)["entities"][0]["id"]
        return json.dumps({
            "summary": "A supported investigation summary.",
            "observations": [{"statement": "Observed host activity.", "confidence": 80, "supporting_facts": [fact_id]}],
            "hypotheses": [], "recommendations": [], "questions": [], "reasoning": [],
        })


class RetryingProvider:
    model = "ollama-reliability-double"

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def complete_json(self, _system, prompt, **kwargs):
        self.calls.append(kwargs)
        response = self.responses[len(self.calls) - 1]
        return response(prompt) if callable(response) else response


def structured_output(prompt):
    fact_id = json.loads(prompt)["entities"][0]["id"]
    return json.dumps({
        "summary": "A supported investigation summary.",
        "observations": [{"statement": "Observed host activity.", "confidence": 80, "supporting_facts": [fact_id]}],
        "hypotheses": [], "recommendations": [], "questions": [], "reasoning": [],
    })


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def context(db, *, suffix=None):
    suffix = suffix or str(uuid4())
    org = Organization(name=f"AIIE {suffix}", slug=f"aiie-{suffix}")
    role = Role(name=f"aiie-role-{suffix}")
    db.add_all([org, role]); db.flush()
    user = User(org_id=org.id, role_id=role.id, email=f"{suffix}@example.test", hashed_password="x", full_name="AIIE reviewer")
    investigation = Investigation(org_id=org.id, title="AIIE test", source="pytest", severity=Severity.MEDIUM, status=InvestigationStatus.NEW)
    db.add_all([user, investigation]); db.flush()
    entity = Entity(org_id=org.id, investigation_id=investigation.id, type="host", canonical_value=f"host-{suffix}", display_name="Test host")
    db.add(entity); db.commit()
    return org, user, investigation, entity


def run(service, org_id, investigation_id):
    return asyncio.run(service.run(org_id, investigation_id))


def test_aiie_persists_analysis_items_and_fact_links(db):
    org, _user, investigation, entity = context(db)
    analysis = run(InvestigationIntelligenceService(db, DeterministicProvider()), org.id, investigation.id)

    assert analysis.status == "COMPLETED"
    assert analysis.provider == "deterministic"
    assert analysis.model == "aiie-test-model"
    assert db.scalar(select(IntelligenceItem).where(IntelligenceItem.analysis_id == analysis.id, IntelligenceItem.kind == "OBSERVATION"))
    link = db.scalar(select(IntelligenceFactLink).where(IntelligenceFactLink.org_id == org.id))
    assert link.fact_id == entity.id and link.role == "SUPPORTS"


@pytest.mark.parametrize("bad_alias", ["EN99", "not-an-alias"])
def test_aiie_rejects_hallucinated_or_malformed_fact_aliases(db, bad_alias):
    org, _user, investigation, _entity = context(db)
    with pytest.raises((ValidationError, ValueError)):
        run(InvestigationIntelligenceService(db, DeterministicProvider(bad_alias)), org.id, investigation.id)
    assert db.scalar(select(IntelligenceAnalysis.status).where(IntelligenceAnalysis.org_id == org.id)) == "FAILED"
    assert db.scalar(select(IntelligenceItem).where(IntelligenceItem.org_id == org.id)) is None


def test_aiie_rejects_fact_reference_from_another_investigation(db):
    org, _user, investigation, _entity = context(db)
    _org, _other_user, other_investigation, other_entity = context(db)
    # This is a different tenant and case, therefore not present in the current compact context.
    with pytest.raises(ValidationError):
        run(InvestigationIntelligenceService(db, DeterministicProvider("EN2")), org.id, investigation.id)
    with pytest.raises(NotFoundError):
        InvestigationIntelligenceService(db, DeterministicProvider()).context(org.id, other_investigation.id)


def test_aiie_cross_org_access_is_not_visible(db):
    org, _user, investigation, _entity = context(db)
    other_org, _other_user, _other_investigation, _other_entity = context(db)
    run(InvestigationIntelligenceService(db, DeterministicProvider()), org.id, investigation.id)
    with pytest.raises(NotFoundError):
        InvestigationIntelligenceService(db, DeterministicProvider()).latest(other_org.id, investigation.id)


def test_aiie_runs_are_append_only_and_do_not_mutate_facts(db):
    org, _user, investigation, entity = context(db)
    before = (entity.canonical_value, entity.display_name, entity.attributes, entity.created_at)
    service = InvestigationIntelligenceService(db, DeterministicProvider())
    first = run(service, org.id, investigation.id)
    second = run(service, org.id, investigation.id)
    db.refresh(entity)

    assert first.id != second.id
    assert db.scalars(select(IntelligenceAnalysis).where(IntelligenceAnalysis.investigation_id == investigation.id)).all().__len__() == 2
    assert db.scalars(select(IntelligenceItem).where(IntelligenceItem.investigation_id == investigation.id)).all().__len__() == 4
    assert (entity.canonical_value, entity.display_name, entity.attributes, entity.created_at) == before


def test_aiie_review_and_audit_history_are_append_only(db):
    org, user, investigation, _entity = context(db)
    analysis = run(InvestigationIntelligenceService(db, DeterministicProvider()), org.id, investigation.id)
    item = db.scalar(select(IntelligenceItem).where(IntelligenceItem.analysis_id == analysis.id, IntelligenceItem.kind == "OBSERVATION"))
    service = InvestigationIntelligenceService(db, DeterministicProvider())
    service.review(org.id, item.id, user.id, "APPROVED", "Evidence is sufficient.")
    service.review(org.id, item.id, user.id, "SUPERSEDED", "A newer analysis replaces it.")

    history = db.scalars(select(IntelligenceReviewEvent).where(IntelligenceReviewEvent.item_id == item.id).order_by(IntelligenceReviewEvent.created_at)).all()
    audits = db.scalars(select(AuditEvent).where(AuditEvent.target_id == item.id, AuditEvent.action == "INTELLIGENCE_ITEM_REVIEWED")).all()
    assert [(event.from_status, event.to_status) for event in history] == [("PENDING", "CONFIRMED"), ("CONFIRMED", "SUPERSEDED")]
    assert len(audits) == 2
    with pytest.raises(ValidationError):
        service.review(org.id, item.id, user.id, "APPROVED", "Terminal items cannot change.")


def test_aiie_review_cannot_cross_organization(db):
    org, user, investigation, _entity = context(db)
    other_org, _other_user, _other_investigation, _other_entity = context(db)
    analysis = run(InvestigationIntelligenceService(db, DeterministicProvider()), org.id, investigation.id)
    item = db.scalar(select(IntelligenceItem).where(IntelligenceItem.analysis_id == analysis.id, IntelligenceItem.kind == "OBSERVATION"))
    with pytest.raises(NotFoundError):
        InvestigationIntelligenceService(db, DeterministicProvider()).review(other_org.id, item.id, user.id, "APPROVED", "not authorized")


def test_aiie_read_route_enforces_permission_and_org_scope(db):
    org, user, investigation, _entity = context(db)
    other_org, other_user, _other_investigation, _other_entity = context(db)
    run(InvestigationIntelligenceService(db, DeterministicProvider()), org.id, investigation.id)
    client = TestClient(app)
    denied = create_access_token(user.id, org.id, "analyst", [])
    allowed = create_access_token(user.id, org.id, "analyst", ["investigation:read"])
    other_allowed = create_access_token(other_user.id, other_org.id, "analyst", ["investigation:read"])

    assert client.get(f"/api/v1/investigations/{investigation.id}/intelligence", headers={"Authorization": f"Bearer {denied}"}).status_code == 403
    assert client.get(f"/api/v1/investigations/{investigation.id}/intelligence", headers={"Authorization": f"Bearer {allowed}"}).status_code == 200
    assert client.get(f"/api/v1/investigations/{investigation.id}/intelligence", headers={"Authorization": f"Bearer {other_allowed}"}).status_code == 404


def test_aiie_legacy_http_route_queues_without_invoking_provider(db, monkeypatch):
    org, user, investigation, _entity = context(db)
    called = []
    monkeypatch.setattr(intelligence_service, "get_llm_provider", lambda: called.append(True))
    client = TestClient(app)
    token = create_access_token(user.id, org.id, "analyst", ["investigation:read", "investigation:write"])
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(f"/api/v1/investigations/{investigation.id}/intelligence", headers=headers)
    assert created.status_code == 200 and created.json()["status"] == "QUEUED"
    assert called == []


@pytest.mark.parametrize("invalid", [
    lambda _prompt: json.dumps({"summary": None, "observations": [], "hypotheses": [], "recommendations": [], "questions": [], "reasoning": []}),
    lambda _prompt: '{"summary":"broken",',
    lambda _prompt: json.dumps({"summary": "s", "observations": [], "hypotheses": [], "recommendations": [], "questions": [], "reasoning": [], "unexpected": True}),
    lambda prompt: json.dumps({"summary": "s", "observations": [], "hypotheses": [], "recommendations": [{"statement": "r", "priority": "URGENT", "reason": "r", "supporting_facts": [json.loads(prompt)["entities"][0]["id"]]}], "questions": [], "reasoning": []}),
], ids=["null-required-field", "malformed-json", "extra-field", "invalid-enum"])
def test_schema_failures_receive_exactly_one_repair_attempt(db, invalid):
    org, _user, investigation, _entity = context(db)
    provider = RetryingProvider(invalid, invalid)
    with pytest.raises(ValidationError, match="after one repair attempt"):
        run(InvestigationIntelligenceService(db, provider), org.id, investigation.id)
    assert len(provider.calls) == 2
    schema = provider.calls[0]["schema"]
    assert schema["$defs"]["Entry"]["properties"]["supporting_facts"]["items"]["enum"] == ["EN1"]
    assert provider.calls[1]["repair_response"] is not None
    assert db.scalar(select(IntelligenceItem).where(IntelligenceItem.org_id == org.id)) is None
    assert db.scalar(select(IntelligenceFactLink).where(IntelligenceFactLink.org_id == org.id)) is None
    failed = db.scalar(select(IntelligenceAnalysis).where(IntelligenceAnalysis.org_id == org.id))
    assert failed.status == "FAILED" and "after one repair attempt" in failed.error_summary


def test_successful_corrected_retry_persists_only_valid_output(db):
    org, _user, investigation, _entity = context(db)
    invalid = json.dumps({"summary": None, "observations": [], "hypotheses": [], "recommendations": [], "questions": [], "reasoning": []})
    provider = RetryingProvider(invalid, structured_output)
    analysis = run(InvestigationIntelligenceService(db, provider), org.id, investigation.id)
    assert analysis.status == "COMPLETED" and len(provider.calls) == 2
    assert db.scalars(select(IntelligenceItem).where(IntelligenceItem.analysis_id == analysis.id)).all().__len__() == 2


def test_hallucinated_alias_is_not_retried_or_persisted(db):
    org, _user, investigation, _entity = context(db)
    hallucinated = "EN999"
    provider = RetryingProvider(lambda _prompt: json.dumps({
        "summary": "s", "observations": [{"statement": "unsupported", "confidence": 80, "supporting_facts": [hallucinated]}],
        "hypotheses": [], "recommendations": [], "questions": [], "reasoning": [],
    }))
    with pytest.raises(ValidationError, match="Unknown factual alias"):
        run(InvestigationIntelligenceService(db, provider), org.id, investigation.id)
    assert len(provider.calls) == 1
    assert db.scalar(select(IntelligenceItem).where(IntelligenceItem.org_id == org.id)) is None
