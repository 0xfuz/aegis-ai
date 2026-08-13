import json
import pytest
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import func, select, text

from app.modules.ai_reasoning.domain.context_builder import ContextBuilder, ContextPolicy
from app.modules.ai_reasoning.domain.reconstruction_gaps import ReconstructionGapPolicy, analyze
from app.modules.ai_reasoning.domain.reconstruction_gaps import ReconstructionGapReader
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis, IntelligenceClaimEvidenceLink, IntelligenceEvidenceReference, IntelligenceItem
from app.modules.alert_triage.infrastructure.models import AlertClusterAssessment, AlertClusterMembership, AlertClusterPromotion
from app.modules.alert_triage.infrastructure.models import AlertCluster, AlertClusterAssessment, AlertClusterMembership, AlertClusterPromotion, CanonicalAlert
from app.modules.connectors.infrastructure.models import Connector, RawEvent
from app.modules.evidence.infrastructure.models import Entity, EntityObservation, EntityRelationship, EvidenceItem, EvidenceParseRun, Event, RawRecord
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.infrastructure.models import Finding, Investigation, InvestigationStatus, MitreMapping, RecommendedAction, Severity
from app.shared.database import SessionLocal
from app.shared.exceptions import NotFoundError, ValidationError

def test_pure_gap_classes_omissions_uncertainty_and_determinism():
    context={"warnings":["PROMOTION_LINK_MISSING"],"omissions":[{"section":"events","reason":"LIMIT","original_count":2}]}
    temporal={"warnings":["ANCHOR_MISSING","BEFORE_ACTIVITY_NOT_OBSERVED"],"activities":[{"type":"EVENT","id":"1","uncertainty":["SOURCE_TIME_INVALID","CLOCK_SKEW_SUSPECTED"]}]}
    provenance=[{"type":"RAW_RECORD","id":"2","state":"failed","raw_unavailable":True,"locator_unresolved":True}]
    output=analyze(ReconstructionGapPolicy(),context,temporal,provenance)
    assert {gap["classification"] for gap in output["gaps"]} >= {"ABSENT","OMITTED","INVALID","UNAVAILABLE","CONTRADICTORY"}
    assert output == analyze(ReconstructionGapPolicy(),context,temporal,provenance)
    assert json.dumps(output,sort_keys=True)

def test_bounds_and_invalid_configuration():
    payload=analyze(ReconstructionGapPolicy(max_gaps=1),{}, {},[{"type":"RAW_RECORD","id":"1","state":"failed","raw_unavailable":True}])
    assert len(payload["gaps"]) == 1 and payload["omitted"] == 1
    with pytest.raises(ValidationError): ReconstructionGapPolicy(max_gaps=0)

def test_parser_taxonomy_safe_detail_and_explicit_two_sided_contradiction():
    result=analyze(ReconstructionGapPolicy(detail_limit=32),{}, {},[
        {"type":"EVIDENCE_ITEM","id":"pending","state":"pending"}, {"type":"EVIDENCE_ITEM","id":"rejected","state":"rejected"},
        {"type":"EVIDENCE_ITEM","id":"odd","state":"password=synthetic-secret"}, {"type":"EVENT","id":"one","state":"complete","contradicts":["two"]},
    ])
    codes={gap["code"] for gap in result["gaps"]}
    assert {"PARSER_INCOMPLETE","PARSER_REJECTED","PARSER_STATE_UNSUPPORTED","EXPLICIT_OBSERVATION_CONTRADICTION"} <= codes
    contradiction=next(gap for gap in result["gaps"] if gap["code"]=="EXPLICIT_OBSERVATION_CONTRADICTION")
    assert contradiction["provenance"] == ["one","two"]
    assert "synthetic-secret" not in json.dumps(result)

@pytest.fixture()
def db():
    session=SessionLocal()
    try: yield session
    finally: session.rollback(); session.close()

