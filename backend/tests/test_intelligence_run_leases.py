"""PostgreSQL lease/fencing contract for Phase 8.4.1; no executor is invoked."""
from datetime import datetime, timedelta, timezone
from threading import Barrier, Thread
from queue import Queue
from uuid import uuid4
import pytest
from sqlalchemy import func, select, text

from app.modules.ai_reasoning.domain.lease_policy import IntelligenceLeasePolicy
from app.modules.ai_reasoning.domain.run_orchestration_service import IntelligenceRunOrchestrationService
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis, IntelligenceItem, IntelligenceEvidenceReference, IntelligenceClaimEvidenceLink
from app.modules.evidence.infrastructure.models import AuditEvent
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.infrastructure.models import Investigation, InvestigationStatus, Severity
from app.shared.database import SessionLocal
from app.shared.exceptions import NotFoundError, ValidationError

@pytest.fixture()
def db():
    session=SessionLocal()
    try: yield session
    finally: session.rollback();session.close()

def scope(db):
    suffix=uuid4().hex;org=Organization(name=suffix,slug=f"lease-{suffix}");role=Role(name=f"lease-role-{suffix}")
    db.add_all([org,role]);db.flush();user=User(org_id=org.id,role_id=role.id,email=f"{suffix}@test",hashed_password="x",full_name="lease")
    inv=Investigation(org_id=org.id,title="lease",source="test",severity=Severity.MEDIUM,status=InvestigationStatus.NEW);db.add_all([user,inv]);db.commit();return org,user,inv

class Clock:
    def __init__(self): self.value=datetime(2026,1,1,tzinfo=timezone.utc)
    def __call__(self): return self.value
    def advance(self, seconds): self.value += timedelta(seconds=seconds)

def queued(db, key="run"):
    org,user,inv=scope(db);clock=Clock();service=IntelligenceRunOrchestrationService(db,clock=clock);row=service.queue(org.id,inv.id,user.id,key);return org,user,inv,clock,service,row

def test_policy_is_bounded_and_rejects_invalid_values():
    assert IntelligenceLeasePolicy().lease_seconds==60 and IntelligenceLeasePolicy().heartbeat_seconds==20 and IntelligenceLeasePolicy().max_execution_attempts==3
    for values in ({"lease_seconds":0},{"heartbeat_seconds":60},{"max_execution_attempts":0},{"recovery_batch_size":0},{"queued_reconciliation_batch_size":1001}):
        with pytest.raises(ValueError): IntelligenceLeasePolicy(**values)

def test_acquire_heartbeat_complete_and_safe_failure_clear_fenced_lease(db):
    org,user,inv,clock,service,row=queued(db)
    token=service.acquire_for_execution(org.id,row.id,"worker-1")
    db.refresh(row);assert row.status=="RUNNING" and row.execution_attempt_count==1 and row.lease_generation==1 and row.execution_started_at==clock.value
    clock.advance(20);renewed=service.heartbeat_execution(org.id,row.id,"worker-1",1);db.refresh(row)
    assert renewed["lease_expires_at"]==clock.value+timedelta(seconds=60) and row.execution_attempt_count==1 and row.lease_generation==1
    completed=service.complete_execution(org.id,row.id,"worker-1",1);assert completed.status=="COMPLETED" and completed.execution_finished_at==clock.value and completed.lease_owner_id is None
    failed=service.queue(org.id,inv.id,user.id,"failed");token=service.acquire_for_execution(org.id,failed.id,"worker-2")
    failed=service.fail_execution(org.id,failed.id,"worker-2",token["lease_generation"],RuntimeError("secret sql prompt marker"))
    assert failed.status=="FAILED" and failed.error_summary=="EXECUTION_FAILED" and "secret" not in failed.error_summary and failed.lease_expires_at is None

@pytest.mark.parametrize("operation",["wrong-owner","wrong-generation","expired","cancelled","terminal"])
def test_heartbeat_rejects_stale_and_non_running_leases(db,operation):
    org,user,inv,clock,service,row=queued(db,operation);token=service.acquire_for_execution(org.id,row.id,"worker-1")
    owner,generation="worker-1",token["lease_generation"]
    if operation=="wrong-owner": owner="worker-2"
    elif operation=="wrong-generation": generation+=1
    elif operation=="expired": clock.advance(61)
    elif operation=="cancelled": service.cancel(org.id,row.id,user.id)
    elif operation=="terminal": service.complete_execution(org.id,row.id,owner,generation)
    with pytest.raises(ValidationError): service.heartbeat_execution(org.id,row.id,owner,generation)

def test_recovery_reacquisition_fences_stale_worker_and_preserves_first_start(db):
    org,user,inv,clock,service,row=queued(db);first=service.acquire_for_execution(org.id,row.id,"worker-a");started=row.execution_started_at;clock.advance(61)
    assert service.recover_expired_leases(org.id)==[row.id];db.refresh(row);assert row.status=="QUEUED" and row.lease_owner_id is None and row.execution_attempt_count==1
    second=service.acquire_for_execution(org.id,row.id,"worker-b");db.refresh(row);assert row.execution_attempt_count==2 and second["lease_generation"]>first["lease_generation"] and row.execution_started_at==started
    with pytest.raises(ValidationError): service.complete_execution(org.id,row.id,"worker-a",first["lease_generation"])
    assert service.recover_expired_leases(org.id)==[]

