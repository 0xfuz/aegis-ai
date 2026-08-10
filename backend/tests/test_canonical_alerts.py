"""Phase 7.1: immutable canonical alert foundation, without downstream actions."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select

from app.modules.ai_reasoning.infrastructure.intelligence_models import IntelligenceAnalysis
from app.modules.alert_triage.domain.service import CanonicalAlertCreate, CanonicalAlertService
from app.modules.alert_triage.infrastructure.models import CanonicalAlert, CanonicalAlertOccurrence
from app.modules.connectors.infrastructure.models import Connector, RawEvent
from app.modules.evidence.infrastructure.models import Entity, EntityRelationship, Event, EvidenceItem, Indicator, RawRecord
from app.modules.identity.infrastructure.models import Organization
from app.modules.investigations.infrastructure.models import Finding, MitreMapping
from app.shared.database import SessionLocal
from app.shared.exceptions import ConflictError, NotFoundError, ValidationError


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def context(db, suffix: str | None = None):
    suffix = suffix or uuid4().hex
    org = Organization(name=f"Alert {suffix}", slug=f"alert-{suffix}")
    db.add(org)
    db.flush()
    connector = Connector(org_id=org.id, name=f"connector-{suffix}", type="webhook", secret_hash="not-used")
    db.add(connector)
    db.flush()
    return org, connector


def raw(db, connector: Connector, payload: dict | None = None):
    event = RawEvent(connector_id=connector.id, received_at=datetime.now(timezone.utc), payload=payload or {"vendor": "test", "message": "untrusted"})
    db.add(event)
    db.commit()
    return event


def payload(**overrides):
    value = {
        "source": "suricata",
        "source_alert_id": "evt-100",
        "observed_at": datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc),
        "title": "Suspicious connection",
        "description": "Source-provided, untrusted text.",
        "severity": "HIGH",
        "category": "network",
        "rule_id": "202001",
        "rule_name": "ET TEST",
        "signature": "test signature",
        "observables": {
            "source_ip": "2001:0db8::1",
            "destination_ip": "198.51.100.20",
            "hostname": "WEB-01.",
            "username": "Admin",
            "process": "PowerShell.EXE",
            "file": "C:/Temp/A.EXE",
            "domain": "Example.TEST.",
            "url": "HTTPS://Example.TEST/Path?x=1#fragment",
        },
        "source_metadata": {"sensor": "edge-1"},
        "normalizer_version": "suricata-v1",
    }
    value.update(overrides)
    return CanonicalAlertCreate(**value)


def test_canonical_alert_creation_preserves_normalized_source_provenance(db):
    org, connector = context(db)
    source = raw(db, connector)
    alert, replay = CanonicalAlertService(db).create(org.id, connector.id, source.id, payload())

    assert replay is False
    assert alert.org_id == org.id and alert.connector_id == connector.id and alert.raw_event_id == source.id
    assert alert.lifecycle == "NEW" and alert.observed_at == datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
    assert alert.normalized_observables == {
        "source_ip": "2001:db8::1", "destination_ip": "198.51.100.20", "hostname": "web-01",
        "username": "admin", "process": "powershell.exe", "file": "c:/temp/a.exe", "domain": "example.test",
        "url": "https://example.test/Path?x=1",
    }
    occurrence = db.scalar(select(CanonicalAlertOccurrence).where(CanonicalAlertOccurrence.canonical_alert_id == alert.id))
    assert occurrence.raw_event_id == source.id and occurrence.disposition == "INITIAL" and len(alert.payload_digest) == 64


def test_exact_source_identity_replay_records_history_without_mutating_alert(db):
    org, connector = context(db)
    first_raw = raw(db, connector, {"sequence": 1})
    service = CanonicalAlertService(db)
    first, replay = service.create(org.id, connector.id, first_raw.id, payload())
    original = (first.raw_event_id, first.title, first.description, first.payload_digest, first.ingested_at)
    second_raw = raw(db, connector, {"sequence": 2})
    replayed, replay = service.create(org.id, connector.id, second_raw.id, payload(title="changed source title", description="changed source text"))

    assert replay is True and replayed.id == first.id
    assert (replayed.raw_event_id, replayed.title, replayed.description, replayed.payload_digest, replayed.ingested_at) == original
    occurrences = service.list_occurrences(org.id, first.id)
    assert [(row.raw_event_id, row.disposition) for row in occurrences] == [(first_raw.id, "INITIAL"), (second_raw.id, "REPLAY")]
    with pytest.raises(ConflictError):
        service.create(org.id, connector.id, second_raw.id, payload())


def test_org_isolation_and_cross_connector_raw_provenance_rejected(db):
    org, connector = context(db)
    other_org, other_connector = context(db)
    source = raw(db, connector)
    other_source = raw(db, other_connector)
    service = CanonicalAlertService(db)
    alert, _ = service.create(org.id, connector.id, source.id, payload())

    with pytest.raises(NotFoundError):
        service.get(other_org.id, alert.id)
    with pytest.raises(NotFoundError):
        service.create(org.id, other_connector.id, other_source.id, payload())
    with pytest.raises(ValidationError):
        service.create(org.id, connector.id, other_source.id, payload(source_alert_id="evt-101"))


@pytest.mark.parametrize("bad", [
    {"severity": "SEVERE"},
    {"observed_at": "not-a-timestamp"},
    {"observed_at": datetime(2026, 8, 9, 12, 0)},
    {"observables": {"source_ip": "not-an-ip"}},
    {"observables": {"url": "javascript:alert(1)"}},
    {"source_metadata": {"x": "z" * (64 * 1024)}},
])
def test_invalid_alert_payloads_are_rejected_before_persistence(bad):
    with pytest.raises(PydanticValidationError):
        payload(**bad)


def test_creation_never_mutates_or_creates_fact_ai_or_verdict_records(db):
    org, connector = context(db)
    source = raw(db, connector)
    models = [EvidenceItem, RawRecord, Event, Indicator, Entity, EntityRelationship, IntelligenceAnalysis, Finding, MitreMapping]
    before = {model.__name__: db.scalar(select(func.count()).select_from(model).where(model.org_id == org.id)) for model in models}
    alert, _ = CanonicalAlertService(db).create(org.id, connector.id, source.id, payload())
    after = {model.__name__: db.scalar(select(func.count()).select_from(model).where(model.org_id == org.id)) for model in models}

    assert alert.id and before == after
    assert db.scalar(select(func.count()).select_from(CanonicalAlert).where(CanonicalAlert.org_id == org.id)) == 1
