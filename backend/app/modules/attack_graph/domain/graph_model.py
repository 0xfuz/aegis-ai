"""
The Attack Graph's data model. This module knows nothing about React Flow,
HTTP, or the database — it's a pure, framework-agnostic representation of
"nodes and edges derived from one investigation's real data." Keeping it
separate from graph_builder.py (which does the deriving) and the API layer
(which serializes it) is what lets the visualization side change freely
without touching how the graph is computed, and vice versa.

THE CORE RULE THIS MODULE EXISTS TO ENFORCE: a node or edge only appears
here if something in the investigation's actual data justified it. There
is no code path anywhere in this module or graph_builder.py that invents
an attack stage, a MITRE technique, or a relationship. Where the
underlying data is genuinely insufficient, that absence is itself
represented — via an UNKNOWN-tier placeholder node, never by silently
filling in what "usually" comes next.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class NodeType(str, enum.Enum):
    INCIDENT = "incident"
    EVENT = "event"
    EVIDENCE = "evidence"
    IOC = "ioc"
    ACCOUNT = "account"
    ASSET = "asset"
    IP_DOMAIN = "ip_domain"
    ATTACK_PHASE = "attack_phase"
    MITRE_TECHNIQUE = "mitre_technique"
    FINDING = "finding"
    HYPOTHESIS = "hypothesis"
    UNCERTAINTY = "uncertainty"  # explicit "insufficient evidence" marker — never omitted silently


class EdgeType(str, enum.Enum):
    CAUSED_BY = "caused_by"
    RELATED_TO = "related_to"
    OBSERVED_IN = "observed_in"
    ORIGINATED_FROM = "originated_from"
    TARGETED = "targeted"
    ASSOCIATED_WITH = "associated_with"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    LEADS_TO = "leads_to"


class ConfidenceTier(str, enum.Enum):
    """The four-tier scale the person explicitly asked for. Assignment
    rules (see graph_builder.py's ASSIGNING CONFIDENCE TIERS section) are
    deterministic and documented, not vibes — the same input always
    produces the same tier."""

    CONFIRMED = "confirmed"  # directly recorded data: an event, a piece of evidence, an IOC
    PROBABLE = "probable"  # AI-derived, backed by confidence >= 70
    POSSIBLE = "possible"  # AI-derived, confidence 40-69
    UNKNOWN = "unknown"  # AI-derived with confidence < 40, OR no data exists to support this at all


@dataclass
class GraphNode:
    id: str
    type: NodeType
    label: str
    tier: ConfidenceTier
    timestamp: datetime | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    id: str
    source: str
    target: str
    relationship: EdgeType
    tier: ConfidenceTier
    rationale: str  # answers "why does this edge exist" — shown when a user clicks it


@dataclass
class AttackGraph:
    investigation_id: str
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