def test_third_expired_attempt_exhausts_without_side_effects(db):
    org,user,inv,clock,service,row=queued(db)
    link_count=db.scalar(select(func.count()).select_from(IntelligenceClaimEvidenceLink))
    for attempt in range(3):
        service.acquire_for_execution(org.id,row.id,f"worker-{attempt}");clock.advance(61);service.recover_expired_leases(org.id)
        db.refresh(row)
        if attempt < 2: assert row.status=="QUEUED"
    assert row.status=="FAILED" and row.error_summary=="EXECUTION_ATTEMPTS_EXHAUSTED" and row.execution_finished_at==clock.value and row.lease_owner_id is None
    assert db.scalar(select(func.count()).select_from(IntelligenceItem).where(IntelligenceItem.analysis_id==row.id))==0
    assert db.scalar(select(func.count()).select_from(IntelligenceEvidenceReference).where(IntelligenceEvidenceReference.analysis_id==row.id))==0
    assert db.scalar(select(func.count()).select_from(IntelligenceClaimEvidenceLink))==link_count

def test_cancellation_clears_lease_and_fences_worker(db):
    org,user,inv,clock,service,row=queued(db);token=service.acquire_for_execution(org.id,row.id,"worker-1");cancelled=service.cancel(org.id,row.id,user.id,"stop")
    assert cancelled.status=="CANCELLED" and cancelled.execution_finished_at==clock.value and cancelled.lease_owner_id is None
    assert service.cancel(org.id,row.id,user.id).id==row.id
    with pytest.raises(ValidationError): service.fail_execution(org.id,row.id,"worker-1",token["lease_generation"],"EXECUTOR_UNAVAILABLE")
    actions=[x.action for x in db.scalars(select(AuditEvent).where(AuditEvent.target_id==row.id).order_by(AuditEvent.occurred_at))]
    assert actions.count("INTELLIGENCE_RUN_CANCELLED")==1

def test_foreign_org_cannot_acquire_or_recover(db):
    org,user,inv,clock,service,row=queued(db);other,_,_=scope(db)
    with pytest.raises(NotFoundError): service.acquire_for_execution(other.id,row.id,"worker-x")
    assert service.recover_expired_leases(other.id)==[]

def test_concurrent_lease_acquisition_has_one_winner():
    db=SessionLocal();org,user,inv,clock,service,row=queued(db,"race");org_id,run_id=org.id,row.id;db.close();barrier=Barrier(2);results=Queue()
    def acquire(index):
        session=SessionLocal()
        try:
            session.execute(text("SET lock_timeout = '1500ms'"));barrier.wait();token=IntelligenceRunOrchestrationService(session).acquire_for_execution(org_id,run_id,f"worker-{index}");results.put(("ok",token["lease_generation"]))
        except Exception as exc: results.put(("error",type(exc).__name__))
        finally: session.rollback();session.close()
    threads=[Thread(target=acquire,args=(index,),daemon=True) for index in range(2)]
    [thread.start() for thread in threads];[thread.join(8) for thread in threads];assert not any(thread.is_alive() for thread in threads)
    outcome=[results.get_nowait() for _ in range(2)];assert sorted(x[0] for x in outcome)==["error","ok"]
    with SessionLocal() as verify: assert verify.get(IntelligenceAnalysis,run_id).status=="RUNNING" and verify.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.target_id==run_id,AuditEvent.action=="INTELLIGENCE_RUN_ACQUIRED"))==1

def test_lease_schema_constraints_and_indexes_are_postgresql_enforced(db):
    org,user,inv,clock,service,row=queued(db,"schema")
    expected={"ix_intelligence_analyses_status_created_id","ix_intelligence_analyses_status_lease_expiry_id","ix_intelligence_analyses_lease_owner_status"}
    names=set(db.scalars(text("SELECT indexname FROM pg_indexes WHERE tablename = 'intelligence_analyses'")))
    assert expected <= names
    for sql in (
        "UPDATE intelligence_analyses SET lease_owner_id = 'partial' WHERE id = :id",
        "UPDATE intelligence_analyses SET lease_generation = -1 WHERE id = :id",
        "UPDATE intelligence_analyses SET execution_attempt_count = -1 WHERE id = :id",
        "UPDATE intelligence_analyses SET execution_finished_at = now() WHERE id = :id",
        "UPDATE intelligence_analyses SET lease_owner_id = 'bad', lease_acquired_at = now(), lease_heartbeat_at = now(), lease_expires_at = now() WHERE id = :id",
    ):
        with pytest.raises(Exception): db.execute(text(sql),{"id":row.id});db.commit()
        db.rollback()
    db.refresh(row);assert row.status=="QUEUED" and row.lease_owner_id is None and row.lease_generation==0 and row.execution_attempt_count==0
