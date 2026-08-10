"""
Transforms one investigation's existing data into an AttackGraph. This is
the only place attack-graph construction logic lives — every rule below
states exactly what data justifies the node/edge it creates, and there is
no rule that fabricates something the underlying data doesn't support.

Deliberately duck-typed rather than importing the SQLAlchemy Investigation
class: this function only reads a handful of attributes, so it accepts
anything with the right shape (the real ORM object, or a plain test
double in attack_graph tests) without a DB dependency. That's what makes
the five required test scenarios pure unit tests with zero database setup.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.modules.attack_graph.domain.graph_model import (
    AttackGraph,
    ConfidenceTier,
    EdgeType,
    GraphEdge,
    GraphNode,
    NodeType,
)

_IP_PATTERN = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:80]


def _tier_from_score(score: int) -> ConfidenceTier:
    """Used ONLY for AI-derived nodes/edges (attack phases, MITRE
    mappings, hypotheses, findings) — directly-recorded data (events,
    evidence, IOCs) is always CONFIRMED and never goes through this
    function, because its existence isn't a confidence judgment at all."""
    if score >= 70:
        return ConfidenceTier.PROBABLE
    if score >= 40:
        return ConfidenceTier.POSSIBLE
    return ConfidenceTier.UNKNOWN


def _classify_identity_type(value: str) -> NodeType:
    """An actor string is either an IP (originated_from an address) or
    some kind of account/identity (a user, service account, or IAM
    role) — we only ever see these two shapes in practice, so this is a
    two-way split, not a guess at a domain name we have no evidence for."""
    if _IP_PATTERN.match(value.strip()):
        return NodeType.IP_DOMAIN
    return NodeType.ACCOUNT


class IOCLookup(Protocol):
    """What the builder needs from the IOC registry — just enough to
    annotate an indicator node with real enrichment when it exists,
    without the builder itself needing repository/DB access."""

    def __call__(self, ioc_type: str, value: str) -> dict[str, Any] | None: ...


class AssetLookup(Protocol):
    """Same contract as IOCLookup, for the asset registry."""

    def __call__(self, name: str) -> dict[str, Any] | None: ...


@dataclass
class _Ctx:
    graph: AttackGraph
    seen_identity_nodes: dict[str, str]  # value -> node id, so the same account/asset/mitre technique isn't duplicated
    nodes_by_id: dict[str, GraphNode] = field(default_factory=dict)  # canonical IP/domain dedup + enrichment merge
    seen_edge_ids: set[str] = field(default_factory=set)  # avoids a duplicate incident->indicator edge when a node is deduped


def build_attack_graph(
    investigation: Any, ioc_lookup: IOCLookup | None = None, asset_lookup: AssetLookup | None = None
) -> AttackGraph:
    ioc_lookup = ioc_lookup or (lambda _t, _v: None)
    asset_lookup = asset_lookup or (lambda _n: None)
    incident_id = f"incident:{investigation.id}"
    graph = AttackGraph(investigation_id=str(investigation.id))
    ctx = _Ctx(graph=graph, seen_identity_nodes={})

    graph.nodes.append(
        GraphNode(
            id=incident_id,
            type=NodeType.INCIDENT,
            label=investigation.title,
            tier=ConfidenceTier.CONFIRMED,
            timestamp=investigation.created_at,
            data={
                "severity": investigation.severity.value if hasattr(investigation.severity, "value") else investigation.severity,
                "status": investigation.status.value if hasattr(investigation.status, "value") else investigation.status,
                "source": investigation.source,
                "confidence": investigation.confidence,
                "root_cause": investigation.root_cause,
            },
        )
    )

    _add_timeline(ctx, incident_id, investigation, ioc_lookup, asset_lookup)
    _add_evidence_records(ctx, incident_id, investigation)
    _add_simple_evidence(ctx, incident_id, investigation, ioc_lookup, asset_lookup)
    _add_attack_chain(ctx, incident_id, investigation)
    _add_mitre_techniques(ctx, incident_id, investigation)
    _add_alternative_hypotheses(ctx, incident_id, investigation)
    _add_findings(ctx, incident_id, investigation)

    return graph