def test_db_parse_raw_gaps_are_scoped_read_only_and_deterministic(db):
    key=uuid4().hex; now=datetime(2026,1,1,tzinfo=timezone.utc)
    org=Organization(name=key,slug=f"gap-{key}"); role=Role(name=f"gap-role-{key}")
    db.add_all((org,role)); db.flush()
    user=User(org_id=org.id,role_id=role.id,email=f"{key}@test",hashed_password="x",full_name="test")
    inv=Investigation(org_id=org.id,title="gap",source="test",severity=Severity.LOW,status=InvestigationStatus.NEW)
    db.add_all((user,inv)); db.flush()
    evidence=EvidenceItem(org_id=org.id,investigation_id=inv.id,original_filename="safe",storage_key=f"gap-{key}",sha256="a"*64,byte_size=0,detected_mime="text/plain",extension=".log",acquisition_source="test",imported_at=now,parsing_status="failed")
    db.add(evidence); db.flush()
    run=EvidenceParseRun(org_id=org.id,evidence_id=evidence.id,parser_name="test",parser_version="1",run_sequence=1,status="failed",started_at=now)
    db.add(run); db.flush(); raw=RawRecord(org_id=org.id,evidence_id=evidence.id,parse_run_id=run.id,ordinal=1,content=None,content_locator={"safe":"locator"},content_type="text/plain")
    unresolved=RawRecord(org_id=org.id,evidence_id=evidence.id,parse_run_id=run.id,ordinal=2,content=None,content_locator={},content_type="text/plain")
    db.add_all((raw,unresolved)); db.commit()
    models=(EvidenceItem,EvidenceParseRun,RawRecord,IntelligenceAnalysis,IntelligenceItem,IntelligenceEvidenceReference,IntelligenceClaimEvidenceLink,Finding,MitreMapping,AlertClusterMembership,AlertClusterAssessment,AlertClusterPromotion,RecommendedAction)
    counts=[db.scalar(select(func.count()).select_from(model)) for model in models]
    first=ReconstructionGapReader(db).reconstruct(org.id,inv.id)
    with SessionLocal() as fresh: second=ReconstructionGapReader(fresh).reconstruct(org.id,inv.id)
    assert first == second
    assert {gap["code"] for gap in first["gaps"]} >= {"PARSER_FAILED","RAW_CONTENT_UNAVAILABLE","LOCATOR_UNRESOLVED","PROMOTION_MISSING"}
    assert counts == [db.scalar(select(func.count()).select_from(model)) for model in models]
    with pytest.raises(NotFoundError): ReconstructionGapReader(db).reconstruct(uuid4(),inv.id)

def test_real_contextbuilder_limit_omission_stays_omitted(db):
    key=uuid4().hex; now=datetime(2026,1,1,tzinfo=timezone.utc)
    org=Organization(name=key,slug=f"limit-{key}"); role=Role(name=f"limit-role-{key}")
    db.add_all((org,role)); db.flush(); inv=Investigation(org_id=org.id,title="limit",source="test",severity=Severity.LOW,status=InvestigationStatus.NEW); db.add(inv); db.flush()
    for ordinal in range(2): db.add(EvidenceItem(org_id=org.id,investigation_id=inv.id,original_filename=f"{ordinal}",storage_key=f"limit-{key}-{ordinal}",sha256=(str(ordinal)*64),byte_size=0,detected_mime="text/plain",extension=".log",acquisition_source="test",imported_at=now,parsing_status="complete"))
    db.commit()
    context=ContextBuilder(db,ContextPolicy(max_evidence=1)).build(org.id,inv.id).snapshot
    output=analyze(ReconstructionGapPolicy(),context,{"warnings":[],"activities":[]},[])
    gap=next(gap for gap in output["gaps"] if gap["code"]=="CONTEXT_OMITTED_BY_LIMIT")
    assert gap["classification"]=="OMITTED" and "TELEMETRY_ABSENT" not in {gap["code"] for gap in output["gaps"]}

