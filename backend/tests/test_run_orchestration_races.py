"""Phase 8.1.3-A2 PostgreSQL two-session race certification."""
from queue import Queue
from threading import Barrier, Event as ThreadEvent, Thread, local
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from app.modules.ai_reasoning.domain.run_orchestration_service import IntelligenceRunOrchestrationService
from app.modules.ai_reasoning.domain.context_builder import ContextBuilder, ContextSnapshot
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis, IntelligenceItem
from app.modules.evidence.infrastructure.models import AuditEvent
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.infrastructure.models import Investigation, InvestigationStatus, Severity
from app.shared.database import SessionLocal
from app.shared.exceptions import ValidationError


def scope():
    db = SessionLocal()
    try:
        suffix = uuid4().hex
        org = Organization(name=suffix, slug=f"a2-{suffix}")
        role = Role(name=f"a2-role-{suffix}")
        db.add_all([org, role]); db.flush()
        user = User(org_id=org.id, role_id=role.id, email=f"{suffix}@test", hashed_password="x", full_name="A2 analyst")
        investigation = Investigation(org_id=org.id, title="A2", source="pytest", severity=Severity.MEDIUM, status=InvestigationStatus.NEW)
        db.add_all([user, investigation]); db.commit()
        return org.id, user.id, investigation.id
    finally:
        db.close()


def run_two(call, prepare=None):
    start = Barrier(2, timeout=5)
    results = Queue()

    def worker(index):
        db = SessionLocal()
        try:
            db.execute(text("SET lock_timeout = '1500ms'"))
            if prepare:
                prepare(db, index)
            start.wait()
            row = call(db, index)
            results.put(("ok", row.id, row.status))
        except Exception as exc:
            results.put(("error", type(exc).__name__, str(exc)[:160]))
        finally:
            db.rollback()
            db.close()

    threads = [Thread(target=worker, args=(index,), daemon=True) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=8)
    assert not any(thread.is_alive() for thread in threads), "bounded PostgreSQL race did not terminate"
    return [results.get_nowait() for _ in range(2)]


def test_concurrent_identical_queue_recovers_unique_winner():
    org_id, user_id, investigation_id = scope()
    flushes = Barrier(2, timeout=5)

    def prepare(db, _index):
        original_flush = db.flush
        first_flush = True

        def synchronized_flush(*args, **kwargs):
            nonlocal first_flush
            if first_flush:
                first_flush = False
                flushes.wait()
            return original_flush(*args, **kwargs)

        db.flush = synchronized_flush

    results = run_two(
        lambda db, _index: IntelligenceRunOrchestrationService(db).queue(org_id, investigation_id, user_id, "same-request"),
        prepare,
    )
    assert [result[0] for result in results].count("ok") == 2
    assert len({result[1] for result in results}) == 1
    with SessionLocal() as verify:
        rows = verify.scalars(select(IntelligenceAnalysis).where(IntelligenceAnalysis.org_id == org_id)).all()
        assert len(rows) == 1 and rows[0].status == "QUEUED"
        assert verify.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.target_id == rows[0].id)) == 1
        assert verify.scalar(select(func.count()).select_from(IntelligenceItem).where(IntelligenceItem.investigation_id == investigation_id)) == 0


def create_run(org_id, user_id, investigation_id, key="run"):
    db = SessionLocal()
    try:
        return IntelligenceRunOrchestrationService(db).queue(org_id, investigation_id, user_id, key).id
    finally:
        db.close()


def run_transition(org_id, run_id, operation, user_id=None):
    db = SessionLocal()
    try:
        service = IntelligenceRunOrchestrationService(db)
        if operation == "cancel":
            return service.cancel(org_id, run_id, user_id)
        if operation == "fail":
            return service.fail(org_id, run_id, RuntimeError("A2 controlled failure"))
        return getattr(service, operation)(org_id, run_id)
    finally:
        db.close()


def test_conflicting_queue_fingerprints_preserve_committed_winner(monkeypatch):
    org_id, user_id, investigation_id = scope()
    snapshots = local()

    def distinct_context(_self, _org, _investigation):
        return ContextSnapshot({"context_version": "test", "label": snapshots.label}, snapshots.fingerprint)

    monkeypatch.setattr(ContextBuilder, "build", distinct_context)
    def prepare(_db, index):
        snapshots.label = f"context-{index}"
        snapshots.fingerprint = chr(97 + index) * 64

    results = run_two(lambda db, _index: IntelligenceRunOrchestrationService(db).queue(org_id, investigation_id, user_id, "conflict"), prepare)
    assert sorted(result[0] for result in results) == ["error", "ok"]
    error = next(result for result in results if result[0] == "error")
    assert error[1] == "ValidationError" and "sql" not in error[2].lower()
    with SessionLocal() as verify:
        rows = verify.scalars(select(IntelligenceAnalysis).where(IntelligenceAnalysis.org_id == org_id)).all()
        assert len(rows) == 1 and rows[0].input_hash in {"a" * 64, "b" * 64}
        assert verify.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.target_id == rows[0].id)) == 1


