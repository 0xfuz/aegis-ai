from datetime import datetime
from typing import Any

from pydantic import BaseModel


class GraphNodeOut(BaseModel):
    id: str
    type: str
    label: str
    tier: str
    timestamp: datetime | None
    data: dict[str, Any]


class GraphEdgeOut(BaseModel):
    id: str
    source: str
    target: str
    relationship: str
    tier: str
    rationale: str


class AttackGraphOut(BaseModel):
    investigation_id: str
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]
