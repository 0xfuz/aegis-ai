from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.modules.identity.api.dependencies import Principal, require_permission
from app.modules.attack_graph.api.schemas import AttackGraphOut
from app.modules.attack_graph.domain.service import AttackGraphService
from app.shared.database import get_db

router = APIRouter(prefix="/investigations", tags=["Attack Graph"])


@router.get("/{investigation_id}/attack-graph", response_model=AttackGraphOut)
def get_attack_graph(
    investigation_id: UUID,
    principal: Principal = Depends(require_permission("attack_graph:read")),
    db: Session = Depends(get_db),
) -> AttackGraphOut:
    graph = AttackGraphService(db).build_graph(principal.org_id, investigation_id)
    return AttackGraphOut.model_validate(graph, from_attributes=True)
