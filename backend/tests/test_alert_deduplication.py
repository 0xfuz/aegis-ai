"""Phase 7.2 deterministic deduplication contracts."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis
from app.modules.alert_triage.domain.deduplication_service import AlertDeduplicationService, SEMANTIC_DEDUPE_VERSION
from app.modules.alert_triage.domain.service import CanonicalAlertCreate, CanonicalAlertService
from app.modules.alert_triage.infrastructure.models import AlertDeduplicationDecision, CanonicalAlert, CanonicalAlertOccurrence
from app.modules.connectors.infrastructure.models import Connector, RawEvent
from app.modules.evidence.infrastructure.models import Entity, EntityRelationship, Event, EvidenceItem, Indicator, RawRecord
from app.modules.identity.infrastructure.models import Organization
from app.modules.investigations.infrastructure.models import Finding, MitreMapping
from app.shared.database import SessionLocal


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def setup(db, suffix=None):
    suffix = suffix or uuid4().hex
    org = Organization(name=f"Dedupe {suffix}", slug=f"dedupe-{suffix}")
    db.add(org); db.flush()
    connector = Connector(org_id=org.id, name=f"sensor-{suffix}", type="webhook", secret_hash="x")
    db.add(connector); db.commit()
    return org, connector


def raw(db, connector, sequence):
    item = RawEvent(connector_id=connector.id, received_at=datetime.now(timezone.utc), payload={"sequence": sequence})
    db.add(item); db.commit()
    return item


def input_for(source_alert_id, observed_at, **overrides):
    fields = {
        "source": "suricata", "source_alert_id": source_alert_id, "observed_at": observed_at,
        "title": "Possible web attack", "description": "untrusted source description", "severity": "HIGH",
        "category": "network", "rule_id": "2010935", "rule_name": "test", "signature": "test",
        "observables": {"hostname": "Web-01", "source_ip": "198.51.100.44"}, "source_metadata": {"sensor": "a"},
    }
    fields.update(overrides)
    return CanonicalAlertCreate(**fields)


def create(db, org, connector, source_alert_id, observed_at, **overrides):
    event = raw(db, connector, source_alert_id)
    return CanonicalAlertService(db).create(org.id, connector.id, event.id, input_for(source_alert_id, observed_at, **overrides))[0], event


def test_exact_replay_adds_occurrence_and_explainable_exact_decision(db):
    org, connector = setup(db)
    when = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    first, first_raw = create(db, org, connector, "same", when)
    second_raw = raw(db, connector, "same-retry")
    replayed, replay = CanonicalAlertService(db).create(org.id, connector.id, second_raw.id, input_for("same", when, title="changed"))

    assert replay is True and replayed.id == first.id
    occurrences = list(db.scalars(select(CanonicalAlertOccurrence).where(CanonicalAlertOccurrence.canonical_alert_id == first.id)))
    replay_occurrence = next(row for row in occurrences if row.disposition == "REPLAY")
    exact = db.scalar(select(AlertDeduplicationDecision).where(AlertDeduplicationDecision.duplicate_occurrence_id == replay_occurrence.id))
    assert len(occurrences) == 2 and exact.decision_type == "EXACT_REPLAY"
    assert exact.representative_alert_id == first.id and exact.reasons[0]["code"] == "EXACT_SOURCE_IDENTITY"
    read = AlertDeduplicationService(db).read(org.id, first.id)
    assert read.is_duplicate is False and read.occurrence_count == 2 and read.first_seen <= read.last_seen
    assert db.get(CanonicalAlert, first.id).raw_event_id == first_raw.id


def test_semantic_duplicate_is_explainable_and_idempotent(db):
    org, connector = setup(db)
    start = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    representative, _ = create(db, org, connector, "one", start)
    duplicate, duplicate_raw = create(db, org, connector, "two", start + timedelta(seconds=30))
    service = AlertDeduplicationService(db)

    result = service.process(org.id, duplicate.id)
    repeated = service.process(org.id, duplicate.id)
    decisions = list(db.scalars(select(AlertDeduplicationDecision).where(AlertDeduplicationDecision.duplicate_alert_id == duplicate.id)))

    assert result.is_duplicate and result.representative_alert_id == representative.id
    assert repeated == result and len(decisions) == 1 and decisions[0].decision_version == SEMANTIC_DEDUPE_VERSION
    assert {reason["code"] for reason in result.reasons} == {"SAME_DETECTION", "SAME_CATEGORY", "SAME_SEVERITY", "SAME_ENTITY_TUPLE", "WITHIN_OBSERVED_TIME_WINDOW"}
    assert db.get(CanonicalAlert, duplicate.id).raw_event_id == duplicate_raw.id


def test_similar_alert_with_changed_entity_or_outside_window_is_not_duplicate(db):
    org, connector = setup(db)
    start = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    representative, _ = create(db, org, connector, "one", start)
    changed_entity, _ = create(db, org, connector, "two", start + timedelta(seconds=10), observables={"hostname": "other", "source_ip": "198.51.100.44"})
    outside, _ = create(db, org, connector, "three", start + timedelta(seconds=61))
    service = AlertDeduplicationService(db)

    assert service.process(org.id, changed_entity.id).is_duplicate is False
    assert service.process(org.id, outside.id).is_duplicate is False
    assert db.scalar(select(func.count()).select_from(AlertDeduplicationDecision).where(AlertDeduplicationDecision.org_id == org.id, AlertDeduplicationDecision.decision_type == "SEMANTIC")) == 0
    assert representative.id != changed_entity.id != outside.id


def test_time_window_is_inclusive_at_sixty_seconds(db):
    org, connector = setup(db)
    start = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    representative, _ = create(db, org, connector, "one", start)
    boundary, _ = create(db, org, connector, "two", start + timedelta(seconds=60))

    result = AlertDeduplicationService(db).process(org.id, boundary.id)
    assert result.is_duplicate and result.representative_alert_id == representative.id
    assert result.reasons[-1]["seconds"] == 60.0 and result.reasons[-1]["window_seconds"] == 60


def test_org_connector_and_source_identity_isolation(db):
    org, connector = setup(db)
    other_org, other_connector = setup(db)
    second_connector = Connector(org_id=org.id, name="other-sensor", type="webhook", secret_hash="x")
    db.add(second_connector); db.commit()
    start = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    primary, _ = create(db, org, connector, "shared", start)
    other_org_alert, _ = create(db, other_org, other_connector, "shared", start + timedelta(seconds=5))
    other_connector_alert, _ = create(db, org, second_connector, "shared", start + timedelta(seconds=5))
    other_source, _ = create(db, org, connector, "shared", start + timedelta(seconds=5), source="elastic")
    service = AlertDeduplicationService(db)

    assert service.process(other_org.id, other_org_alert.id).is_duplicate is False
    assert service.process(org.id, other_connector_alert.id).is_duplicate is False
    assert service.process(org.id, other_source.id).is_duplicate is False
    assert primary.id != other_org_alert.id and primary.id != other_connector_alert.id and primary.id != other_source.id


def test_deduplication_never_mutates_fact_ai_investigation_or_verdict_data(db):
    org, connector = setup(db)
    start = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    create(db, org, connector, "one", start)
    duplicate, _ = create(db, org, connector, "two", start + timedelta(seconds=10))
    models = [EvidenceItem, RawRecord, Event, Indicator, Entity, EntityRelationship, IntelligenceAnalysis, Finding, MitreMapping]
    before = {model.__name__: db.scalar(select(func.count()).select_from(model).where(model.org_id == org.id)) for model in models}

    result = AlertDeduplicationService(db).process(org.id, duplicate.id)
    after = {model.__name__: db.scalar(select(func.count()).select_from(model).where(model.org_id == org.id)) for model in models}

    assert result.is_duplicate and before == after
