"""S1 regression guards for confirmed access-boundary controls (no remediation)."""
from fastapi.testclient import TestClient

from app.main import app


def test_sensitive_investigation_surfaces_reject_anonymous_requests():
    client = TestClient(app)
    for path in (
        "/api/v1/investigations",
        "/api/v1/assets",
        "/api/v1/connectors",
        "/api/v1/demos",
        "/api/v1/investigations/00000000-0000-0000-0000-000000000000/overview",
    ):
        assert client.get(path).status_code == 403


def test_generic_webhook_does_not_accept_missing_connector_secret():
    client = TestClient(app)
    response = client.post(
        "/api/v1/ingest/alerts/v1/00000000-0000-0000-0000-000000000000/source",
        json={"source": "source", "source_alert_id": "a", "observed_at": "2026-01-01T00:00:00Z", "title": "x", "severity": "low"},
    )
    assert response.status_code == 422
