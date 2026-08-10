"""Focused A6 contracts: analyst verdicts copy, rather than mutate, AIIE provenance."""
import asyncio, json
from datetime import datetime, timezone
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select
from app.modules.ai_reasoning.domain.intelligence_service import InvestigationIntelligenceService
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceFactLink, IntelligenceItem
from app.modules.evidence.infrastructure.models import AuditEvent, Entity, EvidenceItem, EvidenceParseRun, RawRecord, Event, Indicator, IndicatorOccurrence, EntityRelationship
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.domain.finding_service import FindingService
from app.modules.investigations.infrastructure.models import Finding, FindingFactLink, Investigation, InvestigationStatus, MitreMapping, Severity
from app.shared.database import SessionLocal
from app.shared.exceptions import ValidationError
from app.core.security import create_access_token
from app.main import app
from fastapi.testclient import TestClient

class Provider:
 model="a6-test"
 async def complete_json(self,_system,prompt,**_kw):
  alias=json.loads(prompt)["entities"][0]["id"]
  return json.dumps({"summary":"Summary.","observations":[{"statement":"Observed.","confidence":80,"supporting_facts":[alias]}],"hypotheses":[{"statement":"Hypothesis.","confidence":70,"supporting_facts":[alias],"contradicting_facts":[],"missing_information":[],"mitre":["T1078","T1059"]}],"recommendations":[],"questions":[],"reasoning":[]})

@pytest.fixture()
def db():
 s=SessionLocal()
 try: yield s
 finally: s.rollback();s.close()
def setup(db):
 key=str(uuid4());org=Organization(name=key,slug=f"a6-{key}");role=Role(name=f"role-{key}");db.add_all([org,role]);db.flush();user=User(org_id=org.id,role_id=role.id,email=f"{key}@a.test",hashed_password="x",full_name="Analyst");inv=Investigation(org_id=org.id,title="A6",source="test",severity=Severity.MEDIUM,status=InvestigationStatus.NEW);db.add_all([user,inv]);db.flush();entity=Entity(org_id=org.id,investigation_id=inv.id,type="host",canonical_value=key,display_name=key);db.add(entity);db.commit();return org,user,inv,entity
def test_approved_item_becomes_durable_finding_and_preserves_fact_links(db):
 org,user,inv,entity=setup(db);asyncio.run(InvestigationIntelligenceService(db,Provider()).run(org.id,inv.id));item=db.scalar(select(IntelligenceItem).where(IntelligenceItem.org_id==org.id,IntelligenceItem.kind=="OBSERVATION"));InvestigationIntelligenceService(db).review(org.id,item.id,user.id,"APPROVED","verified");finding=FindingService(db).create_from_item(org.id,item.id,user.id);assert finding["source_intelligence_item_id"]==str(item.id);assert db.scalar(select(FindingFactLink.fact_id).where(FindingFactLink.finding_id==finding["id"]))==entity.id;assert db.scalar(select(IntelligenceFactLink.fact_id).where(IntelligenceFactLink.item_id==item.id))==entity.id;assert db.scalar(select(AuditEvent).where(AuditEvent.action=="FINDING_CREATED_FROM_AI"))
def test_unreviewed_rejected_duplicate_and_mitre_review_guards(db):
 org,user,inv,_entity=setup(db);asyncio.run(InvestigationIntelligenceService(db,Provider()).run(org.id,inv.id));item=db.scalar(select(IntelligenceItem).where(IntelligenceItem.org_id==org.id,IntelligenceItem.kind=="OBSERVATION"));service=FindingService(db)
 with pytest.raises(ValidationError): service.create_from_item(org.id,item.id,user.id)
 InvestigationIntelligenceService(db).review(org.id,item.id,user.id,"REJECTED","no")
 with pytest.raises(ValidationError): service.create_from_item(org.id,item.id,user.id)
 hypothesis=db.scalar(select(IntelligenceItem).where(IntelligenceItem.org_id==org.id,IntelligenceItem.kind=="HYPOTHESIS"));InvestigationIntelligenceService(db).review(org.id,hypothesis.id,user.id,"APPROVED","yes");service.create_from_item(org.id,hypothesis.id,user.id)
 with pytest.raises(ValidationError): service.create_from_item(org.id,hypothesis.id,user.id)
 mapping=db.scalar(select(MitreMapping).where(MitreMapping.source_intelligence_item_id==hypothesis.id));assert mapping.status=="PROPOSED";service.review_mapping(org.id,mapping.id,user.id,"CONFIRMED","verified");assert mapping.status=="CONFIRMED";assert db.scalar(select(AuditEvent).where(AuditEvent.action=="MITRE_CONFIRMED"))
