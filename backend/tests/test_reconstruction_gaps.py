import json
import pytest
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import func, select

from app.modules.ai_reasoning.domain.context_builder import ContextBuilder, ContextPolicy
from app.modules.ai_reasoning.domain.reconstruction_gaps import ReconstructionGapPolicy, analyze
from app.modules.ai_reasoning.domain.reconstruction_gaps import ReconstructionGapReader
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis, IntelligenceClaimEvidenceLink, IntelligenceEvidenceReference, IntelligenceItem
from app.modules.alert_triage.infrastructure.models import AlertClusterAssessment, AlertClusterMembership, AlertClusterPromotion
from app.modules.evidence.infrastructure.models import EvidenceItem, EvidenceParseRun, RawRecord
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
