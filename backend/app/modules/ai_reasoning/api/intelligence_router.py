from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.modules.ai_reasoning.domain.intelligence_service import InvestigationIntelligenceService
from app.modules.ai_reasoning.domain.run_orchestration_service import IntelligenceRunOrchestrationService
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis
from app.modules.ai_reasoning.domain.reconstruction_read_service import ReconstructionReadService
from app.modules.identity.api.dependencies import Principal, require_permission
from app.modules.identity.infrastructure.models import User
from app.shared.database import get_db
from app.shared.exceptions import ValidationError

router=APIRouter(prefix="/investigations",tags=["Investigation Intelligence"])
class ReviewIn(BaseModel): status:str; rationale:str
class RunRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    request_key:str=Field(min_length=1,max_length=128,pattern=r"^[A-Za-z0-9._:-]+$")
class CancelRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    reason:str=Field(default="",max_length=200)
class RunRead(BaseModel):
    id:UUID; investigation_id:UUID; status:str; request_key:str; input_hash:str; predecessor_analysis_id:UUID|None
    context_version:str|None; builder_version:str|None; prompt_template_version:str; output_schema_version:str
    generated_at:datetime|None; created_at:datetime; updated_at:datetime; error_summary:str|None
class RunList(BaseModel): items:list[RunRead]; limit:int; offset:int
class ReconstructionRead(BaseModel):
    """Strict outer contract; nested sections are fixed, server-produced JSON."""
    model_config=ConfigDict(extra="forbid")
    policy_id:str; investigation:dict; versions:dict; context:dict; activity:dict; gaps:dict; sections:dict; pagination:dict; warnings:list

def safe_run(row: IntelligenceAnalysis) -> RunRead:
    snapshot=row.input_snapshot if isinstance(row.input_snapshot,dict) else {}
    return RunRead(id=row.id,investigation_id=row.investigation_id,status=row.status,request_key=row.request_key,input_hash=row.input_hash,predecessor_analysis_id=row.predecessor_analysis_id,context_version=snapshot.get("context_version"),builder_version=snapshot.get("builder_version"),prompt_template_version=row.prompt_template_version,output_schema_version=row.output_schema_version,generated_at=row.generated_at,created_at=row.created_at,updated_at=row.updated_at,error_summary=row.error_summary)
def conflict(error: ValidationError):
    if error.message.startswith("Request identity conflicts"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,detail="Request identity conflicts with the current context.") from None
    raise error
@router.post("/{investigation_id}/intelligence")
async def run(investigation_id:UUID,principal:Principal=Depends(require_permission("investigation:write")),db:Session=Depends(get_db)):
 row=await InvestigationIntelligenceService(db).run(principal.org_id,investigation_id);return {"id":str(row.id),"status":row.status}
@router.get("/{investigation_id}/intelligence")
def latest(investigation_id:UUID,principal:Principal=Depends(require_permission("investigation:read")),db:Session=Depends(get_db)):
 return InvestigationIntelligenceService(db).latest(principal.org_id,investigation_id)
@router.get("/{investigation_id}/intelligence/reconstruction",response_model=ReconstructionRead)
def reconstruction(investigation_id:UUID,principal:Principal=Depends(require_permission("investigation:read")),db:Session=Depends(get_db)):
    # Token validity is necessary but insufficient: revoked/inactive users fail closed here.
    if not db.scalar(select(User.id).where(User.id==principal.user_id,User.org_id==principal.org_id,User.is_active.is_(True))):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="Investigation not found.")
    return ReconstructionRead.model_validate(ReconstructionReadService(db).read(principal.org_id,investigation_id))
@router.post("/intelligence/items/{item_id}/review")
def review(item_id:UUID,body:ReviewIn,principal:Principal=Depends(require_permission("investigation:write")),db:Session=Depends(get_db)):
 row=InvestigationIntelligenceService(db).review(principal.org_id,item_id,principal.user_id,body.status,body.rationale);return {"id":str(row.id),"review_status":row.review_status}

@router.post("/{investigation_id}/intelligence/runs",response_model=RunRead,status_code=status.HTTP_202_ACCEPTED)
def queue_run(investigation_id:UUID,body:RunRequest,principal:Principal=Depends(require_permission("investigation:write")),db:Session=Depends(get_db)):
    try: return safe_run(IntelligenceRunOrchestrationService(db).queue(principal.org_id,investigation_id,principal.user_id,body.request_key))
    except ValidationError as error: conflict(error)

@router.get("/{investigation_id}/intelligence/runs/{run_id}",response_model=RunRead)
def get_run(investigation_id:UUID,run_id:UUID,principal:Principal=Depends(require_permission("investigation:read")),db:Session=Depends(get_db)):
    return safe_run(IntelligenceRunOrchestrationService(db).get(principal.org_id,investigation_id,principal.user_id,run_id))

@router.get("/{investigation_id}/intelligence/runs",response_model=RunList)
def list_runs(investigation_id:UUID,limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0,le=10000),principal:Principal=Depends(require_permission("investigation:read")),db:Session=Depends(get_db)):
    service=IntelligenceRunOrchestrationService(db)
    return RunList(items=[safe_run(row) for row in service.list(principal.org_id,investigation_id,principal.user_id,limit,offset)],limit=limit,offset=offset)

@router.post("/{investigation_id}/intelligence/runs/{run_id}/cancel",response_model=RunRead)
def cancel_run(investigation_id:UUID,run_id:UUID,body:CancelRequest,principal:Principal=Depends(require_permission("investigation:write")),db:Session=Depends(get_db)):
    if len(body.reason)>200: raise HTTPException(status_code=422,detail="Cancellation reason is too long.")
    IntelligenceRunOrchestrationService(db).get(principal.org_id,investigation_id,principal.user_id,run_id)
    return safe_run(IntelligenceRunOrchestrationService(db).cancel(principal.org_id,run_id,principal.user_id,body.reason))

@router.post("/{investigation_id}/intelligence/runs/{run_id}/retry",response_model=RunRead,status_code=status.HTTP_202_ACCEPTED)
def retry_run(investigation_id:UUID,run_id:UUID,body:RunRequest,principal:Principal=Depends(require_permission("investigation:write")),db:Session=Depends(get_db)):
    service=IntelligenceRunOrchestrationService(db)
    service.get(principal.org_id,investigation_id,principal.user_id,run_id)
    try: return safe_run(service.retry(principal.org_id,run_id,principal.user_id,body.request_key))
    except ValidationError as error: conflict(error)