# --- Timeline: events, and the identities/assets they reference ---
# Every edge here comes directly from a field the event actually has —
# an event only gets an `originated_from`/`targeted` edge if its own
# `actor`/`affected_asset` column is set, and `leads_to` between events
# is pure chronological ordering, never a claimed causal link (we have
# no data that would justify claiming causation).

def _add_timeline(ctx: _Ctx, incident_id: str, investigation: Any, ioc_lookup: IOCLookup, asset_lookup: AssetLookup) -> None:
    events = sorted(investigation.timeline_events, key=lambda e: e.occurred_at)
    previous_event_id: str | None = None

    for event in events:
        event_id = f"event:{event.id}"
        severity = event.severity.value if hasattr(event.severity, "value") and event.severity else event.severity
        ctx.graph.nodes.append(
            GraphNode(
                id=event_id,
                type=NodeType.EVENT,
                label=event.description,
                tier=ConfidenceTier.CONFIRMED,
                timestamp=event.occurred_at,
                data={"severity": severity, "source": event.source, "mitre_technique": event.mitre_technique},
            )
        )
        ctx.graph.edges.append(
            GraphEdge(
                id=f"{incident_id}->{event_id}:observed_in",
                source=incident_id,
                target=event_id,
                relationship=EdgeType.OBSERVED_IN,
                tier=ConfidenceTier.CONFIRMED,
                rationale="This event is recorded on the investigation's timeline.",
            )
        )

        if previous_event_id is not None:
            ctx.graph.edges.append(
                GraphEdge(
                    id=f"{previous_event_id}->{event_id}:leads_to",
                    source=previous_event_id,
                    target=event_id,
                    relationship=EdgeType.LEADS_TO,
                    tier=ConfidenceTier.CONFIRMED,
                    rationale="Observed to occur after the previous event, in chronological order. "
                    "This reflects sequence only, not a verified causal link.",
                )
            )
        previous_event_id = event_id

        if event.actor:
            identity_id = _get_or_create_identity_node(ctx, event.actor, ioc_lookup)
            ctx.graph.edges.append(
                GraphEdge(
                    id=f"{event_id}->{identity_id}:originated_from",
                    source=event_id,
                    target=identity_id,
                    relationship=EdgeType.ORIGINATED_FROM,
                    tier=ConfidenceTier.CONFIRMED,
                    rationale="Recorded as the actor associated with this event.",
                )
            )

        if event.affected_asset:
            asset_id = _get_or_create_asset_node(ctx, event.affected_asset, asset_lookup)
            ctx.graph.edges.append(
                GraphEdge(
                    id=f"{event_id}->{asset_id}:targeted",
                    source=event_id,
                    target=asset_id,
                    relationship=EdgeType.TARGETED,
                    tier=ConfidenceTier.CONFIRMED,
                    rationale="Recorded as the asset affected by this event.",
                )
            )

        if event.mitre_technique:
            mitre_id = _get_or_create_mitre_node(ctx, event.mitre_technique, ConfidenceTier.PROBABLE)
            ctx.graph.edges.append(
                GraphEdge(
                    id=f"{event_id}->{mitre_id}:supports",
                    source=event_id,
                    target=mitre_id,
                    relationship=EdgeType.SUPPORTS,
                    tier=ConfidenceTier.PROBABLE,  # a technique label is always an interpretation, even of a confirmed event
                    rationale="This event was tagged with this MITRE technique when it was recorded.",
                )
            )


def _canonical_ip_domain_id(value: str) -> str:
    """The one node-ID scheme every code path must use for an IP/domain/
    URL indicator, regardless of which of Evidence, the IOC registry, a
    timeline event's actor field, an Asset relationship, or a future
    AI-derived relationship first mentions it. Fixes a real duplication
    bug: the actor path and the Evidence path used to compute two
    different IDs for the same address (`ip_domain:185-220-101-4` from
    the actor path vs `ip_domain:ip-185-220-101-4` from the Evidence
    path, which slugged an extra `ip-` type prefix into the ID), so the
    same real-world indicator rendered as two graph nodes with
    enrichment attached to only one. Keyed on the value alone — not on
    which evidence type reported it — so canonicalization only ever
    merges genuinely identical values, never two different ones."""
    return f"{NodeType.IP_DOMAIN.value}:{_slug(value)}"


