from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConnectorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class ConnectorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    type: str
    status: str
    is_active: bool
    last_event_at: datetime | None
    created_at: datetime


class ConnectorCreated(BaseModel):
    """Returned exactly once, at creation — includes the plaintext secret
    and ready-to-use ingest URL, which are never retrievable again."""

    connector: ConnectorRead
    ingest_url: str
    ingest_secret: str


class WebhookIndicator(BaseModel):
    type: str = Field(description="ip | hash | domain | url | asset")
    value: str


class WebhookEventPayload(BaseModel):
    """The normalized shape any external system POSTs to a webhook
    connector's ingest URL. A real vendor adapter (Sentinel, Splunk, ...)
    would translate that vendor's native alert format into this same
    shape before it ever reaches the investigations module — this schema
    IS the plug-in contract."""

    title: str = Field(min_length=1, max_length=255)
    severity: str = Field(description="critical | high | medium | low | info")
    description: str = Field(default="", description="Becomes the investigation's root cause text")
    indicators: list[WebhookIndicator] = Field(default_factory=list)


class IngestResult(BaseModel):
    investigation_id: UUID
    status: str = "created"


class GenericAlertPayload(BaseModel):
    """Untrusted v1 generic-security-alert contract; no org or DB fields."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source: str = Field(min_length=1, max_length=100)
    source_alert_id: str = Field(min_length=1, max_length=255)
    observed_at: datetime
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=10_000)
    severity: str = Field(min_length=1, max_length=20)
    category: str | None = Field(default=None, max_length=100)
    rule_id: str | None = Field(default=None, max_length=255)
    rule_name: str | None = Field(default=None, max_length=255)
    signature: str | None = Field(default=None, max_length=255)
    source_ip: str | None = Field(default=None, max_length=45)
    destination_ip: str | None = Field(default=None, max_length=45)
    hostname: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=255)
    process: str | None = Field(default=None, max_length=1024)
    file: str | None = Field(default=None, max_length=1024)
    domain: str | None = Field(default=None, max_length=253)
    url: str | None = Field(default=None, max_length=2048)
    source_metadata: dict = Field(default_factory=dict)


class GenericAlertIngestResult(BaseModel):
    status: str
    canonical_alert_id: UUID
    deduplication_status: str
    cluster_id: UUID | None = None
    priority: str | None = None
    score: int | None = None
    correlation_version: str | None = None
    triage_version: str | None = None
