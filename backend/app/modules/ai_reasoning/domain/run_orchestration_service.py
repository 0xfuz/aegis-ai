"""Transport-independent, PostgreSQL-authoritative Intelligence Run orchestration."""
from __future__ import annotations
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from app.modules.ai_reasoning.domain.context_builder import ContextBuilder
from app.modules.ai_reasoning.domain.intelligence_contracts import validate_run_transition
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis
from app.modules.evidence.infrastructure.models import AuditEvent
from app.modules.investigations.domain.service import InvestigationService
from app.modules.identity.infrastructure.models import User
from app.shared.exceptions import NotFoundError, ValidationError

def safe_failure(exc: Exception) -> str:
    """Never retain exception messages, prompts, traces, or telemetry in a run."""
    return f"{type(exc).__name__.upper()}_FAILED"[:200]

class IntelligenceRunOrchestrationService:
    def __init__(self, db: Session): self.db=db
    def _run(self, org: UUID, run_id: UUID, lock=False):
        stmt=select(IntelligenceAnalysis).where(IntelligenceAnalysis.org_id==org,IntelligenceAnalysis.id==run_id)
        if lock: stmt=stmt.with_for_update()
        row=self.db.scalar(stmt)
        if not row: raise NotFoundError("Intelligence run not found.")
        return row
    def get(self, org: UUID, investigation: UUID, actor: UUID, run_id: UUID):
        self._actor(org,actor)
        InvestigationService(self.db).get_investigation(org,investigation)
        row=self._run(org,run_id)
        if row.investigation_id != investigation: raise NotFoundError("Intelligence run not found.")
        return row
    def list(self, org: UUID, investigation: UUID, actor: UUID, limit: int, offset: int):
        self._actor(org,actor)
        InvestigationService(self.db).get_investigation(org,investigation)
        return self.db.scalars(select(IntelligenceAnalysis).where(IntelligenceAnalysis.org_id==org,IntelligenceAnalysis.investigation_id==investigation).order_by(desc(IntelligenceAnalysis.created_at),desc(IntelligenceAnalysis.id)).limit(limit).offset(offset)).all()
    def _actor(self, org: UUID, actor: UUID):
        if actor is None or not self.db.scalar(select(User.id).where(User.id==actor,User.org_id==org,User.is_active.is_(True))): raise NotFoundError("Active analyst not found.")
    def _recover_request(self, org: UUID, investigation: UUID, request_key: str, fingerprint: str):
        existing=self.db.scalar(select(IntelligenceAnalysis).where(IntelligenceAnalysis.org_id==org,IntelligenceAnalysis.investigation_id==investigation,IntelligenceAnalysis.request_key==request_key))
        if existing and existing.input_hash==fingerprint: return existing
        raise ValidationError("Request identity conflicts with a different context fingerprint.")
    def _audit(self, org, inv, actor, action, row, previous, extra=None):
        self.db.add(AuditEvent(org_id=org,investigation_id=inv,actor_id=actor,actor_type="user" if actor else "system",action=action,target_type="IntelligenceAnalysis",target_id=row.id,occurred_at=datetime.now(timezone.utc),metadata_={"previous":previous,"status":row.status,"request_key":row.request_key,"input_hash":row.input_hash,**(extra or {})}))
    def _commit(self):
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise ValidationError("Unable to persist intelligence run.") from None
        except SQLAlchemyError:
            self.db.rollback()
            raise ValidationError("Unable to persist intelligence run.") from None
    def queue(self, org: UUID, investigation: UUID, actor: UUID, request_key: str):
        self._actor(org,actor)
        InvestigationService(self.db).get_investigation(org,investigation)
        snapshot=ContextBuilder(self.db).build(org,investigation)
        existing=self.db.scalar(select(IntelligenceAnalysis).where(IntelligenceAnalysis.org_id==org,IntelligenceAnalysis.investigation_id==investigation,IntelligenceAnalysis.request_key==request_key))
        if existing:
            if existing.input_hash != snapshot.fingerprint: raise ValidationError("Request identity conflicts with a different context fingerprint.")
            return existing
        row=IntelligenceAnalysis(org_id=org,investigation_id=investigation,provider="pending",model="pending",prompt_template_version="aiie-facts-alias-v1",input_snapshot=snapshot.snapshot,input_hash=snapshot.fingerprint,request_key=request_key,output_schema_version="aiie-output-v1",status="QUEUED")
        try:
            self.db.add(row);self.db.flush();self._audit(org,investigation,actor,"INTELLIGENCE_RUN_QUEUED",row,None);self._commit();return row
        except IntegrityError:
            self.db.rollback();return self._recover_request(org,investigation,request_key,snapshot.fingerprint)
        except SQLAlchemyError:
            self.db.rollback();raise ValidationError("Unable to persist intelligence run.") from None
        except Exception:
            self.db.rollback();raise
    def acquire(self, org: UUID, run_id: UUID):
        try:
            row=self._run(org,run_id,True);validate_run_transition(row.status,"RUNNING");previous=row.status;row.status="RUNNING";self._audit(org,row.investigation_id,None,"INTELLIGENCE_RUN_ACQUIRED",row,previous);self._commit();return row
        except SQLAlchemyError:
            self.db.rollback();raise ValidationError("Unable to persist intelligence run.") from None
        except Exception:
            self.db.rollback();raise
    def complete(self, org: UUID, run_id: UUID):
        try:
            row=self._run(org,run_id,True);validate_run_transition(row.status,"COMPLETED");previous=row.status;row.status="COMPLETED";row.generated_at=datetime.now(timezone.utc);self._audit(org,row.investigation_id,None,"INTELLIGENCE_RUN_COMPLETED",row,previous);self._commit();return row
        except SQLAlchemyError:
            self.db.rollback();raise ValidationError("Unable to persist intelligence run.") from None
        except Exception:
            self.db.rollback();raise
    def fail(self, org: UUID, run_id: UUID, exc: Exception):
        try:
            row=self._run(org,run_id,True);validate_run_transition(row.status,"FAILED");previous=row.status;row.status="FAILED";row.error_summary=safe_failure(exc);self._audit(org,row.investigation_id,None,"INTELLIGENCE_RUN_FAILED",row,previous,{"error_code":row.error_summary});self._commit();return row
        except SQLAlchemyError:
            self.db.rollback();raise ValidationError("Unable to persist intelligence run.") from None
        except Exception:
            self.db.rollback();raise
    def cancel(self, org: UUID, run_id: UUID, actor: UUID, reason: str=""):
        self._actor(org,actor)
        try:
            row=self._run(org,run_id,True)
            if row.status=="CANCELLED": return row
            validate_run_transition(row.status,"CANCELLED");previous=row.status;row.status="CANCELLED";self._audit(org,row.investigation_id,actor,"INTELLIGENCE_RUN_CANCELLED",row,previous,{"reason":reason[:200]});self._commit();return row
        except SQLAlchemyError:
            self.db.rollback();raise ValidationError("Unable to persist intelligence run.") from None
        except Exception:
            self.db.rollback();raise
    def retry(self, org: UUID, run_id: UUID, actor: UUID, request_key: str):
        self._actor(org,actor)
        try:
            previous=self._run(org,run_id,True)
            if previous.status not in {"FAILED","CANCELLED"}: raise ValidationError("Only failed or cancelled runs may be retried.")
            snapshot=ContextBuilder(self.db).build(org,previous.investigation_id)
            row=IntelligenceAnalysis(org_id=org,investigation_id=previous.investigation_id,provider=previous.provider,model=previous.model,prompt_template_version=previous.prompt_template_version,input_snapshot=snapshot.snapshot,input_hash=snapshot.fingerprint,request_key=request_key,output_schema_version=previous.output_schema_version,predecessor_analysis_id=previous.id,status="QUEUED")
            self.db.add(row);self.db.flush();self._audit(org,row.investigation_id,actor,"INTELLIGENCE_RUN_RETRY_QUEUED",row,previous.status,{"predecessor_run_id":str(previous.id)});self._commit();return row
        except IntegrityError:
            self.db.rollback();return self._recover_request(org,previous.investigation_id,request_key,snapshot.fingerprint)
        except SQLAlchemyError:
            self.db.rollback();raise ValidationError("Unable to persist intelligence run.") from None
        except Exception:
            self.db.rollback();raise
