"""PostgreSQL contracts for bounded Entity/Indicator occurrence reads."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event as sqlalchemy_event

from app.core.security import create_access_token
from app.main import app
from app.modules.evidence.domain.graph_projection import CanonicalGraphProjectionService, GraphFilters
from app.modules.evidence.infrastructure.models import Entity, EntityObservation, EntityRelationship, Event, EvidenceItem, EvidenceParseRun, Indicator, IndicatorOccurrence, RawRecord
from app.modules.identity.infrastructure.models import Organization, Role, User
from app.modules.investigations.infrastructure.models import Investigation, InvestigationStatus, Severity
from app.shared.database import SessionLocal


@pytest.fixture()
def db():
    session = SessionLocal()
    try: yield session
    finally: session.rollback(); session.close()


def seed(db, name="scope"):
    token = uuid4().hex; prefix = name[:10]; org = Organization(name=f"{prefix}-{token}", slug=f"{prefix}-{token}"); role = Role(name=f"{prefix}-role-{token}")
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


def test_canonical_graph_is_bounded_scoped_and_safe(db):
    org, user, investigation = seed(db)
    first, first_observation, local_indicator, _local = occurrence(db, org, investigation, user, suffix="a", observed=datetime(2026, 1, 1, tzinfo=timezone.utc))
    second, second_observation, _other_indicator, _other = occurrence(db, org, investigation, user, suffix="b", observed=datetime(2026, 1, 2, tzinfo=timezone.utc))
    evidence = db.get(EvidenceItem, first_observation.evidence_id)
    relationship = EntityRelationship(
        org_id=org.id, investigation_id=investigation.id,
        source_entity_id=first.id, target_entity_id=second.id,
        relationship_type="connected_to", derivation_name="safe", derivation_version="v1",
        evidence_id=evidence.id, raw_record_id=first_observation.raw_record_id,
        event_id=first_observation.event_id, source_observation_id=first_observation.id,
        target_observation_id=second_observation.id, source_locator_hash="a" * 64,
        observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    global_only = Indicator(org_id=org.id, type="domain", normalized_value="global.invalid", display_value="global.invalid")
    db.add_all((relationship, global_only)); db.commit()
    client = TestClient(app); path = f"/api/v1/investigations/{investigation.id}/graph"; headers = header(user, org)
    response = client.get(path, headers=headers); assert response.status_code == 200
    body = response.json(); assert client.get(path, headers=headers).json() == body
    assert body["policy_id"] == "canonical-graph-v1" and body["omissions"] == {"nodes": 0, "edges": 0, "reason": None}
    node_ids = {node["id"] for node in body["nodes"]}; assert all(edge["source"] in node_ids and edge["target"] in node_ids for edge in body["edges"])
    assert all(node["status"] == "FACT" for node in body["nodes"]) and all(edge["status"] == "FACT" for edge in body["edges"])
    assert f"indicator:{local_indicator.id}" in node_ids and str(global_only.id) not in str(body)
    support = body["edges"][0]["provenance"][0]
    assert support["relationship_id"] == str(relationship.id) and support["derivation_name"] == "safe"
    assert "raw_record_id" not in str(body) and "normalized" not in str(body) and "attributes" not in str(body)
    assert client.get(f"{path}?entity_type=HOST", headers=headers).status_code == 200
    assert client.get(f"{path}?evidence_id={evidence.id}", headers=headers).status_code == 200
    assert client.get(f"{path}?evidence_id={uuid4()}", headers=headers).status_code == 404
    assert client.get(f"{path}?unknown=true", headers=headers).status_code == 422
    assert client.get(f"{path}?relationship_type=unsupported", headers=headers).status_code == 422
    foreign_org, foreign_user, foreign_investigation = seed(db, "foreign-graph")
    assert client.get(f"/api/v1/investigations/{foreign_investigation.id}/graph", headers=headers).status_code == 404
    assert client.get(f"/api/v1/investigations/{investigation.id}/attack-graph", headers=headers).status_code == 404
    user.is_active = False; db.commit()
    assert client.get(path, headers=headers).status_code == 404


def test_canonical_graph_is_the_only_public_graph_projection_route():
    paths = {route.path for route in app.routes}
    assert "/api/v1/investigations/{investigation_id}/graph" in paths
    assert "/api/v1/investigations/{investigation_id}/attack-graph" not in paths


def test_canonical_graph_uses_a_bounded_query_plan(db):
    org, user, investigation = seed(db)
    first, first_observation, _local_indicator, _local = occurrence(db, org, investigation, user, suffix="a", observed=datetime(2026, 1, 1, tzinfo=timezone.utc))
    second, second_observation, _other_indicator, _other = occurrence(db, org, investigation, user, suffix="b", observed=datetime(2026, 1, 2, tzinfo=timezone.utc))
    db.add(EntityRelationship(
        org_id=org.id, investigation_id=investigation.id, source_entity_id=first.id, target_entity_id=second.id,
        relationship_type="connected_to", derivation_name="safe", derivation_version="v1",
        evidence_id=first_observation.evidence_id, raw_record_id=first_observation.raw_record_id,
        event_id=first_observation.event_id, source_observation_id=first_observation.id,
        target_observation_id=second_observation.id, source_locator_hash="b" * 64,
        observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    ))
    db.commit()
    statements: list[str] = []

    def count_statement(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    sqlalchemy_event.listen(db.bind, "before_cursor_execute", count_statement)
    try:
        graph = CanonicalGraphProjectionService(db).project(org.id, investigation.id, GraphFilters())
    finally:
        sqlalchemy_event.remove(db.bind, "before_cursor_execute", count_statement)
    assert graph["edges"]
    # Projection has a fixed scope/validation/count/read plan; it must not add
    # one query for each returned node or support row.
    assert len(statements) <= 12
    assert not any(statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for statement in statements)
