"""Fenced atomic persistence for already-validated Phase 8.5 candidates."""
from __future__ import annotations
from datetime import datetime,timezone
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.modules.ai_reasoning.domain.evidence_reference_service import IntelligenceEvidenceReferenceService
from app.modules.ai_reasoning.domain.intelligence_contracts import validate_claim_creation
from app.modules.ai_reasoning.domain.prompt_contract import CANDIDATE_SCHEMA_VERSION,ValidatedCandidate
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis,IntelligenceItem,IntelligenceClaimEvidenceLink
from app.modules.evidence.infrastructure.models import AuditEvent
from app.shared.exceptions import ValidationError

class CandidatePersistenceService:
 def __init__(self,db:Session,clock=lambda:datetime.now(timezone.utc)):self.db,self.clock=db,clock
 def persist(self,org_id:UUID,run_id:UUID,owner:str,generation:int,candidate:ValidatedCandidate,*,provider_execution_version:str,provider_request_fingerprint:str):
  if not isinstance(candidate,ValidatedCandidate) or len(provider_execution_version)>64 or len(provider_request_fingerprint)!=64: raise ValidationError("Invalid validated candidate persistence input.")
  try:
   run=self.db.scalar(select(IntelligenceAnalysis).where(IntelligenceAnalysis.id==run_id,IntelligenceAnalysis.org_id==org_id).with_for_update())
   now=self.clock()
   if not run or run.status!="RUNNING" or run.lease_owner_id!=owner or run.lease_generation!=generation or not run.lease_expires_at or run.lease_expires_at<=now: raise ValidationError("Intelligence execution lease is no longer valid.")
   if run.input_snapshot.get("fingerprint")!=run.input_hash or candidate.fingerprint is None: raise ValidationError("Invalid persisted candidate context.")
   refs={};citation=IntelligenceEvidenceReferenceService(self.db)
   for claim in candidate.claims:
    validate_claim_creation(claim["type"],"AI","PENDING")
    item=IntelligenceItem(org_id=run.org_id,analysis_id=run.id,investigation_id=run.investigation_id,kind=claim["type"],origin="AI",ordinal=len([x for x in self.db.new if isinstance(x,IntelligenceItem)]),statement=claim["statement"],confidence=claim["confidence"],payload={"rationale":claim["rationale"],"missing_information":claim["missing_information"],"alternative_hypotheses":claim["alternative_hypotheses"]},review_status="PENDING")
    self.db.add(item);self.db.flush()
    for link in claim["evidence_links"]:
     ref=refs.setdefault(link["alias"],citation._one(run,link["alias"],None))
     self.db.add(IntelligenceClaimEvidenceLink(org_id=run.org_id,investigation_id=run.investigation_id,item_id=item.id,evidence_reference_id=ref.id,role=link["role"]))
   run.provider_execution_version=provider_execution_version;run.provider_request_fingerprint=provider_request_fingerprint;run.candidate_output_schema_version=CANDIDATE_SCHEMA_VERSION;run.candidate_output_fingerprint=candidate.fingerprint;run.status="COMPLETED";run.generated_at=run.execution_finished_at=now;run.lease_owner_id=run.lease_acquired_at=run.lease_heartbeat_at=run.lease_expires_at=None
   self.db.add(AuditEvent(org_id=run.org_id,investigation_id=run.investigation_id,actor_id=None,actor_type="system",action="INTELLIGENCE_RUN_COMPLETED",target_type="IntelligenceAnalysis",target_id=run.id,occurred_at=now,metadata_={"status":"COMPLETED","candidate_fingerprint":candidate.fingerprint}))
   self.db.commit();return run
  except Exception:
   self.db.rollback();raise
