"""Leased, provider-grounded execution.  Candidate persistence owns completion."""
from __future__ import annotations
import hashlib
from dataclasses import dataclass
from datetime import datetime,timezone
from typing import Callable
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.modules.ai_reasoning.domain.candidate_persistence import CandidatePersistenceService
from app.modules.ai_reasoning.domain.lease_policy import IntelligenceLeasePolicy
from app.modules.ai_reasoning.domain.prompt_contract import ContractError,build_prompt,validate_candidate
from app.modules.ai_reasoning.domain.run_orchestration_service import IntelligenceRunOrchestrationService
from app.modules.ai_reasoning.domain.trusted_provider import IntelligenceCandidateProvider,ProviderCategory,ProviderFailure,TrustedPromptRequest
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis
from app.shared.database import SessionLocal
from app.shared.exceptions import NotFoundError,ValidationError

@dataclass(frozen=True)
class GroundedResult: run_id:UUID; category:str|None; authoritative:bool
class GroundedIntelligenceExecutionPipeline:
 def __init__(self,provider:IntelligenceCandidateProvider,*,session_factory:Callable[[],Session]=SessionLocal,policy=None,clock=None):self.provider,self.session_factory,self.policy,self.clock=provider,session_factory,policy or IntelligenceLeasePolicy(),clock or (lambda:datetime.now(timezone.utc))
 def _close(self,db):
  try:db.rollback()
  finally:db.close()
 def _identity(self,run_id):
  db=self.session_factory()
  try:
   row=db.get(IntelligenceAnalysis,run_id)
   if not row:raise NotFoundError("Intelligence run not found.")
   return row.org_id
  finally:self._close(db)
 def _owned(self,org,run,owner,generation):
  db=self.session_factory()
  try:
   service=IntelligenceRunOrchestrationService(db,policy=self.policy,clock=self.clock);row=db.get(IntelligenceAnalysis,run);now=service._now()
   if not row or row.status!="RUNNING" or row.lease_owner_id!=owner or row.lease_generation!=generation or not row.lease_expires_at or row.lease_expires_at<=now:return False
   if (now-row.lease_heartbeat_at).total_seconds()>=self.policy.heartbeat_seconds:service.heartbeat_execution(org,run,owner,generation)
   return True
  except (ValidationError,NotFoundError):return False
  finally:self._close(db)
 def _fail(self,org,run,owner,generation,category):
  db=self.session_factory()
  try:
   row=db.scalar(select(IntelligenceAnalysis).where(IntelligenceAnalysis.id==run,IntelligenceAnalysis.org_id==org).with_for_update())
   if row and row.provider_call_started_at is not None: row.provider_call_finished_at=self.clock()
   IntelligenceRunOrchestrationService(db,policy=self.policy,clock=self.clock).fail_execution(org,run,owner,generation,category);return True
  except (ValidationError,NotFoundError):return False
  finally:self._close(db)
 def _start(self,org,run,owner,generation,prompt_fingerprint):
  db=self.session_factory()
  try:
   service=IntelligenceRunOrchestrationService(db,policy=self.policy,clock=self.clock);row=db.scalar(select(IntelligenceAnalysis).where(IntelligenceAnalysis.id==run,IntelligenceAnalysis.org_id==org).with_for_update());now=service._now()
   if not row or row.status!="RUNNING" or row.lease_owner_id!=owner or row.lease_generation!=generation or not row.lease_expires_at or row.lease_expires_at<=now or row.provider_attempt_count>=self.policy.max_execution_attempts:raise ValidationError("Intelligence execution lease is no longer valid.")
   row.provider_attempt_count+=1;row.provider_execution_version="grounded-execution-v1";row.provider_request_fingerprint=prompt_fingerprint;row.provider_call_started_at=now;row.provider_call_finished_at=None;db.commit();return row.input_snapshot,row.input_hash
  except Exception:db.rollback();raise
  finally:db.close()
 def execute(self,run_id:UUID,owner:str)->GroundedResult:
  try:org=self._identity(run_id)
  except NotFoundError:return GroundedResult(run_id,"LEASE_OWNERSHIP_LOST",False)
  db=self.session_factory()
  try:token=IntelligenceRunOrchestrationService(db,policy=self.policy,clock=self.clock).acquire_for_execution(org,run_id,owner)
  except (ValidationError,NotFoundError):return GroundedResult(run_id,"LEASE_OWNERSHIP_LOST",False)
  finally:self._close(db)
  generation=token["lease_generation"]
  try:
   db=self.session_factory();row=db.get(IntelligenceAnalysis,run_id);artifact=build_prompt(row.input_snapshot,row.input_hash);snapshot,fingerprint=self._start(org,run_id,owner,generation,artifact.prompt_fingerprint)
  except ContractError as exc:return GroundedResult(run_id,exc.category.value,self._fail(org,run_id,owner,generation,"EXECUTOR_VALIDATION_FAILED"))
  except Exception:return GroundedResult(run_id,"EXECUTOR_VALIDATION_FAILED",self._fail(org,run_id,owner,generation,"EXECUTOR_VALIDATION_FAILED"))
  finally:
   try:self._close(db)
   except UnboundLocalError:pass
  request=TrustedPromptRequest(prompt_body=artifact.system_instructions+"\n"+artifact.evidence_context,idempotency_key=hashlib.sha256(f"{run_id}:{generation}:{artifact.prompt_fingerprint}".encode()).hexdigest())
  try:
   response=self.provider.generate(request,lambda:self._owned(org,run_id,owner,generation));candidate=validate_candidate(response.document,artifact.aliases)
  except ProviderFailure as exc:return GroundedResult(run_id,exc.category.value,self._fail(org,run_id,owner,generation,exc.category.value))
  except ContractError as exc:return GroundedResult(run_id,exc.category.value,self._fail(org,run_id,owner,generation,exc.category.value))
  if not self._owned(org,run_id,owner,generation):return GroundedResult(run_id,"LEASE_OWNERSHIP_LOST",False)
  db=self.session_factory()
  try:
   CandidatePersistenceService(db,clock=self.clock).persist(org,run_id,owner,generation,candidate,provider_execution_version="grounded-execution-v1",provider_request_fingerprint=artifact.prompt_fingerprint);return GroundedResult(run_id,None,True)
  except ValidationError:return GroundedResult(run_id,"LEASE_OWNERSHIP_LOST",False)
  finally:self._close(db)