def test_concurrent_acquire_has_one_owner_and_one_audit():
    org_id, user_id, investigation_id = scope()
    run_id = create_run(org_id, user_id, investigation_id, "acquire")
    results = run_two(lambda db, _index: IntelligenceRunOrchestrationService(db).acquire(org_id, run_id))
    assert sorted(result[0] for result in results) == ["error", "ok"]
    with SessionLocal() as verify:
        row = verify.get(IntelligenceAnalysis, run_id)
        assert row.status == "RUNNING"
        assert verify.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.target_id == run_id, AuditEvent.action == "INTELLIGENCE_RUN_ACQUIRED")) == 1


@pytest.mark.parametrize("first,second,expected,absent", [
    ("cancel", "acquire", "CANCELLED", "INTELLIGENCE_RUN_ACQUIRED"),
    ("acquire", "cancel", "CANCELLED", None),
])
def test_acquire_cancel_controlled_orders(first, second, expected, absent):
    org_id, user_id, investigation_id = scope()
    run_id = create_run(org_id, user_id, investigation_id, f"{first}-{second}")
    run_transition(org_id, run_id, first, user_id if first == "cancel" else None)
    if first == "cancel":
        with pytest.raises(ValidationError): run_transition(org_id, run_id, second)
    else:
        run_transition(org_id, run_id, second, user_id)
    with SessionLocal() as verify:
        row = verify.get(IntelligenceAnalysis, run_id)
        actions = [event.action for event in verify.scalars(select(AuditEvent).where(AuditEvent.target_id == run_id).order_by(AuditEvent.occurred_at))]
        assert row.status == expected and actions[0] == "INTELLIGENCE_RUN_QUEUED"
        if absent: assert absent not in actions
        else: assert actions == ["INTELLIGENCE_RUN_QUEUED", "INTELLIGENCE_RUN_ACQUIRED", "INTELLIGENCE_RUN_CANCELLED"]


@pytest.mark.parametrize("first,second,expected,absent", [
    ("cancel", "complete", "CANCELLED", "INTELLIGENCE_RUN_COMPLETED"),
    ("complete", "cancel", "COMPLETED", "INTELLIGENCE_RUN_CANCELLED"),
])
def test_complete_cancel_controlled_orders(first, second, expected, absent):
    org_id, user_id, investigation_id = scope()
    run_id = create_run(org_id, user_id, investigation_id, f"{first}-{second}")
    run_transition(org_id, run_id, "acquire")
    run_transition(org_id, run_id, first, user_id if first == "cancel" else None)
    with pytest.raises(ValidationError):
        run_transition(org_id, run_id, second, user_id if second == "cancel" else None)
    with SessionLocal() as verify:
        row = verify.get(IntelligenceAnalysis, run_id)
        actions = [event.action for event in verify.scalars(select(AuditEvent).where(AuditEvent.target_id == run_id))]
        assert row.status == expected and absent not in actions


@pytest.mark.parametrize("winner,loser,expected,terminal_action", [
    ("complete", "fail", "COMPLETED", "INTELLIGENCE_RUN_COMPLETED"),
    ("fail", "complete", "FAILED", "INTELLIGENCE_RUN_FAILED"),
])
def test_complete_fail_controlled_winner(winner, loser, expected, terminal_action):
    org_id, user_id, investigation_id = scope()
    run_id = create_run(org_id, user_id, investigation_id, f"{winner}-{loser}")
    run_transition(org_id, run_id, "acquire")
    run_transition(org_id, run_id, winner)
    with pytest.raises(ValidationError):
        run_transition(org_id, run_id, loser)
    with SessionLocal() as verify:
        row = verify.get(IntelligenceAnalysis, run_id)
        assert row.status == expected and (row.generated_at is not None) == (expected == "COMPLETED")
        assert verify.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.target_id == run_id, AuditEvent.action == terminal_action)) == 1


