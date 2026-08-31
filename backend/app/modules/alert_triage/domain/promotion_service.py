"""Phase 7.5 analyst-controlled, deterministic alert-cluster promotion."""
from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.alert_triage.domain.correlation_service import AlertCorrelationService
from app.modules.alert_triage.domain.correlation_service import CORRELATION_VERSION
from app.modules.alert_triage.domain.correlation_v2_service import CORRELATION_V2_VERSION
from app.modules.alert_triage.domain.triage_service import AlertClusterTriageService
from app.modules.alert_triage.infrastructure.models import (
    AlertCluster, AlertClusterAssessment, AlertClusterMembership, AlertClusterPromotion,
    AlertDeduplicationDecision, CanonicalAlert,
)
from app.modules.evidence.domain.service import EvidenceIngestionService
from app.modules.evidence.infrastructure.models import AuditEvent
from app.modules.evidence.infrastructure.storage import EvidenceStorage
from app.modules.identity.infrastructure.models import User
from app.modules.investigations.domain.service import InvestigationService
from app.modules.investigations.infrastructure.models import Severity
from app.shared.exceptions import NotFoundError, ValidationError


PROMOTION_EXPORT_VERSION = "alert-promotion-export-v1"
_EXPORT_FORMAT = "aegis.alert-promotion.export"


@dataclass(frozen=True)
class AlertClusterPromotionRead:
    id: UUID
    cluster_id: UUID
    investigation_id: UUID
    evidence_id: UUID
    triage_assessment_id: UUID
    export_version: str
    export_fingerprint: str
    promoted_at: datetime
    created: bool


