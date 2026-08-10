from uuid import UUID

import json
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.identity.api.dependencies import Principal, require_permission
from app.modules.connectors.api.schemas import (
    ConnectorCreate,
    ConnectorCreated,
    ConnectorRead,
    IngestResult,
    WebhookEventPayload,
    GenericAlertPayload, GenericAlertIngestResult,
)
from app.modules.alert_triage.domain.webhook_service import GenericAlertWebhookService, WazuhAlertWebhookService
from app.modules.connectors.domain.service import ConnectorService, IngestService
from app.shared.database import get_db
from app.shared.exceptions import AuthenticationError, ValidationError

settings = get_settings()

# Authenticated admin management — mirrors every other module's pattern.
router = APIRouter(prefix="/connectors", tags=["Connectors"])

# Public ingest — deliberately its own router with no auth dependency at
# all, since external systems can't do a user login. Authorization here
# is entirely the connector secret, checked inside the handler.
ingest_router = APIRouter(prefix="/ingest", tags=["Ingest"])
_MAX_GENERIC_ALERT_BYTES = 256 * 1024
_RATE_WINDOW_SECONDS = 60
_RATE_MAX_REQUESTS = 60
_request_times: dict[str, deque[float]] = defaultdict(deque)


@router.get("", response_model=list[ConnectorRead])
def list_connectors(
    principal: Principal = Depends(require_permission("settings:manage_connectors")),
    db: Session = Depends(get_db),
) -> list[ConnectorRead]:
    connectors = ConnectorService(db).list_connectors(principal.org_id)
    return [ConnectorRead.model_validate(c) for c in connectors]


@router.post("/webhook", response_model=ConnectorCreated, status_code=status.HTTP_201_CREATED)
def create_webhook_connector(
    payload: ConnectorCreate,
    principal: Principal = Depends(require_permission("settings:manage_connectors")),
    db: Session = Depends(get_db),
) -> ConnectorCreated:
    result = ConnectorService(db).create_webhook_connector(principal.org_id, payload.name, settings.PUBLIC_API_BASE_URL)
    db.commit()
    return result


@router.delete("/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connector(
    connector_id: UUID,
    principal: Principal = Depends(require_permission("settings:manage_connectors")),
    db: Session = Depends(get_db),
) -> None:
    ConnectorService(db).delete_connector(principal.org_id, connector_id)
    db.commit()


@ingest_router.post("/webhook/{connector_id}", response_model=IngestResult, status_code=status.HTTP_201_CREATED)
def ingest_webhook_event(
    connector_id: UUID,
    payload: WebhookEventPayload,
    x_ingest_secret: str = Header(..., description="The plaintext secret shown once at connector creation"),
    db: Session = Depends(get_db),
) -> IngestResult:
    ingest = IngestService(db)
    try:
        connector = ingest.authenticate_connector(connector_id, x_ingest_secret)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    investigation = ingest.ingest_webhook_event(connector, payload)
    db.commit()
    return IngestResult(investigation_id=investigation.id)


@ingest_router.post("/alerts/v1/{connector_id}/{source}", response_model=GenericAlertIngestResult, status_code=status.HTTP_201_CREATED)
async def ingest_generic_alert(
    connector_id: UUID, source: str, request: Request, response: Response,
    x_ingest_secret: str = Header(..., description="The connector secret shown at creation"),
    db: Session = Depends(get_db),
) -> GenericAlertIngestResult:
    """External ingress only; alert logic remains in Phase 7 domain services."""
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise ValidationError("Generic alert webhook requires application/json content type.")
    raw_body = await _bounded_body(request)
    try:
        raw_payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise ValidationError("Malformed JSON alert payload.") from exc
    try:
        payload = GenericAlertPayload.model_validate(raw_payload)
    except PydanticValidationError as exc:
        raise ValidationError("Invalid generic alert payload.") from exc
    service = GenericAlertWebhookService(db)
    try:
        connector = service.authenticate(connector_id, x_ingest_secret)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    _enforce_rate_limit(str(connector.id))
    result = service.ingest(connector, source, payload)
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return GenericAlertIngestResult(status="replayed" if result.replayed else "accepted", canonical_alert_id=result.canonical_alert_id,
        deduplication_status=result.deduplication_status, cluster_id=result.cluster_id, priority=result.priority,
        score=result.score, correlation_version=result.correlation_version, triage_version=result.triage_version)


@ingest_router.post("/wazuh/v1/{connector_id}", response_model=GenericAlertIngestResult, status_code=status.HTTP_201_CREATED)
async def ingest_wazuh_alert(
    connector_id: UUID, request: Request, response: Response,
    x_ingest_secret: str = Header(..., description="The connector secret shown at creation"),
    db: Session = Depends(get_db),
) -> GenericAlertIngestResult:
    """Dedicated Wazuh boundary: fixed source, pure mapper, and v2 only."""
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise ValidationError("Wazuh alert webhook requires application/json content type.")
    raw_body = await _bounded_body(request)
    try:
        raw_payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise ValidationError("Malformed JSON Wazuh alert payload.") from exc
    if not isinstance(raw_payload, dict):
        raise ValidationError("Wazuh alert payload must be a JSON object.")
    service = WazuhAlertWebhookService(db)
    try:
        connector = service.authenticate(connector_id, x_ingest_secret)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    _enforce_rate_limit(str(connector.id))
    result = service.ingest(connector, raw_payload)
    if result.replayed: response.status_code = status.HTTP_200_OK
    return GenericAlertIngestResult(status="replayed" if result.replayed else "accepted", canonical_alert_id=result.canonical_alert_id,
        deduplication_status=result.deduplication_status, cluster_id=result.cluster_id, priority=result.priority,
        score=result.score, correlation_version=result.correlation_version, triage_version=result.triage_version)


def _enforce_rate_limit(connector_key: str) -> None:
    now = time.monotonic(); events = _request_times[connector_key]
    while events and events[0] <= now - _RATE_WINDOW_SECONDS: events.popleft()
    if len(events) >= _RATE_MAX_REQUESTS:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Connector ingest rate limit exceeded.")
    events.append(now)


async def _bounded_body(request: Request) -> bytes:
    """Read ASGI chunks only up to the public webhook contract limit."""
    chunks: list[bytes] = []
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > _MAX_GENERIC_ALERT_BYTES:
            raise ValidationError("Generic alert payload exceeds the 256 KiB limit.")
        chunks.append(chunk)
    return b"".join(chunks)