def test_concurrent_retry_recovers_unique_successor_and_keeps_predecessor_terminal():
    org_id, user_id, investigation_id = scope()
    predecessor_id = create_run(org_id, user_id, investigation_id, "retry-source")
    run_transition(org_id, predecessor_id, "acquire")
    run_transition(org_id, predecessor_id, "fail")
    results = run_two(lambda db, _index: IntelligenceRunOrchestrationService(db).retry(org_id, predecessor_id, user_id, "retry-same"))
    assert [result[0] for result in results].count("ok") == 2 and len({result[1] for result in results}) == 1
    with SessionLocal() as verify:
        predecessor = verify.get(IntelligenceAnalysis, predecessor_id)
        successors = verify.scalars(select(IntelligenceAnalysis).where(IntelligenceAnalysis.predecessor_analysis_id == predecessor_id)).all()
        assert predecessor.status == "FAILED" and len(successors) == 1 and successors[0].status == "QUEUED"
        assert verify.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.target_id == successors[0].id, AuditEvent.action == "INTELLIGENCE_RUN_RETRY_QUEUED")) == 1


def test_database_error_is_bounded_and_session_remains_usable(monkeypatch):
    org_id, user_id, investigation_id = scope()
    db = SessionLocal()
    try:
        service = IntelligenceRunOrchestrationService(db)
        original_commit = db.commit
        def fail_commit():
            raise __import__("sqlalchemy").exc.OperationalError("UPDATE synthetic_sql_marker", {}, RuntimeError("synthetic_sql_marker"))
        monkeypatch.setattr(db, "commit", fail_commit)
        with pytest.raises(ValidationError) as error:
            service.queue(org_id, investigation_id, user_id, "db-error")
        assert "synthetic_sql_marker" not in str(error.value)
        monkeypatch.setattr(db, "commit", original_commit)
        assert service.queue(org_id, investigation_id, user_id, "after-error").status == "QUEUED"
    finally:
        db.close()


def test_lock_timeout_is_bounded_and_contender_session_recovers():
    org_id, user_id, investigation_id = scope()
    run_id = create_run(org_id, user_id, investigation_id, "lock-timeout")
    locker, contender = SessionLocal(), SessionLocal()
    try:
        locker.scalar(select(IntelligenceAnalysis).where(IntelligenceAnalysis.id == run_id).with_for_update())
        contender.execute(text("SET lock_timeout = '200ms'"))
        with pytest.raises(ValidationError) as error:
            IntelligenceRunOrchestrationService(contender).acquire(org_id, run_id)
        assert "sql" not in str(error.value).lower()
        locker.rollback()
        assert IntelligenceRunOrchestrationService(contender).acquire(org_id, run_id).status == "RUNNING"
    finally:
        locker.rollback(); contender.rollback(); locker.close(); contender.close()


def test_audit_failure_under_competing_acquire_leaves_no_orphan_audit():
    org_id, user_id, investigation_id = scope()
    run_id = create_run(org_id, user_id, investigation_id, "audit-contention")
    entered_audit, results = ThreadEvent(), Queue()

    def failed_transition():
        db = SessionLocal()
        try:
            service = IntelligenceRunOrchestrationService(db)
            def fail_audit(*_args, **_kwargs):
                entered_audit.set()
                raise RuntimeError("audit sink unavailable")
            service._audit = fail_audit
            service.acquire(org_id, run_id)
        except Exception as exc:
            results.put(("failed", type(exc).__name__))
        finally:
            db.rollback(); db.close()

    def winning_transition():
        db = SessionLocal()
        try:
            assert entered_audit.wait(timeout=5)
            results.put(("winner", IntelligenceRunOrchestrationService(db).acquire(org_id, run_id).status))
        finally:
            db.rollback(); db.close()

    threads = [Thread(target=failed_transition, daemon=True), Thread(target=winning_transition, daemon=True)]
    for thread in threads: thread.start()
    for thread in threads: thread.join(timeout=8)
    assert not any(thread.is_alive() for thread in threads)
    assert {results.get_nowait()[0] for _ in range(2)} == {"failed", "winner"}
    with SessionLocal() as verify:
        row = verify.get(IntelligenceAnalysis, run_id)
        assert row.status == "RUNNING"
        assert verify.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.target_id == run_id, AuditEvent.action == "INTELLIGENCE_RUN_ACQUIRED")) == 1


def test_same_retry_key_isolated_by_organization():
    first_org, first_user, first_investigation = scope()
    second_org, second_user, second_investigation = scope()
    first = create_run(first_org, first_user, first_investigation, "shared-source")
    second = create_run(second_org, second_user, second_investigation, "shared-source")
    for org_id, run_id in ((first_org, first), (second_org, second)):
        run_transition(org_id, run_id, "acquire")
        run_transition(org_id, run_id, "fail")
    db_one, db_two = SessionLocal(), SessionLocal()
    try:
        one = IntelligenceRunOrchestrationService(db_one).retry(first_org, first, first_user, "shared-retry")
        two = IntelligenceRunOrchestrationService(db_two).retry(second_org, second, second_user, "shared-retry")
        assert one.id != two.id and one.org_id != two.org_id
    finally:
        db_one.close(); db_two.close()
