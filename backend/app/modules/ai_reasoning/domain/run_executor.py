"""Fenced, transport-independent executor for already-queued intelligence runs.

This Phase 8.4 boundary intentionally has no provider, prompt, output, claim,
or dispatch dependency. A later worker may call it with only a run ID and a
trusted worker-attempt ID.
"""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Callable, Protocol
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.modules.ai_reasoning.domain.context_builder import BUILDER_VERSION, CONTEXT_VERSION, ContextPolicy
from app.modules.ai_reasoning.domain.lease_policy import IntelligenceLeasePolicy
from app.modules.ai_reasoning.domain.run_orchestration_service import IntelligenceRunOrchestrationService
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis
from app.modules.investigations.domain.service import InvestigationService
from app.shared.database import SessionLocal
from app.shared.exceptions import NotFoundError, ValidationError

PROMPT_TEMPLATE_VERSION = "aiie-facts-alias-v1"
OUTPUT_SCHEMA_VERSION = "aiie-output-v1"

class FakeExecutionOutcome(StrEnum):
    SUCCESS = "SUCCESS"
    SAFE_FAILURE = "SAFE_FAILURE"
    CANCELLED_OR_ABORTED = "CANCELLED_OR_ABORTED"

class FakeExecutionAdapter(Protocol):
    def execute(self, checkpoint: Callable[[], bool]) -> FakeExecutionOutcome: ...

@dataclass(frozen=True)
class ExecutionResult:
    run_id: UUID
    outcome: FakeExecutionOutcome
    category: str | None
    authoritative: bool