def test_manual_edit_status_transitions_rejection_and_mitre_rejection_audit(db):
 org,user,inv,_entity=setup(db);service=FindingService(db);finding=service.create_manual(org.id,inv.id,user.id,{"title":"Manual","description":"Analyst finding","severity":"high","confidence":90});service.update(org.id,UUID(finding["id"]),user.id,{"title":"Edited"});service.status(org.id,UUID(finding["id"]),user.id,"CONFIRMED");service.status(org.id,UUID(finding["id"]),user.id,"RESOLVED");assert db.get(Finding,UUID(finding["id"])).status=="RESOLVED"
 with pytest.raises(ValidationError):service.status(org.id,UUID(finding["id"]),user.id,"DISMISSED")
 assert {"FINDING_CREATED_MANUALLY","FINDING_EDITED","FINDING_STATUS_CHANGED"}.issubset({row.action for row in db.scalars(select(AuditEvent).where(AuditEvent.investigation_id==inv.id))})
 asyncio.run(InvestigationIntelligenceService(db,Provider()).run(org.id,inv.id));hypothesis=db.scalar(select(IntelligenceItem).where(IntelligenceItem.org_id==org.id,IntelligenceItem.kind=="HYPOTHESIS"));mapping=db.scalar(select(MitreMapping).where(MitreMapping.source_intelligence_item_id==hypothesis.id));service.review_mapping(org.id,mapping.id,user.id,"REJECTED","insufficient support");assert mapping.review_rationale=="insufficient support";assert db.scalar(select(AuditEvent).where(AuditEvent.action=="MITRE_REJECTED"))
def test_http_authorization_and_read_only_overview_audit(db):
 org,user,inv,_=setup(db);client=TestClient(app);base=f"/api/v1/investigations/{inv.id}";assert client.get(f"{base}/overview").status_code==403;assert client.get(f"{base}/audit").status_code==403;assert client.get(f"{base}/findings").status_code==403;assert client.get(f"{base}/mitre-mappings").status_code==403
 headers={"Authorization":f"Bearer {create_access_token(user.id,org.id,'analyst',['investigation:read','investigation:write'])}"};assert client.get(f"{base}/overview",headers=headers).status_code==200;assert client.get(f"{base}/audit",headers=headers).status_code==200
def test_http_overview_exact_canonical_counts_and_tenant_isolation(db):
 org,user,inv,entity=setup(db);now=datetime.now(timezone.utc);run_key=uuid4().hex[:12]
 def facts(target_org,target_inv,suffix):
  evidence=EvidenceItem(org_id=target_org.id,investigation_id=target_inv.id,original_filename=f"{suffix}.log",storage_key=f"key-{run_key}-{suffix}",sha256=(suffix[0]*64),byte_size=1,detected_mime="text/plain",extension=".log",acquisition_source="test",imported_at=now,parsing_status="complete");db.add(evidence);db.flush();run=EvidenceParseRun(org_id=target_org.id,evidence_id=evidence.id,parser_name="p",parser_version="1",run_sequence=1,status="complete",started_at=now);db.add(run);db.flush();raw=RawRecord(org_id=target_org.id,evidence_id=evidence.id,parse_run_id=run.id,ordinal=0,content="x",content_type="text/plain");db.add(raw);db.flush();event=Event(org_id=target_org.id,investigation_id=target_inv.id,evidence_id=evidence.id,raw_record_id=raw.id,normalizer_name="n",normalizer_version="1",ordinal=0,timestamp=now,normalized={});db.add(event);db.flush();indicator=Indicator(org_id=target_org.id,type="ip",normalized_value=f"203.0.113.{ord(suffix)}");db.add(indicator);db.flush();db.add(IndicatorOccurrence(org_id=target_org.id,investigation_id=target_inv.id,indicator_id=indicator.id,evidence_id=evidence.id,raw_record_id=raw.id,event_id=event.id,extractor_name="x",extractor_version="1",occurrence_ordinal=0));other=Entity(org_id=target_org.id,investigation_id=target_inv.id,type="ip",canonical_value=f"ip-{run_key}-{suffix}",display_name=f"ip-{suffix}");target=Entity(org_id=target_org.id,investigation_id=target_inv.id,type="host",canonical_value=f"h-{run_key}-{suffix}",display_name="h");db.add_all([other,target]);db.flush();db.add(EntityRelationship(org_id=target_org.id,investigation_id=target_inv.id,source_entity_id=entity.id if target_inv.id==inv.id else other.id,target_entity_id=other.id if target_inv.id==inv.id else target.id,relationship_type="observed",derivation_name="t",derivation_version="1",source_locator_hash=f"h-{run_key}-{suffix}",evidence_id=evidence.id,raw_record_id=raw.id,event_id=event.id));
  return evidence
 facts(org,inv,"a")
 # Legacy timeline/evidence models deliberately do not participate in FACT metrics.
 from app.modules.investigations.infrastructure.models import Evidence, EvidenceType, TimelineEvent
 db.add(Evidence(investigation_id=inv.id,type=EvidenceType.IP,value="legacy"));db.add(TimelineEvent(investigation_id=inv.id,occurred_at=now,description="legacy"));
 other_inv=Investigation(org_id=org.id,title="other",source="t",severity=Severity.MEDIUM,status=InvestigationStatus.NEW);db.add(other_inv);db.flush();facts(org,other_inv,"b")
 other_org,_,other_case,_=setup(db);facts(other_org,other_case,"c");db.commit()
 headers={"Authorization":f"Bearer {create_access_token(user.id,org.id,'analyst',['investigation:read'])}"};response=TestClient(app).get(f"/api/v1/investigations/{inv.id}/overview",headers=headers);assert response.status_code==200;body=response.json();assert body=={"evidence_count":1,"raw_record_count":1,"event_count":1,"indicator_count":1,"entity_count":3,"relationship_count":1,"findings_count":0,"confirmed_mitre_count":0,"latest_aiie_status":"NOT_RUN"}
