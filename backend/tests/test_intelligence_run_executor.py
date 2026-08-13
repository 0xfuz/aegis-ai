"""Phase 8.4.2 executor lifecycle tests: fake outcomes only, no AI/provider work."""
from datetime import datetime, timedelta, timezone
from threading import Barrier, Thread
from queue import Queue
from uuid import uuid4
import pytest
from sqlalchemy import func, select

from app.modules.ai_reasoning.domain.lease_policy import IntelligenceLeasePolicy
from app.modules.ai_reasoning.domain.run_executor import FakeExecutionOutcome, IntelligenceRunExecutor
from app.modules.ai_reasoning.domain.run_orchestration_service import IntelligenceRunOrchestrationService
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis, IntelligenceItem, IntelligenceEvidenceReference, IntelligenceClaimEvidenceLink, IntelligenceFactLink, IntelligenceReviewEvent
from app.modules.alert_triage.infrastructure.models import AlertClusterAssessment, AlertClusterMembership, AlertClusterPromotion
from app.modules.evidence.infrastructure.models import AuditEvent, Event, EntityRelationship
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.infrastructure.models import Finding, Investigation, InvestigationStatus, MitreMapping, RecommendedAction, Severity
from app.shared.database import SessionLocal

class Clock:
    def __init__(self): self.value=datetime(2026,1,1,tzinfo=timezone.utc)
    def __call__(self): return self.value
    def advance(self, seconds): self.value += timedelta(seconds=seconds)

class OutcomeAdapter:
    def __init__(self,outcome=FakeExecutionOutcome.SUCCESS): self.outcome,self.calls=outcome,0
    def execute(self,checkpoint): self.calls+=1; assert checkpoint(); return self.outcome

class RaisingAdapter:
    def __init__(self): self.calls=0
    def execute(self,checkpoint): self.calls+=1; raise RuntimeError("provider secret prompt sql")

class ControlledAdapter:
    def __init__(self, callback): self.callback,self.calls=callback,0
    def execute(self,checkpoint): self.calls+=1; self.callback(); checkpoint(); return FakeExecutionOutcome.SUCCESS

@pytest.fixture()
def db():
    session=SessionLocal()
    try: yield session
    finally: session.rollback();session.close()

def create_scope(db):
    suffix=uuid4().hex;org=Organization(name=suffix,slug=f"exec-{suffix}");role=Role(name=f"exec-role-{suffix}");db.add_all([org,role]);db.flush()
    user=User(org_id=org.id,role_id=role.id,email=f"{suffix}@test",hashed_password="x",full_name="executor")
    inv=Investigation(org_id=org.id,title="executor",source="test",severity=Severity.MEDIUM,status=InvestigationStatus.NEW);db.add_all([user,inv]);db.commit();return org,user,inv

def queued(db,key="executor"):
    org,user,inv=create_scope(db);clock=Clock();service=IntelligenceRunOrchestrationService(db,clock=clock);row=service.queue(org.id,inv.id,user.id,key);return org,user,inv,clock,row

def executor(adapter,clock): return IntelligenceRunExecutor(adapter,session_factory=SessionLocal,clock=clock)

def test_success_and_safe_failure_are_fenced_and_no_side_effects(db):
    org,user,inv,clock,row=queued(db);adapter=OutcomeAdapter()
    protected=(IntelligenceItem,IntelligenceEvidenceReference,IntelligenceClaimEvidenceLink,IntelligenceFactLink,IntelligenceReviewEvent,Finding,MitreMapping,RecommendedAction,AlertClusterMembership,AlertClusterAssessment,AlertClusterPromotion,Event,EntityRelationship)
    before={model:db.scalar(select(func.count()).select_from(model)) for model in protected}
    result=executor(adapter,clock).execute(row.id,"worker-success")
    db.refresh(row);assert result.outcome==FakeExecutionOutcome.SUCCESS and result.authoritative and row.status=="COMPLETED" and row.execution_attempt_count==1 and row.lease_owner_id is None
    failed=IntelligenceRunOrchestrationService(db,clock=clock).queue(org.id,inv.id,user.id,"safe-failure");failure=OutcomeAdapter(FakeExecutionOutcome.SAFE_FAILURE);outcome=executor(failure,clock).execute(failed.id,"worker-failure")
    db.refresh(failed);assert outcome.authoritative and failed.status=="FAILED" and failed.error_summary=="EXECUTION_FAILED" and failure.calls==1
    counts={model:db.scalar(select(func.count()).select_from(model)) for model in protected}
    assert counts==before

