from datetime import datetime, timezone
from uuid import uuid4
import json, pytest
from sqlalchemy import func, select
from app.modules.ai_reasoning.domain.reconstruction_read_service import ReconstructionReadPolicy, ReconstructionReadService
from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis, IntelligenceClaimEvidenceLink, IntelligenceEvidenceReference, IntelligenceItem
from app.modules.evidence.infrastructure.models import EvidenceItem, EvidenceParseRun, Event, RawRecord
from app.modules.identity.infrastructure.models import Organization, Role
from app.modules.investigations.infrastructure.models import Finding, Investigation, InvestigationStatus, MitreMapping, RecommendedAction, Severity
from app.shared.database import SessionLocal
from app.shared.exceptions import NotFoundError, ValidationError

@pytest.fixture()
def db():
 s=SessionLocal()
 try: yield s
 finally: s.rollback();s.close()
def fixture(db):
 key=uuid4().hex; now=datetime(2026,1,1,tzinfo=timezone.utc); org=Organization(name=key,slug=f"read-{key}"); role=Role(name=f"read-role-{key}");db.add_all((org,role));db.flush();inv=Investigation(org_id=org.id,title="read",source="test",severity=Severity.LOW,status=InvestigationStatus.NEW);db.add(inv);db.flush();e=EvidenceItem(org_id=org.id,investigation_id=inv.id,original_filename="safe",storage_key=key,sha256="a"*64,byte_size=0,detected_mime="text/plain",extension=".log",acquisition_source="test",imported_at=now,parsing_status="complete");db.add(e);db.flush();p=EvidenceParseRun(org_id=org.id,evidence_id=e.id,parser_name="test",parser_version="1",run_sequence=1,status="complete",started_at=now);db.add(p);db.flush();r=RawRecord(org_id=org.id,evidence_id=e.id,parse_run_id=p.id,ordinal=1,content="secret=never-exposed",content_locator={"line":1},content_type="text/plain");db.add(r);db.flush();db.add(Event(org_id=org.id,investigation_id=inv.id,evidence_id=e.id,raw_record_id=r.id,normalizer_name="test",normalizer_version="1",ordinal=1,timestamp=now,normalized={"token":"never-exposed"}));db.commit();return org,inv
def test_read_projection_is_scoped_bounded_deterministic_and_write_free(db):
 org,inv=fixture(db); models=(IntelligenceAnalysis,IntelligenceItem,IntelligenceEvidenceReference,IntelligenceClaimEvidenceLink,Finding,MitreMapping,RecommendedAction);before=[db.scalar(select(func.count()).select_from(x)) for x in models]
 first=ReconstructionReadService(db).read(org.id,inv.id)
 with SessionLocal() as fresh: second=ReconstructionReadService(fresh).read(org.id,inv.id)
 assert first==second and "never-exposed" not in json.dumps(first)
 assert first["sections"]["events"] and first["sections"]["raw_records"][0]["locator"]=={"line":1}
 assert before==[db.scalar(select(func.count()).select_from(x)) for x in models]
 with pytest.raises(NotFoundError): ReconstructionReadService(db).read(uuid4(),inv.id)
def test_bounds_reject_unsafe_policy():
 with pytest.raises(ValidationError): ReconstructionReadPolicy(per_section=0)
