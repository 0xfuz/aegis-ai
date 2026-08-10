from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.evidence.domain.service import EvidenceIngestionService
from app.modules.evidence.infrastructure.models import AuditEvent, EntityRelationship, Event, EvidenceItem, EvidenceParseRun, IndicatorOccurrence
from app.modules.evidence.infrastructure.repository import EvidenceRepository
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.infrastructure.models import Investigation, InvestigationStatus, Severity
from app.shared.database import SessionLocal
from app.shared.exceptions import ConflictError, ValidationError

FIXTURES = Path(__file__).parent / "fixtures" / "evidence"


class Upload:
    def __init__(self, filename: str, content: bytes, content_type: str = "text/plain"):
        self.filename = filename
        self.content_type = content_type
        self.file = BytesIO(content)


def _context(db, suffix=None):
    suffix = suffix or str(uuid4())
    role = Role(name=f"evidence-role-{suffix}", description="test")
    org = Organization(name=f"Evidence {suffix}", slug=f"evidence-{suffix}")
    db.add_all([role, org]); db.flush()
    user = User(org_id=org.id, role_id=role.id, email=f"{suffix}@example.test", hashed_password="x", full_name="Evidence Tester")
    investigation = Investigation(org_id=org.id, title="Evidence test", source="pytest", severity=Severity.MEDIUM, status=InvestigationStatus.NEW)
    db.add_all([user, investigation]); db.commit()
    return org, user, investigation


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback(); session.close()


def _service(db, tmp_path, **limits):
    return EvidenceIngestionService(db, Settings(EVIDENCE_STORAGE_DIR=str(tmp_path), **limits))


def test_ingestion_persists_complete_fact_chain_and_provenance(db, tmp_path):
    org, user, investigation = _context(db)
    upload = Upload("auth.log", (FIXTURES / "auth.log").read_bytes())
    evidence = _service(db, tmp_path).ingest(org.id, investigation.id, user.id, upload)

    assert evidence.parsing_status == "complete"
    assert evidence.sha256 == __import__("hashlib").sha256((FIXTURES / "auth.log").read_bytes()).hexdigest()
    assert db.query(EvidenceParseRun).filter_by(evidence_id=evidence.id, status="complete").count() == 1
    assert db.query(Event).filter_by(evidence_id=evidence.id).count() == 2
    assert db.query(IndicatorOccurrence).filter_by(evidence_id=evidence.id).count() >= 2
    assert db.query(EntityRelationship).filter_by(evidence_id=evidence.id).count() >= 2
    assert {row.action for row in db.query(AuditEvent).filter_by(investigation_id=investigation.id)} >= {"EVIDENCE_ACCEPTED", "PARSE_STARTED", "PARSE_COMPLETED"}


def test_duplicate_rejected_and_storage_cleaned(db, tmp_path):
    org, user, investigation = _context(db)
    content = (FIXTURES / "dns.json").read_bytes()
    service = _service(db, tmp_path)
    service.ingest(org.id, investigation.id, user.id, Upload("dns.json", content, "application/json"))
    with pytest.raises(ConflictError):
        service.ingest(org.id, investigation.id, user.id, Upload("copy.json", content, "application/json"))
    assert len(list(tmp_path.iterdir())) == 1
    assert db.query(EvidenceItem).filter_by(investigation_id=investigation.id).count() == 1
    assert db.query(AuditEvent).filter_by(investigation_id=investigation.id, action="EVIDENCE_DUPLICATE").count() == 1


@pytest.mark.parametrize("upload", [
    Upload("../../escape.log", b"hello"), Upload("empty.log", b""), Upload("sample.exe", b"hello"),
    Upload("sample.json", b"{}", "image/png"),
])
def test_rejects_unsafe_or_invalid_uploads(db, tmp_path, upload):
    org, user, investigation = _context(db)
    with pytest.raises(ValidationError):
        _service(db, tmp_path).ingest(org.id, investigation.id, user.id, upload)
    assert not tmp_path.exists() or list(tmp_path.iterdir()) == []


def test_oversized_evidence_is_rejected(db, tmp_path):
    org, user, investigation = _context(db)
    with pytest.raises(ValidationError):
        _service(db, tmp_path, MAX_EVIDENCE_BYTES=4).ingest(org.id, investigation.id, user.id, Upload("large.log", b"12345"))


def test_limits_parse_failure_and_no_partial_active_facts(db, tmp_path):
    org, user, investigation = _context(db)
    service = _service(db, tmp_path, MAX_RAW_RECORDS=1)
    with pytest.raises(ValidationError):
        service.ingest(org.id, investigation.id, user.id, Upload("auth.log", (FIXTURES / "auth.log").read_bytes()))
    evidence = db.query(EvidenceItem).filter_by(investigation_id=investigation.id).one()
    assert evidence.parsing_status == "failed"
    assert db.query(Event).filter_by(evidence_id=evidence.id).count() == 0
    assert db.query(EvidenceParseRun).filter_by(evidence_id=evidence.id, status="failed").count() == 1


def test_invalid_encoding_and_json_depth_fail_without_events(db, tmp_path):
    org, user, investigation = _context(db)
    with pytest.raises(ValidationError):
        _service(db, tmp_path).ingest(org.id, investigation.id, user.id, Upload("invalid.log", b"\xff\xfe"))
    failed = db.query(EvidenceItem).filter_by(investigation_id=investigation.id).one()
    assert failed.parsing_status == "failed"
    assert db.query(Event).filter_by(evidence_id=failed.id).count() == 0

    org, user, investigation = _context(db)
    too_deep = ("[" * 5 + "0" + "]" * 5).encode()
    with pytest.raises(ValidationError):
        _service(db, tmp_path, MAX_JSON_DEPTH=2).ingest(org.id, investigation.id, user.id, Upload("deep.json", too_deep, "application/json"))


def test_cross_org_and_cross_investigation_reads_are_scoped(db, tmp_path):
    org, user, investigation = _context(db)
    evidence = _service(db, tmp_path).ingest(org.id, investigation.id, user.id, Upload("connections.csv", (FIXTURES / "connections.csv").read_bytes(), "text/csv"))
    other_org, _other_user, other_investigation = _context(db)
    repo = EvidenceRepository(db)
    assert repo.get_evidence(other_org.id, investigation.id, evidence.id) is None
    assert repo.get_evidence(org.id, other_investigation.id, evidence.id) is None
