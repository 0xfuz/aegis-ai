from datetime import datetime

from pydantic import BaseModel, Field


class GraphNodeRead(BaseModel):
    id: str
    type: str = Field(max_length=50)
    label: str = Field(max_length=255)
    canonical_value: str | None = Field(default=None, max_length=255)
    observation_count: int
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    status: str = Field(pattern="^FACT$")


class GraphProvenanceRead(BaseModel):
    relationship_id: str
    evidence_id: str | None
    event_id: str | None
    source_observation_id: str | None
    target_observation_id: str | None
    derivation_name: str = Field(max_length=100)
    derivation_version: str = Field(max_length=100)
    observed_at: datetime | None
    support_status: str = Field(pattern="^(AVAILABLE|UNAVAILABLE)$")


class GraphEdgeRead(BaseModel):
    id: str
    source: str
    target: str
    relationship_type: str = Field(max_length=100)
    observed_at: datetime | None
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    occurrence_count: int
    support_omitted: int
    status: str = Field(pattern="^FACT$")
    provenance: list[GraphProvenanceRead] = Field(max_length=20)


class GraphOmissionsRead(BaseModel):
    nodes: int
    edges: int
    reason: str | None


class CanonicalGraphRead(BaseModel):
    investigation_id: str
    policy_id: str
    nodes: list[GraphNodeRead] = Field(max_length=200)
    edges: list[GraphEdgeRead] = Field(max_length=100)
    omissions: GraphOmissionsRead
