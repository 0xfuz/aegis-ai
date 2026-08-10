"""Phase 7.1 source-independent alert creation and read boundary only."""
from __future__ import annotations

import hashlib
import ipaddress
import json
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.alert_triage.infrastructure.models import AlertDeduplicationDecision, CanonicalAlert, CanonicalAlertOccurrence
from app.modules.connectors.infrastructure.models import Connector, RawEvent
from app.shared.exceptions import ConflictError, NotFoundError, ValidationError


class AlertObservables(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_ip: str | None = Field(default=None, max_length=45)
    destination_ip: str | None = Field(default=None, max_length=45)
    hostname: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=255)
    process: str | None = Field(default=None, max_length=1024)
    file: str | None = Field(default=None, max_length=1024)
    domain: str | None = Field(default=None, max_length=253)
    url: str | None = Field(default=None, max_length=2048)

    @field_validator("source_ip", "destination_ip")
    @classmethod
    def valid_ip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return str(ipaddress.ip_address(value))
        except ValueError as exc:
            raise ValueError("must be a valid IP address") from exc

    @field_validator("hostname", "username", "process", "file", "domain")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return value.casefold().rstrip(".") if value else None

    @field_validator("url")
    @classmethod
    def normalize_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("must be an absolute http or https URL")
        return urlunsplit((parsed.scheme.casefold(), parsed.netloc.casefold(), parsed.path, parsed.query, ""))

    def stored(self) -> dict[str, str]:
        return {key: value for key, value in self.model_dump().items() if value is not None}


class CanonicalAlertCreate(BaseModel):
    """Validated normalizer output; raw external payload is never accepted here."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source: str = Field(min_length=1, max_length=100)
    source_alert_id: str = Field(min_length=1, max_length=255)
    observed_at: datetime
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=10_000)
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
    category: str | None = Field(default=None, max_length=100)
    rule_id: str | None = Field(default=None, max_length=255)
    rule_name: str | None = Field(default=None, max_length=255)
    signature: str | None = Field(default=None, max_length=255)
    observables: AlertObservables = Field(default_factory=AlertObservables)
    source_metadata: dict = Field(default_factory=dict)
    normalizer_version: str = Field(default="1", min_length=1, max_length=100)

    @field_validator("observed_at")
    @classmethod
    def aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("must include a timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def bounded_metadata(self) -> "CanonicalAlertCreate":
        try:
            encoded = json.dumps(self.source_metadata, sort_keys=True, separators=(",", ":")).encode()
        except (TypeError, ValueError) as exc:
            raise ValueError("source_metadata must be JSON serializable") from exc
        if len(encoded) > 64 * 1024:
            raise ValueError("source_metadata exceeds the metadata size limit")
        def depth(value: object, current: int = 0) -> None:
            if current > 32:
                raise ValueError("source_metadata exceeds the nesting-depth limit")
            if isinstance(value, dict):
                for child in value.values(): depth(child, current + 1)
            elif isinstance(value, list):
                for child in value: depth(child, current + 1)
        depth(self.source_metadata)
        return self


class CanonicalAlertService:
    """Does not write FACT, AIIE, Findings, MITRE, or Investigations."""

    def __init__(self, db: Session, settings: Settings | None = None):
        self.db = db
        self.settings = settings or Settings()

    def create(self, org_id: UUID, connector_id: UUID, raw_event_id: UUID, alert: CanonicalAlertCreate) -> tuple[CanonicalAlert, bool]:
        connector = self.db.get(Connector, connector_id)
        if connector is None or connector.org_id != org_id:
            raise NotFoundError("Connector not found.")
        raw_event = self.db.get(RawEvent, raw_event_id)
        if raw_event is None or raw_event.connector_id != connector.id:
            raise ValidationError("Raw source provenance does not belong to this connector.")
        digest = hashlib.sha256(json.dumps(raw_event.payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        existing = self.db.scalar(select(CanonicalAlert).where(
            CanonicalAlert.org_id == org_id, CanonicalAlert.connector_id == connector_id,
            CanonicalAlert.source == alert.source, CanonicalAlert.source_alert_id == alert.source_alert_id,
        ))
        if existing is not None:
            if self.db.scalar(select(CanonicalAlertOccurrence).where(CanonicalAlertOccurrence.raw_event_id == raw_event_id)):
                raise ConflictError("Raw source event has already been recorded.")
            occurrence = CanonicalAlertOccurrence(org_id=org_id, canonical_alert_id=existing.id, raw_event_id=raw_event.id, received_at=raw_event.received_at, payload_digest=digest, disposition="REPLAY")
            self.db.add(occurrence)
            self.db.flush()
            self.db.add(AlertDeduplicationDecision(
                org_id=org_id, representative_alert_id=existing.id, duplicate_occurrence_id=occurrence.id,
                decision_type="EXACT_REPLAY", decision_version="exact-v1", subject_key=f"occurrence:{occurrence.id}",
                reasons=[{"code": "EXACT_SOURCE_IDENTITY", "connector_id": str(connector_id), "source": alert.source, "source_alert_id": alert.source_alert_id}],
                decided_at=datetime.now(timezone.utc),
            ))
            self.db.commit()
            return existing, True

        now = datetime.now(timezone.utc)
        created = CanonicalAlert(
            org_id=org_id, connector_id=connector.id, raw_event_id=raw_event.id, source=alert.source,
            source_alert_id=alert.source_alert_id, observed_at=alert.observed_at, ingested_at=now,
            title=alert.title, description=alert.description, severity=alert.severity, category=alert.category,
            rule_id=alert.rule_id, rule_name=alert.rule_name, signature=alert.signature,
            normalized_observables=alert.observables.stored(), source_metadata=alert.source_metadata,
            payload_digest=digest, normalizer_version=alert.normalizer_version, lifecycle="NEW",
        )
        self.db.add(created)
        self.db.flush()
        self.db.add(CanonicalAlertOccurrence(org_id=org_id, canonical_alert_id=created.id, raw_event_id=raw_event.id, received_at=raw_event.received_at, payload_digest=digest, disposition="INITIAL"))
        self.db.commit()
        return created, False

    def get(self, org_id: UUID, alert_id: UUID) -> CanonicalAlert:
        alert = self.db.scalar(select(CanonicalAlert).where(CanonicalAlert.id == alert_id, CanonicalAlert.org_id == org_id))
        if alert is None:
            raise NotFoundError("Canonical alert not found.")
        return alert

    def list_occurrences(self, org_id: UUID, alert_id: UUID) -> list[CanonicalAlertOccurrence]:
        self.get(org_id, alert_id)
        return list(self.db.scalars(select(CanonicalAlertOccurrence).where(
            CanonicalAlertOccurrence.org_id == org_id, CanonicalAlertOccurrence.canonical_alert_id == alert_id,
        ).order_by(CanonicalAlertOccurrence.received_at, CanonicalAlertOccurrence.created_at)))
