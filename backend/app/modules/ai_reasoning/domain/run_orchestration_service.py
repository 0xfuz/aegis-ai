"""Transport-independent, PostgreSQL-authoritative Intelligence Run orchestration."""
from __future__ import annotations
import re
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import UUID
from sqlalchemy import asc, desc, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from app.modules.ai_reasoning.domain.context_builder import ContextBuilder
from app.modules.ai_reasoning.domain.intelligence_contracts import validate_run_transition
from app.modules.ai_reasoning.domain.lease_policy import IntelligenceLeasePolicy
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis
from app.modules.evidence.infrastructure.models import AuditEvent
from app.modules.investigations.domain.service import InvestigationService
from app.modules.identity.infrastructure.models import User
from app.shared.exceptions import NotFoundError, ValidationError

_WORKER_ATTEMPT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SAFE_FAILURE_CODES = {"EXECUTOR_UNAVAILABLE", "EXECUTOR_VALIDATION_FAILED", "EXECUTION_FAILED", "EXECUTION_ATTEMPTS_EXHAUSTED", "PROVIDER_DISABLED", "PROVIDER_MISCONFIGURED", "PROVIDER_UNAVAILABLE", "PROVIDER_MODEL_UNAVAILABLE", "PROVIDER_TIMEOUT", "PROVIDER_RESPONSE_TOO_LARGE", "PROVIDER_PROTOCOL_ERROR", "PROVIDER_CANCELLED", "PROVIDER_CONCURRENCY_LIMIT", "PROMPT_CONTEXT_INVALID", "PROMPT_TOO_LARGE", "CANDIDATE_MALFORMED_JSON", "CANDIDATE_SCHEMA_INVALID", "CANDIDATE_UNSUPPORTED_TYPE", "CANDIDATE_ALIAS_INVALID", "CANDIDATE_ROLE_INVALID", "CANDIDATE_RELATION_INVALID", "CANDIDATE_DUPLICATE", "CANDIDATE_SECRET_DETECTED", "CANDIDATE_TOO_LARGE"}

def safe_failure(exc: Exception | str) -> str:
    """Map all execution failures to bounded categories; never retain messages."""
    if isinstance(exc, str) and exc in _SAFE_FAILURE_CODES:
        return exc
    return "EXECUTION_FAILED"

