from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status as http_status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.modules.identity.api.dependencies import Principal, get_current_principal, require_permission
from app.modules.investigations.api.schemas import (
    DashboardSummary,
    InvestigationDetail,
    InvestigationOverview,
    InvestigationPage,
    InvestigationStatusUpdate,
    InvestigationSummary,
    IOCDetail,
    IOCSummary,
    IOCVerdictRequest,
    IOCWatchRequest,
    NoteCreate,
    NoteRead,
    NotePage,
    AuditEventPage,
    MitreSuggestionPage,
)
from app.modules.identity.infrastructure.models import User
from app.modules.investigations.domain.service import InvestigationService, IOCService
from app.modules.investigations.domain.finding_service import FindingService
from app.shared.database import get_db

router = APIRouter(prefix="/investigations", tags=["Investigations"])


def _active_principal_or_404(principal: Principal, db: Session) -> None:
    user = db.get(User, principal.user_id)
    if user is None or user.org_id != principal.org_id or not user.is_active:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Investigation not found.")

class FindingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=4_000)
    severity: str = "medium"
    confidence: int | None = Field(default=None, ge=0, le=100)
class FindingStatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
class MitreReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(min_length=1, max_length=20)
    rationale: str = Field(default="", max_length=1_000)
@router.get("/{investigation_id}/overview", response_model=InvestigationOverview)
def overview(investigation_id: UUID, principal: Principal = Depends(require_permission("investigation:read")), db: Session = Depends(get_db)) -> InvestigationOverview:
    _active_principal_or_404(principal, db)
    return InvestigationOverview.model_validate(InvestigationService(db).overview(principal.org_id, investigation_id))
@router.get("/{investigation_id}/audit", response_model=AuditEventPage)
def audit(investigation_id: UUID, limit: int = Query(default=100, ge=1, le=200), offset: int = Query(default=0, ge=0), principal: Principal = Depends(require_permission("investigation:read")), db: Session = Depends(get_db)):
    user = db.get(User, principal.user_id)
    if user is None or user.org_id != principal.org_id or not user.is_active:
        # Keep an inactive or stale principal indistinguishable from an
        # inaccessible Investigation at this read boundary.
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Investigation not found.")
    return FindingService(db).audit(principal.org_id, investigation_id, limit, offset)

@router.get("/{investigation_id}/findings")
def findings(
    investigation_id: UUID,
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_permission("investigation:read")),
    db: Session = Depends(get_db),
):
    if set(request.query_params) - {"status", "limit", "offset"}:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported query parameter.")
    _active_principal_or_404(principal, db)
    return FindingService(db).list_findings(principal.org_id, investigation_id, status, limit, offset)
@router.post("/{investigation_id}/findings")
def create_finding(investigation_id: UUID, body: FindingIn, principal: Principal = Depends(require_permission("investigation:write")), db: Session = Depends(get_db)):
    _active_principal_or_404(principal, db)
    return FindingService(db).create_manual(principal.org_id, investigation_id, principal.user_id, body.model_dump())
@router.patch("/findings/{finding_id}")
def edit_finding(finding_id: UUID, body: FindingIn, principal: Principal = Depends(require_permission("investigation:write")), db: Session = Depends(get_db)):
    _active_principal_or_404(principal, db)
    return FindingService(db).update(principal.org_id, finding_id, principal.user_id, body.model_dump())
@router.post("/findings/{finding_id}/status")
def finding_status(finding_id: UUID, body: FindingStatusIn, principal: Principal = Depends(require_permission("investigation:write")), db: Session = Depends(get_db)):
    _active_principal_or_404(principal, db)
    return FindingService(db).status(principal.org_id, finding_id, principal.user_id, body.status)
def _mitre_page(
    investigation_id: UUID,
    request: Request,
    status: str | None,
    limit: int,
    offset: int,
    principal: Principal,
    db: Session,
):
    if set(request.query_params) - {"status", "limit", "offset"}:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported query parameter.")
    _active_principal_or_404(principal, db)
    return FindingService(db).list_mitre_page(principal.org_id, investigation_id, status, limit, offset)