def _get_or_create_ip_domain_node(ctx: _Ctx, value: str, ioc_type: str, ioc_lookup: IOCLookup) -> str:
    """Every IP/domain/URL node in the graph is created or reused
    through this one function — see _canonical_ip_domain_id for why.
    Safe to call repeatedly for the same value from different sources
    within one graph build: the first call creates the node, every
    later call reuses it and merges in whatever real enrichment
    `ioc_lookup` has for it, so a node first created via the actor path
    (which has no IOC context) still ends up carrying the same
    tags/confidence/sightings/enrichment/verdict/provenance/watchlist
    state as one first created via Evidence, and vice versa."""
    node_id = _canonical_ip_domain_id(value)
    node = ctx.nodes_by_id.get(node_id)
    if node is None:
        node = GraphNode(id=node_id, type=NodeType.IP_DOMAIN, label=value, tier=ConfidenceTier.CONFIRMED, data={})
        ctx.graph.nodes.append(node)
        ctx.nodes_by_id[node_id] = node

    enrichment = ioc_lookup(ioc_type, value)
    if enrichment:
        node.data.setdefault("indicator_type", ioc_type)
        node.data.setdefault("value", value)
        node.data.update(enrichment)  # real registry data only — never fabricated if ioc_lookup returned None

    return node_id


def _get_or_create_identity_node(ctx: _Ctx, value: str, ioc_lookup: IOCLookup) -> str:
    if _classify_identity_type(value) == NodeType.IP_DOMAIN:
        return _get_or_create_ip_domain_node(ctx, value, "ip", ioc_lookup)

    key = f"account::{value}"
    if key in ctx.seen_identity_nodes:
        return ctx.seen_identity_nodes[key]
    node_id = f"{NodeType.ACCOUNT.value}:{_slug(value)}"
    ctx.graph.nodes.append(GraphNode(id=node_id, type=NodeType.ACCOUNT, label=value, tier=ConfidenceTier.CONFIRMED))
    ctx.seen_identity_nodes[key] = node_id
    return node_id


def _get_or_create_asset_node(ctx: _Ctx, value: str, asset_lookup: AssetLookup) -> str:
    key = f"asset::{value}"
    if key in ctx.seen_identity_nodes:
        return ctx.seen_identity_nodes[key]
    node_id = f"asset:{_slug(value)}"
    enrichment = asset_lookup(value)
    data: dict[str, Any] = {}
    if enrichment:
        data.update(enrichment)
    ctx.graph.nodes.append(GraphNode(id=node_id, type=NodeType.ASSET, label=value, tier=ConfidenceTier.CONFIRMED, data=data))
    ctx.seen_identity_nodes[key] = node_id
    return node_id


def _get_or_create_mitre_node(ctx: _Ctx, technique_id: str, tier: ConfidenceTier) -> str:
    key = f"mitre::{technique_id}"
    if key in ctx.seen_identity_nodes:
        return ctx.seen_identity_nodes[key]
    node_id = f"mitre:{_slug(technique_id)}"
    ctx.graph.nodes.append(
        GraphNode(id=node_id, type=NodeType.MITRE_TECHNIQUE, label=technique_id, tier=tier)
    )
    ctx.seen_identity_nodes[key] = node_id
    return node_id


# --- Forensic evidence records (Evidence Explorer data) ---
# Attached directly to the incident, never to a specific event: our
# schema has no field linking an EvidenceRecord to a TimelineEvent, so
# claiming "this event caused this evidence" would be inventing a link
# the data doesn't contain.

def _add_evidence_records(ctx: _Ctx, incident_id: str, investigation: Any) -> None:
    for record in investigation.evidence_records:
        node_id = f"evidence:{record.id}"
        ctx.graph.nodes.append(
            GraphNode(
                id=node_id,
                type=NodeType.EVIDENCE,
                label=record.summary,
                tier=ConfidenceTier.CONFIRMED,
                timestamp=record.occurred_at,
                data={"category": record.category, **record.details},
            )
        )
        ctx.graph.edges.append(
            GraphEdge(
                id=f"{incident_id}->{node_id}:related_to",
                source=incident_id,
                target=node_id,
                relationship=EdgeType.RELATED_TO,
                tier=ConfidenceTier.CONFIRMED,
                rationale="This forensic evidence was recorded as part of the investigation.",
            )
        )


