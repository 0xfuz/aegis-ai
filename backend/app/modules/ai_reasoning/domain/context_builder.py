"""Bounded, deterministic, read-only Phase 8 intelligence context snapshots."""
from __future__ import annotations
import hashlib
import json
import re
from dataclasses import dataclass
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.modules.alert_triage.infrastructure.models import AlertCluster, AlertClusterAssessment, AlertClusterMembership, AlertClusterPromotion, CanonicalAlert
from app.modules.evidence.infrastructure.models import EvidenceItem, RawRecord, Event, Entity, EntityRelationship, Indicator, IndicatorOccurrence
from app.modules.investigations.domain.service import InvestigationService
from app.modules.investigations.infrastructure.models import Finding, MitreMapping
from app.shared.exceptions import ValidationError

CONTEXT_VERSION = "phase8-context-v1"
BUILDER_VERSION = "8.1.2"
SENSITIVE_KEY = re.compile(r"(?:pass(?:word|wd)?|secret|token|api[._ -]?key|authorization|cookie|session|private[._ -]?key)", re.I)
BEARER = re.compile(r"\b(?:bearer|token)\s+[A-Za-z0-9._~+/-]{12,}\b", re.I)

@dataclass(frozen=True)
class ContextPolicy:
    max_events: int = 100
    max_evidence: int = 30
    max_raw_records: int = 60
    max_entities: int = 100
    max_indicators: int = 100
    max_relationships: int = 100
    max_findings: int = 30
    max_mitre: int = 30
    max_members: int = 100
    max_text: int = 512
    max_depth: int = 4
    max_collection: int = 20
    max_bytes: int = 250_000

@dataclass(frozen=True)
class ContextSnapshot:
    snapshot: dict
    fingerprint: str


def _text(value, limit: int, warnings: list, path: str):
    if value is None: return None
    value = BEARER.sub("[REDACTED]", str(value))
    if len(value) > limit:
        warnings.append({"code":"TEXT_TRUNCATED","path":path,"returned":limit})
        return value[:limit]
    return value

def sanitize(value, policy: ContextPolicy, warnings: list, path="metadata", depth=0):
    """Make telemetry inert: redact credential-shaped keys, bound recursive JSON."""
    if depth >= policy.max_depth:
        warnings.append({"code":"JSON_DEPTH_TRUNCATED","path":path}); return "[TRUNCATED]"
    if isinstance(value, dict):
        result = {}
        for key in sorted(value, key=lambda x: str(x))[:policy.max_collection]:
            name = str(key)
            if SENSITIVE_KEY.search(name): result[name] = "[REDACTED]"; warnings.append({"code":"SENSITIVE_REDACTED","path":f"{path}.{name}"})
            else: result[name] = sanitize(value[key], policy, warnings, f"{path}.{name}", depth + 1)
        if len(value) > policy.max_collection: warnings.append({"code":"JSON_COLLECTION_TRUNCATED","path":path})
        return result
    if isinstance(value, (list, tuple)):
        if len(value) > policy.max_collection: warnings.append({"code":"JSON_COLLECTION_TRUNCATED","path":path})
        return [sanitize(v, policy, warnings, f"{path}[{i}]", depth + 1) for i,v in enumerate(value[:policy.max_collection])]
    return _text(value, policy.max_text, warnings, path) if isinstance(value, str) else value