class IntelligenceRunExecutor:
    """Uses fresh, short-lived sessions and orchestration fencing for every write."""
    def __init__(self, adapter: FakeExecutionAdapter, *, session_factory: Callable[[], Session] = SessionLocal,
                 policy: IntelligenceLeasePolicy | None = None, clock: Callable[[], datetime] | None = None):
        self.adapter, self.session_factory = adapter, session_factory
        self.policy, self.clock = policy or IntelligenceLeasePolicy(), clock or (lambda: datetime.now(timezone.utc))

    def _service(self, db: Session) -> IntelligenceRunOrchestrationService:
        return IntelligenceRunOrchestrationService(db, policy=self.policy, clock=self.clock)

    def _close(self, db: Session) -> None:
        try: db.rollback()
        finally: db.close()

    def _run_identity(self, run_id: UUID) -> tuple[UUID, UUID]:
        db=self.session_factory()
        try:
            row=db.scalar(select(IntelligenceAnalysis).where(IntelligenceAnalysis.id==run_id))
            if not row: raise NotFoundError("Intelligence run not found.")
            return row.org_id,row.investigation_id
        finally: self._close(db)

    def _validate_snapshot(self, db: Session, org: UUID, investigation: UUID, run_id: UUID, owner: str, generation: int) -> None:
        row=db.scalar(select(IntelligenceAnalysis).where(IntelligenceAnalysis.id==run_id, IntelligenceAnalysis.org_id==org))
        if not row or row.investigation_id != investigation or row.status != "RUNNING" or row.lease_owner_id != owner or row.lease_generation != generation:
            raise ValidationError("Intelligence execution lease is no longer valid.")
        InvestigationService(db).get_investigation(org, investigation)
        snapshot=row.input_snapshot
        if not isinstance(snapshot, dict): raise ValidationError("Invalid persisted execution context.")
        try:
            encoded=json.dumps(snapshot, sort_keys=True, separators=(",",":"), ensure_ascii=False).encode()
        except (TypeError, ValueError):
            raise ValidationError("Invalid persisted execution context.") from None
        if len(encoded) > ContextPolicy().max_bytes + 128: raise ValidationError("Invalid persisted execution context.")
        provided=snapshot.get("fingerprint")
        material={key:value for key,value in snapshot.items() if key != "fingerprint"}
        expected=hashlib.sha256(json.dumps(material,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        if not isinstance(provided,str) or row.input_hash != expected or provided != expected:
            raise ValidationError("Invalid persisted execution context.")
        if snapshot.get("organization_id") != str(org) or snapshot.get("investigation_id") != str(investigation): raise ValidationError("Invalid persisted execution context.")
        if snapshot.get("context_version") != CONTEXT_VERSION or snapshot.get("builder_version") != BUILDER_VERSION or not isinstance(snapshot.get("policy"),dict): raise ValidationError("Invalid persisted execution context.")
        if row.prompt_template_version != PROMPT_TEMPLATE_VERSION or row.output_schema_version != OUTPUT_SCHEMA_VERSION or not isinstance(row.request_key,str) or not row.request_key:
            raise ValidationError("Invalid persisted execution context.")
        if row.predecessor_analysis_id:
            predecessor=db.get(IntelligenceAnalysis,row.predecessor_analysis_id)
            if not predecessor or predecessor.org_id != org or predecessor.investigation_id != investigation or predecessor.status not in {"FAILED","CANCELLED"}:
                raise ValidationError("Invalid persisted execution context.")

    def _ownership(self, org: UUID, run_id: UUID, owner: str, generation: int, last_heartbeat: datetime) -> tuple[bool, datetime]:
        db=self.session_factory()
        try:
            service=self._service(db); now=service._now()
            row=db.scalar(select(IntelligenceAnalysis).where(IntelligenceAnalysis.id==run_id,IntelligenceAnalysis.org_id==org))
            if not row or row.status != "RUNNING" or row.lease_owner_id != owner or row.lease_generation != generation or row.lease_expires_at is None or row.lease_expires_at <= now:
                return False,last_heartbeat
            if (now-last_heartbeat).total_seconds() >= self.policy.heartbeat_seconds:
                token=service.heartbeat_execution(org,run_id,owner,generation)
                return True, token["lease_expires_at"] - timedelta(seconds=self.policy.lease_seconds)
            return True,last_heartbeat
        except (ValidationError, NotFoundError):
            return False,last_heartbeat
        finally: self._close(db)

    def _fail_if_owned(self, org: UUID, run_id: UUID, owner: str, generation: int, category: str) -> bool:
        db=self.session_factory()
        try:
            self._service(db).fail_execution(org,run_id,owner,generation,category)
            return True
        except (ValidationError, NotFoundError):
            return False
        finally: self._close(db)

    def execute(self, run_id: UUID, trusted_worker_attempt_id: str) -> ExecutionResult:
        org, investigation=self._run_identity(run_id)
        db=self.session_factory()
        try:
            token=self._service(db).acquire_for_execution(org,run_id,trusted_worker_attempt_id)
        except (ValidationError, NotFoundError):
            return ExecutionResult(run_id,FakeExecutionOutcome.CANCELLED_OR_ABORTED,"LEASE_OWNERSHIP_LOST",False)
        finally:
            self._close(db)
        generation=int(token["lease_generation"]); last_heartbeat=self.clock()
        db=self.session_factory()
        try:
            self._validate_snapshot(db,org,investigation,run_id,trusted_worker_attempt_id,generation)
        except (ValidationError, NotFoundError):
            authoritative=self._fail_if_owned(org,run_id,trusted_worker_attempt_id,generation,"EXECUTOR_VALIDATION_FAILED")
            return ExecutionResult(run_id,FakeExecutionOutcome.SAFE_FAILURE,"EXECUTOR_VALIDATION_FAILED",authoritative)
        finally:
            self._close(db)
        alive,last_heartbeat=self._ownership(org,run_id,trusted_worker_attempt_id,generation,last_heartbeat)
        if not alive: return ExecutionResult(run_id,FakeExecutionOutcome.CANCELLED_OR_ABORTED,"LEASE_OWNERSHIP_LOST",False)
        heartbeat_state={"at":last_heartbeat}
        def checkpoint() -> bool:
            alive, heartbeat_state["at"] = self._ownership(org,run_id,trusted_worker_attempt_id,generation,heartbeat_state["at"])
            return alive
        try:
            outcome=self.adapter.execute(checkpoint)
        except Exception:
            authoritative=self._fail_if_owned(org,run_id,trusted_worker_attempt_id,generation,"EXECUTOR_UNAVAILABLE")
            return ExecutionResult(run_id,FakeExecutionOutcome.SAFE_FAILURE,"EXECUTOR_UNAVAILABLE",authoritative)
        alive,_=self._ownership(org,run_id,trusted_worker_attempt_id,generation,heartbeat_state["at"])
        if not alive: return ExecutionResult(run_id,FakeExecutionOutcome.CANCELLED_OR_ABORTED,"LEASE_OWNERSHIP_LOST",False)
        if outcome is FakeExecutionOutcome.SUCCESS:
            db=self.session_factory()
            try:
                self._service(db).complete_execution(org,run_id,trusted_worker_attempt_id,generation)
                return ExecutionResult(run_id,outcome,None,True)
            except (ValidationError, NotFoundError):
                return ExecutionResult(run_id,FakeExecutionOutcome.CANCELLED_OR_ABORTED,"LEASE_OWNERSHIP_LOST",False)
            finally: self._close(db)
        category="EXECUTION_FAILED" if outcome is FakeExecutionOutcome.SAFE_FAILURE else "EXECUTOR_UNAVAILABLE"
        authoritative=self._fail_if_owned(org,run_id,trusted_worker_attempt_id,generation,category)
        return ExecutionResult(run_id,outcome,category,authoritative)
