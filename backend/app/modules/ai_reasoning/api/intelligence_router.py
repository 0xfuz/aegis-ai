from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.modules.ai_reasoning.domain.intelligence_service import InvestigationIntelligenceService
from app.modules.identity.api.dependencies import Principal, require_permission
from app.shared.database import get_db

router=APIRouter(prefix="/investigations",tags=["Investigation Intelligence"])
class ReviewIn(BaseModel): status:str; rationale:str
@router.post("/{investigation_id}/intelligence")
async def run(investigation_id:UUID,principal:Principal=Depends(require_permission("investigation:write")),db:Session=Depends(get_db)):
 row=await InvestigationIntelligenceService(db).run(principal.org_id,investigation_id);return {"id":str(row.id),"status":row.status}
@router.get("/{investigation_id}/intelligence")
def latest(investigation_id:UUID,principal:Principal=Depends(require_permission("investigation:read")),db:Session=Depends(get_db)):
 return InvestigationIntelligenceService(db).latest(principal.org_id,investigation_id)
@router.post("/intelligence/items/{item_id}/review")
def review(item_id:UUID,body:ReviewIn,principal:Principal=Depends(require_permission("investigation:write")),db:Session=Depends(get_db)):
 row=InvestigationIntelligenceService(db).review(principal.org_id,item_id,principal.user_id,body.status,body.rationale);return {"id":str(row.id),"review_status":row.review_status}
