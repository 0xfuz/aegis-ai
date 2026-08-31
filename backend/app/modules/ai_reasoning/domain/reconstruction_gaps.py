"""Deterministic, read-only reconstruction completeness and gap analysis."""
from __future__ import annotations

from dataclasses import dataclass
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.ai_reasoning.domain.activity_window import ActivityWindowReader
from app.modules.ai_reasoning.domain.context_builder import ContextBuilder
from app.modules.alert_triage.infrastructure.models import AlertCluster, AlertClusterAssessment, AlertClusterMembership, AlertClusterPromotion
from app.modules.evidence.infrastructure.models import EvidenceItem, EvidenceParseRun, Event, RawRecord
from app.shared.exceptions import ValidationError

POLICY_ID = "reconstruction-gaps-v1"

@dataclass(frozen=True)
class ReconstructionGapPolicy:
    max_gaps: int = 200
    detail_limit: int = 200
    def __post_init__(self):
        if not 0 < self.max_gaps <= 1000 or not 0 < self.detail_limit <= 512: raise ValidationError("Reconstruction gap policy bounds are unsafe.")

_SECRET = re.compile(r"(?i)(?:password|secret|token|authorization)\s*[:=]\s*\S+")
def _safe(value, limit):
    return _SECRET.sub("[REDACTED]", str(value).replace("\n", " "))[:limit]

def analyze(policy: ReconstructionGapPolicy, context: dict, temporal: dict, provenance: list[dict]) -> dict:
    """Pure projection; callers supply only persisted, already-scoped records."""
    gaps=[]
    def add(code, section, severity, classification, target=None, detail="", refs=()):
        gaps.append({"code": code, "section": section, "target_type": target[0] if target else None, "target_id": str(target[1]) if target else None, "severity": severity, "classification": classification, "detail": _safe(detail, policy.detail_limit), "provenance": sorted(str(ref) for ref in refs)})
    warning_map={
        "PROMOTION_LINK_MISSING": ("PROMOTION_MISSING", "promotion", "WARNING", "ABSENT"),
        "PROMOTION_CLUSTER_LINK_MISSING": ("PROMOTION_CLUSTER_MISSING", "correlation", "BLOCKING", "UNAVAILABLE"),
        "CORRELATION_V1_CONTEXT_UNSUPPORTED": ("CORRELATION_VERSION_UNSUPPORTED", "correlation", "BLOCKING", "UNSUPPORTED"),
        "CORRELATION_VERSION_UNSUPPORTED": ("CORRELATION_VERSION_UNSUPPORTED", "correlation", "BLOCKING", "UNSUPPORTED"),
        "CORRELATION_V2_MEMBERSHIP_MISSING": ("EXACT_VERSION_MEMBERSHIP_MISSING", "correlation", "BLOCKING", "INCOMPLETE"),
        "TRIAGE_LINK_MISSING": ("TRIAGE_PROVENANCE_MISSING", "triage", "WARNING", "INCOMPLETE"),
    }
    for warning in context.get("warnings", []):
        code=warning.get("code") if isinstance(warning, dict) else warning
        if code in warning_map: add(*warning_map[code], detail=code)
    for omission in context.get("omissions", []):
        reason=omission.get("reason")
        if reason in {"LIMIT", "TOTAL_SIZE"}: add("CONTEXT_OMITTED_BY_"+reason, omission.get("section", "context"), "INFO", "OMITTED", detail=f"{reason}:{omission.get('original_count', 0)}")
    for warning in temporal.get("warnings", []):
        if warning == "ANCHOR_MISSING": add("TEMPORAL_ANCHOR_MISSING", "temporal", "WARNING", "ABSENT")
        elif warning in {"BEFORE_ACTIVITY_NOT_OBSERVED", "AFTER_ACTIVITY_NOT_OBSERVED"}: add(warning, "temporal", "INFO", "ABSENT", detail="Not observed is not a statement that activity did not happen.")
    for activity in temporal.get("activities", []):
        uncertainty=set(activity.get("uncertainty", [])); target=(activity.get("type"), activity.get("id"))
        if "SOURCE_TIME_INVALID" in uncertainty: add("EVENT_TIME_INVALID", "temporal", "WARNING", "INVALID", target)
        elif "SOURCE_TIME_MISSING" in uncertainty: add("EVENT_TIME_MISSING", "temporal", "INFO", "UNAVAILABLE", target)
        if uncertainty & {"CLOCK_SKEW_SUSPECTED", "CONFLICTING_SENSOR_TIME", "FUTURE_TIME_SUSPECTED", "OUT_OF_ORDER_ARRIVAL"}: add("EVENT_TIME_UNCERTAIN", "temporal", "WARNING", "CONTRADICTORY", target, refs=(target[1],))
    for item in provenance:
        target=(item["type"], item["id"])
        state=item.get("state")
        if state in {"failed", "rejected"}: add("PARSER_"+state.upper(), "parsing", "WARNING", "UNAVAILABLE", target)
        elif state in {"pending", "parsing", "incomplete"}: add("PARSER_INCOMPLETE", "parsing", "INFO", "INCOMPLETE", target)
        elif state != "complete": add("PARSER_STATE_UNSUPPORTED", "parsing", "WARNING", "UNSUPPORTED", target, state)
        if item.get("raw_unavailable"): add("RAW_CONTENT_UNAVAILABLE", "raw_records", "WARNING", "UNAVAILABLE", target)
        if item.get("locator_unresolved"): add("LOCATOR_UNRESOLVED", "raw_records", "WARNING", "INCOMPLETE", target)
        if item.get("dangling"): add("PROVENANCE_UNRESOLVED", "provenance", "WARNING", "INCOMPLETE", target)
        for other in item.get("contradicts", []): add("EXPLICIT_OBSERVATION_CONTRADICTION", "provenance", "WARNING", "CONTRADICTORY", target, refs=(item["id"], other))
    gaps.sort(key=lambda gap:(gap["severity"] != "BLOCKING", gap["severity"] != "WARNING", gap["section"], gap["code"], gap["target_type"] or "", gap["target_id"] or ""))
    omitted=max(0, len(gaps)-policy.max_gaps)
    return {"policy_id": POLICY_ID, "gaps": gaps[:policy.max_gaps], "omitted": omitted}

