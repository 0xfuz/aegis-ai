from datetime import datetime, timezone
import re
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status as http_status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.evidence.api.schemas import (
    EntityRead, EntityRelationshipRead, EventRead, EvidenceDetail, EvidenceRead, EvidenceInventoryPage, TimelinePage,
    IndicatorOccurrenceRead, IndicatorRead, EntityObservationRead, RawRecordRead,
    EntityPage, EntityObservationPage, IndicatorOccurrencePage,
)
from app.modules.evidence.domain.service import EvidenceIngestionService
from app.modules.evidence.domain.read_projection import EvidenceInventoryService
from app.modules.evidence.domain.timeline_projection import TimelineProjectionService
from app.modules.evidence.domain.occurrence_projection import OccurrenceProjectionService
from app.modules.evidence.infrastructure.models import AuditEvent, EvidenceItem, EvidenceParseRun
from app.modules.evidence.infrastructure.repository import EvidenceRepository
from app.modules.evidence.infrastructure.storage import EvidenceStorage
from app.modules.evidence.domain.graph_projection import CanonicalGraphProjectionService, GraphFilters
from app.modules.evidence.api.graph_schemas import CanonicalGraphRead
from app.modules.identity.api.dependencies import Principal, require_permission
from app.modules.identity.infrastructure.models import User
from app.shared.database import get_db
from app.shared.exceptions import NotFoundError

router = APIRouter(prefix="/investigations", tags=["Canonical Evidence"])

_TIMELINE_ISO_8601 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})$"
)


def _active_principal_or_404(principal: Principal, db: Session) -> None:
    user = db.get(User, principal.user_id)
    if user is None or user.org_id != principal.org_id or not user.is_active:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Evidence not found.")


def _evidence(db: Session, principal: Principal, investigation_id: UUID, evidence_id: UUID):
    evidence = EvidenceRepository(db).get_evidence(principal.org_id, investigation_id, evidence_id)
    if evidence is None:
        raise NotFoundError("Evidence not found.")
    return evidence


