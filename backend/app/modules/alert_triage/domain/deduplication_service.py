"""Deterministic, conservative semantic deduplication; no AI or downstream writes."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.alert_triage.infrastructure.models import AlertDeduplicationDecision, CanonicalAlert, CanonicalAlertOccurrence
from app.shared.exceptions import NotFoundError


SEMANTIC_DEDUPE_VERSION = "semantic-v1"
SEMANTIC_WINDOW = timedelta(seconds=60)
ENTITY_KEYS = ("hostname", "source_ip", "destination_ip", "domain", "url", "file")


@dataclass(frozen=True)
class DeduplicationRead:
    alert_id: UUID
    is_duplicate: bool
    representative_alert_id: UUID
    decision_type: str | None
    decision_version: str | None
    reasons: list[dict]
    occurrence_count: int
    first_seen: datetime
    last_seen: datetime


def _detection_key(alert: CanonicalAlert) -> tuple[str, str] | None:
    if alert.rule_id:
        return ("rule_id", alert.rule_id.casefold())
    if alert.signature:
        return ("signature", alert.signature.casefold())
    if alert.title:
        return ("title", alert.title.casefold())
    return None


def _entity_tuple(alert: CanonicalAlert) -> tuple[tuple[str, str], ...]:
    return tuple((key, alert.normalized_observables[key]) for key in ENTITY_KEYS if alert.normalized_observables.get(key))


class AlertDeduplicationService:
    """Phase 7.2: exact decisions are written by CanonicalAlertService; this adds semantic decisions."""

    def __init__(self, db: Session):
        self.db = db

    def process(self, org_id: UUID, alert_id: UUID) -> DeduplicationRead:
        alert = self._alert(org_id, alert_id)
        existing = self.db.scalar(select(AlertDeduplicationDecision).where(
            AlertDeduplicationDecision.org_id == org_id,
            AlertDeduplicationDecision.decision_version == SEMANTIC_DEDUPE_VERSION,
            AlertDeduplicationDecision.subject_key == f"alert:{alert.id}",
        ))
        if existing is not None:
            return self.read(org_id, alert_id)

        key = _detection_key(alert)
        entities = _entity_tuple(alert)
        if key is None or not entities:
            return self.read(org_id, alert_id)
        candidates = list(self.db.scalars(select(CanonicalAlert).where(
            CanonicalAlert.org_id == org_id,
            CanonicalAlert.connector_id == alert.connector_id,
            CanonicalAlert.source == alert.source,
            CanonicalAlert.id != alert.id,
            CanonicalAlert.observed_at >= alert.observed_at - SEMANTIC_WINDOW,
            CanonicalAlert.observed_at <= alert.observed_at + SEMANTIC_WINDOW,
        )))
        matches = [candidate for candidate in candidates if self._matches(alert, candidate, key, entities)]
        if not matches:
            return self.read(org_id, alert_id)
        representative = min(matches + [alert], key=lambda item: (item.observed_at, str(item.id)))
        if representative.id == alert.id:
            # A previous candidate can be semantically deduplicated against this newer processing order;
            # never rewrite its recorded representative. This alert remains independently canonical.
            return self.read(org_id, alert_id)
        reasons = [
            {"code": "SAME_DETECTION", "field": key[0], "value": key[1]},
            {"code": "SAME_CATEGORY", "value": alert.category},
            {"code": "SAME_SEVERITY", "value": alert.severity},
            {"code": "SAME_ENTITY_TUPLE", "values": [{"field": field, "value": value} for field, value in entities]},
            {"code": "WITHIN_OBSERVED_TIME_WINDOW", "seconds": abs((alert.observed_at - representative.observed_at).total_seconds()), "window_seconds": int(SEMANTIC_WINDOW.total_seconds())},
        ]
        self.db.add(AlertDeduplicationDecision(
            org_id=org_id, representative_alert_id=representative.id, duplicate_alert_id=alert.id,
            decision_type="SEMANTIC", decision_version=SEMANTIC_DEDUPE_VERSION, subject_key=f"alert:{alert.id}",
            reasons=reasons, decided_at=datetime.now(timezone.utc),
        ))
        self.db.commit()
        return self.read(org_id, alert_id)

    def read(self, org_id: UUID, alert_id: UUID) -> DeduplicationRead:
        alert = self._alert(org_id, alert_id)
        decision = self.db.scalar(select(AlertDeduplicationDecision).where(
            AlertDeduplicationDecision.org_id == org_id,
            AlertDeduplicationDecision.duplicate_alert_id == alert.id,
        ).order_by(AlertDeduplicationDecision.decided_at.desc()))
        occurrences = list(self.db.scalars(select(CanonicalAlertOccurrence).where(
            CanonicalAlertOccurrence.org_id == org_id,
            CanonicalAlertOccurrence.canonical_alert_id == alert.id,
        )))
        first_seen = min(row.received_at for row in occurrences)
        last_seen = max(row.received_at for row in occurrences)
        return DeduplicationRead(
            alert_id=alert.id, is_duplicate=decision is not None, representative_alert_id=decision.representative_alert_id if decision else alert.id,
            decision_type=decision.decision_type if decision else None, decision_version=decision.decision_version if decision else None,
            reasons=decision.reasons if decision else [], occurrence_count=len(occurrences), first_seen=first_seen, last_seen=last_seen,
        )

    def _alert(self, org_id: UUID, alert_id: UUID) -> CanonicalAlert:
        alert = self.db.scalar(select(CanonicalAlert).where(CanonicalAlert.org_id == org_id, CanonicalAlert.id == alert_id))
        if alert is None:
            raise NotFoundError("Canonical alert not found.")
        return alert

    @staticmethod
    def _matches(alert: CanonicalAlert, candidate: CanonicalAlert, key: tuple[str, str], entities: tuple[tuple[str, str], ...]) -> bool:
        return (
            _detection_key(candidate) == key
            and candidate.category == alert.category
            and candidate.severity == alert.severity
            and _entity_tuple(candidate) == entities
        )
