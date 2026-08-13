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
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis, IntelligenceItem
from app.modules.alert_triage.infrastructure.models import AlertCluster, AlertClusterAssessment, AlertClusterMembership, AlertClusterPromotion
from app.modules.evidence.infrastructure.models import EvidenceItem, EntityObservation, EntityRelationship, Event, IndicatorOccurrence, RawRecord
from app.modules.investigations.domain.service import InvestigationService
from app.modules.investigations.infrastructure.models import Finding, MitreMapping
from app.shared.exceptions import ValidationError

POLICY_ID="reconstruction-read-v1"
@dataclass(frozen=True)
class ReconstructionReadPolicy:
    per_section:int=100
    per_citation_links:int=100
    per_membership_summaries:int=100
    max_bytes:int=250_000
    def __post_init__(self):
        if (not 0 < self.per_section <= 500 or not 0 < self.per_citation_links <= 500
                or not 0 < self.per_membership_summaries <= 500
                or not 4096 <= self.max_bytes <= 1_000_000):
            raise ValidationError("Reconstruction read policy bounds are unsafe.")

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
        citations=list(self.db.scalars(
            select(IntelligenceEvidenceReference)
            .join(IntelligenceAnalysis, IntelligenceAnalysis.id==IntelligenceEvidenceReference.analysis_id)
            .where(IntelligenceEvidenceReference.org_id==org_id,
                   IntelligenceEvidenceReference.investigation_id==investigation_id,
                   IntelligenceAnalysis.org_id==org_id,
                   IntelligenceAnalysis.investigation_id==investigation_id)
        ))
        citation_ids={citation.id for citation in citations}
        citation_links={citation.id:[] for citation in citations}
        if citation_ids:
            # A link is projected only when its reference, claim, and both analyses
            # have the authoritative current scope.  Bad historic rows fail closed.
            rows=self.db.execute(
                select(IntelligenceClaimEvidenceLink, IntelligenceItem, IntelligenceEvidenceReference, IntelligenceAnalysis)
                .join(IntelligenceItem, IntelligenceItem.id==IntelligenceClaimEvidenceLink.item_id)
                .join(IntelligenceEvidenceReference, IntelligenceEvidenceReference.id==IntelligenceClaimEvidenceLink.evidence_reference_id)
                .join(IntelligenceAnalysis, IntelligenceAnalysis.id==IntelligenceItem.analysis_id)
                .where(IntelligenceClaimEvidenceLink.org_id==org_id,
                       IntelligenceClaimEvidenceLink.investigation_id==investigation_id,
                       IntelligenceClaimEvidenceLink.evidence_reference_id.in_(citation_ids),
                       IntelligenceItem.org_id==org_id, IntelligenceItem.investigation_id==investigation_id,
                       IntelligenceEvidenceReference.org_id==org_id, IntelligenceEvidenceReference.investigation_id==investigation_id,
                       IntelligenceAnalysis.org_id==org_id, IntelligenceAnalysis.investigation_id==investigation_id)
            ).all()
            for link,item,reference,analysis in rows:
                if item.analysis_id != reference.analysis_id or analysis.id != reference.analysis_id:
                    continue
                if reference.reference_type in {"FINDING","MITRE_MAPPING"} and link.role != "CONTEXT":
                    continue
                citation_links[reference.id].append({"claim_id":str(item.id),"role":link.role})
        for reference_id,items in citation_links.items():
            citation_links[reference_id]=sorted(items,key=lambda item:(item["claim_id"],item["role"]))

        promotion=self._promotion_explanation(org_id, investigation_id, warnings)

        def citation_row(reference):
            links=citation_links[reference.id]
            omitted=max(0,len(links)-self.policy.per_citation_links)
            return {"id":str(reference.id),"alias":reference.snapshot_alias,"type":reference.reference_type,
                    "context_version":reference.context_version,"builder_version":reference.builder_version,
                    "policy_version":reference.policy_version,
                    "locator":sanitize(reference.locator_metadata or {},ContextPolicy(),warnings,"citation.locator"),
                    "producer":reference.producer_name,"producer_version":reference.producer_version,
                    "claim_links":links[:self.policy.per_citation_links],"claim_links_omitted":omitted}
        sections={
          "evidence":[{"id":str(x.id),"sha256":x.sha256,"status":x.parsing_status,"imported_at":x.imported_at.isoformat()} for x in evidence],
          "raw_records":[{"id":str(x.id),"evidence_id":str(x.evidence_id),"ordinal":x.ordinal,"content_type":x.content_type,"locator":sanitize(x.content_locator or {},ContextPolicy(),[],"locator")} for x in raws],
          "events":[{"id":str(x.id),"evidence_id":str(x.evidence_id),"raw_record_id":str(x.raw_record_id),"timestamp":x.timestamp.isoformat() if x.timestamp else None,"normalizer":x.normalizer_name,"version":x.normalizer_version} for x in events],
          "entity_observations":[{"id":str(x.id),"entity_id":str(x.entity_id),"raw_record_id":str(x.raw_record_id),"event_id":str(x.event_id) if x.event_id else None,"extractor":x.extractor_name,"version":x.extractor_version} for x in observations],
          "indicator_occurrences":[{"id":str(x.id),"indicator_id":str(x.indicator_id),"raw_record_id":str(x.raw_record_id),"event_id":str(x.event_id) if x.event_id else None,"extractor":x.extractor_name,"version":x.extractor_version} for x in occurrences],
          "relationships":[{"id":str(x.id),"source_entity_id":str(x.source_entity_id),"target_entity_id":str(x.target_entity_id),"raw_record_id":str(x.raw_record_id) if x.raw_record_id else None,"event_id":str(x.event_id) if x.event_id else None,"derivation":x.derivation_name,"version":x.derivation_version} for x in relationships],
          "citations":[citation_row(x) for x in citations],
          "findings":[{"id":str(x.id),"title":x.title[:255],"status":x.status} for x in self.db.scalars(select(Finding).where(Finding.org_id==org_id,Finding.investigation_id==investigation_id,Finding.status=="CONFIRMED"))],
          "mitre":[{"id":str(x.id),"technique_id":x.technique_id,"status":x.status} for x in self.db.scalars(select(MitreMapping).where(MitreMapping.org_id==org_id,MitreMapping.investigation_id==investigation_id,MitreMapping.status=="CONFIRMED"))],
        }
        omissions={};
        for name,rows in list(sections.items()): sections[name],omissions[name]=bounded(name,rows)
        result={"policy_id":POLICY_ID,"investigation":{"id":str(inv.id),"title":inv.title,"status":str(inv.status.value if hasattr(inv.status,"value") else inv.status)},"versions":{"context":context["context_version"],"activity":temporal["policy_id"],"gaps":gaps["policy_id"]},"context":{"warnings":context["warnings"],"omissions":context["omissions"],"section_counts":context["section_counts"]},"activity":temporal,"gaps":gaps,"promotion":promotion,"sections":sections,"pagination":{"section_omissions":omissions,"total_omitted":0},"warnings":warnings}
        # Deterministically remove lowest-priority optional rows to meet total bound.
        priority=("citations","relationships","indicator_occurrences","entity_observations","events","raw_records","evidence")
        while len(json.dumps(result,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode())>self.policy.max_bytes:
            promotion_correlation=result["promotion"].get("correlation") if result["promotion"] else None
            if promotion_correlation and promotion_correlation["memberships"]:
                promotion_correlation["memberships"].pop()
                promotion_correlation["memberships_omitted"]+=1
                continue
            name=next((key for key in priority if result["sections"][key]),None)
            if name is None: raise ValidationError("Reconstruction read max_bytes cannot contain mandatory metadata.")
            result["sections"][name].pop(); result["pagination"]["total_omitted"]+=1
        return result

    def _promotion_explanation(self, org_id: UUID, investigation_id: UUID, warnings: list[dict]) -> dict:
        """Project persisted promotion lineage only; never call correlation or triage."""
        promotion=self.db.scalar(select(AlertClusterPromotion).where(
            AlertClusterPromotion.org_id==org_id,
            AlertClusterPromotion.investigation_id==investigation_id,
        ))
        if not promotion:
            return {"state":"UNAVAILABLE","warning":"PROMOTION_LINK_MISSING","promotion":None,"correlation":None,"triage":None}
        promotion_data={"id":str(promotion.id),"status":promotion.status,"cluster_id":str(promotion.cluster_id),"promoted_at":promotion.promoted_at.isoformat()}
        cluster=self.db.get(AlertCluster,promotion.cluster_id)
        if not cluster or cluster.org_id!=org_id:
            return {"state":"DEGRADED","warning":"PROMOTION_CLUSTER_LINK_MISSING","promotion":promotion_data,"correlation":None,"triage":None}
        version=cluster.correlation_version
        if version=="correlation-v1":
            return {"state":"UNSUPPORTED","warning":"CORRELATION_V1_CONTEXT_UNSUPPORTED","promotion":promotion_data,"correlation":{"version":version,"membership_count":0,"memberships":[],"memberships_omitted":0},"triage":None}
        if version!="correlation-v2":
            return {"state":"UNSUPPORTED","warning":"CORRELATION_VERSION_UNSUPPORTED","promotion":promotion_data,"correlation":{"version":version,"membership_count":0,"memberships":[],"memberships_omitted":0},"triage":None}
        members=list(self.db.scalars(select(AlertClusterMembership).where(
            AlertClusterMembership.org_id==org_id,
            AlertClusterMembership.cluster_id==cluster.id,
            AlertClusterMembership.correlation_version==version,
        ).order_by(AlertClusterMembership.added_at,AlertClusterMembership.id)))
        membership_count=len(members)
        member_rows=[{"id":str(member.id),"score":member.score,
                      "reasons":sanitize(member.reasons,ContextPolicy(),warnings,"promotion.membership.reasons"),
                      "added_at":member.added_at.isoformat()} for member in members[:self.policy.per_membership_summaries]]
        correlation={"version":version,"membership_count":membership_count,"memberships":member_rows,
                     "memberships_omitted":max(0,membership_count-len(member_rows))}
        if not members:
            return {"state":"DEGRADED","warning":"CORRELATION_V2_MEMBERSHIP_MISSING","promotion":promotion_data,"correlation":correlation,"triage":None}
        assessment=self.db.get(AlertClusterAssessment,promotion.triage_assessment_id)
        if not assessment or assessment.org_id!=org_id or assessment.cluster_id!=cluster.id:
            return {"state":"DEGRADED","warning":"TRIAGE_LINK_MISSING","promotion":promotion_data,"correlation":correlation,"triage":None}
        triage={"id":str(assessment.id),"status":"AVAILABLE","priority":assessment.priority,"score":assessment.score,
                "version":assessment.scoring_version}
        return {"state":"AVAILABLE","warning":None,"promotion":promotion_data,"correlation":correlation,"triage":triage}
