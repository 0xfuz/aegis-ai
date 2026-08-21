"""PostgreSQL contracts for bounded Entity/Indicator occurrence reads."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from app.modules.evidence.infrastructure.models import Entity, EntityObservation, Event, EvidenceItem, EvidenceParseRun, Indicator, IndicatorOccurrence, RawRecord
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.infrastructure.models import Investigation, InvestigationStatus, Severity
from app.shared.database import SessionLocal


@pytest.fixture()
def db():
    session = SessionLocal()
    try: yield session
    finally: session.rollback(); session.close()


def seed(db, name="scope"):
    token = uuid4().hex; org = Organization(name=f"{name}-{token}", slug=f"{name}-{token}"); role = Role(name=f"{name}-role-{token}")
    db.add_all((org, role)); db.flush(); user = User(org_id=org.id, role_id=role.id, email=f"{token}@test.invalid", hashed_password="x", full_name="Reader")
    investigation = Investigation(org_id=org.id, title="Case", source="test", severity=Severity.MEDIUM, status=InvestigationStatus.NEW); db.add_all((user, investigation)); db.commit(); return org, user, investigation


def header(user, org, permissions=("investigation:read",)):
    return {"Authorization": f"Bearer {create_access_token(user.id, org.id, 'analyst', permissions)}"}


def occurrence(db, org, investigation, user, *, suffix="a", observed=None, raw_content="safe"):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc); evidence = EvidenceItem(org_id=org.id, investigation_id=investigation.id, original_filename=f"{suffix}.log", storage_key=uuid4().hex, sha256=("a" if suffix == "a" else "b") * 64, byte_size=1, detected_mime="text/plain", extension=".log", acquisition_source="test", imported_by_id=user.id, imported_at=now, parsing_status="complete"); db.add(evidence); db.flush()
    parse = EvidenceParseRun(org_id=org.id, evidence_id=evidence.id, parser_name="safe", parser_version="1", run_sequence=1, status="complete", started_at=now); db.add(parse); db.flush()
    raw = RawRecord(org_id=org.id, evidence_id=evidence.id, parse_run_id=parse.id, ordinal=0, content=raw_content, content_locator={"line": 1}, content_type="text/plain"); db.add(raw); db.flush()
    event = Event(org_id=org.id, investigation_id=investigation.id, evidence_id=evidence.id, raw_record_id=raw.id, normalizer_name="safe", normalizer_version="1", ordinal=0, timestamp=observed, normalized={"raw": "never-return"}); db.add(event); db.flush()
    entity = Entity(org_id=org.id, investigation_id=investigation.id, type="host", canonical_value=f"host-{suffix}", display_name=f"<b>host-{suffix}</b>"); db.add(entity); db.flush()
    observation = EntityObservation(org_id=org.id, investigation_id=investigation.id, entity_id=entity.id, evidence_id=evidence.id, raw_record_id=raw.id, event_id=event.id, extractor_name="safe", extractor_version="1", occurrence_ordinal=0, observed_at=observed); db.add(observation); db.flush()
    indicator = Indicator(org_id=org.id, type="ip", normalized_value=f"192.0.2.{1 if suffix == 'a' else 2}", display_value=f"192.0.2.{1 if suffix == 'a' else 2}"); db.add(indicator); db.flush()
    item = IndicatorOccurrence(org_id=org.id, investigation_id=investigation.id, indicator_id=indicator.id, evidence_id=evidence.id, raw_record_id=raw.id, event_id=event.id, extractor_name="safe", extractor_version="1", occurrence_ordinal=0, observed_at=observed); db.add(item); db.commit(); return entity, observation, indicator, item


def test_bounded_entities_and_observations_are_scoped_safe_and_ordered(db):
    org, user, investigation = seed(db); first, _one, _indicator, _occurrence = occurrence(db, org, investigation, user, suffix="a", observed=datetime(2026, 1, 1, tzinfo=timezone.utc)); second, _two, _indicator, _occurrence = occurrence(db, org, investigation, user, suffix="b", observed=None, raw_content=None)
    client = TestClient(app); base = f"/api/v1/investigations/{investigation.id}"
    response = client.get(f"{base}/entities?limit=1&offset=0", headers=header(user, org)); assert response.status_code == 200
    body = response.json(); assert body["total"] == 2 and body["returned_count"] == 1 and body["items"][0]["id"] == str(first.id)
    assert body["items"][0]["display_value"] == "<b>host-a</b>" and "attributes" not in str(body)
    detail = client.get(f"{base}/entities/{second.id}/observations", headers=header(user, org)); assert detail.status_code == 200
    item = detail.json()["items"][0]; assert item["provenance_status"] == "RAW_CONTENT_UNAVAILABLE" and "content" not in item and "normalized" not in item


def test_indicators_are_occurrence_backed_and_scope_authorized(db):
    org, user, investigation = seed(db); _entity, _observation, local_indicator, local = occurrence(db, org, investigation, user)
    global_only = Indicator(org_id=org.id, type="domain", normalized_value="example.invalid", display_value="example.invalid"); db.add(global_only); db.commit()
    client = TestClient(app); path = f"/api/v1/investigations/{investigation.id}/indicators"
    result = client.get(path, headers=header(user, org)); assert result.status_code == 200
    items = result.json()["items"]; assert [item["id"] for item in items] == [str(local.id)] and items[0]["indicator_id"] == str(local_indicator.id)
    assert str(global_only.id) not in str(result.json()) and "normalized" not in str(result.json())
    foreign_org, foreign_user, foreign_investigation = seed(db, "foreign"); assert client.get(f"/api/v1/investigations/{foreign_investigation.id}/indicators", headers=header(user, org)).status_code == 404
    assert client.get(f"{path}?org_id={foreign_org.id}", headers=header(user, org)).status_code == 422
    assert client.get(path, headers=header(user, org, ())).status_code == 403
