from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.modules.identity.api.dependencies import Principal, require_permission
from app.modules.ai_reasoning.domain.service import ReasoningService
from app.modules.investigations.api.schemas import InvestigationDetail
from app.shared.database import get_db

router = APIRouter(prefix="/investigations", tags=["AI Reasoning"])


@router.post("/{investigation_id}/analyze", response_model=InvestigationDetail)
async def analyze_investigation(
    investigation_id: UUID,
    principal: Principal = Depends(require_permission("investigation:write")),
    db: Session = Depends(get_db),
) -> InvestigationDetail:
    """Runs AI analysis on an investigation, populating root cause, MITRE
    mapping, confidence, blast radius, and recommended actions from live
    evidence — the exact fields v1's mock/seeded data hand-filled, now
    generated for real. See ai_reasoning/domain/service.py for the honest
    accounting of what this does and doesn't do yet vs. the architecture
    doc's full multi-agent pipeline."""
    investigation = await ReasoningService(db).analyze(principal.org_id, investigation_id)
    db.commit()
    return InvestigationDetail.model_validate(investigation)
