from datetime import datetime,timezone
from uuid import uuid4
import pytest
from sqlalchemy import func,select
from app.modules.ai_reasoning.domain.candidate_persistence import CandidatePersistenceService
from app.modules.ai_reasoning.domain.prompt_contract import CANDIDATE_SCHEMA_VERSION,validate_candidate
from app.modules.ai_reasoning.domain.run_orchestration_service import IntelligenceRunOrchestrationService
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis,IntelligenceItem,IntelligenceEvidenceReference,IntelligenceClaimEvidenceLink,IntelligenceFactLink
from app.modules.evidence.infrastructure.models import Entity,EvidenceItem
from app.modules.identity.infrastructure.models import Organization,Role,User
from app.modules.investigations.infrastructure.models import Investigation,InvestigationStatus,Severity,Finding,MitreMapping,RecommendedAction
from app.shared.database import SessionLocal
from app.shared.exceptions import ValidationError
@pytest.fixture()
def db():
 s=SessionLocal()
 try:yield s
 finally:s.rollback();s.close()
def ready(db):
 k=uuid4().hex;org=Organization(name=k,slug=f"persist-{k}");role=Role(name=f"persist-role-{k}");db.add_all((org,role));db.flush();user=User(org_id=org.id,role_id=role.id,email=f"{k}@x",hashed_password="x",full_name="x");inv=Investigation(org_id=org.id,title="x",source="x",severity=Severity.LOW,status=InvestigationStatus.NEW);db.add_all((user,inv));db.flush();db.add(EvidenceItem(org_id=org.id,investigation_id=inv.id,original_filename="safe.log",storage_key=k,sha256="a"*64,byte_size=0,detected_mime="text/plain",extension=".log",acquisition_source="test",imported_at=datetime.now(timezone.utc),parsing_status="complete"));db.commit();run=IntelligenceRunOrchestrationService(db).queue(org.id,inv.id,user.id,"persist");token=IntelligenceRunOrchestrationService(db).acquire_for_execution(org.id,run.id,"worker");db.refresh(run);alias=next(key for key,value in run.input_snapshot["aliases"].items() if value["type"]=="E");candidate=validate_candidate(__import__("json").dumps({"schema_version":CANDIDATE_SCHEMA_VERSION,"claims":[{"type":"OBSERVATION","statement":"host activity","rationale":"evidence","confidence":0,"evidence_links":[{"alias":alias,"role":"SUPPORTS"}],"missing_information":[],"alternative_hypotheses":[]},{"type":"HYPOTHESIS","statement":"alternative","rationale":"evidence","confidence":100,"evidence_links":[{"alias":alias,"role":"CONTEXT"}],"missing_information":["process"],"alternative_hypotheses":[]}]}),{key:value["type"] for key,value in run.input_snapshot["aliases"].items() if value["type"]=="E"});return org,inv,run,token,candidate
def test_atomic_persistence_claims_links_metadata_and_idempotent_terminal_rejection(db):
 org,inv,run,token,candidate=ready(db);before={m:db.scalar(select(func.count()).select_from(m)) for m in (Finding,MitreMapping,RecommendedAction,IntelligenceFactLink)}
 completed=CandidatePersistenceService(db).persist(org.id,run.id,"worker",token["lease_generation"],candidate,provider_execution_version="provider-v1",provider_request_fingerprint="a"*64)
 assert completed.status=="COMPLETED" and completed.lease_owner_id is None and completed.candidate_output_fingerprint==candidate.fingerprint
 items=list(db.scalars(select(IntelligenceItem).where(IntelligenceItem.analysis_id==run.id).order_by(IntelligenceItem.ordinal)));assert [(x.kind,x.origin,x.review_status,x.confidence) for x in items]==[("OBSERVATION","AI","PENDING",0),("HYPOTHESIS","AI","PENDING",100)] and items[1].payload["missing_information"]==["process"]
 assert db.scalar(select(func.count()).select_from(IntelligenceEvidenceReference).where(IntelligenceEvidenceReference.analysis_id==run.id))==1 and db.scalar(select(func.count()).select_from(IntelligenceClaimEvidenceLink).where(IntelligenceClaimEvidenceLink.investigation_id==inv.id))==2
 with pytest.raises(ValidationError):CandidatePersistenceService(db).persist(org.id,run.id,"worker",token["lease_generation"],candidate,provider_execution_version="provider-v1",provider_request_fingerprint="a"*64)
 assert {m:db.scalar(select(func.count()).select_from(m)) for m in before}==before
def test_wrong_owner_rolls_back_without_claims(db):
 org,inv,run,token,candidate=ready(db)
 with pytest.raises(ValidationError):CandidatePersistenceService(db).persist(org.id,run.id,"wrong",token["lease_generation"],candidate,provider_execution_version="provider-v1",provider_request_fingerprint="a"*64)
 assert db.get(IntelligenceAnalysis,run.id).status=="RUNNING" and db.scalar(select(func.count()).select_from(IntelligenceItem).where(IntelligenceItem.analysis_id==run.id))==0
