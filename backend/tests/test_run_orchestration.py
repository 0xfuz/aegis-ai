from uuid import uuid4
import pytest
from sqlalchemy import select
from app.modules.ai_reasoning.domain.run_orchestration_service import IntelligenceRunOrchestrationService
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceItem
from app.modules.evidence.infrastructure.models import AuditEvent
from app.modules.identity.infrastructure.models import Organization,Role,User
from app.modules.investigations.infrastructure.models import Investigation,InvestigationStatus,Severity
from app.shared.database import SessionLocal
from app.shared.exceptions import NotFoundError,ValidationError
@pytest.fixture()
def db():
 s=SessionLocal()
 try:yield s
 finally:s.rollback();s.close()
def setup(db):
 x=uuid4().hex;o=Organization(name=x,slug=f"run-{x}");r=Role(name=f"run-role-{x}");db.add_all([o,r]);db.flush();u=User(org_id=o.id,role_id=r.id,email=f"{x}@test",hashed_password="x",full_name="run");i=Investigation(org_id=o.id,title="run",source="test",severity=Severity.MEDIUM,status=InvestigationStatus.NEW);db.add_all([u,i]);db.commit();return o,u,i
def test_queue_lifecycle_audit_cancel_retry_and_no_claims(db):
 o,u,i=setup(db);s=IntelligenceRunOrchestrationService(db);q=s.queue(o.id,i.id,u.id,"one");assert q.status=="QUEUED" and s.queue(o.id,i.id,u.id,"one").id==q.id
 running=s.acquire(o.id,q.id);assert running.status=="RUNNING";done=s.complete(o.id,q.id);assert done.status=="COMPLETED"
 with pytest.raises(ValidationError):s.acquire(o.id,q.id)
 q2=s.queue(o.id,i.id,u.id,"two");s.cancel(o.id,q2.id,u.id,"stop");assert q2.status=="CANCELLED";retry=s.retry(o.id,q2.id,u.id,"three");assert retry.predecessor_analysis_id==q2.id and retry.status=="QUEUED"
 assert db.scalar(select(IntelligenceItem).where(IntelligenceItem.investigation_id==i.id)) is None
 assert db.scalar(select(AuditEvent).where(AuditEvent.target_id==q.id)) is not None
def test_failure_is_safe_and_foreign_actor_rejected(db):
 o,u,i=setup(db);s=IntelligenceRunOrchestrationService(db);q=s.queue(o.id,i.id,u.id,"one");s.acquire(o.id,q.id);row=s.fail(o.id,q.id,RuntimeError("phase8-sensitive-marker"));assert row.error_summary=="RUNTIMEERROR_FAILED" and "sensitive" not in row.error_summary
 other,other_user,_=setup(db)
 with pytest.raises(NotFoundError):s.cancel(other.id,q.id,other_user.id)
