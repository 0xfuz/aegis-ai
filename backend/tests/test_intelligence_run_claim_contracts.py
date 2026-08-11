"""Focused Phase 8.1.1 contracts against the real PostgreSQL persistence layer."""
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.modules.ai_reasoning.domain.intelligence_contracts import validate_claim_creation, validate_review_transition, validate_run_transition
from app.modules.ai_reasoning.domain.intelligence_service import InvestigationIntelligenceService
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceItem, IntelligenceReviewEvent
from app.modules.evidence.infrastructure.models import AuditEvent
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.infrastructure.models import Investigation, InvestigationStatus, Severity
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


def scope(db, suffix=None):
    suffix = suffix or str(uuid4())
    org = Organization(name=f"Phase8 {suffix}", slug=f"phase8-{suffix}")
    role = Role(name=f"phase8-role-{suffix}")
    db.add_all([org, role]); db.flush()
    user = User(org_id=org.id, role_id=role.id, email=f"{suffix}@example.test", hashed_password="x", full_name="Phase 8 analyst")
    investigation = Investigation(org_id=org.id, title="Run contract", source="pytest", severity=Severity.MEDIUM, status=InvestigationStatus.NEW)
    db.add_all([user, investigation]); db.commit()
    return org, user, investigation


def create_run(service, org, investigation, key="request-1", predecessor=None):
    return service.create_run(org.id, investigation.id, provider="test", model="test", prompt_template_version="v1", input_snapshot={}, input_hash="a" * 64, request_key=key, predecessor_analysis_id=predecessor)


@pytest.mark.parametrize("current,target", [("QUEUED", "RUNNING"), ("QUEUED", "CANCELLED"), ("RUNNING", "COMPLETED"), ("RUNNING", "FAILED"), ("RUNNING", "CANCELLED")])
def test_allowed_run_transitions(current, target):
    validate_run_transition(current, target)


@pytest.mark.parametrize("current,target", [("COMPLETED", "RUNNING"), ("FAILED", "RUNNING"), ("CANCELLED", "RUNNING"), ("QUEUED", "COMPLETED"), ("RUNNING", "QUEUED")])
def test_forbidden_run_transitions(current, target):
    with pytest.raises(ValidationError): validate_run_transition(current, target)


def test_run_idempotency_retry_and_cross_org_lineage(db):
    org, _user, investigation = scope(db); other_org, _other_user, other_investigation = scope(db)
    service = InvestigationIntelligenceService(db)
    queued = create_run(service, org, investigation)
    assert create_run(service, org, investigation).id == queued.id
    service.transition_run(org.id, queued.id, "RUNNING")
    service.transition_run(org.id, queued.id, "FAILED")
    retry = service.retry_run(org.id, queued.id, "request-2")
    assert retry.id != queued.id and retry.predecessor_analysis_id == queued.id and retry.status == "QUEUED"
    with pytest.raises(ValidationError): create_run(service, other_org, other_investigation, "cross-org", queued.id)
    with pytest.raises(ValidationError): service.retry_run(org.id, retry.id, "request-3")


@pytest.mark.parametrize("origin,kind,status", [
    ("SOURCE", "OBSERVATION", "PENDING"),
    ("DETERMINISTIC_ENGINE", "FACT", "CONFIRMED"),
    ("DETERMINISTIC_ENGINE", "INFERENCE", "PENDING"),
    ("AI", "HYPOTHESIS", "PENDING"), ("ANALYST", "RECOMMENDATION", "PENDING"),
])
def test_allowed_claim_creation_contract(origin, kind, status):
    validate_claim_creation(kind, origin, status)


@pytest.mark.parametrize("origin,kind,status", [
    ("SOURCE", "FACT", "PENDING"), ("AI", "FACT", "CONFIRMED"),
    ("DETERMINISTIC_ENGINE", "FACT", "PENDING"), ("AI", "OBSERVATION", "CONFIRMED"),
    ("ANALYST", "FACT", "CONFIRMED"),
])
def test_rejected_claim_creation_contract(origin, kind, status):
    with pytest.raises(ValidationError): validate_claim_creation(kind, origin, status)