# --- Simple indicators (IP/hash/domain/url/asset chips) ---
# Enriched with real IOC registry data (tags, confidence, sightings)
# when it exists via ioc_lookup — never fabricated if it doesn't.

def _add_simple_evidence(ctx: _Ctx, incident_id: str, investigation: Any, ioc_lookup: IOCLookup, asset_lookup: AssetLookup) -> None:
    type_map = {
        "ip": NodeType.IP_DOMAIN,
        "domain": NodeType.IP_DOMAIN,
        "url": NodeType.IP_DOMAIN,
        "asset": NodeType.ASSET,
        "hash": NodeType.IOC,
    }

    for ev in investigation.evidence:
        ev_type = ev.type.value if hasattr(ev.type, "value") else ev.type
        node_type = type_map.get(ev_type, NodeType.IOC)

        if node_type == NodeType.IP_DOMAIN:
            # Routed through the same canonical function the actor path
            # uses, so the same value never produces two nodes — see
            # _canonical_ip_domain_id.
            node_id = _get_or_create_ip_domain_node(ctx, ev.value, ev_type, ioc_lookup)
        elif node_type == NodeType.ASSET:
            node_id = _get_or_create_asset_node(ctx, ev.value, asset_lookup)
        else:
            # hash/other IOC types: no cross-source duplication risk
            # exists today (evidence is the only source), but still
            # dedupe against repeated Evidence rows for the same value
            # within one investigation, consistent with the "no
            # duplicate node IDs" invariant this fix enforces overall.
            node_id = f"{node_type.value}:{_slug(f'{ev_type}-{ev.value}')}"
            if node_id not in ctx.nodes_by_id:
                data: dict[str, Any] = {"indicator_type": ev_type, "value": ev.value}
                enrichment = ioc_lookup(ev_type, ev.value)
                if enrichment:
                    data.update(enrichment)
                node = GraphNode(id=node_id, type=node_type, label=ev.value, tier=ConfidenceTier.CONFIRMED, data=data)
                ctx.graph.nodes.append(node)
                ctx.nodes_by_id[node_id] = node

        # A node reused across multiple Evidence rows (e.g. the same IP
        # recorded twice) must not produce two identical incident->node
        # edges.
        edge_id = f"{incident_id}->{node_id}:related_to"
        if edge_id not in ctx.seen_edge_ids:
            ctx.graph.edges.append(
                GraphEdge(
                    id=edge_id,
                    source=incident_id,
                    target=node_id,
                    relationship=EdgeType.RELATED_TO,
                    tier=ConfidenceTier.CONFIRMED,
                    rationale="This indicator was recorded as evidence in the investigation.",
                )
            )
            ctx.seen_edge_ids.add(edge_id)


# --- Attack chain (AI-derived) ---
# If the investigation hasn't been analyzed, or the AI legitimately
# returned no stages because the evidence was too thin (the bare-curl
# case this whole rule exists for), we render exactly one UNKNOWN node
# saying so — never a fabricated default sequence.

def _add_attack_chain(ctx: _Ctx, incident_id: str, investigation: Any) -> None:
    chain = investigation.attack_chain or []
    if not chain:
        node_id = f"uncertainty:{investigation.id}:attack-chain"
        ctx.graph.nodes.append(
            GraphNode(
                id=node_id,
                type=NodeType.UNCERTAINTY,
                label="Insufficient evidence for attack stages",
                tier=ConfidenceTier.UNKNOWN,
            )
        )
        ctx.graph.edges.append(
            GraphEdge(
                id=f"{incident_id}->{node_id}:related_to",
                source=incident_id,
                target=node_id,
                relationship=EdgeType.RELATED_TO,
                tier=ConfidenceTier.UNKNOWN,
                rationale="No attack chain could be identified — either this investigation hasn't been "
                "analyzed yet, or the available evidence was too sparse to reconstruct a reliable sequence.",
            )
        )
        return

    tier = _tier_from_score(investigation.confidence)
    previous_id = incident_id
    for i, step in enumerate(chain):
        node_id = f"phase:{investigation.id}:{i}"
        ctx.graph.nodes.append(
            GraphNode(
                id=node_id,
                type=NodeType.ATTACK_PHASE,
                label=step.get("phase", f"Stage {i + 1}"),
                tier=tier,
                data={"description": step.get("description", "")},
            )
        )
        ctx.graph.edges.append(
            GraphEdge(
                id=f"{previous_id}->{node_id}:leads_to",
                source=previous_id,
                target=node_id,
                relationship=EdgeType.LEADS_TO,
                tier=tier,
                rationale=f"Identified by Aegis AI's analysis of this investigation, at {investigation.confidence}% confidence.",
            )
        )
        previous_id = node_id


