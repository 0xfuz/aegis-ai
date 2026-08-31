"""PostgreSQL/API contracts for the bounded canonical Timeline projection."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from app.core.security import create_access_token
from app.main import app
from app.modules.evidence.infrastructure.models import AuditEvent, Event, EvidenceItem, EvidenceParseRun, RawRecord
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.infrastructure.models import Investigation, InvestigationStatus, Severity
from app.shared.database import SessionLocal


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback(); session.close()


def scope(db, prefix="timeline"):
    suffix = uuid4().hex
    org = Organization(name=f"{prefix}-{suffix}", slug=f"{prefix}-{suffix}")
    role = Role(name=f"{prefix}-role-{suffix}")
    db.add_all((org, role)); db.flush()
    user = User(org_id=org.id, role_id=role.id, email=f"{suffix}@test.invalid", hashed_password="x", full_name="Timeline analyst")
    investigation = Investigation(org_id=org.id, title="Timeline case", source="test", severity=Severity.MEDIUM, status=InvestigationStatus.NEW)
    db.add_all((user, investigation)); db.commit()
    return org, user, investigation


def headers(user, org, permissions=("investigation:read",)):
    return {"Authorization": f"Bearer {create_access_token(user.id, org.id, 'analyst', permissions)}"}


def chain(db, org, investigation, user, *, suffix, timestamp, event_id=None, content="safe", locator=None, status="complete"):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    evidence = EvidenceItem(org_id=org.id, investigation_id=investigation.id, original_filename=f"{suffix}.log", storage_key=uuid4().hex, sha256=(suffix * 64)[:64], byte_size=1, detected_mime="text/plain", extension=".log", acquisition_source="test", imported_by_id=user.id, imported_at=now, parsing_status=status)
    db.add(evidence); db.flush()
    parse = EvidenceParseRun(org_id=org.id, evidence_id=evidence.id, parser_name="parser", parser_version="1", run_sequence=1, status=status, started_at=now)
    db.add(parse); db.flush()
    raw = RawRecord(org_id=org.id, evidence_id=evidence.id, parse_run_id=parse.id, ordinal=0, content=content, content_locator=locator, content_type="text/plain")
    db.add(raw); db.flush()
    row = Event(id=event_id or uuid4(), org_id=org.id, investigation_id=investigation.id, evidence_id=evidence.id, raw_record_id=raw.id, normalizer_name="normalizer", normalizer_version="1", ordinal=0, timestamp=timestamp, source="safe-source", host="safe-host", user="safe-user", source_ip="192.0.2.10", destination_ip="198.51.100.20", event_type="authentication", deterministic_severity="medium", normalized={"secret": "never-return"})
    db.add(row); db.commit()
    return evidence, raw, row


def path(investigation, suffix=""):
    return f"/api/v1/investigations/{investigation.id}/timeline{suffix}"


def test_timeline_orders_source_timestamps_with_id_tiebreak_and_missing_last(db):
    org, user, investigation = scope(db)
    at = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    _first_evidence, _raw, first = chain(db, org, investigation, user, suffix="a", timestamp=at, event_id=UUID("00000000-0000-0000-0000-000000000001"), locator={"line": 1})
    _second_evidence, _raw, second = chain(db, org, investigation, user, suffix="b", timestamp=at, event_id=UUID("00000000-0000-0000-0000-000000000002"), locator=None)
    _missing_evidence, _raw, missing = chain(db, org, investigation, user, suffix="c", timestamp=None, content=None, locator={"line": 1})
    response = TestClient(app).get(path(investigation), headers=headers(user, org))
    assert response.status_code == 200
    body = response.json()
    assert [row["id"] for row in body["items"]] == [str(first.id), str(second.id), str(missing.id)]
    assert body["items"][0]["timestamp"].endswith(("Z", "+00:00")) and body["items"][0]["time_basis"] == "SOURCE_EVENT_TIMESTAMP"
    assert body["items"][1]["provenance_status"] == "RAW_LOCATOR_UNAVAILABLE"
    assert body["items"][2]["timestamp"] is None and body["items"][2]["time_basis"] == "UNAVAILABLE"
    assert body["items"][2]["provenance_status"] == "RAW_CONTENT_UNAVAILABLE"
    assert "never-return" not in str(body) and "normalized" not in str(body) and "storage_key" not in str(body)


def test_timeline_pagination_range_evidence_filter_and_scope(db):
    org, user, investigation = scope(db)
    at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first_evidence, _raw, first = chain(db, org, investigation, user, suffix="d", timestamp=at)
    _second_evidence, _raw, second = chain(db, org, investigation, user, suffix="e", timestamp=at + timedelta(hours=1))
    client = TestClient(app)
    base = path(investigation)
    result = client.get(f"{base}?limit=1&offset=0", headers=headers(user, org)).json()
    next_page = client.get(f"{base}?limit=1&offset=1", headers=headers(user, org)).json()
    assert result["total"] == 2 and result["returned_count"] == 1 and result["items"][0]["id"] == str(first.id)
    assert next_page["items"][0]["id"] == str(second.id)
    ranged = client.get(f"{base}?from=2026-01-01T00:00:00%2B00:00&to=2026-01-01T01:00:00%2B00:00", headers=headers(user, org))
    assert ranged.status_code == 200 and [row["id"] for row in ranged.json()["items"]] == [str(first.id)]
    filtered = client.get(f"{base}?evidence_id={first_evidence.id}", headers=headers(user, org))
    assert filtered.status_code == 200 and [row["id"] for row in filtered.json()["items"]] == [str(first.id)]
    other_org, _other_user, other_investigation = scope(db, "other")
    foreign_evidence, _raw, _event = chain(db, other_org, other_investigation, _other_user, suffix="f", timestamp=at)
    assert client.get(f"{base}?evidence_id={foreign_evidence.id}", headers=headers(user, org)).status_code == 404


@pytest.mark.parametrize("suffix", ["?from=2026-01-01T00:00:00&to=2026-01-01T01:00:00", "?from=2026-01-01T00:00:00%2B00:00", "?from=123&to=2026-01-01T01:00:00%2B00:00", "?from=2026-01-01T00:00:00%2B00:00&from=2026-01-01T00:01:00%2B00:00&to=2026-01-01T01:00:00%2B00:00", "?from=2026-01-02T00:00:00%2B00:00&to=2026-01-01T00:00:00%2B00:00", "?from=2026-01-01T00:00:00%2B00:00&to=2026-05-01T00:00:00%2B00:00", "?host=unsafe", "?limit=0", "?evidence_id=not-a-uuid"])
def test_timeline_rejects_unsafe_or_unsupported_query(db, suffix):
    org, user, investigation = scope(db)
    assert TestClient(app).get(path(investigation, suffix), headers=headers(user, org)).status_code == 422


def test_timeline_enforces_active_permission_scope_and_bounded_query_count(db):
    org, user, investigation = scope(db)
    chain(db, org, investigation, user, suffix="a1", timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
    other_org, _other_user, other_investigation = scope(db, "foreign")
    client = TestClient(app)
    assert client.get(path(investigation), headers=headers(user, org, ())).status_code == 403
    assert client.get(path(other_investigation), headers=headers(user, org)).status_code == 404
    user.is_active = False; db.commit()
    assert client.get(path(investigation), headers=headers(user, org)).status_code == 404
    user.is_active = True; db.commit()
    statements = []
    engine = SessionLocal().get_bind()
    listener = lambda *args: statements.append(args[2])
    event.listen(engine, "before_cursor_execute", listener)
    try:
        response = client.get(path(investigation), headers=headers(user, org))
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    # Principal activity/permission checks, scope lookup, count, and one joined
    # page query remain bounded; the page does not fan out per Event.
    assert response.status_code == 200 and len(statements) <= 8


def test_timeline_empty_is_distinct_from_error_and_read_has_no_side_effects(db):
    org, user, investigation = scope(db)
    client = TestClient(app)
    before = {
        "events": db.scalar(select(func.count()).select_from(Event)),
        "raw_records": db.scalar(select(func.count()).select_from(RawRecord)),
        "audit": db.scalar(select(func.count()).select_from(AuditEvent)),
    }
    response = client.get(path(investigation), headers=headers(user, org))
    assert response.status_code == 200
    assert response.json() == {"items": [], "limit": 50, "offset": 0, "returned_count": 0, "total": 0}
    after = {
        "events": db.scalar(select(func.count()).select_from(Event)),
        "raw_records": db.scalar(select(func.count()).select_from(RawRecord)),
        "audit": db.scalar(select(func.count()).select_from(AuditEvent)),
    }
    assert after == before


def test_timeline_allowlists_bounded_inert_fields_and_route_is_read_only(db):
    org, user, investigation = scope(db)
    evidence, _raw, row = chain(db, org, investigation, user, suffix="d1", timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
    row.source = "<script>inert</script>"
    row.host = "host-" + "x" * 250
    db.commit()
    response = TestClient(app).get(path(investigation), headers=headers(user, org))
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["source"] == "<script>inert</script>"
    assert len(item["host"]) <= 255
    assert item["evidence"] == {"id": str(evidence.id), "filename": "d1.log"}
    assert set(item) == {
        "id", "timestamp", "time_basis", "event_type", "source", "host", "user", "source_ip",
        "destination_ip", "deterministic_severity", "evidence", "raw_content_available",
        "raw_locator_available", "provenance_status",
    }
    matches = [route for route in app.routes if getattr(route, "path", None) == "/api/v1/investigations/{investigation_id}/timeline"]
    assert len(matches) == 1 and matches[0].methods == {"GET"}
