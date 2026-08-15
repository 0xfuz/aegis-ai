"""AIIE: structured, fact-cited investigation reasoning; never mutates FACT rows."""
from __future__ import annotations
import hashlib, json, re, time
from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field, ValidationError as PydanticValidationError
from typing import Literal
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis, IntelligenceFactLink, IntelligenceItem, IntelligenceReviewEvent
from app.modules.ai_reasoning.infrastructure.llm_provider import LLMProvider, get_llm_provider
from app.modules.evidence.infrastructure.models import EvidenceItem, Event, Entity, EntityRelationship, Indicator, RawRecord
from app.modules.evidence.infrastructure.models import AuditEvent
from app.modules.investigations.domain.service import InvestigationService
from app.modules.investigations.infrastructure.models import MitreMapping, MitreMappingFactLink
from app.shared.exceptions import NotFoundError, ValidationError
from app.modules.ai_reasoning.domain.intelligence_contracts import canonical_claim_type, canonical_review_status, validate_claim_creation, validate_review_transition, validate_run_transition
from app.modules.ai_reasoning.domain.context_builder import ContextBuilder

PROMPT_VERSION="aiie-facts-alias-v1"
ALIAS_PREFIXES={"evidence":"E","raw_records":"RR","events":"EV","indicators":"IN","entities":"EN","relationships":"REL"}
ALIAS_PATTERN=re.compile(r"^(?:E|RR|EV|IN|EN|REL)[1-9][0-9]*$")
class StrictOutput(BaseModel): model_config=ConfigDict(extra="forbid", strict=True)
class Entry(StrictOutput): statement:str; confidence:int|None=Field(default=None,ge=0,le=100); supporting_facts:list[str]=Field(default_factory=list)
class Hypothesis(Entry): contradicting_facts:list[str]=Field(default_factory=list); missing_information:list[str]=Field(default_factory=list); mitre:list[str]=Field(default_factory=list)
class Recommendation(Entry): priority:Literal["LOW","MEDIUM","HIGH","CRITICAL"]="MEDIUM"; reason:str=""
class Output(StrictOutput): summary:str=""; observations:list[Entry]=Field(default_factory=list); hypotheses:list[Hypothesis]=Field(default_factory=list); recommendations:list[Recommendation]=Field(default_factory=list); questions:list[Entry]=Field(default_factory=list); reasoning:list[Entry]=Field(default_factory=list)
AIIE_JSON_SCHEMA=Output.model_json_schema()
def build_alias_map(context:dict)->dict[str,str]:
 aliases={}
 for collection,prefix in ALIAS_PREFIXES.items():
  for ordinal,row in enumerate(sorted(context.get(collection,[]),key=lambda item:item["id"]),1):
   alias=f"{prefix}{ordinal}"
   if alias in aliases: raise ValidationError(f"Duplicate factual alias: {alias}")
   aliases[alias]=row["id"]
 return aliases
def alias_context(context:dict,aliases:dict[str,str])->dict:
 id_to_alias={fact_id:alias for alias,fact_id in aliases.items()}
 def replace(value):
  if isinstance(value,str): return id_to_alias.get(value,value)
  if isinstance(value,list): return [replace(item) for item in value]
  if isinstance(value,dict): return {key:replace(item) for key,item in value.items()}
  return value
 return {key:replace(value) for key,value in context.items() if key!="investigation_id"}
def resolve_aliases(aliases:list[str],alias_map:dict[str,str])->list[UUID]:
 resolved=[]
 for alias in aliases:
  if not ALIAS_PATTERN.fullmatch(alias): raise ValidationError(f"Invalid factual alias syntax: {alias}")
  fact_id=alias_map.get(alias)
  if fact_id is None: raise ValidationError(f"Unknown factual alias for this analysis: {alias}")
  resolved.append(UUID(fact_id))
 return resolved
def schema_for_fact_aliases(fact_aliases:set[str])->dict:
 schema=deepcopy(AIIE_JSON_SCHEMA)
 def constrain(node):
  if isinstance(node,dict):
   for name,value in node.items():
    if name in {"supporting_facts","contradicting_facts"} and isinstance(value,dict) and isinstance(value.get("items"),dict): value["items"]={"type":"string","enum":sorted(fact_aliases)}
    else: constrain(value)
  elif isinstance(node,list):
   for value in node: constrain(value)
 constrain(schema);return schema
def system_prompt(schema:dict)->str:
 return f"""You are Aegis Investigation Intelligence Engine. Return exactly one JSON object and nothing else: no markdown, no code fences, no prose. The JSON must conform exactly to this schema: {json.dumps(schema, separators=(',', ':'))}. Required non-null fields include summary and every statement. Allowed recommendation priority values are LOW, MEDIUM, HIGH, CRITICAL. The schema's fact-reference enums are the only aliases you may use; never output a database UUID, invent an alias, transform an alias, or reuse an alias not listed in the context. Do not include extra fields. Every non-summary item must cite at least one supplied factual alias. Do not claim facts not in the context."""

