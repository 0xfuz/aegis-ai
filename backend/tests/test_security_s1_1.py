"""Regression tests for the confirmed S1 vulnerabilities only."""
import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select

from app.core.config import Settings
from app.modules.connectors.api.router import _MAX_GENERIC_ALERT_BYTES, _bounded_body
from app.main import app
from app.modules.alert_triage.infrastructure.models import CanonicalAlert, AlertClusterMembership
from app.modules.connectors.domain.service import ConnectorService
from app.modules.connectors.infrastructure.models import RawEvent
from app.modules.identity.infrastructure.models import Organization
from app.shared.database import SessionLocal
from app.seed import bootstrap
from app.shared.exceptions import ValidationError


def test_production_rejects_default_security_configuration():
    with pytest.raises(PydanticValidationError):
        Settings(ENVIRONMENT="production", DEBUG=False)
    with pytest.raises(PydanticValidationError):
        Settings(ENVIRONMENT="production", DEBUG=True, JWT_SECRET_KEY="non-default", DATABASE_URL="postgresql+psycopg2://user:strong@db:5432/app")


def test_production_accepts_explicit_nondefault_configuration():
    settings = Settings(ENVIRONMENT="production", DEBUG=False, SEED_DEMO_DATA=False,
        JWT_SECRET_KEY="test-only-non-default-secret", DATABASE_URL="postgresql+psycopg2://user:strong@db:5432/app")
    assert settings.ENVIRONMENT == "production"


def test_demo_seed_is_explicit_and_never_runs_in_production(monkeypatch):
    called = []
    monkeypatch.setattr(bootstrap, "seed", lambda: called.append(True))
    monkeypatch.setattr(bootstrap, "get_settings", lambda: Settings(ENVIRONMENT="development", SEED_DEMO_DATA=False))
    assert bootstrap.seed_demo_if_enabled() is False and not called
    monkeypatch.setattr(bootstrap, "get_settings", lambda: Settings(ENVIRONMENT="development", SEED_DEMO_DATA=True))
    assert bootstrap.seed_demo_if_enabled() is True and called == [True]


class _ChunkedRequest:
    def __init__(self, chunks): self.chunks = chunks
    async def stream(self):
        for chunk in self.chunks: yield chunk


@pytest.mark.asyncio
async def test_webhook_bounded_read_accepts_limit_and_rejects_above_without_collecting_tail():
    assert len(await _bounded_body(_ChunkedRequest([b"a" * _MAX_GENERIC_ALERT_BYTES]))) == _MAX_GENERIC_ALERT_BYTES
    with pytest.raises(ValidationError):
        await _bounded_body(_ChunkedRequest([b"a" * _MAX_GENERIC_ALERT_BYTES, b"tail"]))
    with pytest.raises(ValidationError):
        await _bounded_body(_ChunkedRequest([b"a" * (_MAX_GENERIC_ALERT_BYTES + 1)]))


def test_oversized_authenticated_webhook_creates_no_alert_state():
    db = SessionLocal()
    try:
        suffix = f"s11-retest-{uuid4().hex}"
        org = Organization(name=suffix, slug=suffix); db.add(org); db.commit()
        created = ConnectorService(db).create_webhook_connector(org.id, suffix, "http://testserver"); db.commit()
        response = TestClient(app).post(
            f"/api/v1/ingest/alerts/v1/{created.connector.id}/source", content=b"x" * (_MAX_GENERIC_ALERT_BYTES + 1),
            headers={"content-type": "application/json", "X-Ingest-Secret": created.ingest_secret},
        )
        assert response.status_code == 422 and "traceback" not in response.text.casefold()
        assert db.scalar(select(func.count()).select_from(RawEvent).where(RawEvent.connector_id == created.connector.id)) == 0
        assert db.scalar(select(func.count()).select_from(CanonicalAlert).where(CanonicalAlert.org_id == org.id)) == 0
        assert db.scalar(select(func.count()).select_from(AlertClusterMembership).where(AlertClusterMembership.org_id == org.id)) == 0
    finally:
        db.rollback(); db.close()