def promoted_complete(db):
    key=uuid4().hex; now=datetime(2026,1,1,tzinfo=timezone.utc)
    org=Organization(name=key,slug=f"full-{key}"); role=Role(name=f"full-role-{key}"); db.add_all((org,role)); db.flush()
    user=User(org_id=org.id,role_id=role.id,email=f"{key}@test",hashed_password="x",full_name="test"); inv=Investigation(org_id=org.id,title="full",source="test",severity=Severity.LOW,status=InvestigationStatus.NEW); db.add_all((user,inv)); db.flush()
    evidence=EvidenceItem(org_id=org.id,investigation_id=inv.id,original_filename="safe",storage_key=f"full-{key}",sha256="a"*64,byte_size=0,detected_mime="text/plain",extension=".log",acquisition_source="test",imported_at=now,parsing_status="complete"); db.add(evidence); db.flush()
    parse=EvidenceParseRun(org_id=org.id,evidence_id=evidence.id,parser_name="test",parser_version="1",run_sequence=1,status="complete",started_at=now); db.add(parse); db.flush()
    raw=RawRecord(org_id=org.id,evidence_id=evidence.id,parse_run_id=parse.id,ordinal=1,content="safe",content_locator={"line":1},content_type="text/plain"); db.add(raw); db.flush()
    event=Event(org_id=org.id,investigation_id=inv.id,evidence_id=evidence.id,raw_record_id=raw.id,normalizer_name="test",normalizer_version="1",ordinal=1,timestamp=now,normalized={}); db.add(event); db.flush()
    left=Entity(org_id=org.id,investigation_id=inv.id,type="host",canonical_value="left",display_name="left"); right=Entity(org_id=org.id,investigation_id=inv.id,type="host",canonical_value="right",display_name="right"); db.add_all((left,right)); db.flush()
    obs=EntityObservation(org_id=org.id,investigation_id=inv.id,entity_id=left.id,evidence_id=evidence.id,raw_record_id=raw.id,event_id=event.id,extractor_name="test",extractor_version="1",occurrence_ordinal=1); rel=EntityRelationship(org_id=org.id,investigation_id=inv.id,source_entity_id=left.id,target_entity_id=right.id,relationship_type="seen",derivation_name="test",derivation_version="1",raw_record_id=raw.id,source_locator_hash="b"*64); db.add_all((obs,rel)); db.flush()
    connector=Connector(org_id=org.id,name="test",type="webhook",status="CONNECTED",secret_hash="x",is_active=True); db.add(connector); db.flush(); raw_event=RawEvent(connector_id=connector.id,received_at=now,payload={"safe":True},investigation_id=inv.id); db.add(raw_event); db.flush()
    alert=CanonicalAlert(org_id=org.id,connector_id=connector.id,raw_event_id=raw_event.id,source="test",source_alert_id=key,observed_at=now,ingested_at=now,title="test",description="",severity="LOW",normalized_observables={},source_metadata={},payload_digest="c"*64,normalizer_version="v1",lifecycle="CORRELATED"); db.add(alert); db.flush()
    cluster=AlertCluster(org_id=org.id,identity_key=key,correlation_version="correlation-v2",status="PROMOTED",first_seen=now,last_seen=now,member_count=1,source_diversity=1); db.add(cluster); db.flush(); membership=AlertClusterMembership(org_id=org.id,cluster_id=cluster.id,alert_id=alert.id,correlation_version="correlation-v2",score=1,reasons=[],added_at=now); db.add(membership); db.flush()
    assessment=AlertClusterAssessment(org_id=org.id,cluster_id=cluster.id,scoring_version="triage-v1",input_hash="d"*64,score=1,priority="LOW",ledger=[],reference_at=now,evaluated_at=now); db.add(assessment); db.flush(); db.add(AlertClusterPromotion(org_id=org.id,cluster_id=cluster.id,investigation_id=inv.id,evidence_id=evidence.id,actor_id=user.id,triage_assessment_id=assessment.id,export_version="v1",export_fingerprint="e"*64,manifest={"correlation_version":"correlation-v2"},status="COMPLETED",promoted_at=now)); db.commit()
    return org,inv,evidence,raw,event

def test_complete_promoted_v2_chain_has_no_false_provenance_or_lineage_gaps(db):
    org,inv,_evidence,_raw,_event=promoted_complete(db)
    output=ReconstructionGapReader(db).reconstruct(org.id,inv.id)
    forbidden={"PARSER_FAILED","PARSER_REJECTED","PARSER_INCOMPLETE","RAW_CONTENT_UNAVAILABLE","LOCATOR_UNRESOLVED","PROMOTION_MISSING","PROMOTION_CLUSTER_MISSING","EXACT_VERSION_MEMBERSHIP_MISSING","TRIAGE_PROVENANCE_MISSING","PROVENANCE_UNRESOLVED"}
    assert not ({gap["code"] for gap in output["gaps"]} & forbidden)

def test_real_total_size_omission_and_persisted_sensor_contradiction(db):
    org,inv,evidence,raw,event=promoted_complete(db)
    for ordinal in range(2,20): db.add(Event(org_id=org.id,investigation_id=inv.id,evidence_id=evidence.id,raw_record_id=raw.id,normalizer_name=f"n{ordinal}",normalizer_version="1",ordinal=ordinal,timestamp=event.timestamp,normalized={"sensor_time":f"2026-01-01T12:{ordinal:02}:00Z" if ordinal < 4 else None, "note":"x"*200}))
    db.commit()
    policy=ContextPolicy(max_events=20,max_bytes=8000,max_text=512)
    output=ReconstructionGapReader(db,context_policy=policy).reconstruct(org.id,inv.id)
    assert any(gap["code"]=="CONTEXT_OMITTED_BY_TOTAL_SIZE" and gap["classification"]=="OMITTED" for gap in output["gaps"])
    contradictions=[gap for gap in output["gaps"] if gap["code"]=="EXPLICIT_OBSERVATION_CONTRADICTION"]
    assert contradictions and all(len(gap["provenance"])==2 for gap in contradictions)

