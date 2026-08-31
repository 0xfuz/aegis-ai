"""PostgreSQL contracts for bounded U3-A Investigation projections."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from app.modules.evidence.infrastructure.models import EvidenceItem, EvidenceParseRun, Event, RawRecord
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.infrastructure.models import Investigation, InvestigationStatus, Severity
from app.shared.database import SessionLocal


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def scope(db, name="u3"):
    suffix = uuid4().hex
    org = Organization(name=f"{name}-{suffix}", slug=f"{name}-{suffix}")
    role = Role(name=f"{name}-role-{suffix}")
    db.add_all((org, role)); db.flush()
    user = User(org_id=org.id, role_id=role.id, email=f"{suffix}@test.invalid", hashed_password="x", full_name="Evidence analyst")
    investigation = Investigation(org_id=org.id, title="Bounded case", source="test", severity=Severity.HIGH, status=InvestigationStatus.INVESTIGATING)
    db.add_all((user, investigation)); db.commit()
    return org, user, investigation


def headers(user, org, permissions=("investigation:read",)):
    return {"Authorization": f"Bearer {create_access_token(user.id, org.id, 'analyst', permissions)}"}


def evidence_chain(db, org, investigation, user, filename, imported_at, status="complete", content="never expose raw", warnings=None):
    token = uuid4().hex
    item = EvidenceItem(org_id=org.id, investigation_id=investigation.id, original_filename=filename, storage_key=token, sha256=(token * 2)[:64], byte_size=9, detected_mime="text/plain", extension=".log", source_description="<script>unsafe</script>", acquisition_source="test", imported_by_id=user.id, imported_at=imported_at, parsing_status=status)
    db.add(item); db.flush()
    run = EvidenceParseRun(org_id=org.id, evidence_id=item.id, parser_name="parser", parser_version="1", run_sequence=1, status=status, started_at=imported_at, warnings=warnings)
    db.add(run); db.flush()
    raw = RawRecord(org_id=org.id, evidence_id=item.id, parse_run_id=run.id, ordinal=0, content=content, content_type="text/plain")
    db.add(raw); db.flush()
    db.add(Event(org_id=org.id, investigation_id=investigation.id, evidence_id=item.id, raw_record_id=raw.id, normalizer_name="normalizer", normalizer_version="1", ordinal=0, timestamp=imported_at, normalized={}))
    db.commit()
    return item


def test_overview_is_bounded_deterministic_and_omits_sensitive_state(db):
    org, user, investigation = scope(db)
    evidence_chain(db, org, investigation, user, "hostile <b>name</b>.log", datetime(2026, 1, 1, tzinfo=timezone.utc), content="secret raw body")
    client = TestClient(app)
    path = f"/api/v1/investigations/{investigation.id}/overview"
    first = client.get(path, headers=headers(user, org))
    second = client.get(path, headers=headers(user, org))
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    body = first.json()
    assert body["investigation"]["title"] == "Bounded case"
    assert body["counts"]["evidence_items"] == body["counts"]["raw_records"] == body["counts"]["events"] == 1
    assert "secret raw body" not in str(body) and "root_cause" not in str(body) and "org_id" not in str(body)


def test_overview_and_inventory_enforce_scoped_active_read_access(db):
    org, user, investigation = scope(db)
    other_org, other_user, other_investigation = scope(db, "other")
    inactive = User(org_id=org.id, role_id=user.role_id, email=f"inactive-{uuid4().hex}@test.invalid", hashed_password="x", full_name="Inactive", is_active=False)
    db.add(inactive); db.commit()
    client = TestClient(app)
    assert client.get(f"/api/v1/investigations/{other_investigation.id}/overview", headers=headers(user, org)).status_code == 404
    assert client.get(f"/api/v1/investigations/{other_investigation.id}/evidence/inventory", headers=headers(user, org)).status_code == 404
    assert client.get(f"/api/v1/investigations/{investigation.id}/overview", headers=headers(inactive, org)).status_code == 404
    assert client.get(f"/api/v1/investigations/{investigation.id}/evidence/inventory", headers=headers(user, org, ())).status_code == 403


def test_evidence_inventory_is_server_ordered_bounded_and_raw_free(db):
    org, user, investigation = scope(db)
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = evidence_chain(db, org, investigation, user, "first.log", timestamp, warnings=["safe warning"])
    second = evidence_chain(db, org, investigation, user, "second.log", timestamp, status="failed", content="raw never returned")
    client = TestClient(app)
    base = f"/api/v1/investigations/{investigation.id}/evidence/inventory"
    response = client.get(f"{base}?limit=1&offset=0", headers=headers(user, org))
    assert response.status_code == 200
    page = response.json()
    assert page["limit"] == 1 and page["offset"] == 0 and page["total"] == 2
    assert page["items"][0]["id"] == str(max((first, second), key=lambda row: str(row.id)).id)
    item = page["items"][0]
    assert set(item) == {"id", "filename", "detected_mime", "byte_size", "sha256", "acquisition_source", "imported_at", "parsing_status", "latest_parse_status", "parser_name", "parser_version", "parse_warning_count", "raw_record_count", "raw_content_unavailable_count", "event_count", "importer"}
    assert item["raw_record_count"] == item["event_count"] == 1
    assert "raw never returned" not in str(page) and "source_description" not in str(page)
    assert client.get(f"{base}?limit=0", headers=headers(user, org)).status_code == 422
    assert client.get(f"{base}?unknown=value", headers=headers(user, org)).status_code == 422


def test_raw_records_remain_separate_authorized_workflow(db):
    org, user, investigation = scope(db)
    item = evidence_chain(db, org, investigation, user, "safe.log", datetime.now(timezone.utc), content="bounded existing workflow")
    client = TestClient(app)
    inventory = client.get(f"/api/v1/investigations/{investigation.id}/evidence/inventory", headers=headers(user, org)).json()
    assert "bounded existing workflow" not in str(inventory)
    raw = client.get(f"/api/v1/investigations/{investigation.id}/evidence/{item.id}/raw-records", headers=headers(user, org))
    assert raw.status_code == 200 and raw.json()[0]["content"] == "bounded existing workflow"


def test_inventory_distinguishes_unavailable_raw_content_from_empty_parse(db):
    org, user, investigation = scope(db)
    item = evidence_chain(db, org, investigation, user, "locator-only.log", datetime.now(timezone.utc), status="complete")
    raw = db.query(RawRecord).filter_by(evidence_id=item.id).one()
    raw.content = None
    raw.content_locator = {"line": 1}
    db.commit()
    response = TestClient(app).get(f"/api/v1/investigations/{investigation.id}/evidence/inventory", headers=headers(user, org))
    assert response.status_code == 200
    row = response.json()["items"][0]
    assert row["raw_record_count"] == 1 and row["raw_content_unavailable_count"] == 1 and row["event_count"] == 1
