"""Conservative deterministic correlation-v2; v1 remains untouched."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.alert_triage.infrastructure.models import (
    AlertCluster,
    AlertClusterMembership,
    AlertDeduplicationDecision,
    CanonicalAlert,
)
from app.shared.exceptions import NotFoundError


CORRELATION_V2_VERSION = "correlation-v2"
WINDOW = timedelta(seconds=180)


class AlertCorrelationV2Service:
    def __init__(self, db: Session):
        self.db = db

    def process(self, org: UUID, alert_id: UUID):
        alert = self._alert(org, alert_id)
        if self.db.scalar(select(AlertDeduplicationDecision.id).where(
            AlertDeduplicationDecision.org_id == org,
            AlertDeduplicationDecision.duplicate_alert_id == alert.id,
            AlertDeduplicationDecision.decision_type == "SEMANTIC",
        )):
            return None
        old = self.db.scalar(select(AlertClusterMembership).where(
            AlertClusterMembership.org_id == org,
            AlertClusterMembership.alert_id == alert.id,
            AlertClusterMembership.correlation_version == CORRELATION_V2_VERSION,
        ))
        if old:
            return self.db.get(AlertCluster, old.cluster_id)

        roots = list(self.db.scalars(select(AlertCluster).where(
            AlertCluster.org_id == org,
            AlertCluster.correlation_version == CORRELATION_V2_VERSION,
            AlertCluster.status == "OPEN",
        )))
        candidate_members, candidate_alerts = self._candidate_read_maps(org, roots)
        candidates = []
        for cluster in roots:
            members = candidate_members.get(cluster.id, [])
            alerts = [candidate_alerts[member.alert_id] for member in members]
            if not alerts:
                # Open clusters created by this service always contain their
                # first membership. Do not silently invent a candidate from an
                # inconsistent persisted row.
                raise NotFoundError("Correlation membership is unavailable.")
            representative = min(alerts, key=lambda item: (item.observed_at, str(item.id)))
            ledger = self._decision(alert, representative)
            compatible = [self._decision(alert, item) for item in alerts]
            if ledger["merge"] and sum(item["merge"] for item in compatible) * 2 >= len(compatible):
                candidates.append((cluster, ledger))

        if not candidates:
            cluster = AlertCluster(
                org_id=org,
                identity_key=f"{CORRELATION_V2_VERSION}:alert:{alert.id}",
                correlation_version=CORRELATION_V2_VERSION,
                status="OPEN",
                first_seen=alert.observed_at,
                last_seen=alert.observed_at,
                member_count=0,
                source_diversity=0,
            )
            self.db.add(cluster)
            self.db.flush()
            ledger = {
                "version": CORRELATION_V2_VERSION,
                "score": 0,
                "positive": [],
                "discriminators": [],
                "merge": False,
                "code": "INITIAL_CLUSTER",
            }
        else:
            cluster, ledger = min(candidates, key=lambda item: item[0].identity_key)

        self.db.add(AlertClusterMembership(
            org_id=org,
            cluster_id=cluster.id,
            alert_id=alert.id,
            candidate_alert_id=None,
            correlation_version=CORRELATION_V2_VERSION,
            score=ledger["score"],
            reasons=[ledger],
            added_at=datetime.now(timezone.utc),
        ))
        self.db.flush()
        members = list(self.db.scalars(select(AlertClusterMembership).where(
            AlertClusterMembership.cluster_id == cluster.id,
            AlertClusterMembership.correlation_version == CORRELATION_V2_VERSION,
        )))
        alerts = [self._alert(org, member.alert_id) for member in members]
        cluster.member_count = len(alerts)
        cluster.first_seen = min(item.observed_at for item in alerts)
        cluster.last_seen = max(item.observed_at for item in alerts)
        cluster.source_diversity = len({(item.connector_id, item.source) for item in alerts})
        self.db.commit()
        return cluster

    def _candidate_read_maps(
        self,
        org: UUID,
        roots: list[AlertCluster],
    ) -> tuple[dict[UUID, list[AlertClusterMembership]], dict[UUID, CanonicalAlert]]:
        """Bulk-read the existing candidate boundary without changing decisions.

        ``roots`` already carries the certified OPEN/v2/organization selection.
        The two queries below preserve those predicates, reject inconsistent
        memberships rather than skipping them, and retain each database-returned
        membership traversal order inside its original cluster grouping.
        """
        cluster_ids = [cluster.id for cluster in roots]
        if not cluster_ids:
            return {}, {}
        memberships = list(self.db.scalars(select(AlertClusterMembership).where(
            AlertClusterMembership.org_id == org,
            AlertClusterMembership.cluster_id.in_(cluster_ids),
            AlertClusterMembership.correlation_version == CORRELATION_V2_VERSION,
        ).order_by(
            AlertClusterMembership.cluster_id,
            AlertClusterMembership.added_at,
            AlertClusterMembership.id,
        )))
        root_ids = set(cluster_ids)
        grouped: dict[UUID, list[AlertClusterMembership]] = defaultdict(list)
        for membership in memberships:
            if (
                membership.org_id != org
                or membership.cluster_id not in root_ids
                or membership.correlation_version != CORRELATION_V2_VERSION
            ):
                raise NotFoundError("Correlation membership is unavailable.")
            grouped[membership.cluster_id].append(membership)

        alert_ids = {membership.alert_id for membership in memberships}
        if not alert_ids:
            return dict(grouped), {}
        alerts = list(self.db.scalars(select(CanonicalAlert).where(
            CanonicalAlert.org_id == org,
            CanonicalAlert.id.in_(alert_ids),
        )))
        by_id = {alert.id: alert for alert in alerts}
        for membership in memberships:
            if membership.alert_id not in by_id:
                # This covers an inaccessible cross-org reference and any
                # unavailable row without silently altering the candidate set.
                raise NotFoundError("Canonical alert not found.")
        return dict(grouped), by_id

    def _decision(self, alert: CanonicalAlert, candidate: CanonicalAlert):
        observables = alert.normalized_observables
        prior = candidate.normalized_observables
        positive: list[str] = []
        discriminators: list[str] = []
        score = 0
        if abs((alert.observed_at - candidate.observed_at).total_seconds()) > WINDOW.total_seconds():
            return {
                "version": CORRELATION_V2_VERSION,
                "score": 0,
                "positive": [],
                "discriminators": ["OUTSIDE_WINDOW"],
                "merge": False,
            }
        for key, points, family in (
            ("hostname", 2, "host"),
            ("username", 3, "account"),
            ("process", 3, "process"),
            ("destination_ip", 3, "destination"),
            ("domain", 3, "destination"),
        ):
            if observables.get(key) and observables.get(key) == prior.get(key):
                score += points
                positive.append(family)
        if observables.get("username") and prior.get("username") and observables["username"] != prior["username"]:
            discriminators.append("DIFFERENT_USER")
        if observables.get("process") and prior.get("process") and observables["process"] != prior["process"]:
            discriminators.append("INCOMPATIBLE_PROCESS")
        if (
            observables.get("destination_ip") and prior.get("destination_ip") and observables["destination_ip"] != prior["destination_ip"]
        ) or (
            observables.get("domain") and prior.get("domain") and observables["domain"] != prior["domain"]
        ):
            discriminators.append("DESTINATION_CONFLICT")
        if alert.rule_id and candidate.rule_id and alert.rule_id != candidate.rule_id and not ({"process", "destination"} & set(positive)):
            discriminators.append("INDEPENDENT_RULE_FAMILY")
        score += 1
        positive.append("time")
        return {
            "version": CORRELATION_V2_VERSION,
            "score": score,
            "positive": sorted(set(positive)),
            "discriminators": discriminators,
            "merge": not discriminators and score >= 8 and len(set(positive) - {"time"}) >= 2,
        }

    def _alert(self, org: UUID, alert_id: UUID):
        alert = self.db.scalar(select(CanonicalAlert).where(
            CanonicalAlert.org_id == org,
            CanonicalAlert.id == alert_id,
        ))
        if not alert:
            raise NotFoundError("Canonical alert not found.")
        return alert
