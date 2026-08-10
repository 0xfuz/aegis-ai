"""Integration tests for the additive Phase 1 canonical FACT schema.

These tests require PostgreSQL with Alembic revision 0010 applied. They do not
exercise parser, upload, API, graph, or AI behavior.
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.modules.evidence.infrastructure.models import (
    AuditEvent,
    Entity,
    EntityObservation,
    EntityRelationship,
    Event,
    EvidenceItem,
    EvidenceParseRun,
    Indicator,
    IndicatorOccurrence,
    RawRecord,
)
from app.modules.identity.infrastructure.models import Organization
from app.modules.investigations.infrastructure.models import Investigation, InvestigationStatus, Severity
from app.shared.database import SessionLocal

NOW = datetime.now(timezone.utc)
SHA256 = "a" * 64


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _investigation(db):
    org = Organization(name=f"Provenance {uuid4()}", slug=f"provenance-{uuid4()}")
    db.add(org)
    db.flush()
    investigation = Investigation(
        org_id=org.id,
        title="Canonical provenance test",
        source="pytest",
        severity=Severity.MEDIUM,
        status=InvestigationStatus.NEW,
    )
    db.add(investigation)
    db.flush()
    return org, investigation


def _chain(db):
    org, investigation = _investigation(db)
    evidence = EvidenceItem(
        org_id=org.id,
        investigation_id=investigation.id,
        original_filename="fixture.log",
        storage_key=str(uuid4()),
        sha256=SHA256,
        byte_size=12,
        detected_mime="text/plain",
        extension=".log",
        acquisition_source="test",
        imported_at=NOW,
        parsing_status="pending",
    )
    db.add(evidence)
    db.flush()
    run = EvidenceParseRun(
        org_id=org.id,
        evidence_id=evidence.id,
        parser_name="fixture-parser",
        parser_version="1.0.0",
        run_sequence=1,
        status="complete",
        started_at=NOW,
        ended_at=NOW,
    )
    db.add(run)
    db.flush()
    raw = RawRecord(
        org_id=org.id,
        evidence_id=evidence.id,
        parse_run_id=run.id,
        ordinal=0,
        content="fixture raw record",
        content_type="text/plain",
    )
    db.add(raw)
    db.flush()
    event = Event(
        org_id=org.id,
        investigation_id=investigation.id,
        evidence_id=evidence.id,
        raw_record_id=raw.id,
        normalizer_name="fixture-normalizer",
        normalizer_version="1.0.0",
        ordinal=0,
        timestamp=NOW,
        event_type="fixture_event",
        normalized={"fixture": True},
    )
    db.add(event)
    db.flush()
    return org, investigation, evidence, run, raw, event


def test_model_creation_and_complete_provenance_linkage(db):
    org, investigation, evidence, _run, raw, event = _chain(db)
    indicator = Indicator(org_id=org.id, type="ip", normalized_value="203.0.113.7")
    source = Entity(org_id=org.id, investigation_id=investigation.id, type="user", canonical_value="alice", display_name="alice")
    target = Entity(org_id=org.id, investigation_id=investigation.id, type="host", canonical_value="host-1", display_name="host-1")
    db.add_all([indicator, source, target])
    db.flush()
    indicator_occurrence = IndicatorOccurrence(
        org_id=org.id, investigation_id=investigation.id, indicator_id=indicator.id,
        evidence_id=evidence.id, raw_record_id=raw.id, event_id=event.id,
        extractor_name="fixture-extractor", extractor_version="1.0.0", occurrence_ordinal=0, observed_at=NOW,
    )
    source_observation = EntityObservation(
        org_id=org.id, investigation_id=investigation.id, entity_id=source.id,
        evidence_id=evidence.id, raw_record_id=raw.id, event_id=event.id,
        extractor_name="fixture-extractor", extractor_version="1.0.0", occurrence_ordinal=0, observed_at=NOW,
    )
    target_observation = EntityObservation(
        org_id=org.id, investigation_id=investigation.id, entity_id=target.id,
        evidence_id=evidence.id, raw_record_id=raw.id, event_id=event.id,
        extractor_name="fixture-extractor", extractor_version="1.0.0", occurrence_ordinal=0, observed_at=NOW,
    )
    db.add_all([indicator_occurrence, source_observation, target_observation])
    db.flush()
    relationship = EntityRelationship(
        org_id=org.id, investigation_id=investigation.id, source_entity_id=source.id,
        target_entity_id=target.id, relationship_type="logged_into",
        derivation_name="fixture-rule", derivation_version="1.0.0", event_id=event.id,
        source_observation_id=source_observation.id, target_observation_id=target_observation.id,
        source_locator_hash="b" * 64, observed_at=NOW,
    )
    db.add(relationship)
    db.flush()
    audit = AuditEvent(
        org_id=org.id, investigation_id=investigation.id, actor_type="system",
        action="FACT_CREATED", target_type="EntityRelationship", target_id=relationship.id, occurred_at=NOW,
    )
    db.add(audit)
    db.flush()

    assert event.raw_record_id == raw.id
    assert indicator_occurrence.indicator_id == indicator.id
    assert relationship.event_id == event.id
    assert audit.investigation_id == investigation.id


def test_unique_constraints_and_parse_status_check(db):
    org, investigation, evidence, run, raw, _event = _chain(db)
    duplicate = EvidenceItem(
        org_id=org.id, investigation_id=investigation.id, original_filename="duplicate.log",
        storage_key=str(uuid4()), sha256=SHA256, byte_size=1, detected_mime="text/plain",
        extension=".log", acquisition_source="test", imported_at=NOW, parsing_status="pending",
    )
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()

    # Recreate after rollback and validate the stable lifecycle check separately.
    _org, _investigation_, evidence, _run, _raw, _event = _chain(db)
    invalid_run = EvidenceParseRun(
        org_id=evidence.org_id, evidence_id=evidence.id, parser_name="fixture-parser",
        parser_version="bad", run_sequence=1, status="not-a-status", started_at=NOW,
    )
    db.add(invalid_run)
    with pytest.raises(IntegrityError):
        db.flush()


def test_fk_integrity_and_restrictive_investigation_deletion(db):
    _org, investigation, evidence, _run, _raw, _event = _chain(db)
    invalid = EvidenceParseRun(
        org_id=evidence.org_id, evidence_id=uuid4(), parser_name="missing-parent",
        parser_version="1", run_sequence=1, status="pending", started_at=NOW,
    )
    db.add(invalid)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()

    _org, investigation, _evidence, _run, _raw, _event = _chain(db)
    with pytest.raises(IntegrityError):
        db.execute(delete(Investigation).where(Investigation.id == investigation.id))
        db.flush()


def test_raw_record_and_relationship_provenance_checks(db):
    org, investigation, evidence, run, _raw, _event = _chain(db)
    missing_content = RawRecord(
        org_id=org.id, evidence_id=evidence.id, parse_run_id=run.id, ordinal=99, content_type="text/plain"
    )
    db.add(missing_content)
    with pytest.raises(IntegrityError):
        db.flush()


def test_indicator_and_entity_identity_are_scoped_as_contracts_require(db):
    org, investigation, _evidence, _run, _raw, _event = _chain(db)
    indicator = Indicator(org_id=org.id, type="domain", normalized_value="example.test")
    entity = Entity(org_id=org.id, investigation_id=investigation.id, type="host", canonical_value="host-1", display_name="host-1")
    db.add_all([indicator, entity])
    db.flush()

    duplicate_indicator = Indicator(org_id=org.id, type="domain", normalized_value="example.test")
    duplicate_entity = Entity(org_id=org.id, investigation_id=investigation.id, type="host", canonical_value="host-1", display_name="other")
    db.add_all([duplicate_indicator, duplicate_entity])
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()

    org, investigation, _evidence, _run, _raw, _event = _chain(db)
    entity = Entity(org_id=org.id, investigation_id=investigation.id, type="host", canonical_value="same", display_name="same")
    db.add(entity)
    db.flush()
    invalid_relationship = EntityRelationship(
        org_id=org.id, investigation_id=investigation.id, source_entity_id=entity.id, target_entity_id=entity.id,
        relationship_type="self", derivation_name="fixture", derivation_version="1", source_locator_hash="c" * 64,
    )
    db.add(invalid_relationship)
    with pytest.raises(IntegrityError):
        db.flush()