class ReconstructionGapReader:
    def __init__(self, db: Session, policy: ReconstructionGapPolicy = ReconstructionGapPolicy(), context_policy=None): self.db, self.policy, self.context_policy=db,policy,context_policy
    def reconstruct(self, org_id: UUID, investigation_id: UUID):
        context=ContextBuilder(self.db, self.context_policy) if self.context_policy else ContextBuilder(self.db)
        context=context.build(org_id, investigation_id).snapshot
        temporal=ActivityWindowReader(self.db).reconstruct(org_id, investigation_id)
        evidence=list(self.db.scalars(select(EvidenceItem).where(EvidenceItem.org_id==org_id, EvidenceItem.investigation_id==investigation_id)))
        evidence_by_id={row.id:row for row in evidence}; provenance=[]
        for item in evidence:
            runs=list(self.db.scalars(select(EvidenceParseRun).where(EvidenceParseRun.org_id==org_id, EvidenceParseRun.evidence_id==item.id)))
            provenance.extend({"type":"EVIDENCE_ITEM","id":item.id,"state":run.status} for run in runs)
        for raw in self.db.scalars(select(RawRecord).where(RawRecord.org_id==org_id, RawRecord.evidence_id.in_(evidence_by_id))):
            provenance.append({"type":"RAW_RECORD","id":raw.id,"state":"complete","raw_unavailable":raw.content is None,"locator_unresolved":raw.content is None and not raw.content_locator})
        events=list(self.db.scalars(select(Event).where(Event.org_id==org_id, Event.investigation_id==investigation_id)))
        by_raw={}
        for event in events:
            sensor=event.normalized.get("sensor_time") if isinstance(event.normalized,dict) else None
            if sensor is not None: by_raw.setdefault(event.raw_record_id,[]).append((event.id, str(sensor)))
        for pairs in by_raw.values():
            if len({value for _,value in pairs}) > 1:
                for event_id,_ in pairs: provenance.append({"type":"EVENT","id":event_id,"state":"complete","contradicts":[other_id for other_id,_ in pairs if other_id != event_id]})
        return analyze(self.policy, context, temporal, provenance)
