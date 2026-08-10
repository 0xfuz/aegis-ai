from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.modules.identity.api.dependencies import Principal, get_current_principal, require_permission
from app.modules.investigations.api.schemas import (
    DashboardSummary,
    InvestigationDetail,
    InvestigationStatusUpdate,
    InvestigationSummary,
    IOCDetail,
    IOCSummary,
    IOCVerdictRequest,
    IOCWatchRequest,
    NoteCreate,
)
from app.modules.investigations.domain.service import InvestigationService, IOCService
from app.modules.investigations.domain.finding_service import FindingService
from app.shared.database import get_db

router = APIRouter(prefix="/investigations", tags=["Investigations"])

class FindingIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    severity: str = "medium"
    confidence: int | None = Field(default=None, ge=0, le=100)
class FindingFromAIIn(BaseModel):
    title: str | None = None
    severity: str = "medium"
class FindingStatusIn(BaseModel): status: str
class MitreReviewIn(BaseModel): status: str; rationale: str = ""
@router.get("/{investigation_id}/overview")
def overview(investigation_id: UUID, principal: Principal = Depends(require_permission("investigation:read")), db: Session = Depends(get_db)):
    return FindingService(db).overview(principal.org_id, investigation_id)
@router.get("/{investigation_id}/audit")
def audit(investigation_id: UUID, limit: int = Query(default=100, le=200), offset: int = Query(default=0, ge=0), principal: Principal = Depends(require_permission("investigation:read")), db: Session = Depends(get_db)):
    return FindingService(db).audit(principal.org_id, investigation_id, limit, offset)

@router.get("/{investigation_id}/findings")
def findings(investigation_id: UUID, principal: Principal = Depends(require_permission("investigation:read")), db: Session = Depends(get_db)):
    return FindingService(db).list_findings(principal.org_id, investigation_id)
@router.post("/{investigation_id}/findings")
def create_finding(investigation_id: UUID, body: FindingIn, principal: Principal = Depends(require_permission("investigation:write")), db: Session = Depends(get_db)):
    return FindingService(db).create_manual(principal.org_id, investigation_id, principal.user_id, body.model_dump())
@router.post("/intelligence/items/{item_id}/finding")
def convert_finding(item_id: UUID, body: FindingFromAIIn, principal: Principal = Depends(require_permission("investigation:write")), db: Session = Depends(get_db)):
    return FindingService(db).create_from_item(principal.org_id, item_id, principal.user_id, **body.model_dump())
@router.patch("/findings/{finding_id}")
def edit_finding(finding_id: UUID, body: FindingIn, principal: Principal = Depends(require_permission("investigation:write")), db: Session = Depends(get_db)):
    return FindingService(db).update(principal.org_id, finding_id, principal.user_id, body.model_dump())
@router.post("/findings/{finding_id}/status")
def finding_status(finding_id: UUID, body: FindingStatusIn, principal: Principal = Depends(require_permission("investigation:write")), db: Session = Depends(get_db)):
    return FindingService(db).status(principal.org_id, finding_id, principal.user_id, body.status)
@router.get("/{investigation_id}/mitre-mappings")
def mitre_mappings(investigation_id: UUID, principal: Principal = Depends(require_permission("investigation:read")), db: Session = Depends(get_db)):
    return FindingService(db).list_mitre(principal.org_id, investigation_id)
@router.post("/mitre-mappings/{mapping_id}/review")
def review_mitre(mapping_id: UUID, body: MitreReviewIn, principal: Principal = Depends(require_permission("investigation:write")), db: Session = Depends(get_db)):
    return FindingService(db).review_mapping(principal.org_id, mapping_id, principal.user_id, body.status, body.rationale)


@router.get("", response_model=list[InvestigationSummary])
def list_investigations(
    status: str | None = Query(default=None, description="Filter by status, e.g. 'new', 'investigating'"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_permission("investigation:read")),
    db: Session = Depends(get_db),
) -> list[InvestigationSummary]:
    investigations = InvestigationService(db).list_investigations(principal.org_id, status, limit, offset)
    return [InvestigationSummary.model_validate(i) for i in investigations]


@router.get("/dashboard-summary", response_model=DashboardSummary)
def dashboard_summary(
    principal: Principal = Depends(require_permission("investigation:read")),
    db: Session = Depends(get_db),
) -> DashboardSummary:
    return InvestigationService(db).dashboard_summary(principal.org_id)


