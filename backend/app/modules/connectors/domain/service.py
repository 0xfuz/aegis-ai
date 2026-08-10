"""
Application services for the connectors module.

`ConnectorService` is authenticated-admin-only CRUD (register/list/delete
a connector, matching settings:manage_connectors from the permission
table). `IngestService` is deliberately separate — it's called from an
UNAUTHENTICATED route (the external system posting a webhook has no
Aegis user account), authorized only by the connector's own secret, so
it must never assume a Principal exists.
"""
import secrets
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.modules.connectors.infrastructure.models import Connector, ConnectorStatus, ConnectorType, RawEvent
from app.modules.connectors.infrastructure.repository import ConnectorRepository
from app.modules.connectors.api.schemas import ConnectorCreated, ConnectorRead, WebhookEventPayload
from app.modules.investigations.infrastructure.models import (
    Evidence,
    EvidenceType,
    Investigation,
    InvestigationStatus,
    IOC,
    Severity,
    TimelineEvent,
)
from app.modules.assets.infrastructure.repository import AssetRepository
from app.modules.investigations.infrastructure.repository import IOCRepository
from app.shared.exceptions import AuthenticationError, NotFoundError, ValidationError


class ConnectorService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ConnectorRepository(db)

    def list_connectors(self, org_id: UUID) -> list[Connector]:
        return self.repo.list_by_org(org_id)

    def create_webhook_connector(self, org_id: UUID, name: str, base_url: str) -> ConnectorCreated:
        secret = secrets.token_urlsafe(32)
        connector = Connector(
            org_id=org_id,
            name=name,
            type=ConnectorType.WEBHOOK.value,
            status=ConnectorStatus.CONNECTED.value,
            secret_hash=hash_password(secret),
            is_active=True,
        )
        self.repo.create(connector)

        return ConnectorCreated(
            connector=ConnectorRead.model_validate(connector),
            ingest_url=f"{base_url}/api/v1/ingest/webhook/{connector.id}",
            ingest_secret=secret,
        )

    def delete_connector(self, org_id: UUID, connector_id: UUID) -> None:
        connector = self.repo.get_by_id_for_org(org_id, connector_id)
        if connector is None:
            raise NotFoundError("Connector not found.")
        self.repo.delete(connector)


class IngestService:
    """No Principal, no org_id from a JWT — everything here is derived
    from the connector row itself, found via the secret the caller
    presents. This is the module boundary where "outside the platform"
    becomes "inside the platform": everything past normalize_webhook_event
    is indistinguishable from an investigation created any other way."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = ConnectorRepository(db)
        self.ioc_repo = IOCRepository(db)
        self.asset_repo = AssetRepository(db)

    def authenticate_connector(self, connector_id: UUID, secret: str) -> Connector:
        connector = self.repo.get_by_id(connector_id)
        if connector is None or not connector.is_active:
            raise AuthenticationError("Unknown or inactive connector.")
        if not verify_password(secret, connector.secret_hash):
            raise AuthenticationError("Invalid ingest secret.")
        return connector

    def ingest_webhook_event(self, connector: Connector, payload: WebhookEventPayload) -> Investigation:
        try:
            severity = Severity(payload.severity.lower())
        except ValueError as exc:
            valid = ", ".join(s.value for s in Severity)
            raise ValidationError(f"Invalid severity '{payload.severity}'. Must be one of: {valid}.") from exc

        now = datetime.now(timezone.utc)

        raw_event = RawEvent(
            connector_id=connector.id,
            received_at=now,
            payload=payload.model_dump(),
        )
        self.repo.add_raw_event(raw_event)

        # No AI reasoning fields populated here on purpose — that's the
        # ai_reasoning module's job in a later phase. A freshly ingested
        # investigation honestly reflects "a connector reported this,
        # nothing has assessed it yet" rather than faking a confidence
        # score with no reasoning behind it.
        investigation = Investigation(
            org_id=connector.org_id,
            title=payload.title,
            source=connector.name,
            severity=severity,
            status=InvestigationStatus.NEW,
            confidence=0,
            root_cause=payload.description or "Awaiting analysis.",
            mitre_techniques=[],
            blast_radius_summary="",
            false_positive_probability=0,
            created_at=now,
        )
        self.db.add(investigation)
        self.db.flush()

        # Watchlisted indicators that showed up in THIS ingest — collected
        # while recording sightings below, then turned into one Timeline
        # Event each after the main "event received" entry. Deduped by
        # (type, value) so a payload that happens to list the same
        # indicator twice doesn't produce two identical match events.
        watchlist_matches: list[IOC] = []
        seen_watch_pairs: set[tuple[str, str]] = set()

        for indicator in payload.indicators:
            try:
                evidence_type = EvidenceType(indicator.type.lower())
            except ValueError:
                continue  # unrecognized indicator type — skip rather than fail the whole ingest
            self.db.add(Evidence(investigation_id=investigation.id, type=evidence_type, value=indicator.value))
            if evidence_type == EvidenceType.ASSET:
                self.asset_repo.record_mention(connector.org_id, indicator.value, seen_at=now)
            else:
                ioc = self.ioc_repo.record_sighting(connector.org_id, evidence_type, indicator.value, seen_at=now)
                pair = (evidence_type.value, indicator.value)
                if ioc.is_watched and pair not in seen_watch_pairs:
                    seen_watch_pairs.add(pair)
                    watchlist_matches.append(ioc)

        self.db.add(
            TimelineEvent(
                investigation_id=investigation.id,
                occurred_at=now,
                description=f"Event received via {connector.name}",
                severity=severity,
                mitre_technique=None,
                source=connector.name,
                affected_asset=None,
                actor=None,
            )
        )

        # Watchlist Match: reuses the existing Timeline/TimelineEvent
        # architecture rather than a parallel alert system — this means
        # it automatically shows up wherever timeline events already do
        # (Investigation Workspace, Attack Graph), with no new UI surface.
        for ioc in watchlist_matches:
            self.db.add(
                TimelineEvent(
                    investigation_id=investigation.id,
                    occurred_at=now,
                    description=(
                        f"Watchlist match: {ioc.type.value} '{ioc.value}' is on the analyst watchlist "
                        f"({ioc.sightings_count} total sightings across all investigations)."
                    ),
                    severity=severity,
                    mitre_technique=None,
                    source="Watchlist",
                    affected_asset=None,
                    actor=None,
                )
            )

        raw_event.investigation_id = investigation.id
        connector.last_event_at = now
        self.db.flush()

        return investigation
