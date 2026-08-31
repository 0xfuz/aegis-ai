"""Shared, in-process Wazuh webhook fixture; never serialize its secret."""
from dataclasses import dataclass, field
from uuid import uuid4
from fastapi.testclient import TestClient
from app.modules.connectors.domain.service import ConnectorService
from app.modules.identity.infrastructure.models import Organization

@dataclass(repr=False)
class WazuhWebhookFixture:
    organization: object
    connector: object
    ingest_secret: str = field(repr=False)

def create_wazuh_webhook_fixture(db):
    suffix = uuid4().hex
    org = Organization(name=f"Wazuh {suffix}", slug=f"wazuh-{suffix}")
    db.add(org); db.commit()
    created = ConnectorService(db).create_webhook_connector(org.id, f"wazuh-{suffix}", "http://testserver")
    db.commit()
    return WazuhWebhookFixture(org, created.connector, created.ingest_secret)

def post_wazuh_webhook_event(client: TestClient, fixture: WazuhWebhookFixture, body, **kwargs):
    return client.post(f"/api/v1/ingest/wazuh/v1/{fixture.connector.id}", json=body, headers={"X-Ingest-Secret": fixture.ingest_secret}, **kwargs)