class InvestigationIntelligenceService:
 def __init__(self,db:Session,llm:LLMProvider|None=None): self.db=db; self.llm=llm or get_llm_provider()
 def context(self,org:UUID,investigation:UUID)->dict:
  InvestigationService(self.db).get_investigation(org,investigation)
  ev=list(self.db.execute(select(EvidenceItem).where(EvidenceItem.org_id==org,EvidenceItem.investigation_id==investigation)).scalars())
  raws=list(self.db.execute(select(RawRecord).where(RawRecord.org_id==org,RawRecord.evidence_id.in_([row.id for row in ev]))).scalars()) if ev else []
  events=list(self.db.execute(select(Event).where(Event.org_id==org,Event.investigation_id==investigation)).scalars())
  entities=list(self.db.execute(select(Entity).where(Entity.org_id==org,Entity.investigation_id==investigation)).scalars())
  rels=list(self.db.execute(select(EntityRelationship).where(EntityRelationship.org_id==org,EntityRelationship.investigation_id==investigation)).scalars())
  inds=list(self.db.execute(select(Indicator).where(Indicator.org_id==org,Indicator.occurrences.any(investigation_id=investigation))).scalars())
  return {"investigation_id":str(investigation),"evidence":[{"id":str(x.id),"name":x.original_filename,"sha256":x.sha256,"status":x.parsing_status} for x in ev],"raw_records":[{"id":str(x.id),"evidence_id":str(x.evidence_id),"ordinal":x.ordinal,"content_type":x.content_type} for x in raws],"events":[{"id":str(x.id),"timestamp":x.timestamp.isoformat() if x.timestamp else None,"type":x.event_type,"host":x.host,"user":x.user,"source_ip":x.source_ip,"destination_ip":x.destination_ip} for x in events],"entities":[{"id":str(x.id),"type":x.type,"value":x.canonical_value} for x in entities],"relationships":[{"id":str(x.id),"source_entity_id":str(x.source_entity_id),"target_entity_id":str(x.target_entity_id),"type":x.relationship_type,"event_id":str(x.event_id) if x.event_id else None,"evidence_id":str(x.evidence_id) if x.evidence_id else None} for x in rels],"indicators":[{"id":str(x.id),"type":x.type,"value":x.normalized_value} for x in inds]}
 def create_run(self,org:UUID,investigation:UUID,*,provider:str,model:str,prompt_template_version:str,input_snapshot:dict,input_hash:str,request_key:str,predecessor_analysis_id:UUID|None=None)->IntelligenceAnalysis:
  InvestigationService(self.db).get_investigation(org,investigation)
  existing=self.db.scalar(select(IntelligenceAnalysis).where(IntelligenceAnalysis.org_id==org,IntelligenceAnalysis.investigation_id==investigation,IntelligenceAnalysis.request_key==request_key))
  if existing:return existing
  predecessor=None
  if predecessor_analysis_id:
   predecessor=self.db.get(IntelligenceAnalysis,predecessor_analysis_id)
   if not predecessor or predecessor.org_id!=org or predecessor.investigation_id!=investigation:raise ValidationError("Run predecessor must belong to the same organization and investigation.")
   if predecessor.status not in {"COMPLETED","FAILED","CANCELLED"}:raise ValidationError("Only terminal runs may be retried.")
  row=IntelligenceAnalysis(org_id=org,investigation_id=investigation,provider=provider,model=model,prompt_template_version=prompt_template_version,input_snapshot=input_snapshot,input_hash=input_hash,request_key=request_key,output_schema_version="aiie-output-v1",predecessor_analysis_id=predecessor.id if predecessor else None,status="QUEUED")
  self.db.add(row);self.db.flush();return row
 def create_context_run(self,org:UUID,investigation:UUID,request_key:str,*,provider="pending",model="pending"):
  """Persistence seam only: building context never invokes a provider or starts a run."""
  context=ContextBuilder(self.db).build(org,investigation)
  return self.create_run(org,investigation,provider=provider,model=model,prompt_template_version=PROMPT_VERSION,input_snapshot=context.snapshot,input_hash=context.fingerprint,request_key=request_key)
 def transition_run(self,org:UUID,analysis_id:UUID,status:str)->IntelligenceAnalysis:
  row=self.db.get(IntelligenceAnalysis,analysis_id)
  if not row or row.org_id!=org:raise NotFoundError("Intelligence run not found.")
  validate_run_transition(row.status,status);row.status=status
  if status=="COMPLETED":row.generated_at=datetime.now(timezone.utc)
  self.db.commit();return row
 def retry_run(self,org:UUID,analysis_id:UUID,request_key:str)->IntelligenceAnalysis:
  row=self.db.get(IntelligenceAnalysis,analysis_id)
  if not row or row.org_id!=org:raise NotFoundError("Intelligence run not found.")
  return self.create_run(org,row.investigation_id,provider=row.provider,model=row.model,prompt_template_version=row.prompt_template_version,input_snapshot=row.input_snapshot,input_hash=row.input_hash,request_key=request_key,predecessor_analysis_id=row.id)
 def create_claim(self,org:UUID,analysis_id:UUID,investigation:UUID,*,kind:str,origin:str,statement:str,ordinal:int=0,confidence:int|None=None,payload:dict|None=None,review_status:str="PENDING",supersedes_item_id:UUID|None=None,reviewer_id:UUID|None=None)->IntelligenceItem:
  analysis=self.db.get(IntelligenceAnalysis,analysis_id)
  if not analysis or analysis.org_id!=org or analysis.investigation_id!=investigation:raise ValidationError("Claim analysis must belong to the same organization and investigation.")
  validate_claim_creation(kind,origin,review_status)
  predecessor=None
  if supersedes_item_id:
   predecessor=self.db.get(IntelligenceItem,supersedes_item_id)
   if not predecessor or predecessor.org_id!=org or predecessor.investigation_id!=investigation:raise ValidationError("Superseded claim must belong to the same organization and investigation.")
   if reviewer_id is None:raise ValidationError("Supersession requires an authenticated analyst reviewer.")
   seen=set()
   cursor=predecessor
   while cursor:
    if cursor.id in seen:raise ValidationError("Supersession cycle detected.")
    seen.add(cursor.id);cursor=self.db.get(IntelligenceItem,cursor.supersedes_item_id) if cursor.supersedes_item_id else None
   if self.db.scalar(select(IntelligenceItem).where(IntelligenceItem.supersedes_item_id==predecessor.id)):raise ValidationError("A claim may have only one successor.")
  item=IntelligenceItem(org_id=org,analysis_id=analysis_id,investigation_id=investigation,kind=kind,origin=origin,ordinal=ordinal,statement=statement,confidence=confidence,payload=payload or {},review_status=review_status,supersedes_item_id=predecessor.id if predecessor else None)
  self.db.add(item);self.db.flush()
  if predecessor:
   previous=predecessor.review_status;validate_review_transition(previous,"SUPERSEDED");predecessor.review_status="SUPERSEDED";predecessor.reviewed_by_id=reviewer_id;predecessor.reviewed_at=datetime.now(timezone.utc);self.db.add(IntelligenceReviewEvent(org_id=org,item_id=predecessor.id,from_status=previous,to_status="SUPERSEDED",reviewer_id=reviewer_id,rationale="Superseded by successor claim."));self.db.add(AuditEvent(org_id=org,investigation_id=investigation,actor_id=reviewer_id,actor_type="user",action="INTELLIGENCE_ITEM_REVIEWED",target_type="IntelligenceItem",target_id=predecessor.id,occurred_at=predecessor.reviewed_at,rationale="Superseded by successor claim.",metadata_={"status":"SUPERSEDED"}))
  return item
 async def run(self,org:UUID,investigation:UUID)->IntelligenceAnalysis:
  context=self.context(org,investigation); raw=json.dumps(context,sort_keys=True,separators=(",",":")); provider=type(self.llm).__name__.replace("Provider", "").lower(); model=getattr(self.llm,"model",None) or "unknown"; analysis=self.create_run(org,investigation,provider=provider,model=model,prompt_template_version=PROMPT_VERSION,input_snapshot=context,input_hash=hashlib.sha256(raw.encode()).hexdigest(),request_key=f"run:{uuid4()}");validate_run_transition(analysis.status,"RUNNING");analysis.status="RUNNING";self.db.flush()
  try:
   aliases=build_alias_map(context); llm_context=alias_context(context,aliases); llm_raw=json.dumps(llm_context,sort_keys=True,separators=(",",":")); schema=schema_for_fact_aliases(set(aliases)); prompt=system_prompt(schema); started=time.monotonic(); raw_output=await self.llm.complete_json(prompt,llm_raw,schema=schema)
   try: output=Output.model_validate(json.loads(raw_output))
   except (json.JSONDecodeError,PydanticValidationError) as first_error:
    raw_output=await self.llm.complete_json(prompt,llm_raw,schema=schema,repair_response=raw_output,validation_error=str(first_error)[:2000])
    try: output=Output.model_validate(json.loads(raw_output))
    except (json.JSONDecodeError,PydanticValidationError) as retry_error: raise ValidationError(f"AI output remained structurally invalid after one repair attempt: {retry_error}") from retry_error
   analysis.generation_duration_ms=int((time.monotonic()-started)*1000)
   groups=[("INFERENCE",[Entry(statement=output.summary)]),("OBSERVATION",output.observations),("HYPOTHESIS",output.hypotheses),("RECOMMENDATION",output.recommendations),("INFERENCE",output.questions),("INFERENCE",output.reasoning)]
   # Validate the complete response before persisting any inference item, so a
   # rejected/hallucinated reference cannot leave a partial analysis behind.
   for kind,items in groups:
    for item in items:
     fact_aliases=item.supporting_facts+getattr(item,"contradicting_facts",[])
     if item.statement!=output.summary and not item.supporting_facts: raise ValidationError("AI output contains missing factual aliases.")
     if item.statement!=output.summary: resolve_aliases(fact_aliases,aliases)
   for kind,items in groups:
    for ordinal,item in enumerate(items):
     row=self.create_claim(org,analysis.id,investigation,kind=kind,origin="AI",ordinal=ordinal,statement=item.statement,confidence=item.confidence,payload=item.model_dump(exclude={"statement","confidence","supporting_facts","contradicting_facts"}))
     for fact_id in resolve_aliases(item.supporting_facts,aliases):self.db.add(IntelligenceFactLink(org_id=org,item_id=row.id,fact_type="FACT",fact_id=fact_id,role="SUPPORTS"))
     for fact_id in resolve_aliases(getattr(item,"contradicting_facts",[]),aliases):self.db.add(IntelligenceFactLink(org_id=org,item_id=row.id,fact_type="FACT",fact_id=fact_id,role="CONTRADICTS"))
     # MITRE output is always a proposal; analysts alone can confirm it.
     for technique in getattr(item,"mitre",[]):
      mapping=MitreMapping(org_id=org,investigation_id=investigation,source_intelligence_item_id=row.id,technique_id=technique,technique_name=None,tactic=None,confidence=item.confidence,ai_rationale=item.statement,status="PROPOSED");self.db.add(mapping);self.db.flush()
      for fact_id in resolve_aliases(item.supporting_facts,aliases):self.db.add(MitreMappingFactLink(org_id=org,mapping_id=mapping.id,fact_type="FACT",fact_id=fact_id,role="SUPPORTS"))
   validate_run_transition(analysis.status,"COMPLETED");analysis.status="COMPLETED";analysis.generated_at=datetime.now(timezone.utc);self.db.commit();return analysis
  except Exception as exc: validate_run_transition(analysis.status,"FAILED");analysis.status="FAILED";analysis.error_summary=str(exc)[:2000];self.db.commit();raise
 def latest(self,org:UUID,investigation:UUID,analysis_id:UUID|None=None):
  statement=select(IntelligenceAnalysis).where(IntelligenceAnalysis.org_id==org,IntelligenceAnalysis.investigation_id==investigation)
  if analysis_id is not None: statement=statement.where(IntelligenceAnalysis.id==analysis_id)
  row=self.db.execute(statement.order_by(IntelligenceAnalysis.created_at.desc())).scalars().first()
  if not row: raise NotFoundError("No investigation intelligence analysis exists.")
  items=list(self.db.execute(select(IntelligenceItem).where(IntelligenceItem.org_id==org,IntelligenceItem.analysis_id==row.id).order_by(IntelligenceItem.kind,IntelligenceItem.ordinal)).scalars()); links=list(self.db.execute(select(IntelligenceFactLink).where(IntelligenceFactLink.org_id==org,IntelligenceFactLink.item_id.in_([x.id for x in items]))).scalars()) if items else []
  return {"id":str(row.id),"status":row.status,"generated_at":row.generated_at,"items":[{"id":str(x.id),"kind":x.kind,"claim_type":canonical_claim_type(x.kind),"origin":x.origin,"statement":x.statement,"confidence":x.confidence,"payload":x.payload,"review_status":x.review_status,"fact_links":[{"fact_id":str(l.fact_id),"role":l.role} for l in links if l.item_id==x.id]} for x in items]}
 def review(self,org:UUID,item_id:UUID,user:UUID,status:str,rationale:str):
  item=self.db.get(IntelligenceItem,item_id)
  if not item or item.org_id!=org: raise NotFoundError("Intelligence item not found.")
  status=canonical_review_status(status);validate_review_transition(item.review_status,status)
  previous=item.review_status;item.review_status=status;item.reviewed_by_id=user;item.reviewed_at=datetime.now(timezone.utc);item.review_rationale=rationale;self.db.add(IntelligenceReviewEvent(org_id=org,item_id=item.id,from_status=previous,to_status=status,reviewer_id=user,rationale=rationale));self.db.add(AuditEvent(org_id=org,investigation_id=item.investigation_id,actor_id=user,actor_type="user",action="INTELLIGENCE_ITEM_REVIEWED",target_type="IntelligenceItem",target_id=item.id,occurred_at=item.reviewed_at,rationale=rationale,metadata_={"status":status}));self.db.commit();return item
