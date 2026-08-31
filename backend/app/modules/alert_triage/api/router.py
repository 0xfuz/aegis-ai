from uuid import UUID
from fastapi import APIRouter,Body,Depends,Query
from pydantic import BaseModel,ConfigDict
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.modules.alert_triage.domain.promotion_service import AlertClusterPromotionService
from app.modules.alert_triage.domain.read_service import AlertClusterTriageReadService
from app.modules.identity.api.dependencies import Principal,require_permission
from app.modules.identity.infrastructure.models import User
from app.shared.database import get_db
from app.shared.exceptions import AuthorizationError, NotFoundError
router=APIRouter(prefix="/alert-triage",tags=["Alert Triage"])
class PromotionRequest(BaseModel): model_config=ConfigDict(extra="forbid")
def _active(p:Principal,db:Session):
    row=db.get(User,p.user_id)
    if row is None or row.org_id!=p.org_id or not row.is_active:
        raise AuthorizationError("Your account is not active in this organization.")
@router.get("/clusters")
def list_clusters(limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),p:Principal=Depends(require_permission("investigation:read")),db:Session=Depends(get_db)):
    _active(p,db);return AlertClusterTriageReadService(db).list(p.org_id,limit,offset)
@router.get("/clusters/{cluster_id}")
def get_cluster(cluster_id:UUID,p:Principal=Depends(require_permission("investigation:read")),db:Session=Depends(get_db)):
    _active(p,db);return AlertClusterTriageReadService(db).get(p.org_id,cluster_id)
@router.post("/clusters/{cluster_id}/promote",status_code=201)
def promote(cluster_id:UUID,_body:PromotionRequest=Body(default_factory=PromotionRequest),p:Principal=Depends(require_permission("investigation:write")),db:Session=Depends(get_db)):
    _active(p,db);result=AlertClusterPromotionService(db,get_settings()).promote(p.org_id,cluster_id,p.user_id)
    return {"promotion_id":str(result.id),"status":"COMPLETED","investigation_id":str(result.investigation_id),"created":result.created}