def test_exception_and_invalid_snapshot_fail_with_safe_categories(db):
    org,user,inv,clock,row=queued(db);raising=RaisingAdapter();result=executor(raising,clock).execute(row.id,"worker-raise")
    db.refresh(row);assert result.category=="EXECUTOR_UNAVAILABLE" and result.authoritative and row.error_summary=="EXECUTOR_UNAVAILABLE" and "secret" not in row.error_summary
    invalid=IntelligenceRunOrchestrationService(db,clock=clock).queue(org.id,inv.id,user.id,"bad-snapshot");invalid.input_snapshot={"fingerprint":"bad"};db.commit();adapter=OutcomeAdapter();result=executor(adapter,clock).execute(invalid.id,"worker-invalid")
    db.refresh(invalid);assert result.category=="EXECUTOR_VALIDATION_FAILED" and result.authoritative and invalid.status=="FAILED" and adapter.calls==0

def test_cancelled_and_terminal_runs_never_invoke_adapter(db):
    org,user,inv,clock,row=queued(db);service=IntelligenceRunOrchestrationService(db,clock=clock);service.cancel(org.id,row.id,user.id)
    adapter=OutcomeAdapter();result=executor(adapter,clock).execute(row.id,"worker-cancelled")
    assert not result.authoritative and adapter.calls==0
    terminal=service.queue(org.id,inv.id,user.id,"terminal");token=service.acquire_for_execution(org.id,terminal.id,"other");service.complete_execution(org.id,terminal.id,"other",token["lease_generation"])
    result=executor(adapter,clock).execute(terminal.id,"worker-terminal");assert not result.authoritative and adapter.calls==0

def test_controlled_cancellation_and_expiry_prevent_stale_completion(db):
    org,user,inv,clock,row=queued(db)
    def cancel():
        session=SessionLocal()
        try: IntelligenceRunOrchestrationService(session,clock=clock).cancel(org.id,row.id,user.id)
        finally: session.close()
    adapter=ControlledAdapter(cancel);result=executor(adapter,clock).execute(row.id,"worker-control")
    db.refresh(row);assert result.outcome==FakeExecutionOutcome.CANCELLED_OR_ABORTED and not result.authoritative and row.status=="CANCELLED" and row.lease_owner_id is None
    expired=IntelligenceRunOrchestrationService(db,clock=clock).queue(org.id,inv.id,user.id,"expiry")
    adapter=ControlledAdapter(lambda: clock.advance(61));result=executor(adapter,clock).execute(expired.id,"worker-expired")
    db.refresh(expired);assert not result.authoritative and expired.status=="RUNNING" and expired.execution_attempt_count==1
    assert IntelligenceRunOrchestrationService(db,clock=clock).recover_expired_leases(org.id)==[expired.id]
    token=IntelligenceRunOrchestrationService(db,clock=clock).acquire_for_execution(org.id,expired.id,"worker-new")
    assert token["lease_generation"]==2

def test_heartbeat_checkpoint_renews_without_attempt_or_generation_change(db):
    org,user,inv,clock,row=queued(db)
    class HeartbeatAdapter:
        def execute(self,checkpoint): clock.advance(20);assert checkpoint();return FakeExecutionOutcome.SUCCESS
    result=executor(HeartbeatAdapter(),clock).execute(row.id,"worker-heartbeat");db.refresh(row)
    assert result.authoritative and row.execution_attempt_count==1 and row.lease_generation==1
    actions=[event.action for event in db.scalars(select(AuditEvent).where(AuditEvent.target_id==row.id))]
    assert actions.count("INTELLIGENCE_RUN_HEARTBEAT")==1 and actions.count("INTELLIGENCE_RUN_COMPLETED")==1

def test_duplicate_executor_invocation_has_one_adapter_call_and_one_terminal_audit():
    db=SessionLocal();org,user,inv,clock,row=queued(db,"duplicate");org_id,run_id=org.id,row.id;db.close();barrier=Barrier(2);results=Queue();adapter=OutcomeAdapter()
    def invoke(index):
        try: barrier.wait();result=IntelligenceRunExecutor(adapter,session_factory=SessionLocal).execute(run_id,f"worker-{index}");results.put(result)
        except Exception as exc: results.put(exc)
    threads=[Thread(target=invoke,args=(index,),daemon=True) for index in range(2)];[thread.start() for thread in threads];[thread.join(8) for thread in threads]
    assert not any(thread.is_alive() for thread in threads);outcomes=[results.get_nowait() for _ in range(2)];assert sum(item.authoritative for item in outcomes)==1 and adapter.calls==1
    with SessionLocal() as verify: assert verify.get(IntelligenceAnalysis,run_id).status=="COMPLETED" and verify.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.target_id==run_id,AuditEvent.action=="INTELLIGENCE_RUN_COMPLETED"))==1