class IntelligenceRunOrchestrationService:
    def __init__(self, db: Session, *, policy: IntelligenceLeasePolicy | None = None, clock: Callable[[], datetime] | None = None):
        self.db, self.policy, self._clock = db, policy or IntelligenceLeasePolicy(), clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None: raise ValueError("Lease clock must be timezone-aware.")
        return now.astimezone(timezone.utc)

    def _run(self, org: UUID, run_id: UUID, lock=False):
        stmt=select(IntelligenceAnalysis).where(IntelligenceAnalysis.org_id==org,IntelligenceAnalysis.id==run_id)
        if lock: stmt=stmt.with_for_update()
        row=self.db.scalar(stmt)
        if not row: raise NotFoundError("Intelligence run not found.")
        return row

    def get(self, org: UUID, investigation: UUID, actor: UUID, run_id: UUID):
        self._actor(org,actor); InvestigationService(self.db).get_investigation(org,investigation)
        row=self._run(org,run_id)
        if row.investigation_id != investigation: raise NotFoundError("Intelligence run not found.")
        return row

    def list(self, org: UUID, investigation: UUID, actor: UUID, limit: int, offset: int):
        self._actor(org,actor); InvestigationService(self.db).get_investigation(org,investigation)
        return self.db.scalars(select(IntelligenceAnalysis).where(IntelligenceAnalysis.org_id==org,IntelligenceAnalysis.investigation_id==investigation).order_by(desc(IntelligenceAnalysis.created_at),desc(IntelligenceAnalysis.id)).limit(limit).offset(offset)).all()

    def _actor(self, org: UUID, actor: UUID):
        if actor is None or not self.db.scalar(select(User.id).where(User.id==actor,User.org_id==org,User.is_active.is_(True))): raise NotFoundError("Active analyst not found.")

    def _recover_request(self, org: UUID, investigation: UUID, request_key: str, fingerprint: str):
        existing=self.db.scalar(select(IntelligenceAnalysis).where(IntelligenceAnalysis.org_id==org,IntelligenceAnalysis.investigation_id==investigation,IntelligenceAnalysis.request_key==request_key))
        if existing and existing.input_hash==fingerprint: return existing
        raise ValidationError("Request identity conflicts with a different context fingerprint.")

    def _audit(self, org, inv, actor, action, row, previous, extra=None):
        safe_extra={key:value for key,value in (extra or {}).items() if key in {"error_code","lease_generation","execution_attempt_count","predecessor_run_id","reason"}}
        self.db.add(AuditEvent(org_id=org,investigation_id=inv,actor_id=actor,actor_type="user" if actor else "system",action=action,target_type="IntelligenceAnalysis",target_id=row.id,occurred_at=self._now(),metadata_={"previous":previous,"status":row.status,"request_key":row.request_key,"input_hash":row.input_hash,**safe_extra}))

    def _commit(self):
        try: self.db.commit()
        except (IntegrityError, SQLAlchemyError): self.db.rollback(); raise ValidationError("Unable to persist intelligence run.") from None

    def _clear_lease(self, row: IntelligenceAnalysis) -> None:
        row.lease_owner_id=row.lease_acquired_at=row.lease_expires_at=row.lease_heartbeat_at=None

    def _validate_worker(self, worker_attempt_id: str) -> None:
        if not isinstance(worker_attempt_id,str) or not _WORKER_ATTEMPT.fullmatch(worker_attempt_id): raise ValidationError("Invalid worker attempt identity.")

    def _require_lease(self, row: IntelligenceAnalysis, worker_attempt_id: str, generation: int, now: datetime) -> None:
        self._validate_worker(worker_attempt_id)
        if row.status != "RUNNING" or row.lease_owner_id != worker_attempt_id or row.lease_generation != generation or row.lease_expires_at is None or row.lease_expires_at <= now:
            raise ValidationError("Intelligence execution lease is no longer valid.")

    def queue(self, org: UUID, investigation: UUID, actor: UUID, request_key: str):
        self._actor(org,actor); InvestigationService(self.db).get_investigation(org,investigation); snapshot=ContextBuilder(self.db).build(org,investigation)
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

    def acquire_for_execution(self, org: UUID, run_id: UUID, worker_attempt_id: str) -> dict[str, object]:
        self._validate_worker(worker_attempt_id); now=self._now()
        try:
            row=self._run(org,run_id,True)
            if row.status != "QUEUED" or row.execution_attempt_count >= self.policy.max_execution_attempts: raise ValidationError("Intelligence run is not available for execution.")
            previous=row.status; row.status="RUNNING"; row.execution_attempt_count += 1; row.lease_generation += 1
            row.lease_owner_id=worker_attempt_id; row.lease_acquired_at=row.lease_heartbeat_at=now; row.lease_expires_at=now+timedelta(seconds=self.policy.lease_seconds)
            if row.execution_started_at is None: row.execution_started_at=now
            row.execution_finished_at=None
            self._audit(org,row.investigation_id,None,"INTELLIGENCE_RUN_ACQUIRED",row,previous,{"lease_generation":row.lease_generation,"execution_attempt_count":row.execution_attempt_count});self._commit()
            return {"run_id":row.id,"lease_generation":row.lease_generation,"lease_expires_at":row.lease_expires_at}
        except SQLAlchemyError:
            self.db.rollback();raise ValidationError("Unable to persist intelligence run.") from None
        except Exception:
            self.db.rollback();raise

    def heartbeat_execution(self, org: UUID, run_id: UUID, worker_attempt_id: str, generation: int) -> dict[str, object]:
        now=self._now()
        try:
            row=self._run(org,run_id,True);self._require_lease(row,worker_attempt_id,generation,now)
            row.lease_heartbeat_at=now;row.lease_expires_at=now+timedelta(seconds=self.policy.lease_seconds)
            self._audit(org,row.investigation_id,None,"INTELLIGENCE_RUN_HEARTBEAT",row,"RUNNING",{"lease_generation":generation,"execution_attempt_count":row.execution_attempt_count});self._commit()
            return {"run_id":row.id,"lease_generation":generation,"lease_expires_at":row.lease_expires_at}
        except SQLAlchemyError:
            self.db.rollback();raise ValidationError("Unable to persist intelligence run.") from None
        except Exception:
            self.db.rollback();raise

    def complete_execution(self, org: UUID, run_id: UUID, worker_attempt_id: str, generation: int):
        now=self._now()
        try:
            row=self._run(org,run_id,True);self._require_lease(row,worker_attempt_id,generation,now);previous=row.status;row.status="COMPLETED";row.generated_at=row.execution_finished_at=now;self._clear_lease(row)
            self._audit(org,row.investigation_id,None,"INTELLIGENCE_RUN_COMPLETED",row,previous,{"lease_generation":generation,"execution_attempt_count":row.execution_attempt_count});self._commit();return row
        except SQLAlchemyError:
            self.db.rollback();raise ValidationError("Unable to persist intelligence run.") from None
        except Exception:
            self.db.rollback();raise

    def fail_execution(self, org: UUID, run_id: UUID, worker_attempt_id: str, generation: int, error: Exception | str):
        now=self._now()
        try:
            row=self._run(org,run_id,True);self._require_lease(row,worker_attempt_id,generation,now);previous=row.status;row.status="FAILED";row.error_summary=safe_failure(error);row.execution_finished_at=now;self._clear_lease(row)
            self._audit(org,row.investigation_id,None,"INTELLIGENCE_RUN_FAILED",row,previous,{"error_code":row.error_summary,"lease_generation":generation,"execution_attempt_count":row.execution_attempt_count});self._commit();return row
        except SQLAlchemyError:
            self.db.rollback();raise ValidationError("Unable to persist intelligence run.") from None
        except Exception:
            self.db.rollback();raise

    # Compatibility wrappers retain the existing internal test/service seam;
    # public APIs do not expose these worker transitions.
    def acquire(self, org: UUID, run_id: UUID):
        self.acquire_for_execution(org,run_id,"legacy-orchestration")
        return self._run(org,run_id)
    def complete(self, org: UUID, run_id: UUID):
        row=self._run(org,run_id); return self.complete_execution(org,run_id,row.lease_owner_id or "legacy-orchestration",row.lease_generation)
    def fail(self, org: UUID, run_id: UUID, exc: Exception):
        row=self._run(org,run_id); return self.fail_execution(org,run_id,row.lease_owner_id or "legacy-orchestration",row.lease_generation,exc)

    def cancel(self, org: UUID, run_id: UUID, actor: UUID, reason: str=""):
        self._actor(org,actor)
        try:
            row=self._run(org,run_id,True)
            if row.status=="CANCELLED": return row
            validate_run_transition(row.status,"CANCELLED");previous=row.status;row.status="CANCELLED"
            if row.execution_started_at is not None: row.execution_finished_at=self._now()
            self._clear_lease(row);self._audit(org,row.investigation_id,actor,"INTELLIGENCE_RUN_CANCELLED",row,previous,{"reason":reason[:200]});self._commit();return row
        except SQLAlchemyError:
            self.db.rollback();raise ValidationError("Unable to persist intelligence run.") from None
        except Exception:
            self.db.rollback();raise

    def recover_expired_leases(self, org: UUID | None = None) -> list[UUID]:
        now=self._now();stmt=select(IntelligenceAnalysis).where(IntelligenceAnalysis.status=="RUNNING",IntelligenceAnalysis.lease_expires_at < now)
        if org is not None: stmt=stmt.where(IntelligenceAnalysis.org_id==org)
        rows=self.db.scalars(stmt.order_by(asc(IntelligenceAnalysis.lease_expires_at),asc(IntelligenceAnalysis.id)).limit(self.policy.recovery_batch_size).with_for_update(skip_locked=True)).all(); recovered=[]
        try:
            for row in rows:
                previous=row.status;self._audit(row.org_id,row.investigation_id,None,"INTELLIGENCE_RUN_LEASE_EXPIRED",row,previous,{"lease_generation":row.lease_generation,"execution_attempt_count":row.execution_attempt_count});self._clear_lease(row)
                if row.execution_attempt_count >= self.policy.max_execution_attempts:
                    row.status="FAILED";row.error_summary="EXECUTION_ATTEMPTS_EXHAUSTED";row.execution_finished_at=now;action="INTELLIGENCE_RUN_ATTEMPTS_EXHAUSTED"
                else:
                    row.status="QUEUED";action="INTELLIGENCE_RUN_RECOVERED_TO_QUEUE"
                self._audit(row.org_id,row.investigation_id,None,action,row,previous,{"error_code":row.error_summary,"lease_generation":row.lease_generation,"execution_attempt_count":row.execution_attempt_count});recovered.append(row.id)
            if rows: self._commit()
            return recovered
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
