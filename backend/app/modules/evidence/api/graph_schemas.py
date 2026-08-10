from datetime import datetime
from typing import Any

from pydantic import BaseModel


class GraphNodeRead(BaseModel):
    id: str
    type: str
    label: str
    canonical_value: str | None
    observation_count: int
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    status: str
    metadata: dict[str, Any]


class GraphProvenanceRead(BaseModel):
    relationship_id: str
    evidence_id: str | None
    raw_record_id: str | None
    event_id: str | None
    source_observation_id: str | None
    target_observation_id: str | None


class GraphEdgeRead(BaseModel):
    id: str
    source: str
    target: str
    relationship_type: str
    observed_at: datetime | None
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    occurrence_count: int
    confidence: float | None
    status: str
    provenance: list[GraphProvenanceRead]


class CanonicalGraphRead(BaseModel):
    investigation_id: str
    nodes: list[GraphNodeRead]
    edges: list[GraphEdgeRead]
