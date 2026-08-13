import json
import pytest
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import func, select

from app.modules.ai_reasoning.domain.reconstruction_gaps import ReconstructionGapPolicy, analyze
from app.modules.ai_reasoning.domain.reconstruction_gaps import ReconstructionGapReader
from app.modules.evidence.infrastructure.models import EvidenceItem, EvidenceParseRun, RawRecord
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.infrastructure.models import Investigation, InvestigationStatus, Severity
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
    db.add(raw); db.commit()
    counts=[db.scalar(select(func.count()).select_from(model)) for model in (EvidenceItem,EvidenceParseRun,RawRecord)]
    first=ReconstructionGapReader(db).reconstruct(org.id,inv.id)
    with SessionLocal() as fresh: second=ReconstructionGapReader(fresh).reconstruct(org.id,inv.id)
    assert first == second
    assert {gap["code"] for gap in first["gaps"]} >= {"PARSER_FAILED","RAW_CONTENT_UNAVAILABLE","PROMOTION_MISSING"}
    assert counts == [db.scalar(select(func.count()).select_from(model)) for model in (EvidenceItem,EvidenceParseRun,RawRecord)]
    with pytest.raises(NotFoundError): ReconstructionGapReader(db).reconstruct(uuid4(),inv.id)