@pytest.mark.parametrize("case,warning,gap,classification,severity", [
    ("no_promotion", "PROMOTION_LINK_MISSING", "PROMOTION_MISSING", "ABSENT", "WARNING"),
    ("v1", "CORRELATION_V1_CONTEXT_UNSUPPORTED", "CORRELATION_VERSION_UNSUPPORTED", "UNSUPPORTED", "BLOCKING"),
    ("unknown", "CORRELATION_VERSION_UNSUPPORTED", "CORRELATION_VERSION_UNSUPPORTED", "UNSUPPORTED", "BLOCKING"),
    ("missing_members", "CORRELATION_V2_MEMBERSHIP_MISSING", "EXACT_VERSION_MEMBERSHIP_MISSING", "INCOMPLETE", "BLOCKING"),
    ("triage_other_cluster", "TRIAGE_LINK_MISSING", "TRIAGE_PROVENANCE_MISSING", "INCOMPLETE", "WARNING"),
])
def test_persisted_promotion_provenance_gap_matrix(db, case, warning, gap, classification, severity):
    org,inv,evidence,_raw,_event=promoted_complete(db)
    promotion=db.scalar(select(AlertClusterPromotion).where(AlertClusterPromotion.investigation_id==inv.id))
    cluster=db.get(AlertCluster,promotion.cluster_id)
    if case=="no_promotion": db.delete(promotion)
    elif case in {"v1","unknown"}:
        cluster.correlation_version="correlation-v1" if case=="v1" else "correlation-x"; promotion.manifest={"correlation_version":cluster.correlation_version}
    elif case=="missing_members": db.query(AlertClusterMembership).filter(AlertClusterMembership.cluster_id==cluster.id).delete()
    elif case=="triage_other_cluster":
        other=AlertCluster(org_id=org.id,identity_key=uuid4().hex,correlation_version="correlation-v2",status="OPEN",first_seen=promotion.promoted_at,last_seen=promotion.promoted_at,member_count=0,source_diversity=0); db.add(other); db.flush()
        assessment=AlertClusterAssessment(org_id=org.id,cluster_id=other.id,scoring_version="triage-v1",input_hash="f"*64,score=1,priority="LOW",ledger=[],reference_at=promotion.promoted_at,evaluated_at=promotion.promoted_at); db.add(assessment); db.flush(); promotion.triage_assessment_id=assessment.id
    db.commit()
    models=(AlertClusterPromotion,AlertCluster,AlertClusterMembership,AlertClusterAssessment,IntelligenceAnalysis,IntelligenceItem,IntelligenceEvidenceReference,IntelligenceClaimEvidenceLink,Finding,MitreMapping,RecommendedAction)
    before=[db.scalar(select(func.count()).select_from(model)) for model in models]
    context=ContextBuilder(db).build(org.id,inv.id).snapshot
    assert warning in [entry.get("code") if isinstance(entry,dict) else entry for entry in context["warnings"]]
    first=ReconstructionGapReader(db).reconstruct(org.id,inv.id)
    with SessionLocal() as fresh: second=ReconstructionGapReader(fresh).reconstruct(org.id,inv.id)
    row=next(entry for entry in first["gaps"] if entry["code"]==gap)
    assert first==second and (row["classification"],row["severity"])==(classification,severity)
    assert before==[db.scalar(select(func.count()).select_from(model)) for model in models]

def test_promotion_cluster_and_missing_triage_links_are_fk_not_applicable(db):
    org,inv,_evidence,_raw,_event=promoted_complete(db)
    promotion=db.scalar(select(AlertClusterPromotion).where(AlertClusterPromotion.investigation_id==inv.id))
    # Both columns are non-null RESTRICT foreign keys; a dangling persisted link cannot exist.
    with pytest.raises(Exception):
        db.execute(text("UPDATE alert_cluster_promotions SET cluster_id = '00000000-0000-0000-0000-000000000001' WHERE id = :id"), {"id":str(promotion.id)}); db.commit()
    db.rollback()
    with pytest.raises(Exception):
        db.execute(text("UPDATE alert_cluster_promotions SET triage_assessment_id = '00000000-0000-0000-0000-000000000001' WHERE id = :id"), {"id":str(promotion.id)}); db.commit()
    db.rollback()
