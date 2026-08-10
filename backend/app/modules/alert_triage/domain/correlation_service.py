"""Phase 7.3 deterministic correlation and cluster assembly; no AI or promotion."""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.alert_triage.infrastructure.models import (
    AlertCluster, AlertClusterMembership, AlertClusterMerge, AlertDeduplicationDecision, CanonicalAlert,
)
from app.shared.exceptions import NotFoundError, ValidationError


CORRELATION_VERSION = "correlation-v1"
CORRELATION_WINDOW = timedelta(seconds=180)
STRONG_FIELDS = {"hostname": 40, "domain": 40, "url": 40, "file": 40}
WEAK_FIELDS = {"username": 15, "process": 15}


@dataclass(frozen=True)
class CorrelationMatch:
    score: int
    reasons: list[dict]


@dataclass(frozen=True)
class AlertClusterRead:
    id: UUID
    identity_key: str
    status: str
    correlation_version: str
    first_seen: datetime
    last_seen: datetime
    member_count: int
    source_diversity: int
    merged_into_cluster_id: UUID | None


class AlertCorrelationService:
    """Groups only distinct, non-semantic-duplicate CanonicalAlerts."""

    def __init__(self, db: Session):
        self.db = db

    def process(self, org_id: UUID, alert_id: UUID) -> AlertClusterRead | None:
        alert = self._alert(org_id, alert_id)
        if self._is_semantic_duplicate(org_id, alert.id):
            return None
        membership = self.db.scalar(select(AlertClusterMembership).where(
            AlertClusterMembership.org_id == org_id, AlertClusterMembership.alert_id == alert.id,
            AlertClusterMembership.correlation_version == CORRELATION_VERSION,
        ))
        if membership is not None:
            return self._read(self._root_cluster(org_id, membership.cluster_id))

        roots, best_matches = self._matching_roots(org_id, alert)
        now = datetime.now(timezone.utc)
        if not roots:
            cluster = AlertCluster(
                org_id=org_id, identity_key=f"{CORRELATION_VERSION}:alert:{alert.id}", correlation_version=CORRELATION_VERSION,
                status="OPEN", first_seen=alert.observed_at, last_seen=alert.observed_at, member_count=0, source_diversity=0,
            )
            self.db.add(cluster)
            self.db.flush()
            self.db.add(AlertClusterMembership(
                org_id=org_id, cluster_id=cluster.id, alert_id=alert.id, candidate_alert_id=None,
                correlation_version=CORRELATION_VERSION, score=0, reasons=[{"code": "INITIAL_CLUSTER"}], added_at=now,
            ))
            self.db.flush()
            self._refresh_metrics(cluster.id)
            self.db.commit()
            return self._read(cluster)

        survivor = min(roots, key=lambda item: item.identity_key)
        candidate, match = best_matches[survivor.id]
        self.db.add(AlertClusterMembership(
            org_id=org_id, cluster_id=survivor.id, alert_id=alert.id, candidate_alert_id=candidate.id,
            correlation_version=CORRELATION_VERSION, score=match.score, reasons=match.reasons, added_at=now,
        ))
        for cluster in roots:
            if cluster.id == survivor.id:
                continue
            merge_candidate, merge_match = best_matches[cluster.id]
            cluster.status = "CLOSED"
            cluster.merged_into_cluster_id = survivor.id
            self.db.add(AlertClusterMerge(
                org_id=org_id, survivor_cluster_id=survivor.id, absorbed_cluster_id=cluster.id,
                trigger_alert_id=alert.id, correlation_version=CORRELATION_VERSION,
                reasons=[{"code": "MERGED_BY_TRIGGER_ALERT", "candidate_alert_id": str(merge_candidate.id), "score": merge_match.score, "signals": merge_match.reasons}], merged_at=now,
            ))
        self.db.flush()
        self._refresh_metrics(survivor.id)
        self.db.commit()
        return self._read(survivor)

    def list_clusters(self, org_id: UUID, include_closed: bool = False) -> list[AlertClusterRead]:
        stmt = select(AlertCluster).where(AlertCluster.org_id == org_id)
        if not include_closed:
            stmt = stmt.where(AlertCluster.status == "OPEN")
        return [self._read(cluster) for cluster in self.db.scalars(stmt.order_by(AlertCluster.first_seen, AlertCluster.identity_key))]

    def get_cluster(self, org_id: UUID, cluster_id: UUID) -> AlertClusterRead:
        return self._read(self._cluster(org_id, cluster_id))

    def list_members(self, org_id: UUID, cluster_id: UUID) -> list[AlertClusterMembership]:
        root = self._root_cluster(org_id, cluster_id)
        lineage = {cluster.id for cluster in self.db.scalars(select(AlertCluster).where(AlertCluster.org_id == org_id)) if self._root_cluster(org_id, cluster.id).id == root.id}
        return list(self.db.scalars(select(AlertClusterMembership).where(
            AlertClusterMembership.org_id == org_id, AlertClusterMembership.cluster_id.in_(lineage),
            AlertClusterMembership.correlation_version == CORRELATION_VERSION,
        ).order_by(AlertClusterMembership.added_at, AlertClusterMembership.id)))

    def _matching_roots(self, org_id: UUID, alert: CanonicalAlert) -> tuple[list[AlertCluster], dict[UUID, tuple[CanonicalAlert, CorrelationMatch]]]:
        clusters = {cluster.id: cluster for cluster in self.db.scalars(select(AlertCluster).where(AlertCluster.org_id == org_id))}
        memberships = list(self.db.scalars(select(AlertClusterMembership).where(AlertClusterMembership.org_id == org_id, AlertClusterMembership.correlation_version == CORRELATION_VERSION)))
        alerts = {candidate.id: candidate for candidate in self.db.scalars(select(CanonicalAlert).where(CanonicalAlert.org_id == org_id, CanonicalAlert.id != alert.id))}
        matches: dict[UUID, tuple[CanonicalAlert, CorrelationMatch]] = {}
        for membership in memberships:
            candidate = alerts.get(membership.alert_id)
            if candidate is None or self._is_semantic_duplicate(org_id, candidate.id):
                continue
            root = self._root_from_map(clusters, membership.cluster_id)
            if root.status != "OPEN":
                continue
            result = self._correlate(alert, candidate)
            if result is None:
                continue
            existing = matches.get(root.id)
            if existing is None or (-result.score, candidate.observed_at, str(candidate.id)) < (-existing[1].score, existing[0].observed_at, str(existing[0].id)):
                matches[root.id] = (candidate, result)
        roots = sorted((clusters[root_id] for root_id in matches), key=lambda item: item.identity_key)
        return roots, matches

    def _correlate(self, alert: CanonicalAlert, candidate: CanonicalAlert) -> CorrelationMatch | None:
        seconds = abs((alert.observed_at - candidate.observed_at).total_seconds())
        if seconds > CORRELATION_WINDOW.total_seconds():
            return None
        shared: list[dict] = []
        score = 20
        direct_strong = 0
        ip_strong = 0
        weak = 0
        for field, points in STRONG_FIELDS.items():
            if self._same(alert, candidate, field):
                shared.append({"code": "SAME_OBSERVABLE", "field": field, "value": alert.normalized_observables[field], "points": points})
                score += points; direct_strong += 1
        for field in ("source_ip", "destination_ip"):
            if self._same(alert, candidate, field) and self._public_ip(alert.normalized_observables[field]):
                shared.append({"code": "SAME_PUBLIC_IP", "field": field, "value": alert.normalized_observables[field], "points": 30})
                score += 30; ip_strong += 1
        for field, points in WEAK_FIELDS.items():
            if self._same(alert, candidate, field):
                shared.append({"code": "SAME_WEAK_OBSERVABLE", "field": field, "value": alert.normalized_observables[field], "points": points})
                score += points; weak += 1
        if alert.category and alert.category == candidate.category:
            shared.append({"code": "SAME_CATEGORY", "value": alert.category, "points": 5}); score += 5
        if self._shared_mitre(alert, candidate):
            shared.append({"code": "SAME_SOURCE_MITRE", "points": 5}); score += 5
        shared.append({"code": "WITHIN_OBSERVED_TIME_WINDOW", "seconds": seconds, "window_seconds": int(CORRELATION_WINDOW.total_seconds()), "points": 20})
        # A lone shared IP is deliberately insufficient: NAT, gateways, and scanners are common.
        # A non-IP strong observable or both public source/destination IPs may satisfy the strong path.
        if not (((direct_strong >= 1 or ip_strong >= 2) and score >= 50) or (weak >= 2 and score >= 45)):
            return None
        return CorrelationMatch(score=score, reasons=shared)

    @staticmethod
    def _same(left: CanonicalAlert, right: CanonicalAlert, field: str) -> bool:
        value = left.normalized_observables.get(field)
        return bool(value) and value == right.normalized_observables.get(field)

    @staticmethod
    def _public_ip(value: str) -> bool:
        parsed = ipaddress.ip_address(value)
        return not (parsed.is_private or parsed.is_loopback or parsed.is_link_local or parsed.is_multicast or parsed.is_reserved or parsed.is_unspecified)

    @staticmethod
    def _shared_mitre(left: CanonicalAlert, right: CanonicalAlert) -> bool:
        def values(alert: CanonicalAlert) -> set[str]:
            raw = alert.source_metadata.get("mitre_techniques", [])
            return {item for item in raw if isinstance(item, str)} if isinstance(raw, list) else set()
        return bool(values(left) & values(right))

    def _is_semantic_duplicate(self, org_id: UUID, alert_id: UUID) -> bool:
        return self.db.scalar(select(AlertDeduplicationDecision.id).where(
            AlertDeduplicationDecision.org_id == org_id, AlertDeduplicationDecision.duplicate_alert_id == alert_id,
            AlertDeduplicationDecision.decision_type == "SEMANTIC",
        )) is not None

    def _refresh_metrics(self, cluster_id: UUID) -> None:
        cluster = self._cluster_by_id(cluster_id)
        members = self.list_members(cluster.org_id, cluster.id)
        alerts = [self._alert(cluster.org_id, member.alert_id) for member in members]
        cluster.member_count = len(alerts)
        cluster.first_seen = min(alert.observed_at for alert in alerts)
        cluster.last_seen = max(alert.observed_at for alert in alerts)
        cluster.source_diversity = len({(alert.connector_id, alert.source) for alert in alerts})

    def _root_cluster(self, org_id: UUID, cluster_id: UUID) -> AlertCluster:
        clusters = {cluster.id: cluster for cluster in self.db.scalars(select(AlertCluster).where(AlertCluster.org_id == org_id))}
        return self._root_from_map(clusters, cluster_id)

    @staticmethod
    def _root_from_map(clusters: dict[UUID, AlertCluster], cluster_id: UUID) -> AlertCluster:
        current = clusters.get(cluster_id)
        if current is None:
            raise NotFoundError("Alert cluster not found.")
        seen: set[UUID] = set()
        while current.merged_into_cluster_id is not None:
            if current.id in seen:
                raise ValidationError("Invalid alert cluster merge lineage.")
            seen.add(current.id)
            current = clusters.get(current.merged_into_cluster_id)
            if current is None:
                raise ValidationError("Invalid alert cluster merge reference.")
        return current

    def _cluster(self, org_id: UUID, cluster_id: UUID) -> AlertCluster:
        cluster = self.db.scalar(select(AlertCluster).where(AlertCluster.org_id == org_id, AlertCluster.id == cluster_id))
        if cluster is None:
            raise NotFoundError("Alert cluster not found.")
        return cluster

    def _cluster_by_id(self, cluster_id: UUID) -> AlertCluster:
        cluster = self.db.get(AlertCluster, cluster_id)
        if cluster is None:
            raise NotFoundError("Alert cluster not found.")
        return cluster

    def _alert(self, org_id: UUID, alert_id: UUID) -> CanonicalAlert:
        alert = self.db.scalar(select(CanonicalAlert).where(CanonicalAlert.org_id == org_id, CanonicalAlert.id == alert_id))
        if alert is None:
            raise NotFoundError("Canonical alert not found.")
        return alert

    @staticmethod
    def _read(cluster: AlertCluster) -> AlertClusterRead:
        return AlertClusterRead(
            id=cluster.id, identity_key=cluster.identity_key, status=cluster.status, correlation_version=cluster.correlation_version,
            first_seen=cluster.first_seen, last_seen=cluster.last_seen, member_count=cluster.member_count,
            source_diversity=cluster.source_diversity, merged_into_cluster_id=cluster.merged_into_cluster_id,
        )
