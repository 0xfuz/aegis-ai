"""Phase 7.4 bounded, explainable AlertCluster priority scoring; never AI-driven."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.alert_triage.domain.correlation_service import AlertCorrelationService, CORRELATION_VERSION
from app.modules.alert_triage.domain.correlation_v2_service import CORRELATION_V2_VERSION
from app.modules.alert_triage.infrastructure.models import AlertCluster, AlertClusterAssessment, AlertClusterMembership, CanonicalAlert
from app.modules.assets.infrastructure.models import Asset
from app.modules.investigations.infrastructure.models import IOC
from app.shared.exceptions import NotFoundError, ValidationError


SCORING_VERSION = "triage-v1"
SEVERITY_POINTS = {"CRITICAL": 25, "HIGH": 18, "MEDIUM": 10, "LOW": 4, "INFO": 0}


@dataclass(frozen=True)
class ClusterAssessmentRead:
    id: UUID
    cluster_id: UUID
    score: int
    priority: str
    scoring_version: str
    ledger: list[dict]
    reference_at: datetime
    evaluated_at: datetime


def priority_band(score: int) -> str:
    if not 0 <= score <= 100:
        raise ValueError("Score must be within 0..100")
    if score <= 24:
        return "LOW"
    if score <= 49:
        return "MEDIUM"
    if score <= 74:
        return "HIGH"
    return "CRITICAL"


class AlertClusterTriageService:
    """Append-only assessment history; does not alter cluster/canonical/downstream state."""

    def __init__(self, db: Session):
        self.db = db

    def assess(self, org_id: UUID, cluster_id: UUID, reference_at: datetime) -> ClusterAssessmentRead:
        if reference_at.tzinfo is None or reference_at.utcoffset() is None:
            raise ValidationError("Scoring reference timestamp must include a timezone.")
        reference_at = reference_at.astimezone(timezone.utc)
        cluster = self._root_cluster(org_id, cluster_id)
        members, alerts = self._materialize_assessment_inputs(org_id, cluster)
        ledger = self._ledger(org_id, cluster, alerts, members, reference_at)
        score = sum(entry["points"] for entry in ledger)
        if not 0 <= score <= 100:
            raise ValidationError("Deterministic triage ledger is outside its bounded range.")
        input_snapshot = self._input_snapshot(cluster, alerts, members, ledger, reference_at)
        input_hash = hashlib.sha256(json.dumps(input_snapshot, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
        existing = self.db.scalar(select(AlertClusterAssessment).where(
            AlertClusterAssessment.cluster_id == cluster.id, AlertClusterAssessment.scoring_version == SCORING_VERSION,
            AlertClusterAssessment.input_hash == input_hash,
        ))
        if existing is not None:
            return self._read(existing)
        row = AlertClusterAssessment(
            org_id=org_id, cluster_id=cluster.id, scoring_version=SCORING_VERSION, input_hash=input_hash,
            score=score, priority=priority_band(score), ledger=ledger, reference_at=reference_at,
            evaluated_at=datetime.now(timezone.utc),
        )
        self.db.add(row); self.db.commit()
        return self._read(row)

    def get_latest(self, org_id: UUID, cluster_id: UUID) -> ClusterAssessmentRead | None:
        cluster = self._root_cluster(org_id, cluster_id)
        row = self.db.scalar(select(AlertClusterAssessment).where(
            AlertClusterAssessment.org_id == org_id, AlertClusterAssessment.cluster_id == cluster.id,
        ).order_by(AlertClusterAssessment.evaluated_at.desc(), AlertClusterAssessment.id.desc()))
        return self._read(row) if row else None

    def list_history(self, org_id: UUID, cluster_id: UUID) -> list[ClusterAssessmentRead]:
        cluster = self._root_cluster(org_id, cluster_id)
        return [self._read(row) for row in self.db.scalars(select(AlertClusterAssessment).where(
            AlertClusterAssessment.org_id == org_id, AlertClusterAssessment.cluster_id == cluster.id,
        ).order_by(AlertClusterAssessment.evaluated_at, AlertClusterAssessment.id))]

    def _ledger(self, org_id: UUID, cluster: AlertCluster, alerts: list[CanonicalAlert], members: list[AlertClusterMembership], reference_at: datetime) -> list[dict]:
        return [
            self._severity(alerts), self._asset_criticality(org_id, alerts), self._member_count(cluster),
            self._source_diversity(cluster), self._correlation_strength(members), self._sequence(alerts),
            self._trusted_ioc(org_id, alerts), self._recency(cluster, reference_at),
        ]

    @staticmethod
    def _entry(factor: str, points: int, reason: str, references: list[dict] | None = None) -> dict:
        return {"factor": factor, "points": points, "reason": reason, "references": references or [], "scoring_version": SCORING_VERSION}

    def _severity(self, alerts: list[CanonicalAlert]) -> dict:
        winner = min(alerts, key=lambda alert: (-SEVERITY_POINTS[alert.severity], alert.observed_at, str(alert.id)))
        points = SEVERITY_POINTS[winner.severity]
        return self._entry("source_severity", points, f"Highest distinct canonical alert severity is {winner.severity}.", [{"alert_id": str(winner.id), "severity": winner.severity}])

    def _asset_criticality(self, org_id: UUID, alerts: list[CanonicalAlert]) -> dict:
        hostnames = {alert.normalized_observables.get("hostname") for alert in alerts if alert.normalized_observables.get("hostname")}
        assets = [asset for asset in self.db.scalars(select(Asset).where(Asset.org_id == org_id)) if asset.name.casefold() in hostnames]
        points_by_criticality = {"critical": 20, "high": 12, "medium": 0, "low": 0}
        if not assets:
            return self._entry("asset_criticality", 0, "Unavailable: no trusted asset registry match for normalized hostnames.")
        winner = max(assets, key=lambda asset: points_by_criticality.get(asset.criticality, 0))
        points = points_by_criticality.get(winner.criticality, 0)
        return self._entry("asset_criticality", points, f"Trusted asset registry criticality is {winner.criticality}.", [{"asset_id": str(winner.id), "name": winner.name, "criticality": winner.criticality}])

    def _member_count(self, cluster: AlertCluster) -> dict:
        points = 0 if cluster.member_count <= 1 else 4 if cluster.member_count <= 3 else 7 if cluster.member_count <= 7 else 10
        return self._entry("member_count", points, f"{cluster.member_count} distinct non-duplicate canonical alerts; bounded at 10 points.")

    def _source_diversity(self, cluster: AlertCluster) -> dict:
        points = 0 if cluster.source_diversity <= 1 else 5 if cluster.source_diversity == 2 else 10
        return self._entry("source_diversity", points, f"{cluster.source_diversity} independent connector/source pairs; repeated occurrences do not count.")

    def _correlation_strength(self, members: list[AlertClusterMembership]) -> dict:
        score = max((member.score for member in members), default=0)
        points = 10 if score >= 100 else 8 if score >= 80 else 6 if score >= 60 else 4 if score >= 45 else 0
        return self._entry("correlation_strength", points, f"Maximum deterministic correlation score is {score}.", [{"membership_id": str(member.id), "score": member.score} for member in members if member.score == score])

    def _sequence(self, alerts: list[CanonicalAlert]) -> dict:
        ordered = sorted(alerts, key=lambda alert: (alert.observed_at, str(alert.id)))
        categories = [alert.category for alert in ordered]
        auth_pair = self._ordered(categories, "authentication_failed", "authentication_success")
        execution_after = self._after(categories, "authentication_success", {"process_execution", "suspicious_activity"})
        outbound_pair = self._ordered(categories, "process_execution", "outbound_connection")
        if auth_pair and execution_after:
            return self._entry("behavior_sequence", 10, "Deterministic sequence: authentication failure → success → execution/activity.")
        if outbound_pair:
            return self._entry("behavior_sequence", 8, "Deterministic sequence: process execution → outbound connection.")
        return self._entry("behavior_sequence", 0, "Unavailable: no approved deterministic behavioral sequence.")

    @staticmethod
    def _ordered(categories: list[str | None], first: str, second: str) -> bool:
        try:
            return categories.index(first) < categories.index(second)
        except ValueError:
            return False

    @staticmethod
    def _after(categories: list[str | None], first: str, later: set[str]) -> bool:
        try:
            index = categories.index(first)
        except ValueError:
            return False
        return any(category in later for category in categories[index + 1:])

    def _trusted_ioc(self, org_id: UUID, alerts: list[CanonicalAlert]) -> dict:
        observables: set[tuple[str, str]] = set()
        for alert in alerts:
            for field in ("source_ip", "destination_ip"):
                if value := alert.normalized_observables.get(field): observables.add(("ip", value))
            for field, ioc_type in (("domain", "domain"), ("url", "url")):
                if value := alert.normalized_observables.get(field): observables.add((ioc_type, value))
        iocs = [ioc for ioc in self.db.scalars(select(IOC).where(IOC.org_id == org_id)) if (ioc.type.value, ioc.value) in observables]
        trusted = [ioc for ioc in iocs if ioc.is_watched or (ioc.verdict == "malicious" and ioc.provenance == "internal")]
        if not trusted:
            return self._entry("trusted_ioc_context", 0, "Unavailable: no matching analyst-curated watchlist or internal malicious IOC.")
        points = 10 if any(ioc.is_watched for ioc in trusted) else 8
        return self._entry("trusted_ioc_context", points, "Matching trusted IOC context exists.", [{"ioc_id": str(ioc.id), "type": ioc.type.value, "value": ioc.value, "watched": ioc.is_watched, "verdict": ioc.verdict, "provenance": ioc.provenance} for ioc in trusted])

    def _recency(self, cluster: AlertCluster, reference_at: datetime) -> dict:
        age = reference_at - cluster.last_seen
        if age < timedelta(0):
            raise ValidationError("Scoring reference timestamp cannot precede the cluster's last seen time.")
        points = 5 if age <= timedelta(hours=1) else 3 if age <= timedelta(hours=24) else 1 if age <= timedelta(days=7) else 0
        return self._entry("recency", points, f"Reference timestamp is {int(age.total_seconds())} seconds after cluster last_seen.", [{"cluster_id": str(cluster.id), "last_seen": cluster.last_seen.isoformat(), "reference_at": reference_at.isoformat()}])

    @staticmethod
    def _input_snapshot(cluster: AlertCluster, alerts: list[CanonicalAlert], members: list[AlertClusterMembership], ledger: list[dict], reference_at: datetime) -> dict:
        return {
            "cluster_id": str(cluster.id), "version": SCORING_VERSION, "reference_at": reference_at.isoformat(),
            "alerts": [{"id": str(alert.id), "severity": alert.severity, "category": alert.category, "observed_at": alert.observed_at.isoformat(), "observables": alert.normalized_observables} for alert in sorted(alerts, key=lambda item: str(item.id))],
            "memberships": [{"id": str(member.id), "score": member.score, "cluster_id": str(member.cluster_id)} for member in sorted(members, key=lambda item: str(item.id))],
            "ledger": ledger,
        }

    def _root_cluster(self, org_id: UUID, cluster_id: UUID) -> AlertCluster:
        cluster = self.db.scalar(select(AlertCluster).where(AlertCluster.org_id == org_id, AlertCluster.id == cluster_id))
        if cluster is None:
            raise NotFoundError("Alert cluster not found.")
        return AlertCorrelationService(self.db)._root_cluster(org_id, cluster.id)

    def _lineage_for_cluster(self, org_id: UUID, cluster: AlertCluster) -> set[UUID]:
        clusters = {row.id: row for row in self.db.scalars(select(AlertCluster).where(AlertCluster.org_id == org_id))}
        return {row.id for row in clusters.values() if AlertCorrelationService._root_from_map(clusters, row.id).id == cluster.id}

    def _members_for_cluster_version(
        self,
        org_id: UUID,
        cluster: AlertCluster,
        lineage: set[UUID] | None = None,
    ) -> list[AlertClusterMembership]:
        """Read exactly this cluster's persisted correlation-version history.

        V1 merge lineage remains supported, while v2 reads only v2 memberships.
        This is a read-boundary compatibility fix; scoring inputs and rules stay
        unchanged.
        """
        lineage = self._lineage_for_cluster(org_id, cluster) if lineage is None else lineage
        return list(self.db.scalars(select(AlertClusterMembership).where(
            AlertClusterMembership.org_id == org_id, AlertClusterMembership.cluster_id.in_(lineage),
            AlertClusterMembership.correlation_version == cluster.correlation_version,
        ).order_by(AlertClusterMembership.added_at, AlertClusterMembership.id)))

    def _materialize_assessment_inputs(
        self,
        org_id: UUID,
        cluster: AlertCluster,
    ) -> tuple[list[AlertClusterMembership], list[CanonicalAlert]]:
        """Bulk-read the persisted, version-scoped inputs for one assessment.

        The membership query retains the certified lineage and ordering rules.
        One same-organization alert query replaces the prior one lookup per
        membership; the returned list is rebuilt in membership order so ledger
        ordering and all score tie-breakers remain unchanged.
        """
        if cluster.correlation_version not in {CORRELATION_VERSION, CORRELATION_V2_VERSION}:
            raise ValidationError("Unsupported correlation version.")
        lineage = self._lineage_for_cluster(org_id, cluster)
        members = self._members_for_cluster_version(org_id, cluster, lineage)
        alert_ids = {member.alert_id for member in members}
        if not alert_ids:
            return members, []
        fetched = list(self.db.scalars(select(CanonicalAlert).where(
            CanonicalAlert.org_id == org_id,
            CanonicalAlert.id.in_(alert_ids),
        )))
        alerts_by_id = {alert.id: alert for alert in fetched}
        for member in members:
            if (
                member.org_id != org_id
                or member.cluster_id not in lineage
                or member.correlation_version != cluster.correlation_version
            ):
                raise NotFoundError("Correlation membership is unavailable.")
            if member.alert_id not in alerts_by_id:
                raise NotFoundError("Canonical alert not found.")
        return members, [alerts_by_id[member.alert_id] for member in members]

    def _alert(self, org_id: UUID, alert_id: UUID) -> CanonicalAlert:
        alert = self.db.scalar(select(CanonicalAlert).where(CanonicalAlert.org_id == org_id, CanonicalAlert.id == alert_id))
        if alert is None:
            raise NotFoundError("Canonical alert not found.")
        return alert

    @staticmethod
    def _read(row: AlertClusterAssessment) -> ClusterAssessmentRead:
        return ClusterAssessmentRead(id=row.id, cluster_id=row.cluster_id, score=row.score, priority=row.priority, scoring_version=row.scoring_version, ledger=row.ledger, reference_at=row.reference_at, evaluated_at=row.evaluated_at)
