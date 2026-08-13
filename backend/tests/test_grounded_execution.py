import json
from datetime import datetime,timezone
from uuid import uuid4
import pytest
from sqlalchemy import select
from app.modules.ai_reasoning.domain.grounded_execution import GroundedIntelligenceExecutionPipeline
from app.modules.ai_reasoning.domain.trusted_provider import BoundedCandidateResponse,ProviderCategory,ProviderFailure
from app.modules.ai_reasoning.domain.run_orchestration_service import IntelligenceRunOrchestrationService
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis,IntelligenceItem,IntelligenceClaimEvidenceLink
from app.modules.evidence.infrastructure.models import EvidenceItem
from app.modules.identity.infrastructure.models import Organization,Role,User
from app.modules.investigations.infrastructure.models import Investigation,InvestigationStatus,Severity,Finding,MitreMapping,RecommendedAction
from app.shared.database import SessionLocal
@pytest.fixture()
def db():
 s=SessionLocal()
 try:yield s
 finally:s.rollback();s.close()
def run(db):
 k=uuid4().hex;org=Organization(name=k,slug=f"ground-{k}");role=Role(name=f"ground-role-{k}");db.add_all((org,role));db.flush();user=User(org_id=org.id,role_id=role.id,email=f"{k}@x",hashed_password="x",full_name="x");inv=Investigation(org_id=org.id,title="x",source="x",severity=Severity.LOW,status=InvestigationStatus.NEW);db.add_all((user,inv));db.flush();db.add(EvidenceItem(org_id=org.id,investigation_id=inv.id,original_filename="x",storage_key=k,sha256="a"*64,byte_size=0,detected_mime="text/plain",extension=".log",acquisition_source="t",imported_at=datetime.now(timezone.utc),parsing_status="complete"));db.commit();row=IntelligenceRunOrchestrationService(db).queue(org.id,inv.id,user.id,"ground");return org,inv,row
class Provider:
 def __init__(self,mode="ok"):self.mode,self.calls=mode,0
 def generate(self,request,checkpoint):
  self.calls+=1
  if self.mode=="fail":raise ProviderFailure(ProviderCategory.UNAVAILABLE)
  if not checkpoint():raise ProviderFailure(ProviderCategory.CANCELLED)
  if self.mode=="schema-invalid":
   return BoundedCandidateResponse(json.dumps({"schema_version":"intelligence-candidate-output-v1","claims":[{"type":"OBSERVATION","statement":"observed","rationale":"evidence","confidence":50,"evidence_links":[{"alias":"E1","role":"SUPPORTS"}],"missing_information":[],"alternative_hypotheses":[],"review_status":"CONFIRMED"}]}))
  return BoundedCandidateResponse(json.dumps({"schema_version":"intelligence-candidate-output-v1","claims":[{"type":"OBSERVATION","statement":"observed","rationale":"evidence","confidence":50,"evidence_links":[{"alias":"E1","role":"SUPPORTS"}],"missing_information":[],"alternative_hypotheses":[]}]}))
def test_grounded_pipeline_completes_only_via_atomic_candidate_persistence(db):
 org,inv,row=run(db);provider=Provider();result=GroundedIntelligenceExecutionPipeline(provider).execute(row.id,"grounded-worker");db.refresh(row)
 assert result.authoritative and result.category is None and row.status=="COMPLETED" and row.provider_attempt_count==1 and row.candidate_output_fingerprint and row.provider_call_started_at and row.provider_call_finished_at>=row.provider_call_started_at
 assert db.scalar(select(IntelligenceItem).where(IntelligenceItem.analysis_id==row.id)).origin=="AI" and db.scalar(select(IntelligenceClaimEvidenceLink).where(IntelligenceClaimEvidenceLink.investigation_id==inv.id))
 assert provider.calls==1
def test_provider_failure_creates_no_claims_or_authority_side_effects(db):
 org,inv,row=run(db);provider=Provider("fail");result=GroundedIntelligenceExecutionPipeline(provider).execute(row.id,"grounded-failure");db.refresh(row)
 assert result.category=="PROVIDER_UNAVAILABLE" and row.status=="FAILED" and row.provider_call_started_at and row.provider_call_finished_at>=row.provider_call_started_at and db.scalar(select(IntelligenceItem).where(IntelligenceItem.analysis_id==row.id)) is None
 assert db.scalar(select(Finding).where(Finding.investigation_id==inv.id)) is None and db.scalar(select(MitreMapping).where(MitreMapping.investigation_id==inv.id)) is None and db.scalar(select(RecommendedAction).where(RecommendedAction.investigation_id==inv.id)) is None
def test_schema_invalid_candidate_is_safe_failed_without_partial_persistence(db):
 org,inv,row=run(db);result=GroundedIntelligenceExecutionPipeline(Provider("schema-invalid")).execute(row.id,"grounded-schema-invalid");db.refresh(row)
 assert result.category=="CANDIDATE_SCHEMA_INVALID" and row.status=="FAILED" and row.error_summary=="CANDIDATE_SCHEMA_INVALID"
 assert row.provider_call_started_at and row.provider_call_finished_at>=row.provider_call_started_at and row.candidate_output_fingerprint is None
 assert db.scalar(select(IntelligenceItem).where(IntelligenceItem.analysis_id==row.id)) is None and db.scalar(select(IntelligenceClaimEvidenceLink).where(IntelligenceClaimEvidenceLink.investigation_id==inv.id)) is None
