"""Deterministic, read-only Phase 8 activity reconstruction."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.alert_triage.infrastructure.models import AlertCluster, AlertClusterMembership, AlertClusterPromotion, CanonicalAlert
from app.modules.evidence.infrastructure.models import EntityObservation, EntityRelationship, Event, EvidenceItem, IndicatorOccurrence
from app.shared.exceptions import NotFoundError, ValidationError

POLICY_ID = "activity-window-v1"


@dataclass(frozen=True)
class ActivityWindowPolicy:
    before_minutes: int = 30
    after_minutes: int = 60
    future_skew_minutes: int = 5
    receipt_skew_minutes: int = 15
    max_activities: int = 200
    def __post_init__(self):
        if min(self.before_minutes, self.after_minutes, self.future_skew_minutes, self.receipt_skew_minutes, self.max_activities) <= 0 or self.max_activities > 1000:
            raise ValidationError("Activity-window policy bounds are unsafe.")


def _utc(value):
    if value is None: return None, "SOURCE_TIME_MISSING"
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None: return None, "SOURCE_TIME_INVALID"
    return value.astimezone(timezone.utc), None


def project(policy: ActivityWindowPolicy, activities: list[dict], anchor_start: datetime | None, anchor_end: datetime | None, evaluation_time: datetime | None = None) -> dict:
    """Pure projection. Inputs must be persisted timestamps; no wall clock is consulted."""
    anchor_start, anchor_error = _utc(anchor_start); anchor_end, _ = _utc(anchor_end)
    if anchor_start is None or anchor_end is None:
        return {"policy_id": POLICY_ID, "anchor": None, "activities": [], "omitted": 0, "warnings": ["ANCHOR_MISSING"]}
    evaluation, _ = _utc(evaluation_time) if evaluation_time else (None, None)
    before, after = anchor_start - timedelta(minutes=policy.before_minutes), anchor_end + timedelta(minutes=policy.after_minutes)
    rows = []
    for item in activities:
        source, source_error = _utc(item.get("source_time")); receipt, _ = _utc(item.get("receipt_time")); codes = []
        effective, basis = source, "SOURCE"
        if source_error:
            codes.append(source_error); effective, basis = receipt, "RECEIPT"
            if receipt is not None: codes.append("RECEIPT_TIME_FALLBACK")
        if source and receipt and abs(source - receipt) > timedelta(minutes=policy.receipt_skew_minutes):
            codes.extend(("CLOCK_SKEW_SUSPECTED", "CONFLICTING_SENSOR_TIME"))
            if source < receipt: codes.append("OUT_OF_ORDER_ARRIVAL")
        if source and evaluation and source > evaluation + timedelta(minutes=policy.future_skew_minutes):
            codes.append("FUTURE_TIME_SUSPECTED")
            if receipt is not None: effective, basis = receipt, "RECEIPT"; codes.append("RECEIPT_TIME_FALLBACK")
        if effective is None: position = "UNKNOWN"
        elif effective < before: position = "BEFORE"
        elif effective > after: position = "AFTER"
        elif anchor_start <= effective <= anchor_end: position = "ANCHOR"
        else: position = "BEFORE" if effective < anchor_start else "AFTER"
        inside = effective is not None and before <= effective <= after
        if effective is not None and not inside: codes.append("OUTSIDE_WINDOW"); position = "OUTSIDE"
        rows.append({"type": item["type"], "id": str(item["id"]), "alias": item.get("alias"), "original_timestamp": item.get("source_time").isoformat() if isinstance(item.get("source_time"), datetime) else None, "effective_timestamp": effective.isoformat() if effective else None, "time_basis": basis if effective else "NONE", "normalization": "UTC" if effective else "UNAVAILABLE", "uncertainty": sorted(set(codes)), "position": position, "_time": effective, "_inside": inside})
    rows.sort(key=lambda row: (row["_time"] is None, row["_time"] or datetime.max.replace(tzinfo=timezone.utc), row["type"], row["id"]))
    for index, row in enumerate(rows):
        if index and row["_time"] is not None and row["_time"] == rows[index - 1]["_time"]: row["uncertainty"].append("EQUAL_TIMESTAMP_TIE")
    selected = [row for row in rows if row["_inside"]]
    outside = [row for row in rows if not row["_inside"]]
    omitted = max(0, len(selected) - policy.max_activities)
    for row in selected[policy.max_activities:]: row["uncertainty"].append("OMITTED_BY_POLICY_LIMIT")
    output = selected[:policy.max_activities] + outside
    if not any(row["position"] == "BEFORE" for row in output): warning_before = "BEFORE_ACTIVITY_NOT_OBSERVED"
    else: warning_before = None
    if not any(row["position"] == "AFTER" for row in output): warning_after = "AFTER_ACTIVITY_NOT_OBSERVED"
    else: warning_after = None
    for row in output: row.pop("_time"); row.pop("_inside")
    return {"policy_id": POLICY_ID, "anchor": {"start": anchor_start.isoformat(), "end": anchor_end.isoformat()}, "activities": output, "omitted": omitted, "warnings": [x for x in (warning_before, warning_after) if x]}


class ActivityWindowReader:
    def __init__(self, db: Session, policy: ActivityWindowPolicy = ActivityWindowPolicy()): self.db, self.policy = db, policy
    def reconstruct(self, org_id: UUID, investigation_id: UUID, evaluation_time: datetime | None = None) -> dict:
        promotion = self.db.scalar(select(AlertClusterPromotion).where(AlertClusterPromotion.org_id == org_id, AlertClusterPromotion.investigation_id == investigation_id))
        items, start, end = [], None, None
        if promotion:
            cluster = self.db.get(AlertCluster, promotion.cluster_id)
            if cluster and cluster.org_id == org_id:
                members = list(self.db.scalars(select(AlertClusterMembership).where(AlertClusterMembership.org_id == org_id, AlertClusterMembership.cluster_id == cluster.id, AlertClusterMembership.correlation_version == cluster.correlation_version)))
                alerts = [self.db.get(CanonicalAlert, member.alert_id) for member in members]
                alerts = [alert for alert in alerts if alert and alert.org_id == org_id]
                times = [alert.observed_at for alert in alerts if _utc(alert.observed_at)[0]]
                if times: start, end = min(times), max(times)
                items.extend({"type": "CANONICAL_ALERT", "id": alert.id, "source_time": alert.observed_at, "receipt_time": alert.ingested_at} for alert in alerts)
        events = list(self.db.scalars(select(Event).where(Event.org_id == org_id, Event.investigation_id == investigation_id)))
        if start is None:
            times = [event.timestamp for event in events if _utc(event.timestamp)[0]]
            if times: start = end = min(times)
        evidence = {row.id: row for row in self.db.scalars(select(EvidenceItem).where(EvidenceItem.org_id == org_id, EvidenceItem.investigation_id == investigation_id))}
        items.extend({"type": "EVIDENCE_ITEM", "id": row.id, "source_time": None, "receipt_time": row.imported_at} for row in evidence.values())
        items.extend({"type": "EVENT", "id": event.id, "source_time": event.timestamp, "receipt_time": evidence.get(event.evidence_id).imported_at if event.evidence_id in evidence else None} for event in events)
        for model, name in ((EntityObservation, "ENTITY_OBSERVATION"), (IndicatorOccurrence, "INDICATOR_OCCURRENCE"), (EntityRelationship, "ENTITY_RELATIONSHIP")):
            for row in self.db.scalars(select(model).where(model.org_id == org_id, model.investigation_id == investigation_id)):
                items.append({"type": name, "id": row.id, "source_time": getattr(row, "observed_at", None), "receipt_time": row.created_at})
        if start is None:
            receipts = [item["receipt_time"] for item in items if _utc(item.get("receipt_time"))[0]]
            if receipts: start = end = min(receipts)
        return project(self.policy, items, start, end, evaluation_time)
