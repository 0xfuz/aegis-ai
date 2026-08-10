"""Versioned generic-alert webhook orchestration; never a FACT boundary."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import ValidationError as PydanticValidationError

from app.modules.alert_triage.domain.correlation_service import AlertCorrelationService, CORRELATION_VERSION
from app.modules.alert_triage.domain.correlation_v2_service import AlertCorrelationV2Service, CORRELATION_V2_VERSION
from app.modules.alert_triage.domain.deduplication_service import AlertDeduplicationService
from app.modules.alert_triage.domain.service import AlertObservables, CanonicalAlertCreate, CanonicalAlertService
from app.modules.alert_triage.domain.triage_service import AlertClusterTriageService
from app.modules.alert_triage.domain.wazuh_mapper import WazuhMappingError, map_wazuh_alert
from app.modules.alert_triage.infrastructure.models import AlertClusterMembership
from app.modules.connectors.api.schemas import GenericAlertPayload
from app.modules.connectors.domain.service import IngestService
from app.modules.connectors.infrastructure.models import Connector, ConnectorStatus, RawEvent
from app.shared.exceptions import AuthenticationError, ValidationError


@dataclass(frozen=True)
class GenericAlertIngestRead:
    replayed: bool
    canonical_alert_id: UUID
    deduplication_status: str
    cluster_id: UUID | None
    priority: str | None
    score: int | None
    correlation_version: str | None
    triage_version: str | None


class GenericAlertWebhookService:
    """Adapts v1 HTTP payloads to the frozen Phase 7 domain services."""

    def __init__(self, db: Session):
        self.db = db

    def authenticate(self, connector_id: UUID, secret: str) -> Connector:
        connector = IngestService(self.db).authenticate_connector(connector_id, secret)
        if connector.status != ConnectorStatus.CONNECTED.value:
            raise AuthenticationError("Unknown or inactive connector.")
        return connector

    def ingest(self, connector: Connector, path_source: str, payload: GenericAlertPayload) -> GenericAlertIngestRead:
        if payload.source != path_source:
            raise ValidationError("Payload source must match the webhook source identity.")
        raw = RawEvent(connector_id=connector.id, received_at=datetime.now(timezone.utc), payload=payload.model_dump(mode="json"))
        self.db.add(raw); self.db.flush()
        try:
            alert_input = CanonicalAlertCreate(
                source=path_source, source_alert_id=payload.source_alert_id, observed_at=payload.observed_at,
                title=payload.title, description=payload.description, severity=payload.severity.upper(), category=payload.category,
                rule_id=payload.rule_id, rule_name=payload.rule_name, signature=payload.signature,
                observables=AlertObservables(source_ip=payload.source_ip, destination_ip=payload.destination_ip,
                    hostname=payload.hostname, username=payload.username, process=payload.process, file=payload.file,
                    domain=payload.domain, url=payload.url), source_metadata=payload.source_metadata, normalizer_version="generic-webhook-v1",
            )
        except PydanticValidationError as exc:
            raise ValidationError("Generic alert payload violates the canonical alert contract.") from exc
        alert, replayed = CanonicalAlertService(self.db).create(connector.org_id, connector.id, raw.id, alert_input)
        connector.last_event_at = raw.received_at
        if replayed:
            self.db.commit()
            return self._existing_state(connector.org_id, alert.id, True)
        dedupe = AlertDeduplicationService(self.db).process(connector.org_id, alert.id)
        if dedupe.is_duplicate:
            return GenericAlertIngestRead(False, alert.id, "SEMANTIC_DUPLICATE", None, None, None, None, None)
        cluster = AlertCorrelationService(self.db).process(connector.org_id, alert.id)
        # Triage requires a reference at or after cluster.last_seen. A source
        # timestamp can legitimately be slightly ahead of receipt time.
        reference_at = max(datetime.now(timezone.utc), cluster.last_seen) if cluster else None
        assessment = AlertClusterTriageService(self.db).assess(connector.org_id, cluster.id, reference_at) if cluster else None
        return GenericAlertIngestRead(False, alert.id, "UNIQUE", cluster.id if cluster else None,
            assessment.priority if assessment else None, assessment.score if assessment else None,
            cluster.correlation_version if cluster else None, assessment.scoring_version if assessment else None)

    def _existing_state(self, org_id: UUID, alert_id: UUID, replayed: bool) -> GenericAlertIngestRead:
        membership = self.db.scalar(select(AlertClusterMembership).where(AlertClusterMembership.org_id == org_id, AlertClusterMembership.alert_id == alert_id, AlertClusterMembership.correlation_version == CORRELATION_VERSION))
        if membership is None:
            return GenericAlertIngestRead(replayed, alert_id, "REPLAY", None, None, None, None, None)
        cluster = AlertCorrelationService(self.db).get_cluster(org_id, membership.cluster_id)
        assessment = AlertClusterTriageService(self.db).get_latest(org_id, cluster.id)
        return GenericAlertIngestRead(replayed, alert_id, "REPLAY", cluster.id,
            assessment.priority if assessment else None, assessment.score if assessment else None,
            cluster.correlation_version, assessment.scoring_version if assessment else None)


class WazuhAlertWebhookService:
    """Dedicated v2-only Wazuh orchestration; mapping stays pure and external."""

    def __init__(self, db: Session): self.db = db

    def authenticate(self, connector_id: UUID, secret: str) -> Connector:
        connector = IngestService(self.db).authenticate_connector(connector_id, secret)
        if connector.status != ConnectorStatus.CONNECTED.value: raise AuthenticationError("Unknown or inactive connector.")
        return connector

    def ingest(self, connector: Connector, payload: dict) -> GenericAlertIngestRead:
        raw = RawEvent(connector_id=connector.id, received_at=datetime.now(timezone.utc), payload=payload)
        self.db.add(raw); self.db.flush()
        try: alert_input = map_wazuh_alert(payload)
        except WazuhMappingError as exc: raise ValidationError("Invalid Wazuh alert payload.") from exc
        alert, replayed = CanonicalAlertService(self.db).create(connector.org_id, connector.id, raw.id, alert_input)
        connector.last_event_at = raw.received_at
        if replayed:
            self.db.commit()
            return self._existing_state(connector.org_id, alert.id, True)
        dedupe = AlertDeduplicationService(self.db).process(connector.org_id, alert.id)
        if dedupe.is_duplicate: return GenericAlertIngestRead(False, alert.id, "SEMANTIC_DUPLICATE", None, None, None, None, None)
        cluster = AlertCorrelationV2Service(self.db).process(connector.org_id, alert.id)
        reference_at = max(datetime.now(timezone.utc), cluster.last_seen) if cluster else None
        assessment = AlertClusterTriageService(self.db).assess(connector.org_id, cluster.id, reference_at) if cluster else None
        return GenericAlertIngestRead(False, alert.id, "UNIQUE", cluster.id if cluster else None,
            assessment.priority if assessment else None, assessment.score if assessment else None,
            CORRELATION_V2_VERSION if cluster else None, assessment.scoring_version if assessment else None)

    def _existing_state(self, org_id: UUID, alert_id: UUID, replayed: bool) -> GenericAlertIngestRead:
        membership = self.db.scalar(select(AlertClusterMembership).where(
            AlertClusterMembership.org_id == org_id, AlertClusterMembership.alert_id == alert_id,
            AlertClusterMembership.correlation_version == CORRELATION_V2_VERSION,
        ))
        if membership is None: return GenericAlertIngestRead(replayed, alert_id, "REPLAY", None, None, None, None, None)
        assessment = AlertClusterTriageService(self.db).get_latest(org_id, membership.cluster_id)
        return GenericAlertIngestRead(replayed, alert_id, "REPLAY", membership.cluster_id,
            assessment.priority if assessment else None, assessment.score if assessment else None,
            CORRELATION_V2_VERSION, assessment.scoring_version if assessment else None)