def test_http_a6_end_to_end_workflow_and_provenance(db):
 org,user,inv,entity=setup(db);analysis=asyncio.run(InvestigationIntelligenceService(db,Provider()).run(org.id,inv.id));observation=db.scalar(select(IntelligenceItem).where(IntelligenceItem.org_id==org.id,IntelligenceItem.analysis_id==analysis.id,IntelligenceItem.kind=="OBSERVATION"));hypothesis=db.scalar(select(IntelligenceItem).where(IntelligenceItem.org_id==org.id,IntelligenceItem.analysis_id==analysis.id,IntelligenceItem.kind=="HYPOTHESIS"));InvestigationIntelligenceService(db).review(org.id,observation.id,user.id,"APPROVED","approved");headers={"Authorization":f"Bearer {create_access_token(user.id,org.id,'analyst',['investigation:read','investigation:write'])}"};client=TestClient(app)
 converted=client.post(f"/api/v1/investigations/intelligence/items/{observation.id}/finding",json={},headers=headers);assert converted.status_code==200;finding=converted.json();assert finding["source_intelligence_item_id"]==str(observation.id) and finding["fact_links"][0]["fact_id"]==str(entity.id)
 found=client.get(f"/api/v1/investigations/{inv.id}/findings",headers=headers);assert found.status_code==200 and found.json()[0]["id"]==finding["id"]
 changed=client.post(f"/api/v1/investigations/findings/{finding['id']}/status",json={"status":"CONFIRMED"},headers=headers);assert changed.status_code==200 and changed.json()["status"]=="CONFIRMED"
 mappings=client.get(f"/api/v1/investigations/{inv.id}/mitre-mappings",headers=headers);assert mappings.status_code==200 and len(mappings.json())==2 and all(row["source_intelligence_item_id"]==str(hypothesis.id) for row in mappings.json());first,second=mappings.json();assert client.post(f"/api/v1/investigations/mitre-mappings/{first['id']}/review",json={"status":"CONFIRMED","rationale":"verified"},headers=headers).status_code==200;rejected=client.post(f"/api/v1/investigations/mitre-mappings/{second['id']}/review",json={"status":"REJECTED","rationale":"not supported"},headers=headers);assert rejected.status_code==200 and rejected.json()["status"]=="REJECTED"
 overview=client.get(f"/api/v1/investigations/{inv.id}/overview",headers=headers);assert overview.status_code==200 and overview.json()["findings_count"]==1 and overview.json()["confirmed_mitre_count"]==1 and overview.json()["latest_aiie_status"]=="COMPLETED"
 audit=client.get(f"/api/v1/investigations/{inv.id}/audit",headers=headers);assert audit.status_code==200;actions={row["action"] for row in audit.json()};assert {"FINDING_CREATED_FROM_AI","FINDING_STATUS_CHANGED","MITRE_CONFIRMED","MITRE_REJECTED"}.issubset(actions);assert db.get(Entity,entity.id).canonical_value==entity.canonical_value