def test_claim_requires_matching_non_null_run_and_scoped_investigation(db):
    org, _user, investigation = scope(db); _other_org, _other_user, other_investigation = scope(db)
    service = InvestigationIntelligenceService(db); run = create_run(service, org, investigation)
    item = service.create_claim(org.id, run.id, investigation.id, kind="OBSERVATION", origin="AI", statement="claim")
    assert item.analysis_id == run.id and item.origin == "AI" and item.review_status == "PENDING"
    with pytest.raises(ValidationError): service.create_claim(org.id, run.id, other_investigation.id, kind="OBSERVATION", origin="AI", statement="wrong case")


@pytest.mark.parametrize("current,target", [("PENDING", "CONFIRMED"), ("PENDING", "REJECTED"), ("PENDING", "UNRESOLVED"), ("PENDING", "SUPERSEDED"), ("UNRESOLVED", "CONFIRMED"), ("UNRESOLVED", "REJECTED"), ("UNRESOLVED", "SUPERSEDED"), ("CONFIRMED", "SUPERSEDED"), ("REJECTED", "SUPERSEDED")])
def test_allowed_review_transitions(current, target):
    validate_review_transition(current, target)


@pytest.mark.parametrize("current,target", [("PENDING", "PENDING"), ("CONFIRMED", "REJECTED"), ("REJECTED", "CONFIRMED"), ("SUPERSEDED", "CONFIRMED")])
def test_forbidden_review_transitions(current, target):
    with pytest.raises(ValidationError): validate_review_transition(current, target)


def test_review_is_append_only_and_ai_can_be_analyst_confirmed(db):
    org, user, investigation = scope(db); service = InvestigationIntelligenceService(db); run = create_run(service, org, investigation)
    item = service.create_claim(org.id, run.id, investigation.id, kind="OBSERVATION", origin="AI", statement="review me")
    db.commit(); service.review(org.id, item.id, user.id, "CONFIRMED", "analyst verified")
    event = db.scalar(select(IntelligenceReviewEvent).where(IntelligenceReviewEvent.item_id == item.id))
    audit = db.scalar(select(AuditEvent).where(AuditEvent.target_id == item.id, AuditEvent.action == "INTELLIGENCE_ITEM_REVIEWED"))
    assert (event.from_status, event.to_status, item.origin, item.kind) == ("PENDING", "CONFIRMED", "AI", "OBSERVATION")
    assert audit is not None


def test_same_scope_supersession_is_linear_and_readable(db):
    org, user, investigation = scope(db); service = InvestigationIntelligenceService(db); run = create_run(service, org, investigation)
    predecessor = service.create_claim(org.id, run.id, investigation.id, kind="HYPOTHESIS", origin="AI", statement="old")
    db.commit()
    successor = service.create_claim(org.id, run.id, investigation.id, kind="HYPOTHESIS", origin="AI", statement="new", supersedes_item_id=predecessor.id, reviewer_id=user.id)
    db.commit(); db.refresh(predecessor)
    assert successor.supersedes_item_id == predecessor.id and predecessor.review_status == "SUPERSEDED"
    with pytest.raises(ValidationError): service.create_claim(org.id, run.id, investigation.id, kind="HYPOTHESIS", origin="AI", statement="branch", supersedes_item_id=predecessor.id, reviewer_id=user.id)


def test_supersession_rejects_cross_org_and_cross_investigation(db):
    org, _user, investigation = scope(db); other_org, _other_user, other_investigation = scope(db)
    service = InvestigationIntelligenceService(db); first_run = create_run(service, org, investigation); other_run = create_run(service, other_org, other_investigation)
    item = service.create_claim(org.id, first_run.id, investigation.id, kind="INFERENCE", origin="AI", statement="old")
    db.commit()
    with pytest.raises(ValidationError): service.create_claim(other_org.id, other_run.id, other_investigation.id, kind="INFERENCE", origin="AI", statement="bad", supersedes_item_id=item.id)
