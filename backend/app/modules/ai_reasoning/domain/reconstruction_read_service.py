"""Bounded, deterministic analyst reconstruction read model; no writes."""
from __future__ import annotations
import json
from dataclasses import dataclass
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.modules.ai_reasoning.domain.context_builder import ContextBuilder, ContextPolicy, sanitize
from app.modules.ai_reasoning.domain.activity_window import ActivityWindowReader
from app.modules.ai_reasoning.domain.reconstruction_gaps import ReconstructionGapReader
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceClaimEvidenceLink, IntelligenceEvidenceReference
from app.modules.evidence.infrastructure.models import EvidenceItem, EntityObservation, EntityRelationship, Event, IndicatorOccurrence, RawRecord
from app.modules.investigations.domain.service import InvestigationService
from app.modules.investigations.infrastructure.models import Finding, MitreMapping
from app.shared.exceptions import ValidationError

POLICY_ID="reconstruction-read-v1"
@dataclass(frozen=True)
class ReconstructionReadPolicy:
    per_section:int=100
    max_bytes:int=250_000
    def __post_init__(self):
        if not 0 < self.per_section <= 500 or not 4096 <= self.max_bytes <= 1_000_000: raise ValidationError("Reconstruction read policy bounds are unsafe.")

class ReconstructionReadService:
    def __init__(self,db:Session,policy:ReconstructionReadPolicy=ReconstructionReadPolicy()): self.db,self.policy=db,policy
    def read(self,org_id:UUID,investigation_id:UUID)->dict:
        inv=InvestigationService(self.db).get_investigation(org_id,investigation_id)
        context=ContextBuilder(self.db).build(org_id,investigation_id).snapshot
        temporal=ActivityWindowReader(self.db).reconstruct(org_id,investigation_id)
        gaps=ReconstructionGapReader(self.db).reconstruct(org_id,investigation_id)
        warnings=[]
        def bounded(name,rows):
            rows=sorted(rows,key=lambda row:(str(row.get("id",""))))
            omitted=max(0,len(rows)-self.policy.per_section)
            if omitted:warnings.append({"section":name,"reason":"READ_LIMIT","omitted":omitted})
            return rows[:self.policy.per_section],omitted
        evidence=list(self.db.scalars(select(EvidenceItem).where(EvidenceItem.org_id==org_id,EvidenceItem.investigation_id==investigation_id)))
        evidence_ids={row.id for row in evidence}
        raws=list(self.db.scalars(select(RawRecord).where(RawRecord.org_id==org_id,RawRecord.evidence_id.in_(evidence_ids)))) if evidence_ids else []
        events=list(self.db.scalars(select(Event).where(Event.org_id==org_id,Event.investigation_id==investigation_id)))
        observations=list(self.db.scalars(select(EntityObservation).where(EntityObservation.org_id==org_id,EntityObservation.investigation_id==investigation_id)))
        occurrences=list(self.db.scalars(select(IndicatorOccurrence).where(IndicatorOccurrence.org_id==org_id,IndicatorOccurrence.investigation_id==investigation_id)))
        relationships=list(self.db.scalars(select(EntityRelationship).where(EntityRelationship.org_id==org_id,EntityRelationship.investigation_id==investigation_id)))
        citations=list(self.db.scalars(select(IntelligenceEvidenceReference).where(IntelligenceEvidenceReference.org_id==org_id,IntelligenceEvidenceReference.investigation_id==investigation_id)))
        links={link.evidence_reference_id:link.role for link in self.db.scalars(select(IntelligenceClaimEvidenceLink).where(IntelligenceClaimEvidenceLink.org_id==org_id,IntelligenceClaimEvidenceLink.investigation_id==investigation_id))}
        sections={
          "evidence":[{"id":str(x.id),"sha256":x.sha256,"status":x.parsing_status,"imported_at":x.imported_at.isoformat()} for x in evidence],
          "raw_records":[{"id":str(x.id),"evidence_id":str(x.evidence_id),"ordinal":x.ordinal,"content_type":x.content_type,"locator":sanitize(x.content_locator or {},ContextPolicy(),[],"locator")} for x in raws],
          "events":[{"id":str(x.id),"evidence_id":str(x.evidence_id),"raw_record_id":str(x.raw_record_id),"timestamp":x.timestamp.isoformat() if x.timestamp else None,"normalizer":x.normalizer_name,"version":x.normalizer_version} for x in events],
          "entity_observations":[{"id":str(x.id),"entity_id":str(x.entity_id),"raw_record_id":str(x.raw_record_id),"event_id":str(x.event_id) if x.event_id else None,"extractor":x.extractor_name,"version":x.extractor_version} for x in observations],
          "indicator_occurrences":[{"id":str(x.id),"indicator_id":str(x.indicator_id),"raw_record_id":str(x.raw_record_id),"event_id":str(x.event_id) if x.event_id else None,"extractor":x.extractor_name,"version":x.extractor_version} for x in occurrences],
          "relationships":[{"id":str(x.id),"source_entity_id":str(x.source_entity_id),"target_entity_id":str(x.target_entity_id),"raw_record_id":str(x.raw_record_id) if x.raw_record_id else None,"event_id":str(x.event_id) if x.event_id else None,"derivation":x.derivation_name,"version":x.derivation_version} for x in relationships],
          "citations":[{"id":str(x.id),"alias":x.snapshot_alias,"type":x.reference_type,"context_version":x.context_version,"builder_version":x.builder_version,"policy_version":x.policy_version,"locator":sanitize(x.locator_metadata or {},ContextPolicy(),[],"citation.locator"),"producer":x.producer_name,"producer_version":x.producer_version,"claim_role":links.get(x.id)} for x in citations],
          "findings":[{"id":str(x.id),"title":x.title[:255],"status":x.status} for x in self.db.scalars(select(Finding).where(Finding.org_id==org_id,Finding.investigation_id==investigation_id,Finding.status=="CONFIRMED"))],
          "mitre":[{"id":str(x.id),"technique_id":x.technique_id,"status":x.status} for x in self.db.scalars(select(MitreMapping).where(MitreMapping.org_id==org_id,MitreMapping.investigation_id==investigation_id,MitreMapping.status=="CONFIRMED"))],
        }
        omissions={};
        for name,rows in list(sections.items()): sections[name],omissions[name]=bounded(name,rows)
        result={"policy_id":POLICY_ID,"investigation":{"id":str(inv.id),"title":inv.title,"status":str(inv.status.value if hasattr(inv.status,"value") else inv.status)},"versions":{"context":context["context_version"],"activity":temporal["policy_id"],"gaps":gaps["policy_id"]},"context":{"warnings":context["warnings"],"omissions":context["omissions"],"section_counts":context["section_counts"]},"activity":temporal,"gaps":gaps,"sections":sections,"pagination":{"section_omissions":omissions,"total_omitted":0},"warnings":warnings}
        # Deterministically remove lowest-priority optional rows to meet total bound.
        priority=("relationships","indicator_occurrences","entity_observations","events","raw_records","evidence")
        while len(json.dumps(result,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode())>self.policy.max_bytes:
            name=next((key for key in priority if result["sections"][key]),None)
            if name is None: raise ValidationError("Reconstruction read max_bytes cannot contain mandatory metadata.")
            result["sections"][name].pop(); result["pagination"]["total_omitted"]+=1
        return result
