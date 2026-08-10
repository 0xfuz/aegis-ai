from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.modules.demos.domain.service import DemoInvestigationService
from app.modules.identity.api.dependencies import Principal, require_permission
from app.shared.database import get_db

router=APIRouter(prefix="/demos",tags=["Demo Investigations"])
@router.get("")
def catalog(principal:Principal=Depends(require_permission("investigation:read")),db:Session=Depends(get_db)): return DemoInvestigationService(db).catalog(principal.org_id)
@router.post("/{scenario_id}")
def load(scenario_id:str,principal:Principal=Depends(require_permission("investigation:write")),db:Session=Depends(get_db)):
 row=DemoInvestigationService(db).load(principal.org_id,principal.user_id,scenario_id);return {"id":str(row.id),"title":row.title}
@router.delete("/{scenario_id}")
def remove(scenario_id:str,principal:Principal=Depends(require_permission("investigation:write")),db:Session=Depends(get_db)):
 DemoInvestigationService(db).delete(principal.org_id,scenario_id);return {"deleted":scenario_id}
