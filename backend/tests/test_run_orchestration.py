from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.modules.ai_reasoning.domain.context_builder import ContextBuilder
from app.modules.ai_reasoning.domain.run_orchestration_service import IntelligenceRunOrchestrationService
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis, IntelligenceItem
from app.modules.evidence.infrastructure.models import AuditEvent, Entity
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.infrastructure.models import Investigation, InvestigationStatus, Severity
from app.shared.database import SessionLocal
from app.shared.exceptions import NotFoundError, ValidationError


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def setup(db):
    suffix = uuid4().hex
    org = Organization(name=suffix, slug=f"run-{suffix}")
    role = Role(name=f"run-role-{suffix}")
    db.add_all([org, role]); db.flush()
    user = User(org_id=org.id, role_id=role.id, email=f"{suffix}@test", hashed_password="x", full_name="run")
    investigation = Investigation(org_id=org.id, title="run", source="test", severity=Severity.MEDIUM, status=InvestigationStatus.NEW)
    db.add_all([user, investigation]); db.commit()
    return org, user, investigation


def audit_actions(db, run_id):
    return [row.action for row in db.scalars(select(AuditEvent).where(AuditEvent.target_id == run_id).order_by(AuditEvent.occurred_at))]


def test_queue_lifecycle_audit_cancel_retry_and_no_claims(db):
    org, user, investigation = setup(db)
    service = IntelligenceRunOrchestrationService(db)
    queued = service.queue(org.id, investigation.id, user.id, "one")
    assert queued.status == "QUEUED"
    assert service.queue(org.id, investigation.id, user.id, "one").id == queued.id
    running = service.acquire(org.id, queued.id)
    assert running.status == "RUNNING"
    completed = service.complete(org.id, queued.id)
    assert completed.status == "COMPLETED"
    with pytest.raises(ValidationError):
        service.acquire(org.id, queued.id)
    with pytest.raises(ValidationError):
        service.retry(org.id, queued.id, user.id, "completed-retry")

    cancelled = service.queue(org.id, investigation.id, user.id, "two")
    service.cancel(org.id, cancelled.id, user.id, "operator cancelled")
    assert cancelled.status == "CANCELLED"
    assert service.cancel(org.id, cancelled.id, user.id).id == cancelled.id
    retry = service.retry(org.id, cancelled.id, user.id, "three")
    assert retry.predecessor_analysis_id == cancelled.id and retry.status == "QUEUED"
    assert audit_actions(db, queued.id) == ["INTELLIGENCE_RUN_QUEUED", "INTELLIGENCE_RUN_ACQUIRED", "INTELLIGENCE_RUN_COMPLETED"]
    assert audit_actions(db, cancelled.id) == ["INTELLIGENCE_RUN_QUEUED", "INTELLIGENCE_RUN_CANCELLED"]
    assert audit_actions(db, retry.id) == ["INTELLIGENCE_RUN_RETRY_QUEUED"]
    assert db.scalar(select(IntelligenceItem).where(IntelligenceItem.investigation_id == investigation.id)) is None


def test_failure_is_safe_and_terminal_and_running_cancellation_is_audited(db):
    org, user, investigation = setup(db)
    service = IntelligenceRunOrchestrationService(db)
    failed = service.queue(org.id, investigation.id, user.id, "failure")
    service.acquire(org.id, failed.id)
    row = service.fail(org.id, failed.id, RuntimeError("phase8-sensitive-marker"))
    assert row.error_summary == "EXECUTION_FAILED" and "sensitive" not in row.error_summary
    assert audit_actions(db, failed.id) == ["INTELLIGENCE_RUN_QUEUED", "INTELLIGENCE_RUN_ACQUIRED", "INTELLIGENCE_RUN_FAILED"]
    with pytest.raises(ValidationError):
        service.complete(org.id, failed.id)
    retry = service.retry(org.id, failed.id, user.id, "failed-retry")
    assert retry.status == "QUEUED" and retry.predecessor_analysis_id == failed.id

    running = service.queue(org.id, investigation.id, user.id, "running-cancel")
    service.acquire(org.id, running.id)
    service.cancel(org.id, running.id, user.id)
    with pytest.raises(ValidationError):
        service.complete(org.id, running.id)
    with pytest.raises(ValidationError):
        service.fail(org.id, running.id, RuntimeError("ignored"))
    assert audit_actions(db, running.id) == ["INTELLIGENCE_RUN_QUEUED", "INTELLIGENCE_RUN_ACQUIRED", "INTELLIGENCE_RUN_CANCELLED"]