# --- Investigation-level MITRE mapping (AI-derived, not tied to one event) ---

def _add_mitre_techniques(ctx: _Ctx, incident_id: str, investigation: Any) -> None:
    techniques = investigation.mitre_techniques or []
    already_linked = {t for t in techniques if f"mitre::{t}" in ctx.seen_identity_nodes}

    if not techniques:
        # Only add the placeholder if no per-event MITRE tag exists either —
        # if events already supplied techniques, there's no real gap to flag.
        if not any(k.startswith("mitre::") for k in ctx.seen_identity_nodes):
            node_id = f"uncertainty:{investigation.id}:mitre"
            ctx.graph.nodes.append(
                GraphNode(id=node_id, type=NodeType.UNCERTAINTY, label="No MITRE technique identified", tier=ConfidenceTier.UNKNOWN)
            )
            ctx.graph.edges.append(
                GraphEdge(
                    id=f"{incident_id}->{node_id}:related_to",
                    source=incident_id,
                    target=node_id,
                    relationship=EdgeType.RELATED_TO,
                    tier=ConfidenceTier.UNKNOWN,
                    rationale="No MITRE ATT&CK technique could be mapped from the available evidence.",
                )
            )
        return

    tier = _tier_from_score(investigation.confidence)
    for technique in techniques:
        if technique in already_linked:
            continue  # already connected via a specific event — don't duplicate at the incident level
        mitre_id = _get_or_create_mitre_node(ctx, technique, tier)
        ctx.graph.edges.append(
            GraphEdge(
                id=f"{incident_id}->{mitre_id}:supports",
                source=incident_id,
                target=mitre_id,
                relationship=EdgeType.SUPPORTS,
                tier=tier,
                rationale=f"Identified in Aegis AI's overall analysis, at {investigation.confidence}% confidence.",
            )
        )


# --- Alternative hypotheses: real competing explanations, shown as such ---

def _add_alternative_hypotheses(ctx: _Ctx, incident_id: str, investigation: Any) -> None:
    for i, hyp in enumerate(investigation.alternative_hypotheses or []):
        likelihood = hyp.get("likelihood", 0)
        node_id = f"hypothesis:{investigation.id}:{i}"
        ctx.graph.nodes.append(
            GraphNode(
                id=node_id,
                type=NodeType.HYPOTHESIS,
                label=hyp.get("hypothesis", "Alternative explanation"),
                tier=_tier_from_score(likelihood),
                data={"likelihood": likelihood},
            )
        )
        ctx.graph.edges.append(
            GraphEdge(
                id=f"{incident_id}->{node_id}:contradicts",
                source=incident_id,
                target=node_id,
                relationship=EdgeType.CONTRADICTS,
                tier=_tier_from_score(likelihood),
                rationale=f"An alternative explanation considered by Aegis AI, estimated at {likelihood}% "
                "likelihood against the primary root cause.",
            )
        )


# --- Recommended actions / findings ---

def _add_findings(ctx: _Ctx, incident_id: str, investigation: Any) -> None:
    for action in investigation.recommended_actions:
        tier = _tier_from_score(action.confidence) if action.confidence is not None else ConfidenceTier.UNKNOWN
        node_id = f"finding:{action.id}"
        ctx.graph.nodes.append(
            GraphNode(
                id=node_id,
                type=NodeType.FINDING,
                label=action.title,
                tier=tier,
                data={
                    "description": action.description,
                    "status": action.status.value if hasattr(action.status, "value") else action.status,
                    "business_impact": action.business_impact,
                    "approval_tier": action.approval_tier,
                },
            )
        )
        ctx.graph.edges.append(
            GraphEdge(
                id=f"{incident_id}->{node_id}:related_to",
                source=incident_id,
                target=node_id,
                relationship=EdgeType.RELATED_TO,
                tier=tier,
                rationale="Recommended by Aegis AI's analysis of this investigation.",
            )
        )
