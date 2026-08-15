"""Persisted, bounded alert-triage projections; never recomputes Phase 7 state."""
from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.modules.alert_triage.domain.correlation_service import CORRELATION_VERSION
from app.modules.alert_triage.domain.correlation_v2_service import CORRELATION_V2_VERSION
from app.modules.alert_triage.infrastructure.models import (
    AlertCluster, AlertClusterAssessment, AlertClusterMembership,
    AlertClusterPromotion, AlertDeduplicationDecision, CanonicalAlert,
    CanonicalAlertOccurrence,
)
from app.shared.exceptions import NotFoundError


_SAFE_TEXT = re.compile(r"^[A-Za-z0-9._:-]{1,255}$")
_SAFE_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}


class AlertClusterTriageReadService:
    def __init__(self, db: Session):
        self.db = db

    def list(self, org_id: UUID, limit: int, offset: int) -> list[dict]:
        rows = self.db.scalars(select(AlertCluster).where(AlertCluster.org_id == org_id).order_by(
            desc(AlertCluster.updated_at), desc(AlertCluster.id),
        ).limit(limit).offset(offset)).all()
        return [self._project(org_id, row, member_limit=1) for row in rows]

    def get(self, org_id: UUID, cluster_id: UUID) -> dict:
        row = self.db.scalar(select(AlertCluster).where(AlertCluster.org_id == org_id, AlertCluster.id == cluster_id))
        if row is None:
            raise NotFoundError("Alert cluster not found.")
        return self._project(org_id, row, member_limit=50)

    def _project(self, org_id: UUID, cluster: AlertCluster, member_limit: int) -> dict:
        assessment = self.db.scalar(select(AlertClusterAssessment).where(
            AlertClusterAssessment.org_id == org_id, AlertClusterAssessment.cluster_id == cluster.id,
        ).order_by(desc(AlertClusterAssessment.evaluated_at), desc(AlertClusterAssessment.id)))
        promotion = self.db.scalar(select(AlertClusterPromotion).where(
            AlertClusterPromotion.org_id == org_id, AlertClusterPromotion.cluster_id == cluster.id,
        ))
        members = self.db.scalars(select(AlertClusterMembership).where(
            AlertClusterMembership.org_id == org_id,
            AlertClusterMembership.cluster_id == cluster.id,
            AlertClusterMembership.correlation_version == cluster.correlation_version,
        ).order_by(AlertClusterMembership.added_at, AlertClusterMembership.id).limit(member_limit)).all()
        eligible, reason = self._eligibility(cluster, assessment, promotion)
        return {
            "id": str(cluster.id), "correlation_version": cluster.correlation_version, "status": cluster.status,
            "created_at": cluster.created_at.isoformat(), "updated_at": cluster.updated_at.isoformat(),
            "member_count": cluster.member_count,
            "members": [self._member(org_id, member) for member in members],
            "triage": None if assessment is None else {
                "id": str(assessment.id), "priority": assessment.priority, "score": assessment.score,
                "version": assessment.scoring_version,
            },
            "promotion": None if promotion is None else {
                "id": str(promotion.id), "status": promotion.status, "investigation_id": str(promotion.investigation_id),
            },
            "promotion_eligible": eligible, "promotion_reason": reason,
        }

    def _member(self, org_id: UUID, member: AlertClusterMembership) -> dict:
        alert = self.db.scalar(select(CanonicalAlert).where(
            CanonicalAlert.org_id == org_id, CanonicalAlert.id == member.alert_id,
        ))
        # A foreign/missing alert is never projected; the persisted membership
        # remains untouched and no correlation fallback is attempted.
        if alert is None:
            return {"id": str(member.id), "score": member.score, "reason_codes": self._reason_codes(member.reasons),
                    "added_at": member.added_at.isoformat(), "unavailable": True}
        duplicate = self.db.scalar(select(AlertDeduplicationDecision.id).where(
            AlertDeduplicationDecision.org_id == org_id,
            AlertDeduplicationDecision.decision_type == "SEMANTIC",
            or_(AlertDeduplicationDecision.representative_alert_id == alert.id,
                AlertDeduplicationDecision.duplicate_alert_id == alert.id),
        )) is not None
        occurrence_count = self.db.scalar(select(func.count()).select_from(CanonicalAlertOccurrence).where(
            CanonicalAlertOccurrence.org_id == org_id,
            CanonicalAlertOccurrence.canonical_alert_id == alert.id,
        )) or 0
        observables = alert.normalized_observables if isinstance(alert.normalized_observables, dict) else {}
        return {
            "id": str(member.id), "score": member.score, "reason_codes": self._reason_codes(member.reasons),
            "added_at": member.added_at.isoformat(), "source": self._safe(alert.source),
            "detection_label": self._detection_label(alert.source, alert.rule_id),
            "rule_id": self._safe(alert.rule_id), "category": self._safe(alert.category),
            "severity": alert.severity if alert.severity in _SAFE_SEVERITIES else None,
            "observed_at": alert.observed_at.isoformat(),
            "hostname": self._safe(observables.get("hostname")),
            "agent_identity": self._safe(observables.get("agent_name") or observables.get("agent_id")),
            "semantic_duplicate": duplicate, "occurrence_count": int(occurrence_count),
        }

    @staticmethod
    def _safe(value: object) -> str | None:
        return value if isinstance(value, str) and _SAFE_TEXT.fullmatch(value) else None

    @classmethod
    def _detection_label(cls, source: object, rule_id: object) -> str:
        safe_rule = cls._safe(rule_id)
        if safe_rule is None:
            return "Persisted detection"
        return f"Wazuh rule {safe_rule}" if source == "wazuh" else f"Rule {safe_rule}"

    @staticmethod
    def _reason_codes(reasons: object) -> list[str]:
        if not isinstance(reasons, list):
            return []
        return [item["code"] for item in reasons if isinstance(item, dict)
                and isinstance(item.get("code"), str) and _SAFE_TEXT.fullmatch(item["code"])][:12]

    @staticmethod
    def _eligibility(cluster, assessment, promotion):
        if promotion is not None:
            return False, "ALREADY_PROMOTED"
        if cluster.correlation_version not in {CORRELATION_VERSION, CORRELATION_V2_VERSION}:
            return False, "CORRELATION_VERSION_UNSUPPORTED"
        if cluster.status != "OPEN":
            return False, "CLUSTER_NOT_OPEN"
        if assessment is None or assessment.cluster_id != cluster.id:
            return False, "TRIAGE_REQUIRED"
        return True, "ELIGIBLE"
