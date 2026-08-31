"""Best-effort post-commit dispatch and PostgreSQL reconciliation."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import UUID
from sqlalchemy import asc, select
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.modules.ai_reasoning.domain.lease_policy import IntelligenceLeasePolicy
from app.modules.ai_reasoning.domain.run_orchestration_service import IntelligenceRunOrchestrationService
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis
from app.modules.evidence.infrastructure.models import AuditEvent
from app.shared.database import SessionLocal

DispatchSender=Callable[[str,str],None]

def celery_sender(run_id: str, protocol: str) -> None:
    from app.workers.intelligence_tasks import execute_intelligence_run
    execute_intelligence_run.apply_async(args=[run_id,protocol])

class IntelligenceRunDispatcher:
    def __init__(self, db: Session, *, sender: DispatchSender=celery_sender, settings=None):
        self.db,self.sender,self.settings=db,sender,settings or get_settings()

    def _audit(self,row: IntelligenceAnalysis, action: str, category: str | None=None) -> None:
        metadata={"status":row.status,"request_key":row.request_key}
        if category: metadata["category"]=category
        self.db.add(AuditEvent(org_id=row.org_id,investigation_id=row.investigation_id,actor_id=None,actor_type="system",action=action,target_type="IntelligenceAnalysis",target_id=row.id,occurred_at=datetime.now(timezone.utc),metadata_=metadata))

    def dispatch_committed(self, run_id: UUID) -> bool:
        """Call only after queue/retry commit; failures never alter run status."""
        if not (self.settings.INTELLIGENCE_EXECUTION_ENABLED and self.settings.INTELLIGENCE_DISPATCH_ENABLED): return False
        row=self.db.get(IntelligenceAnalysis,run_id)
        if not row or row.status != "QUEUED": return False
        try:
            self.sender(str(row.id),self.settings.INTELLIGENCE_TASK_PROTOCOL_VERSION)
            self._audit(row,"INTELLIGENCE_RUN_DISPATCH_REQUESTED");self.db.commit();return True
        except Exception:
            self.db.rollback()
            row=self.db.get(IntelligenceAnalysis,run_id)
            if row:
                try: self._audit(row,"INTELLIGENCE_RUN_DISPATCH_FAILED","DISPATCH_UNAVAILABLE");self.db.commit()
                except Exception: self.db.rollback()
            return False

class IntelligenceRunMaintenance:
    def __init__(self, *, session_factory: Callable[[],Session]=SessionLocal, sender: DispatchSender=celery_sender, settings=None, policy: IntelligenceLeasePolicy | None=None):
        self.session_factory,self.sender,self.settings,self.policy=session_factory,sender,settings or get_settings(),policy or IntelligenceLeasePolicy()

    def reconcile_queued_runs(self) -> list[UUID]:
        if not (self.settings.INTELLIGENCE_EXECUTION_ENABLED and self.settings.INTELLIGENCE_DISPATCH_ENABLED): return []
        db=self.session_factory()
        try:
            cutoff=datetime.now(timezone.utc)-timedelta(seconds=self.settings.INTELLIGENCE_QUEUE_MIN_AGE_SECONDS)
            ids=list(db.scalars(select(IntelligenceAnalysis.id).where(IntelligenceAnalysis.status=="QUEUED",IntelligenceAnalysis.created_at<=cutoff).order_by(asc(IntelligenceAnalysis.created_at),asc(IntelligenceAnalysis.id)).limit(self.policy.queued_reconciliation_batch_size)))
        finally: db.close()
        dispatched=[]
        for run_id in ids:
            db=self.session_factory()
            try:
                if IntelligenceRunDispatcher(db,sender=self.sender,settings=self.settings).dispatch_committed(run_id): dispatched.append(run_id)
            finally: db.close()
        return dispatched

    def recover_expired_leases(self) -> list[UUID]:
        db=self.session_factory()
        try:
            recovered=IntelligenceRunOrchestrationService(db,policy=self.policy).recover_expired_leases()
        finally: db.close()
        if not (self.settings.INTELLIGENCE_EXECUTION_ENABLED and self.settings.INTELLIGENCE_DISPATCH_ENABLED): return recovered
        for run_id in recovered:
            db=self.session_factory()
            try: IntelligenceRunDispatcher(db,sender=self.sender,settings=self.settings).dispatch_committed(run_id)
            finally: db.close()
        return recovered