class ContextBuilder:
    def __init__(self, db: Session, policy: ContextPolicy = ContextPolicy()): self.db, self.policy = db, policy
    def _bounded(self, rows, limit, name, omissions):
        rows = list(rows)
        if len(rows) > limit: omissions.append({"section":name,"reason":"LIMIT","original_count":len(rows),"returned_count":limit})
        return rows[:limit]
    def build(self, org_id: UUID, investigation_id: UUID) -> ContextSnapshot:
        inv = InvestigationService(self.db).get_investigation(org_id, investigation_id)
        warnings, omissions, aliases = [], [], {}
        def alias(prefix, row):
            key=f"{prefix}{len([x for x in aliases if x.startswith(prefix)])+1}"
            aliases[key]={"type":prefix,"id":str(row.id)}; return key
        evidence=self._bounded(self.db.scalars(select(EvidenceItem).where(EvidenceItem.org_id==org_id,EvidenceItem.investigation_id==investigation_id).order_by(EvidenceItem.imported_at,EvidenceItem.id)),self.policy.max_evidence,"evidence",omissions)
        evidence_ids=[x.id for x in evidence]
        raws=self._bounded(self.db.scalars(select(RawRecord).where(RawRecord.org_id==org_id,RawRecord.evidence_id.in_(evidence_ids)).order_by(RawRecord.ordinal,RawRecord.id)) if evidence_ids else [],self.policy.max_raw_records,"raw_records",omissions)
        events=self._bounded(self.db.scalars(select(Event).where(Event.org_id==org_id,Event.investigation_id==investigation_id).order_by(Event.timestamp.nulls_last(),Event.id)),self.policy.max_events,"events",omissions)
        entities=self._bounded(self.db.scalars(select(Entity).where(Entity.org_id==org_id,Entity.investigation_id==investigation_id).order_by(Entity.type,Entity.canonical_value,Entity.id)),self.policy.max_entities,"entities",omissions)
        indicators=self._bounded(self.db.scalars(select(Indicator).join(IndicatorOccurrence).where(Indicator.org_id==org_id,IndicatorOccurrence.org_id==org_id,IndicatorOccurrence.investigation_id==investigation_id).distinct().order_by(Indicator.type,Indicator.normalized_value,Indicator.id)),self.policy.max_indicators,"indicators",omissions)
        relationships=self._bounded(self.db.scalars(select(EntityRelationship).where(EntityRelationship.org_id==org_id,EntityRelationship.investigation_id==investigation_id).order_by(EntityRelationship.observed_at.nulls_last(),EntityRelationship.id)),self.policy.max_relationships,"relationships",omissions)
        findings=self._bounded(self.db.scalars(select(Finding).where(Finding.org_id==org_id,Finding.investigation_id==investigation_id,Finding.status=="CONFIRMED").order_by(Finding.id)),self.policy.max_findings,"findings",omissions)
        mitre=self._bounded(self.db.scalars(select(MitreMapping).where(MitreMapping.org_id==org_id,MitreMapping.investigation_id==investigation_id,MitreMapping.status=="CONFIRMED").order_by(MitreMapping.technique_id,MitreMapping.id)),self.policy.max_mitre,"mitre",omissions)
        promotion=self.db.scalar(select(AlertClusterPromotion).where(AlertClusterPromotion.org_id==org_id,AlertClusterPromotion.investigation_id==investigation_id))
        correlation=[]; triage=None; alerts=[]
        if promotion:
            cluster=self.db.get(AlertCluster,promotion.cluster_id)
            if not cluster or cluster.org_id!=org_id or cluster.correlation_version!="correlation-v2": warnings.append({"code":"V2_PROMOTION_LINK_MISSING"})
            else:
                members=self._bounded(self.db.scalars(select(AlertClusterMembership).where(AlertClusterMembership.org_id==org_id,AlertClusterMembership.cluster_id==cluster.id,AlertClusterMembership.correlation_version=="correlation-v2").order_by(AlertClusterMembership.added_at,AlertClusterMembership.id)),self.policy.max_members,"correlation_members",omissions)
                correlation=[{"alias":alias("CM",m),"score":m.score,"reasons":sanitize(m.reasons,self.policy,warnings,"correlation.reasons"),"version":m.correlation_version,"alert_id":str(m.alert_id)} for m in members]
                alert_ids=[m.alert_id for m in members]
                alerts=list(self.db.scalars(select(CanonicalAlert).where(CanonicalAlert.org_id==org_id,CanonicalAlert.id.in_(alert_ids)).order_by(CanonicalAlert.observed_at,CanonicalAlert.id))) if alert_ids else []
                assessment=self.db.get(AlertClusterAssessment,promotion.triage_assessment_id)
                if assessment and assessment.org_id==org_id: triage={"alias":alias("TR",assessment),"score":assessment.score,"priority":assessment.priority,"version":assessment.scoring_version,"ledger":sanitize(assessment.ledger,self.policy,warnings,"triage.ledger")}
                else: warnings.append({"code":"TRIAGE_LINK_MISSING"})
        else: warnings.append({"code":"PROMOTION_LINK_MISSING"})
        snapshot={"context_version":CONTEXT_VERSION,"builder_version":BUILDER_VERSION,"organization_id":str(org_id),"investigation_id":str(investigation_id),"policy":self.policy.__dict__,"investigation":{"title":_text(inv.title,self.policy.max_text,warnings,"investigation.title"),"source":_text(inv.source,self.policy.max_text,warnings,"investigation.source"),"severity":str(inv.severity.value if hasattr(inv.severity,"value") else inv.severity),"status":str(inv.status.value if hasattr(inv.status,"value") else inv.status)},"evidence":[{"alias":alias("E",x),"sha256":x.sha256,"name":_text(x.original_filename,self.policy.max_text,warnings,"evidence.name"),"status":x.parsing_status} for x in evidence],"raw_records":[{"alias":alias("RR",x),"evidence_id":str(x.evidence_id),"ordinal":x.ordinal,"content_type":x.content_type,"content":_text(x.content,self.policy.max_text,warnings,"raw.content")} for x in raws],"events":[{"alias":alias("EV",x),"timestamp":x.timestamp.isoformat() if x.timestamp else None,"type":x.event_type,"host":_text(x.host,self.policy.max_text,warnings,"event.host"),"user":_text(x.user,self.policy.max_text,warnings,"event.user"),"normalized":sanitize(x.normalized,self.policy,warnings,"event.normalized")} for x in events],"entities":[{"alias":alias("EN",x),"type":x.type,"value":_text(x.canonical_value,self.policy.max_text,warnings,"entity.value"),"attributes":sanitize(x.attributes or {},self.policy,warnings,"entity.attributes")} for x in entities],"indicators":[{"alias":alias("IN",x),"type":x.type,"value":_text(x.normalized_value,self.policy.max_text,warnings,"indicator.value")} for x in indicators],"relationships":[{"alias":alias("REL",x),"source_entity_id":str(x.source_entity_id),"target_entity_id":str(x.target_entity_id),"type":x.relationship_type} for x in relationships],"alerts":[{"alias":alias("AL",x),"source":x.source,"source_alert_id":_text(x.source_alert_id,self.policy.max_text,warnings,"alert.id"),"observed_at":x.observed_at.isoformat(),"severity":x.severity,"observables":sanitize(x.normalized_observables,self.policy,warnings,"alert.observables")} for x in alerts],"correlation_v2":correlation,"triage":triage,"findings":[{"alias":alias("FI",x),"title":_text(x.title,self.policy.max_text,warnings,"finding.title"),"status":x.status} for x in findings],"mitre":[{"alias":alias("MT",x),"technique_id":x.technique_id,"tactic":x.tactic} for x in mitre],"assets":[],"aliases":aliases,"omissions":omissions,"warnings":warnings}
        warnings.append({"code":"ASSETS_OMITTED_NO_EXPLICIT_INVESTIGATION_LINK"})
        snapshot["section_counts"]={k:len(snapshot[k]) for k in ("evidence","raw_records","events","entities","indicators","relationships","alerts","correlation_v2","findings","mitre")}
        raw=json.dumps(snapshot,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
        if len(raw)>self.policy.max_bytes: raise ValidationError("Deterministic context snapshot exceeds total-size policy.")
        fingerprint=hashlib.sha256(json.dumps(snapshot,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        snapshot["fingerprint"]=fingerprint
        return ContextSnapshot(snapshot,fingerprint)