@router.get("/{investigation_id}/mitre")
def mitre(
    investigation_id: UUID,
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_permission("investigation:read")),
    db: Session = Depends(get_db),
):
    return _mitre_page(investigation_id, request, status, limit, offset, principal, db)


@router.get("/{investigation_id}/mitre-suggestions", response_model=MitreSuggestionPage)
def mitre_suggestions(
    investigation_id: UUID,
    principal: Principal = Depends(require_permission("investigation:read")),
    db: Session = Depends(get_db),
) -> MitreSuggestionPage:
    _active_principal_or_404(principal, db)
    return MitreSuggestionPage.model_validate(InvestigationService(db).mitre_suggestions(principal.org_id, investigation_id))


# Compatibility read route retained for the legacy workspace. New consumers
# use the bounded /mitre contract above; this route retains its historical
# array shape only until U4-C2 replaces that consumer.
@router.get("/{investigation_id}/mitre-mappings")
def mitre_mappings(
    investigation_id: UUID,
    principal: Principal = Depends(require_permission("investigation:read")),
    db: Session = Depends(get_db),
):
    _active_principal_or_404(principal, db)
    return FindingService(db).list_mitre(principal.org_id, investigation_id)
@router.post("/mitre-mappings/{mapping_id}/review")
def review_mitre(mapping_id: UUID, body: MitreReviewIn, principal: Principal = Depends(require_permission("investigation:write")), db: Session = Depends(get_db)):
    return FindingService(db).review_mapping(principal.org_id, mapping_id, principal.user_id, body.status, body.rationale)


@router.get("", response_model=InvestigationPage)
def list_investigations(
    request: Request,
    status: str | None = Query(default=None, description="Filter by status, e.g. 'new', 'investigating'"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_permission("investigation:read")),
    db: Session = Depends(get_db),
) -> InvestigationPage:
    if set(request.query_params) - {"status", "limit", "offset"}:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported query parameter.")
    _active_principal_or_404(principal, db)
    page = InvestigationService(db).list_investigations(principal.org_id, status, limit, offset)
    return InvestigationPage(
        items=[InvestigationSummary.model_validate(item) for item in page["items"]],
        limit=page["limit"], offset=page["offset"], returned_count=page["returned_count"], total=page["total"],
    )


@router.get("/dashboard-summary", response_model=DashboardSummary)
def dashboard_summary(
    request: Request,
    window: str | None = Query(default=None),
    from_at: datetime | None = Query(default=None, alias="from"),
    to_at: datetime | None = Query(default=None, alias="to"),
    principal: Principal = Depends(require_permission("investigation:read")),
    db: Session = Depends(get_db),
) -> DashboardSummary:
    if set(request.query_params) - {"window", "from", "to"}:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported query parameter.")
    _active_principal_or_404(principal, db)
    resolved_window = InvestigationService.resolve_dashboard_window(window, from_at, to_at)
    return InvestigationService(db).dashboard_summary(principal.org_id, resolved_window)


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


@router.post("/{investigation_id}/notes", response_model=NoteRead)
def add_note(
    investigation_id: UUID,
    payload: NoteCreate,
    principal: Principal = Depends(require_permission("investigation:write")),
    db: Session = Depends(get_db),
) -> NoteRead:
    _active_principal_or_404(principal, db)
    note = InvestigationService(db).add_note(
        principal.org_id, investigation_id, principal.user_id, payload.body
    )
    db.commit()
    return NoteRead.model_validate(note)


@router.get("/{investigation_id}/notes", response_model=NotePage)
def list_notes(
    investigation_id: UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_permission("investigation:read")),
    db: Session = Depends(get_db),
) -> NotePage:
    if set(request.query_params) - {"limit", "offset"}:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported query parameter.")
    _active_principal_or_404(principal, db)
    return InvestigationService(db).list_notes(principal.org_id, investigation_id, limit, offset)


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