class AlertClusterPromotionService:
    """Explicit analyst action only; it never writes canonical FACT models itself."""

    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def promote(self, org_id: UUID, cluster_id: UUID, actor_id: UUID) -> AlertClusterPromotionRead:
        storage_key: str | None = None
        try:
            self._actor(org_id, actor_id)
            cluster = self._root_cluster_for_update(org_id, cluster_id)
            existing = self._existing(org_id, cluster.id)
            if existing is not None:
                return self._read(existing, created=False)
            if cluster.status != "OPEN":
                raise ValidationError("Only an OPEN alert cluster may be promoted.")
            members = self._members_for_cluster(org_id, cluster)
            if not members:
                raise ValidationError("Alert cluster has no promotable members.")
            alerts = [self._alert(org_id, member.alert_id) for member in members]
            self._validate_members(org_id, alerts)
            assessment_read = AlertClusterTriageService(self.db).get_latest(org_id, cluster.id)
            if assessment_read is None:
                raise ValidationError("A current deterministic triage assessment is required before promotion.")
            assessment = self.db.get(AlertClusterAssessment, assessment_read.id)
            if assessment is None or assessment.org_id != org_id:
                raise ValidationError("Promotion assessment is unavailable in this organization.")

            manifest, export = self._manifest_and_export(cluster, members, alerts, assessment)
            export_bytes = _canonical_json(export)
            fingerprint = hashlib.sha256(export_bytes).hexdigest()
            severity = Severity(assessment.priority.lower())
            investigation = InvestigationService(self.db).create_alert_promotion_investigation(
                org_id, f"Promoted alert cluster {cluster.id}", severity,
            )
            evidence = EvidenceIngestionService(self.db, self.settings).ingest(
                org_id, investigation.id, actor_id,
                SimpleNamespace(filename="alert-promotion-v1.json", content_type="application/json", file=io.BytesIO(export_bytes)),
                atomic=True, acquisition_source="alert_cluster_promotion",
            )
            storage_key = evidence.storage_key
            promotion = AlertClusterPromotion(
                org_id=org_id, cluster_id=cluster.id, investigation_id=investigation.id, evidence_id=evidence.id,
                actor_id=actor_id, triage_assessment_id=assessment.id, export_version=PROMOTION_EXPORT_VERSION,
                export_fingerprint=fingerprint, manifest=manifest, status="COMPLETED", promoted_at=datetime.now(timezone.utc),
            )
            self.db.add(promotion)
            self.db.flush()
            cluster.status = "PROMOTED"
            self._audit(org_id, investigation.id, actor_id, cluster.id, promotion.id, assessment.id, fingerprint)
            self.db.commit()
            return self._read(promotion, created=True)
        except Exception:
            self.db.rollback()
            if storage_key:
                EvidenceStorage(self.settings).delete(storage_key)
            raise

    def get_by_cluster(self, org_id: UUID, cluster_id: UUID) -> AlertClusterPromotionRead | None:
        cluster = AlertCorrelationService(self.db)._root_cluster(org_id, cluster_id)
        row = self._existing(org_id, cluster.id)
        return self._read(row, created=False) if row else None

    def _root_cluster_for_update(self, org_id: UUID, cluster_id: UUID) -> AlertCluster:
        selected = self.db.scalar(select(AlertCluster).where(
            AlertCluster.org_id == org_id, AlertCluster.id == cluster_id,
        ).with_for_update())
        if selected is None:
            raise NotFoundError("Alert cluster not found.")
        root = AlertCorrelationService(self.db)._root_cluster(org_id, selected.id)
        if root.id != selected.id:
            root = self.db.scalar(select(AlertCluster).where(AlertCluster.id == root.id).with_for_update())
        return root

    def _actor(self, org_id: UUID, actor_id: UUID) -> User:
        actor = self.db.scalar(select(User).where(User.id == actor_id, User.org_id == org_id, User.is_active.is_(True)))
        if actor is None:
            raise NotFoundError("Active analyst not found in this organization.")
        return actor

    def _existing(self, org_id: UUID, cluster_id: UUID) -> AlertClusterPromotion | None:
        return self.db.scalar(select(AlertClusterPromotion).where(
            AlertClusterPromotion.org_id == org_id, AlertClusterPromotion.cluster_id == cluster_id,
        ))

    def _members_for_cluster(self, org_id: UUID, cluster: AlertCluster) -> list[AlertClusterMembership]:
        """Read the cluster's already-persisted, explicitly versioned history only."""
        if cluster.correlation_version not in {CORRELATION_VERSION, CORRELATION_V2_VERSION}:
            raise ValidationError("Unsupported correlation version for promotion.")
        return list(self.db.scalars(select(AlertClusterMembership).where(
            AlertClusterMembership.org_id == org_id,
            AlertClusterMembership.cluster_id == cluster.id,
            AlertClusterMembership.correlation_version == cluster.correlation_version,
        ).order_by(AlertClusterMembership.added_at, AlertClusterMembership.id)))

    def _alert(self, org_id: UUID, alert_id: UUID) -> CanonicalAlert:
        row = self.db.scalar(select(CanonicalAlert).where(CanonicalAlert.id == alert_id, CanonicalAlert.org_id == org_id))
        if row is None:
            raise ValidationError("Cluster member alert is outside the organization scope.")
        return row

    def _validate_members(self, org_id: UUID, alerts: list[CanonicalAlert]) -> None:
        if len({alert.id for alert in alerts}) != len(alerts):
            raise ValidationError("Alert cluster has duplicate members.")
        for alert in alerts:
            semantic = self.db.scalar(select(AlertDeduplicationDecision.id).where(
                AlertDeduplicationDecision.org_id == org_id,
                AlertDeduplicationDecision.duplicate_alert_id == alert.id,
                AlertDeduplicationDecision.decision_type == "SEMANTIC",
            ))
            if semantic is not None:
                raise ValidationError("Semantic duplicate alerts cannot be promoted as cluster members.")

    def _manifest_and_export(self, cluster: AlertCluster, members: list[AlertClusterMembership], alerts: list[CanonicalAlert], assessment: AlertClusterAssessment) -> tuple[dict, dict]:
        member_by_alert = {member.alert_id: member for member in members}
        ordered = sorted(alerts, key=lambda item: (item.observed_at, str(item.id)))
        entries = [self._alert_entry(alert, member_by_alert[alert.id]) for alert in ordered]
        assessment_snapshot = {
            "id": str(assessment.id), "scoring_version": assessment.scoring_version, "input_hash": assessment.input_hash,
            "score": assessment.score, "priority": assessment.priority, "reference_at": assessment.reference_at.isoformat(),
        }
        manifest = {
            "format": "aegis.alert-promotion.manifest", "version": "1.0", "cluster_id": str(cluster.id),
            "correlation_version": cluster.correlation_version, "members": entries,
            "triage_assessment": assessment_snapshot, "export_version": PROMOTION_EXPORT_VERSION,
        }
        export = {
            "format": _EXPORT_FORMAT, "version": "1.0", "cluster_id": str(cluster.id),
            "manifest_fingerprint": hashlib.sha256(_canonical_json(manifest)).hexdigest(), "alerts": entries,
        }
        return manifest, export

    @staticmethod
    def _alert_entry(alert: CanonicalAlert, member: AlertClusterMembership) -> dict:
        return {
            "canonical_alert_id": str(alert.id), "connector_id": str(alert.connector_id), "raw_event_id": str(alert.raw_event_id),
            "source": alert.source, "source_alert_id": alert.source_alert_id, "observed_at": alert.observed_at.isoformat(),
            "ingested_at": alert.ingested_at.isoformat(), "severity": alert.severity, "category": alert.category,
            "rule_id": alert.rule_id, "rule_name": alert.rule_name, "signature": alert.signature,
            "observables": alert.normalized_observables, "payload_digest": alert.payload_digest,
            "membership_context": {"cluster_id": str(member.cluster_id), "membership_id": str(member.id),
                                   "correlation_version": member.correlation_version, "score": member.score, "reasons": member.reasons},
        }

    def _audit(self, org_id: UUID, investigation_id: UUID, actor_id: UUID, cluster_id: UUID, promotion_id: UUID, assessment_id: UUID, fingerprint: str) -> None:
        self.db.add(AuditEvent(
            org_id=org_id, investigation_id=investigation_id, actor_id=actor_id, actor_type="user",
            action="ALERT_CLUSTER_PROMOTED", target_type="AlertCluster", target_id=cluster_id,
            occurred_at=datetime.now(timezone.utc), metadata_={"promotion_id": str(promotion_id),
                "triage_assessment_id": str(assessment_id), "export_fingerprint": fingerprint,
                "export_version": PROMOTION_EXPORT_VERSION},
        ))

    @staticmethod
    def _read(row: AlertClusterPromotion, created: bool) -> AlertClusterPromotionRead:
        return AlertClusterPromotionRead(row.id, row.cluster_id, row.investigation_id, row.evidence_id,
            row.triage_assessment_id, row.export_version, row.export_fingerprint, row.promoted_at, created)


def _canonical_json(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