@router.get("/iocs", response_model=list[IOCSummary])
def list_iocs(
    verdict: str | None = Query(default=None, description="Filter by malicious | suspicious | unknown | benign"),
    watched_only: bool = Query(default=False, description="Only return watchlisted indicators"),
    principal: Principal = Depends(require_permission("threat_intel:read")),
    db: Session = Depends(get_db),
) -> list[IOCSummary]:
    iocs = IOCService(db).list_iocs(principal.org_id, verdict=verdict, watched_only=watched_only)
    return [IOCSummary.model_validate(i) for i in iocs]


@router.get("/iocs/watchlist", response_model=list[IOCSummary])
def list_watchlist(
    principal: Principal = Depends(require_permission("threat_intel:read")),
    db: Session = Depends(get_db),
) -> list[IOCSummary]:
    iocs = IOCService(db).list_watchlist(principal.org_id)
    return [IOCSummary.model_validate(i) for i in iocs]


@router.get("/iocs/lookup", response_model=IOCDetail)
def lookup_ioc(
    type: str = Query(description="ip | hash | domain | url | asset"),
    value: str = Query(description="The indicator's value, e.g. an IP address or hash"),
    exclude_investigation_id: UUID | None = Query(
        default=None, description="Omit this investigation from the related-incidents list"
    ),
    principal: Principal = Depends(require_permission("threat_intel:read")),
    db: Session = Depends(get_db),
) -> IOCDetail:
    return IOCService(db).get_ioc_detail(principal.org_id, type, value, exclude_investigation_id)


@router.post("/iocs/watch", response_model=IOCDetail)
def set_ioc_watch(
    payload: IOCWatchRequest,
    principal: Principal = Depends(require_permission("threat_intel:write")),
    db: Session = Depends(get_db),
) -> IOCDetail:
    detail = IOCService(db).set_watched(principal.org_id, payload.type, payload.value, payload.watched)
    db.commit()
    return detail


@router.post("/iocs/verdict", response_model=IOCDetail)
def set_ioc_verdict(
    payload: IOCVerdictRequest,
    principal: Principal = Depends(require_permission("threat_intel:write")),
    db: Session = Depends(get_db),
) -> IOCDetail:
    detail = IOCService(db).set_verdict(principal.org_id, payload.type, payload.value, payload.verdict)
    db.commit()
    return detail


@router.get("/{investigation_id}", response_model=InvestigationDetail)
def get_investigation(
    investigation_id: UUID,
    principal: Principal = Depends(require_permission("investigation:read")),
    db: Session = Depends(get_db),
) -> InvestigationDetail:
    investigation = InvestigationService(db).get_investigation(principal.org_id, investigation_id)
    return InvestigationDetail.model_validate(investigation)


@router.patch("/{investigation_id}/status", response_model=InvestigationDetail)
def update_status(
    investigation_id: UUID,
    payload: InvestigationStatusUpdate,
    principal: Principal = Depends(require_permission("investigation:write")),
    db: Session = Depends(get_db),
) -> InvestigationDetail:
    investigation = InvestigationService(db).update_status(principal.org_id, investigation_id, payload.status)
    db.commit()
    return InvestigationDetail.model_validate(investigation)


@router.post("/{investigation_id}/notes", response_model=InvestigationDetail)
def add_note(
    investigation_id: UUID,
    payload: NoteCreate,
    principal: Principal = Depends(require_permission("investigation:write")),
    db: Session = Depends(get_db),
) -> InvestigationDetail:
    investigation = InvestigationService(db).add_note(
        principal.org_id, investigation_id, principal.user_id, payload.body
    )
    db.commit()
    return InvestigationDetail.model_validate(investigation)


@router.post("/actions/{action_id}/approve", response_model=InvestigationDetail)
def approve_action(
    action_id: UUID,
    principal: Principal = Depends(require_permission("investigation:approve_remediation")),
    db: Session = Depends(get_db),
) -> InvestigationDetail:
    investigation = InvestigationService(db).decide_action(principal.org_id, action_id, approve=True)
    db.commit()
    return InvestigationDetail.model_validate(investigation)


@router.post("/actions/{action_id}/dismiss", response_model=InvestigationDetail)
def dismiss_action(
    action_id: UUID,
    principal: Principal = Depends(require_permission("investigation:approve_remediation")),
    db: Session = Depends(get_db),
) -> InvestigationDetail:
    investigation = InvestigationService(db).decide_action(principal.org_id, action_id, approve=False)
    db.commit()
    return InvestigationDetail.model_validate(investigation)