def test_queue_identity_actor_and_org_boundaries(db):
    org, user, investigation = setup(db)
    other, other_user, other_investigation = setup(db)
    service = IntelligenceRunOrchestrationService(db)
    queued = service.queue(org.id, investigation.id, user.id, "same-key")
    db.add(Entity(org_id=org.id, investigation_id=investigation.id, type="host", canonical_value="new-host", display_name="new-host")); db.commit()
    with pytest.raises(ValidationError):
        service.queue(org.id, investigation.id, user.id, "same-key")
    with pytest.raises(NotFoundError):
        service.queue(org.id, other_investigation.id, user.id, "foreign-investigation")
    with pytest.raises(NotFoundError):
        service.cancel(other.id, queued.id, other_user.id)
    with pytest.raises(NotFoundError):
        service.retry(other.id, queued.id, other_user.id, "foreign-predecessor")
    with pytest.raises(NotFoundError):
        service.queue(org.id, investigation.id, None, "no-actor")
    user.is_active = False; db.commit()
    with pytest.raises(NotFoundError):
        service.queue(org.id, investigation.id, user.id, "inactive-actor")


def test_audit_failure_rolls_back_transition(db, monkeypatch):
    org, user, investigation = setup(db)
    service = IntelligenceRunOrchestrationService(db)
    queued = service.queue(org.id, investigation.id, user.id, "audit-rollback")

    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(service, "_audit", fail_audit)
    with pytest.raises(RuntimeError):
        service.acquire(org.id, queued.id)
    with SessionLocal() as verify:
        persisted = verify.scalar(select(IntelligenceAnalysis).where(IntelligenceAnalysis.id == queued.id))
        assert persisted.status == "QUEUED"
        assert verify.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.target_id == queued.id)) == 1


@pytest.mark.parametrize("operation", ["queue", "retry"])
def test_context_failure_creates_no_partial_run(db, monkeypatch, operation):
    org, user, investigation = setup(db)
    service = IntelligenceRunOrchestrationService(db)
    predecessor = None
    if operation == "retry":
        predecessor = service.queue(org.id, investigation.id, user.id, "retry-source")
        service.acquire(org.id, predecessor.id)
        service.fail(org.id, predecessor.id, RuntimeError("safe"))

    def fail_context(*_args, **_kwargs):
        raise RuntimeError("context unavailable")

    monkeypatch.setattr(ContextBuilder, "build", fail_context)
    with pytest.raises(RuntimeError):
        if operation == "queue":
            service.queue(org.id, investigation.id, user.id, "context-failure")
        else:
            service.retry(org.id, predecessor.id, user.id, "retry-context-failure")
    expected = 0 if operation == "queue" else 1
    assert db.scalar(select(func.count()).select_from(IntelligenceAnalysis).where(IntelligenceAnalysis.investigation_id == investigation.id)) == expected


def test_integrity_error_is_rolled_back_without_sql_detail_leakage(db, monkeypatch):
    org, user, investigation = setup(db)
    service = IntelligenceRunOrchestrationService(db)

    def fail_commit():
        raise IntegrityError("INSERT synthetic_sql_marker", {}, RuntimeError("synthetic_sql_marker"))

    monkeypatch.setattr(db, "commit", fail_commit)
    with pytest.raises(ValidationError) as error:
        service.queue(org.id, investigation.id, user.id, "integrity-error")
    assert "synthetic_sql_marker" not in str(error.value)
    with SessionLocal() as verify:
        assert verify.scalar(select(func.count()).select_from(IntelligenceAnalysis).where(IntelligenceAnalysis.investigation_id == investigation.id)) == 0
