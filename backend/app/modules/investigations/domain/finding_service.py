"""Analyst verdict workflow; never mutates AIIE or canonical FACT rows."""
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceFactLink, IntelligenceItem
from app.modules.evidence.infrastructure.models import AuditEvent
from app.modules.evidence.infrastructure.models import EvidenceItem, RawRecord, Event, Indicator, IndicatorOccurrence, Entity, EntityRelationship
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis
from app.modules.investigations.domain.service import InvestigationService
from app.modules.investigations.infrastructure.models import Finding, FindingFactLink, MitreMapping, MitreMappingFactLink
from app.shared.exceptions import NotFoundError, ValidationError

class FindingService:
 def __init__(self,db:Session): self.db=db
 def _item(self,org:UUID,item_id:UUID):
  item=self.db.get(IntelligenceItem,item_id)
  if not item or item.org_id!=org: raise NotFoundError("Intelligence item not found.")
  return item
 def _audit(self,org,investigation,user,action,target,rationale=None): self.db.add(AuditEvent(org_id=org,investigation_id=investigation,actor_id=user,actor_type="user",action=action,target_type=type(target).__name__,target_id=target.id,occurred_at=datetime.now(timezone.utc),rationale=rationale))
 def list_findings(self,org,investigation,status=None,limit=50,offset=0):
  InvestigationService(self.db).get_investigation(org,investigation)
  allowed={"OPEN","CONFIRMED","DISMISSED","RESOLVED"}
  if status is not None and status not in allowed: raise ValidationError("Invalid finding status.")
  where=[Finding.org_id==org,Finding.investigation_id==investigation]
  if status is not None: where.append(Finding.status==status)
  total=self.db.scalar(select(func.count()).select_from(Finding).where(*where)) or 0
  rows=list(self.db.scalars(select(Finding).where(*where).order_by(Finding.created_at.desc(),Finding.id.desc()).limit(limit).offset(offset)))
  links=list(self.db.scalars(select(FindingFactLink).where(FindingFactLink.org_id==org,FindingFactLink.finding_id.in_([row.id for row in rows])))) if rows else []
  by_finding={}
  for link in links: by_finding.setdefault(link.finding_id,[]).append(link)
  return {"items":[self._finding(row,by_finding.get(row.id,[])) for row in rows],"limit":limit,"offset":offset,"returned_count":len(rows),"total":total}
 def _finding(self,row,links=None):
  if links is None: links=list(self.db.scalars(select(FindingFactLink).where(FindingFactLink.finding_id==row.id)))
  return {"id":str(row.id),"title":row.title[:255],"description":row.description[:1000],"severity":row.severity,"confidence":row.confidence,"status":row.status,"created_at":row.created_at,"updated_at":row.updated_at,"provenance":{"available":bool(links),"omitted":0},"fact_links":[{"fact_id":str(x.fact_id),"fact_type":x.fact_type,"role":x.role} for x in links[:50]]}
 def create_manual(self,org,investigation,user,data):
  InvestigationService(self.db).get_investigation(org,investigation); row=Finding(org_id=org,investigation_id=investigation,analyst_id=user,**data);self.db.add(row);self.db.flush();self._audit(org,investigation,user,"FINDING_CREATED_MANUALLY",row);self.db.commit();return self._finding(row)
 def create_from_item(self,org,item_id,user,title=None,severity="medium"):
  item=self._item(org,item_id)
  if item.review_status!="CONFIRMED" or item.kind not in {"OBSERVATION","HYPOTHESIS","RECOMMENDATION"}: raise ValidationError("Only confirmed observations, hypotheses, or recommendations can become findings.")
  if self.db.scalar(select(Finding).where(Finding.source_intelligence_item_id==item.id)): raise ValidationError("This intelligence item has already been converted to a finding.")
  row=Finding(org_id=org,investigation_id=item.investigation_id,source_intelligence_item_id=item.id,source_analysis_id=item.analysis_id,title=title or item.statement[:255],description=item.statement,severity=severity,confidence=item.confidence,status="OPEN",analyst_id=user);self.db.add(row);self.db.flush()
  for link in self.db.scalars(select(IntelligenceFactLink).where(IntelligenceFactLink.org_id==org,IntelligenceFactLink.item_id==item.id)): self.db.add(FindingFactLink(org_id=org,finding_id=row.id,fact_type=link.fact_type,fact_id=link.fact_id,role=link.role))
  self._audit(org,item.investigation_id,user,"FINDING_CREATED_FROM_AI",row);self.db.commit();return self._finding(row)
 def update(self,org,finding_id,user,data):
  row=self.db.get(Finding,finding_id)
  if not row or row.org_id!=org: raise NotFoundError("Finding not found.")
  for key in ("title","description","severity","confidence"): 
   if key in data and data[key] is not None:setattr(row,key,data[key])
  self._audit(org,row.investigation_id,user,"FINDING_EDITED",row);self.db.commit();return self._finding(row)
 def status(self,org,finding_id,user,status):
  if status not in {"OPEN","CONFIRMED","DISMISSED","RESOLVED"}:raise ValidationError("Invalid finding status.")
  row=self.db.get(Finding,finding_id)
  if not row or row.org_id!=org:raise NotFoundError("Finding not found.")
  allowed={"OPEN":{"CONFIRMED","DISMISSED"},"CONFIRMED":{"RESOLVED"},"DISMISSED":set(),"RESOLVED":set()}
  if status not in allowed.get(row.status,set()):raise ValidationError(f"Invalid finding transition from {row.status} to {status}.")
  try:
   row.status=status
   self._audit(org,row.investigation_id,user,"FINDING_STATUS_CHANGED",row,status)
   self.db.commit()
  except Exception:
   self.db.rollback()
   raise ValidationError("Unable to save finding review.") from None
  return self._finding(row)
 def list_mitre(self,org,investigation):
  InvestigationService(self.db).get_investigation(org,investigation)
  rows=self.db.scalars(select(MitreMapping).where(MitreMapping.org_id==org,MitreMapping.investigation_id==investigation).order_by(MitreMapping.created_at.desc()))
  return [self._mapping(row) for row in rows]
 def list_mitre_page(self,org,investigation,status=None,limit=50,offset=0):
  InvestigationService(self.db).get_investigation(org,investigation)
  allowed={"PROPOSED","CONFIRMED","REJECTED"}
  if status is not None and status not in allowed: raise ValidationError("Invalid MITRE mapping status.")
  where=[MitreMapping.org_id==org,MitreMapping.investigation_id==investigation]
  if status is not None: where.append(MitreMapping.status==status)
  total=self.db.scalar(select(func.count()).select_from(MitreMapping).where(*where)) or 0
  rows=list(self.db.scalars(select(MitreMapping).where(*where).order_by(MitreMapping.created_at.desc(),MitreMapping.id.desc()).limit(limit).offset(offset)))
  mapping_ids=[row.id for row in rows]
  counts={mapping_id:count for mapping_id,count in self.db.execute(select(MitreMappingFactLink.mapping_id,func.count()).where(MitreMappingFactLink.org_id==org,MitreMappingFactLink.mapping_id.in_(mapping_ids)).group_by(MitreMappingFactLink.mapping_id))} if mapping_ids else {}
  ranked_links=select(MitreMappingFactLink.id.label("id"),func.row_number().over(partition_by=MitreMappingFactLink.mapping_id,order_by=MitreMappingFactLink.id).label("position")).where(MitreMappingFactLink.org_id==org,MitreMappingFactLink.mapping_id.in_(mapping_ids)).subquery() if mapping_ids else None
  links=list(self.db.scalars(select(MitreMappingFactLink).join(ranked_links,MitreMappingFactLink.id==ranked_links.c.id).where(ranked_links.c.position<=50).order_by(MitreMappingFactLink.mapping_id,MitreMappingFactLink.id))) if ranked_links is not None else []
  by_mapping={}
  for link in links: by_mapping.setdefault(link.mapping_id,[]).append(link)
  return {"items":[self._mapping_read(row,by_mapping.get(row.id,[]),counts.get(row.id,0)) for row in rows],"limit":limit,"offset":offset,"returned_count":len(rows),"total":total}
 def overview(self,org,investigation):
  InvestigationService(self.db).get_investigation(org,investigation)
  count=lambda model,*where:self.db.scalar(select(func.count()).select_from(model).where(*where)) or 0
  evidence=count(EvidenceItem,EvidenceItem.org_id==org,EvidenceItem.investigation_id==investigation)
  raw=count(RawRecord,RawRecord.org_id==org,RawRecord.evidence_id.in_(select(EvidenceItem.id).where(EvidenceItem.org_id==org,EvidenceItem.investigation_id==investigation)))
  indicators=self.db.scalar(select(func.count(func.distinct(IndicatorOccurrence.indicator_id))).where(IndicatorOccurrence.org_id==org,IndicatorOccurrence.investigation_id==investigation)) or 0
  latest=self.db.scalars(select(IntelligenceAnalysis).where(IntelligenceAnalysis.org_id==org,IntelligenceAnalysis.investigation_id==investigation).order_by(IntelligenceAnalysis.created_at.desc())).first()
  return {"evidence_count":evidence,"raw_record_count":raw,"event_count":count(Event,Event.org_id==org,Event.investigation_id==investigation),"indicator_count":indicators,"entity_count":count(Entity,Entity.org_id==org,Entity.investigation_id==investigation),"relationship_count":count(EntityRelationship,EntityRelationship.org_id==org,EntityRelationship.investigation_id==investigation),"findings_count":count(Finding,Finding.org_id==org,Finding.investigation_id==investigation),"confirmed_mitre_count":count(MitreMapping,MitreMapping.org_id==org,MitreMapping.investigation_id==investigation,MitreMapping.status=="CONFIRMED"),"latest_aiie_status":latest.status if latest else "NOT_RUN"}
 def audit(self,org,investigation,limit=100,offset=0):
  """Return the bounded, read-only audit projection for one Investigation.

  Audit rationale and arbitrary metadata can contain analyst prose or internal
  dispatch context.  They are intentionally not an API contract.  The small
  transition projection below is the only metadata permitted to cross this
  boundary.
  """
  InvestigationService(self.db).get_investigation(org,investigation)
  where=(AuditEvent.org_id==org,AuditEvent.investigation_id==investigation)
  total=self.db.scalar(select(func.count()).select_from(AuditEvent).where(*where)) or 0
  rows=self.db.scalars(select(AuditEvent).where(*where).order_by(AuditEvent.occurred_at.desc(),AuditEvent.id.desc()).limit(limit).offset(offset))
  return {"items":[self._audit_read(x) for x in rows],"limit":limit,"offset":offset,"total":total}

 @staticmethod
 def _audit_label(value, maximum, fallback):
  if not isinstance(value,str) or len(value)>maximum or not value.replace("_","").replace("-","").isalnum(): return fallback
  return value

 @classmethod
 def _audit_read(cls,row):
  metadata=row.metadata_ if isinstance(row.metadata_,dict) else {}
  previous=cls._audit_label(metadata.get("previous"),64,None)
  status=cls._audit_label(metadata.get("status"),64,None)
  transition={"from":previous,"to":status} if previous or status else None
  return {"id":str(row.id),"event_type":cls._audit_label(row.action,100,"AUDIT_EVENT"),
          "occurred_at":row.occurred_at,"actor":{"type":cls._audit_label(row.actor_type,50,"unknown"),"id":str(row.actor_id) if row.actor_id else None},
          "target":{"type":cls._audit_label(row.target_type,100,"unknown"),"id":str(row.target_id)},"transition":transition}
 def _mapping(self,row):
  links=self.db.scalars(select(MitreMappingFactLink).where(MitreMappingFactLink.mapping_id==row.id))
  return {"id":str(row.id),"technique_id":row.technique_id,"technique_name":row.technique_name,"tactic":row.tactic,"confidence":row.confidence,"ai_rationale":row.ai_rationale,"status":row.status,"source_intelligence_item_id":str(row.source_intelligence_item_id) if row.source_intelligence_item_id else None,"finding_id":str(row.finding_id) if row.finding_id else None,"fact_links":[{"fact_id":str(x.fact_id),"role":x.role} for x in links]}
 def _mapping_read(self,row,links,count):
  return {"id":str(row.id),"technique_id":row.technique_id[:32],"technique_name":row.technique_name[:255] if row.technique_name else None,"tactic":row.tactic[:100] if row.tactic else None,"status":row.status,"confidence":row.confidence,"review_rationale":row.review_rationale[:1000] if row.review_rationale else None,"created_at":row.created_at,"reviewed_at":row.reviewed_at,"provenance":{"available":bool(count),"omitted":max(0,count-50)},"fact_links":[{"fact_id":str(x.fact_id),"fact_type":x.fact_type,"role":x.role} for x in links[:50]]}
 def review_mapping(self,org,mapping_id,user,status,rationale):
  if status not in {"CONFIRMED","REJECTED"} or (status=="REJECTED" and not rationale.strip()):raise ValidationError("A rejection rationale is required.")
  row=self.db.scalar(select(MitreMapping).where(MitreMapping.id==mapping_id,MitreMapping.org_id==org).with_for_update())
  if not row:raise NotFoundError("MITRE mapping not found.")
  if row.status!="PROPOSED":raise ValidationError("Only proposed MITRE mappings can be reviewed.")
  try:
   row.status=status;row.reviewed_by_id=user;row.reviewed_at=datetime.now(timezone.utc);row.review_rationale=rationale;self._audit(org,row.investigation_id,user,f"MITRE_{status}",row,rationale);self.db.commit()
  except Exception:
   self.db.rollback()
   raise ValidationError("Unable to save MITRE mapping review.") from None
  return self._mapping_read(row,[],0)