def _serialize_evidence(db: Session, evidence: EvidenceItem) -> EvidenceRead:
    """Return public evidence metadata and the latest parser identity only."""
    run = db.execute(
        select(EvidenceParseRun)
        .where(EvidenceParseRun.evidence_id == evidence.id)
        .order_by(EvidenceParseRun.run_sequence.desc(), EvidenceParseRun.started_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    return EvidenceRead(
        id=evidence.id, investigation_id=evidence.investigation_id,
        original_filename=evidence.original_filename, sha256=evidence.sha256,
        byte_size=evidence.byte_size, detected_mime=evidence.detected_mime,
        extension=evidence.extension, source_description=evidence.source_description,
        acquisition_source=evidence.acquisition_source, imported_at=evidence.imported_at,
        parsing_status=evidence.parsing_status,
        parser_name=run.parser_name if run else None,
        parser_version=run.parser_version if run else None,
    )


@router.post("/{investigation_id}/evidence", response_model=EvidenceRead, status_code=201)
def upload_evidence(
    investigation_id: UUID,
    file: UploadFile = File(...),
    principal: Principal = Depends(require_permission("investigation:write")),
    db: Session = Depends(get_db),
) -> EvidenceRead:
    evidence = EvidenceIngestionService(db, get_settings()).ingest(principal.org_id, investigation_id, principal.user_id, file)
    return _serialize_evidence(db, evidence)


@router.get("/{investigation_id}/evidence", response_model=list[EvidenceRead])
def list_evidence(
    investigation_id: UUID,
    principal: Principal = Depends(require_permission("investigation:read")),
    db: Session = Depends(get_db),
) -> list[EvidenceRead]:
    rows = db.execute(select(EvidenceItem).where(EvidenceItem.org_id == principal.org_id, EvidenceItem.investigation_id == investigation_id).order_by(EvidenceItem.imported_at.desc())).scalars()
    return [_serialize_evidence(db, row) for row in rows]


@router.get("/{investigation_id}/evidence/inventory", response_model=EvidenceInventoryPage)
def evidence_inventory(
    investigation_id: UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(require_permission("investigation:read")),
    db: Session = Depends(get_db),
) -> EvidenceInventoryPage:
    if set(request.query_params) - {"limit", "offset"}:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported query parameter.")
    _active_principal_or_404(principal, db)
    return EvidenceInventoryPage.model_validate(
        EvidenceInventoryService(db).list(principal.org_id, investigation_id, limit, offset)
    )


@router.get("/{investigation_id}/evidence/{evidence_id}", response_model=EvidenceDetail)
def get_evidence(investigation_id: UUID, evidence_id: UUID, principal: Principal = Depends(require_permission("investigation:read")), db: Session = Depends(get_db)) -> EvidenceDetail:
    evidence = _evidence(db, principal, investigation_id, evidence_id)
    return EvidenceDetail.model_validate(_serialize_evidence(db, evidence))


@router.get("/{investigation_id}/evidence/{evidence_id}/download")
def download_evidence(investigation_id: UUID, evidence_id: UUID, principal: Principal = Depends(require_permission("investigation:read")), db: Session = Depends(get_db)) -> FileResponse:
    evidence = _evidence(db, principal, investigation_id, evidence_id)
    storage = EvidenceStorage(get_settings())
    # Resolve via opaque DB key only after organization/investigation auth.
    stream = storage.open_for_read(evidence.storage_key)
    stream.close()
    path = storage._path(evidence.storage_key)
    db.add(AuditEvent(
        org_id=principal.org_id, investigation_id=investigation_id, actor_id=principal.user_id,
        actor_type="user", action="EVIDENCE_DOWNLOADED", target_type="EvidenceItem", target_id=evidence.id,
        occurred_at=datetime.now(timezone.utc),
    ))
    db.commit()
    return FileResponse(path, media_type="application/octet-stream", filename="evidence-download")


@router.get("/{investigation_id}/evidence/{evidence_id}/raw-records", response_model=list[RawRecordRead])
def list_raw_records(investigation_id: UUID, evidence_id: UUID, principal: Principal = Depends(require_permission("investigation:read")), db: Session = Depends(get_db)) -> list[RawRecordRead]:
    _evidence(db, principal, investigation_id, evidence_id)
    return [RawRecordRead.model_validate(row) for row in EvidenceRepository(db).raw_records(principal.org_id, investigation_id, evidence_id)]


@router.get("/{investigation_id}/events", response_model=list[EventRead])
def list_events(investigation_id: UUID, principal: Principal = Depends(require_permission("investigation:read")), db: Session = Depends(get_db)) -> list[EventRead]:
    return [EventRead.model_validate(row) for row in EvidenceRepository(db).events(principal.org_id, investigation_id)]


@router.get("/{investigation_id}/timeline", response_model=TimelinePage)
def timeline(
    investigation_id: UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    from_at: datetime | None = Query(default=None, alias="from"),
    to_at: datetime | None = Query(default=None, alias="to"),
    evidence_id: UUID | None = Query(default=None),
    principal: Principal = Depends(require_permission("investigation:read")),
    db: Session = Depends(get_db),
) -> TimelinePage:
    if set(request.query_params) - {"limit", "offset", "from", "to", "evidence_id"}:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported query parameter.")
    for name in ("from", "to"):
        values = request.query_params.getlist(name)
        if len(values) > 1 or (values and not _TIMELINE_ISO_8601.fullmatch(values[0])):
            raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Timeline ranges must use timezone-aware ISO-8601 timestamps.")
    _active_principal_or_404(principal, db)
    return TimelinePage.model_validate(TimelineProjectionService(db).list(
        principal.org_id, investigation_id, limit=limit, offset=offset,
        from_at=from_at, to_at=to_at, evidence_id=evidence_id,
    ))


def _bounded_query(request: Request) -> None:
    if set(request.query_params) - {"limit", "offset"}:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported query parameter.")


@router.get("/{investigation_id}/indicators", response_model=IndicatorOccurrencePage)
def list_indicators(investigation_id: UUID, request: Request, limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0), principal: Principal = Depends(require_permission("investigation:read")), db: Session = Depends(get_db)) -> IndicatorOccurrencePage:
    _bounded_query(request); _active_principal_or_404(principal, db)
    return IndicatorOccurrencePage.model_validate(OccurrenceProjectionService(db).indicators(principal.org_id, investigation_id, limit, offset))


@router.get("/{investigation_id}/entities", response_model=EntityPage)
def list_entities(investigation_id: UUID, request: Request, limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0), principal: Principal = Depends(require_permission("investigation:read")), db: Session = Depends(get_db)) -> EntityPage:
    _bounded_query(request); _active_principal_or_404(principal, db)
    return EntityPage.model_validate(OccurrenceProjectionService(db).entities(principal.org_id, investigation_id, limit, offset))


@router.get("/{investigation_id}/entities/{entity_id}/observations", response_model=EntityObservationPage)
def list_entity_observations(investigation_id: UUID, entity_id: UUID, request: Request, limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0), principal: Principal = Depends(require_permission("investigation:read")), db: Session = Depends(get_db)) -> EntityObservationPage:
    _bounded_query(request); _active_principal_or_404(principal, db)
    return EntityObservationPage.model_validate(OccurrenceProjectionService(db).entity_observations(principal.org_id, investigation_id, entity_id, limit, offset))


@router.get("/{investigation_id}/relationships", response_model=list[EntityRelationshipRead])
def list_relationships(investigation_id: UUID, principal: Principal = Depends(require_permission("investigation:read")), db: Session = Depends(get_db)) -> list[EntityRelationshipRead]:
    return [EntityRelationshipRead.model_validate(row) for row in EvidenceRepository(db).relationships(principal.org_id, investigation_id)]


@router.get("/{investigation_id}/graph", response_model=CanonicalGraphRead, tags=["Canonical Graph"])
def get_canonical_graph(
    investigation_id: UUID,
    entity_type: str | None = Query(default=None),
    relationship_type: str | None = Query(default=None),
    evidence_id: UUID | None = Query(default=None),
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    principal: Principal = Depends(require_permission("investigation:read")),
    db: Session = Depends(get_db),
) -> CanonicalGraphRead:
    graph = CanonicalGraphProjectionService(db).project(
        principal.org_id, investigation_id,
        GraphFilters(entity_type, relationship_type, evidence_id, start_at, end_at),
    )
    return CanonicalGraphRead.model_validate(graph)
