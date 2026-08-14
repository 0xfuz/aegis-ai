"""Phase 8.4.3 PostgreSQL/dispatch tests; no Redis broker or provider is used."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
import pytest
from sqlalchemy import func, select
from app.modules.ai_reasoning.domain.run_dispatch import IntelligenceRunDispatcher, IntelligenceRunMaintenance
from app.modules.ai_reasoning.domain.lease_policy import IntelligenceLeasePolicy
from app.modules.ai_reasoning.domain.run_orchestration_service import IntelligenceRunOrchestrationService
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis
from app.modules.evidence.infrastructure.models import AuditEvent
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.infrastructure.models import Investigation, InvestigationStatus, Severity
from app.shared.database import SessionLocal
from app.workers import intelligence_tasks
from app.modules.ai_reasoning.domain.grounded_execution import GroundedResult

SETTINGS=SimpleNamespace(INTELLIGENCE_EXECUTION_ENABLED=True,INTELLIGENCE_DISPATCH_ENABLED=True,INTELLIGENCE_TASK_PROTOCOL_VERSION="intelligence-run-v1",INTELLIGENCE_QUEUE_MIN_AGE_SECONDS=15)
@pytest.fixture()
def db():
    session=SessionLocal()
    try: yield session
    finally: session.rollback();session.close()
def queued(db,key="dispatch"):
    suffix=uuid4().hex;org=Organization(name=suffix,slug=f"dispatch-{suffix}");role=Role(name=f"dispatch-role-{suffix}");db.add_all([org,role]);db.flush();user=User(org_id=org.id,role_id=role.id,email=f"{suffix}@test",hashed_password="x",full_name="dispatch");inv=Investigation(org_id=org.id,title="dispatch",source="test",severity=Severity.MEDIUM,status=InvestigationStatus.NEW);db.add_all([user,inv]);db.commit();row=IntelligenceRunOrchestrationService(db).queue(org.id,inv.id,user.id,key);return org,user,inv,row
def test_dispatch_uses_only_run_id_and_protocol_after_queue_commit(db):
    org,user,inv,row=queued(db);calls=[];assert IntelligenceRunDispatcher(db,sender=lambda run_id,protocol: calls.append((run_id,protocol)),settings=SETTINGS).dispatch_committed(row.id);assert calls==[(str(row.id),"intelligence-run-v1")];assert db.get(IntelligenceAnalysis,row.id).status=="QUEUED";assert db.scalar(select(AuditEvent).where(AuditEvent.target_id==row.id,AuditEvent.action=="INTELLIGENCE_RUN_DISPATCH_REQUESTED")) is not None
def test_redis_failure_keeps_queue_and_records_bounded_safe_audit(db):
    org,user,inv,row=queued(db);assert not IntelligenceRunDispatcher(db,sender=lambda *_: (_ for _ in ()).throw(RuntimeError("redis://secret")),settings=SETTINGS).dispatch_committed(row.id);db.refresh(row);assert row.status=="QUEUED";event=db.scalar(select(AuditEvent).where(AuditEvent.target_id==row.id,AuditEvent.action=="INTELLIGENCE_RUN_DISPATCH_FAILED"));assert event.metadata_["category"]=="DISPATCH_UNAVAILABLE" and "secret" not in str(event.metadata_)
def test_disabled_dispatch_never_calls_sender(db):
    org,user,inv,row=queued(db);calls=[];disabled=SimpleNamespace(**{**SETTINGS.__dict__,"INTELLIGENCE_EXECUTION_ENABLED":False});assert not IntelligenceRunDispatcher(db,sender=lambda *args: calls.append(args),settings=disabled).dispatch_committed(row.id) and calls==[] and row.status=="QUEUED"
def test_reconciliation_is_ordered_bounded_and_leaves_rows_queued(db):
    org,user,inv,first=queued(db,"first");second=IntelligenceRunOrchestrationService(db).queue(org.id,inv.id,user.id,"second");first.created_at=second.created_at=datetime(2000,1,1,tzinfo=timezone.utc);db.commit();calls=[];policy=IntelligenceLeasePolicy(queued_reconciliation_batch_size=100);maintenance=IntelligenceRunMaintenance(session_factory=SessionLocal,sender=lambda run_id,protocol: calls.append(run_id),settings=SETTINGS,policy=policy);dispatched=maintenance.reconcile_queued_runs();assert first.id in dispatched and second.id in dispatched and str(first.id) in calls and str(second.id) in calls;db.refresh(first);db.refresh(second);assert first.status==second.status=="QUEUED"
def test_recovery_redispatches_recovered_run(db):
    org,user,inv,row=queued(db);clock=lambda: datetime(2024,1,1,tzinfo=timezone.utc);service=IntelligenceRunOrchestrationService(db,clock=clock);service.acquire_for_execution(org.id,row.id,"worker");row.lease_expires_at=datetime(2025,1,1,tzinfo=timezone.utc);db.commit();calls=[];maintenance=IntelligenceRunMaintenance(session_factory=SessionLocal,sender=lambda run_id,protocol: calls.append(run_id),settings=SETTINGS);assert row.id in maintenance.recover_expired_leases() and str(row.id) in calls

def test_task_rejects_bad_payload_and_disabled_execution_without_database_mutation(db,monkeypatch):
    org,user,inv,row=queued(db);monkeypatch.setattr(intelligence_tasks,"get_settings",lambda: SETTINGS)
    assert intelligence_tasks.execute_intelligence_run.run("not-a-uuid","intelligence-run-v1")["category"]=="TASK_PAYLOAD_REJECTED"
    assert intelligence_tasks.execute_intelligence_run.run(str(row.id),"wrong")["category"]=="TASK_PROTOCOL_REJECTED"
    disabled=SimpleNamespace(**{**SETTINGS.__dict__,"INTELLIGENCE_EXECUTION_ENABLED":False});monkeypatch.setattr(intelligence_tasks,"get_settings",lambda: disabled)
    assert intelligence_tasks.execute_intelligence_run.run(str(row.id),"intelligence-run-v1")["category"]=="EXECUTION_DISABLED";db.refresh(row);assert row.status=="QUEUED"

def test_task_uses_internal_identity_and_explicit_test_adapter_only(db,monkeypatch):
    from app.modules.ai_reasoning.domain.run_executor import FakeExecutionOutcome
    org,user,inv,row=queued(db,"task");calls=[]
    class Adapter:
        def execute(self,checkpoint): calls.append(checkpoint());return FakeExecutionOutcome.SUCCESS
    monkeypatch.setattr(intelligence_tasks,"get_settings",lambda: SETTINGS);intelligence_tasks.install_test_adapter(Adapter())
    try:
        result=intelligence_tasks.execute_intelligence_run.run(str(row.id),"intelligence-run-v1")
    finally: intelligence_tasks.install_test_adapter(None)
    db.refresh(row);assert result["category"]=="SUCCESS" and calls==[True] and row.status=="COMPLETED" and row.lease_owner_id is None

@pytest.mark.parametrize(("result","expected"),[
    (GroundedResult(uuid4(),None,True),"COMPLETED"),
    (GroundedResult(uuid4(),"PROVIDER_TIMEOUT",True),"PROVIDER_TIMEOUT"),
    (GroundedResult(uuid4(),"LEASE_OWNERSHIP_LOST",False),"LEASE_OWNERSHIP_LOST"),
])
def test_task_maps_grounded_results_to_bounded_safe_categories(db,monkeypatch,result,expected):
    org,user,inv,row=queued(db,"grounded-return")
    class Executor:
        def execute(self,run_id,owner): return GroundedResult(run_id,result.category,result.authoritative)
    monkeypatch.setattr(intelligence_tasks,"get_settings",lambda: SETTINGS)
    monkeypatch.setattr(intelligence_tasks,"_executor",lambda: Executor())
    assert intelligence_tasks.execute_intelligence_run.run(str(row.id),"intelligence-run-v1")=={"category":expected}
    db.refresh(row)
    assert row.status=="QUEUED"

def test_terminal_redelivery_returns_safe_category_without_new_authority_mutation(db,monkeypatch):
    org,user,inv,row=queued(db,"terminal-redelivery")
    service=IntelligenceRunOrchestrationService(db)
    token=service.acquire_for_execution(org.id,row.id,"first-worker")
    service.complete_execution(org.id,row.id,"first-worker",token["lease_generation"])
    before_audits=db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.target_id==row.id))
    class Executor:
        def execute(self,run_id,owner): return GroundedResult(run_id,"LEASE_OWNERSHIP_LOST",False)
    monkeypatch.setattr(intelligence_tasks,"get_settings",lambda: SETTINGS)
    monkeypatch.setattr(intelligence_tasks,"_executor",lambda: Executor())
    assert intelligence_tasks.execute_intelligence_run.run(str(row.id),"intelligence-run-v1")=={"category":"LEASE_OWNERSHIP_LOST"}
    db.refresh(row)
    after_audits=db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.target_id==row.id))
    assert row.status=="COMPLETED" and row.execution_attempt_count==1 and row.provider_attempt_count==0 and before_audits==after_audits
