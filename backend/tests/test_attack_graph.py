"""
The five required test scenarios for the Attack Graph. These are pure
unit tests against build_attack_graph() with plain SimpleNamespace test
doubles — no database, no app, no fixtures — because graph_builder.py is
deliberately duck-typed to make exactly this possible.

The thing every test in this file is really checking, one way or
another: does the graph ever show more than the data actually supports?
"""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.modules.attack_graph.domain.graph_builder import build_attack_graph
from app.modules.attack_graph.domain.graph_model import ConfidenceTier, EdgeType, NodeType

NOW = datetime.now(timezone.utc)


def _event(minutes_ago, description, mitre_technique=None, actor=None, affected_asset=None, severity=None, source="Mock"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        occurred_at=NOW - timedelta(minutes=minutes_ago),
        description=description,
        severity=severity,
        mitre_technique=mitre_technique,
        source=source,
        affected_asset=affected_asset,
        actor=actor,
    )


def _evidence(ev_type, value):
    return SimpleNamespace(id=uuid.uuid4(), type=ev_type, value=value)


def _evidence_record(category, summary, details=None, minutes_ago=10):
    return SimpleNamespace(
        id=uuid.uuid4(), category=category, occurred_at=NOW - timedelta(minutes=minutes_ago),
        summary=summary, details=details or {},
    )


def _action(title, confidence=None, business_impact=None, approval_tier=None, status="pending"):
    return SimpleNamespace(
        id=uuid.uuid4(), title=title, description="", status=status,
        confidence=confidence, business_impact=business_impact, approval_tier=approval_tier,
    )


def _investigation(**overrides):
    base = dict(
        id=uuid.uuid4(),
        title="Test investigation",
        severity="medium",
        status="new",
        source="Mock",
        confidence=0,
        root_cause="",
        mitre_techniques=[],
        blast_radius_summary="",
        false_positive_probability=0,
        attack_chain=[],
        alternative_hypotheses=[],
        reasoning_chain=[],
        created_at=NOW,
        timeline_events=[],
        evidence_records=[],
        evidence=[],
        notes=[],
        recommended_actions=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _nodes_by_type(graph, node_type: NodeType):
    return [n for n in graph.nodes if n.type == node_type]


def _edges_by_relationship(graph, rel: EdgeType):
    return [e for e in graph.edges if e.relationship == rel]


# --- Scenario 1: sparse evidence / bare curl request ---
# This is the scenario the whole integrity rule exists for: a single IP
# indicator, a bare "event received" description, no MITRE, no attack
# chain. The graph must not invent Initial Access -> Execution ->
# Persistence -> Exfiltration.

def test_sparse_evidence_shows_uncertainty_not_fabricated_stages():
    inv = _investigation(
        confidence=0,
        evidence=[_evidence("ip", "203.0.113.5")],
        timeline_events=[_event(5, "Event received via webhook", actor=None)],
    )
    graph = build_attack_graph(inv)

    assert _nodes_by_type(graph, NodeType.ATTACK_PHASE) == []
    uncertainty_nodes = _nodes_by_type(graph, NodeType.UNCERTAINTY)
    labels = {n.label for n in uncertainty_nodes}
    assert "Insufficient evidence for attack stages" in labels
    assert "No MITRE technique identified" in labels
    assert all(n.tier == ConfidenceTier.UNKNOWN for n in uncertainty_nodes)

    # The one real indicator should still show up, confirmed.
    ip_nodes = _nodes_by_type(graph, NodeType.IP_DOMAIN)
    assert len(ip_nodes) == 1
    assert ip_nodes[0].tier == ConfidenceTier.CONFIRMED


# --- Scenario 2: suspicious authentication incident ---

def test_authentication_incident_links_actor_and_asset_with_correct_tiers():
    inv = _investigation(
        confidence=92,
        mitre_techniques=["T1078"],
        attack_chain=[
            {"phase": "Initial Access", "description": "Login from an unrecognized location."},
            {"phase": "Persistence", "description": "Session token reused from a different IP."},
        ],
        timeline_events=[
            _event(10, "Login from new geo", mitre_technique="T1078", actor="j.martinez@example.com", affected_asset="okta-tenant"),
        ],
        evidence=[_evidence("ip", "185.220.101.4")],
    )
    graph = build_attack_graph(inv)

    accounts = _nodes_by_type(graph, NodeType.ACCOUNT)
    assert len(accounts) == 1 and accounts[0].label == "j.martinez@example.com"

    assets = _nodes_by_type(graph, NodeType.ASSET)
    assert len(assets) == 1 and assets[0].label == "okta-tenant"

    originated_from = _edges_by_relationship(graph, EdgeType.ORIGINATED_FROM)
    assert len(originated_from) == 1
    assert originated_from[0].tier == ConfidenceTier.CONFIRMED  # the link itself is a recorded fact

    # High confidence (92) -> attack phases and MITRE should be PROBABLE
    phases = _nodes_by_type(graph, NodeType.ATTACK_PHASE)
    assert len(phases) == 2
    assert all(p.tier == ConfidenceTier.PROBABLE for p in phases)

    # MITRE technique appears once (event-level), not duplicated at incident level
    mitre_nodes = _nodes_by_type(graph, NodeType.MITRE_TECHNIQUE)
    assert len(mitre_nodes) == 1
    assert mitre_nodes[0].label == "T1078"


# --- Scenario 3: multi-stage incident with several evidence types ---

def test_multi_stage_incident_covers_every_evidence_type():
    inv = _investigation(
        confidence=85,
        attack_chain=[{"phase": "Initial Access", "description": "..."}],
        evidence=[
            _evidence("ip", "10.0.0.5"),
            _evidence("hash", "abc123"),
            _evidence("asset", "web-server-01"),
        ],
        evidence_records=[
            _evidence_record("process", "Suspicious process spawned"),
            _evidence_record("dns", "Query for known-bad domain"),
        ],
        recommended_actions=[_action("Isolate host", confidence=88, business_impact="medium", approval_tier="SOC Tier 2")],
    )
    graph = build_attack_graph(inv)

    assert len(_nodes_by_type(graph, NodeType.IP_DOMAIN)) == 1
    assert len(_nodes_by_type(graph, NodeType.IOC)) == 1  # the hash
    assert len(_nodes_by_type(graph, NodeType.ASSET)) == 1
    assert len(_nodes_by_type(graph, NodeType.EVIDENCE)) == 2
    assert len(_nodes_by_type(graph, NodeType.FINDING)) == 1

    finding = _nodes_by_type(graph, NodeType.FINDING)[0]
    assert finding.tier == ConfidenceTier.PROBABLE  # confidence=88 -> probable


# --- Scenario 4: conflicting evidence (alternative hypotheses) ---

def test_alternative_hypotheses_use_contradicts_edge_with_own_tier():
    inv = _investigation(
        confidence=70,
        attack_chain=[{"phase": "Impact", "description": "..."}],
        alternative_hypotheses=[
            {"hypothesis": "Benign internal tooling", "likelihood": 45},
            {"hypothesis": "Coincidental scan", "likelihood": 10},
        ],
    )
    graph = build_attack_graph(inv)

    hypothesis_nodes = _nodes_by_type(graph, NodeType.HYPOTHESIS)
    assert len(hypothesis_nodes) == 2

    contradicts_edges = _edges_by_relationship(graph, EdgeType.CONTRADICTS)
    assert len(contradicts_edges) == 2

    by_label = {n.label: n for n in hypothesis_nodes}
    assert by_label["Benign internal tooling"].tier == ConfidenceTier.POSSIBLE  # 45 -> possible
    assert by_label["Coincidental scan"].tier == ConfidenceTier.UNKNOWN  # 10 -> unknown

    # Hypotheses are never CONFIRMED — they're always AI-derived judgments.
    assert all(n.tier != ConfidenceTier.CONFIRMED for n in hypothesis_nodes)


# --- Scenario 5: missing MITRE mapping (but otherwise well-evidenced) ---

def test_missing_mitre_mapping_does_not_block_attack_chain():
    inv = _investigation(
        confidence=80,
        mitre_techniques=[],  # explicitly no MITRE mapping
        attack_chain=[
            {"phase": "Initial Access", "description": "..."},
            {"phase": "Impact", "description": "..."},
        ],
        timeline_events=[_event(5, "Bucket policy changed", mitre_technique=None)],
    )
    graph = build_attack_graph(inv)

    # Attack chain should still render fully — a missing MITRE mapping is
    # a separate gap, not a reason to withhold the attack chain too.
    assert len(_nodes_by_type(graph, NodeType.ATTACK_PHASE)) == 2

    uncertainty_labels = {n.label for n in _nodes_by_type(graph, NodeType.UNCERTAINTY)}
    assert "No MITRE technique identified" in uncertainty_labels
    assert "Insufficient evidence for attack stages" not in uncertainty_labels

    assert _nodes_by_type(graph, NodeType.MITRE_TECHNIQUE) == []


# --- Cross-cutting: every edge must reference a real node ---

@pytest.mark.parametrize(
    "inv",
    [
        _investigation(),  # totally empty investigation
        _investigation(
            confidence=90, attack_chain=[{"phase": "P", "description": "d"}],
            evidence=[_evidence("ip", "1.2.3.4")], mitre_techniques=["T1078"],
            alternative_hypotheses=[{"hypothesis": "h", "likelihood": 50}],
            recommended_actions=[_action("a", confidence=60)],
        ),
    ],
)
def test_every_edge_references_an_existing_node(inv):
    graph = build_attack_graph(inv)
    node_ids = {n.id for n in graph.nodes}
    for edge in graph.edges:
        assert edge.source in node_ids
        assert edge.target in node_ids


# --- Regression: canonical IP/domain node ID (stabilization fix) ---
# Previously, an IP seen as an event's `actor` and the same IP seen as
# Evidence produced two different node IDs
# (`ip_domain:185-220-101-4` vs `ip_domain:ip-185-220-101-4`) for the
# same real-world indicator, with enrichment attached to only one.

def test_same_ip_from_evidence_and_actor_becomes_one_node():
    inv = _investigation(
        evidence=[_evidence("ip", "185.220.101.4")],
        timeline_events=[_event(5, "Login from watched IP", actor="185.220.101.4")],
    )
    graph = build_attack_graph(inv)

    ip_nodes = _nodes_by_type(graph, NodeType.IP_DOMAIN)
    assert len(ip_nodes) == 1
    assert ip_nodes[0].label == "185.220.101.4"

    # Both the Evidence-derived edge and the actor-derived edge must
    # point at that same single node.
    originated_from = _edges_by_relationship(graph, EdgeType.ORIGINATED_FROM)
    related_to = [e for e in _edges_by_relationship(graph, EdgeType.RELATED_TO) if e.target == ip_nodes[0].id]
    assert len(originated_from) == 1
    assert originated_from[0].target == ip_nodes[0].id
    assert len(related_to) == 1


def test_same_domain_from_multiple_evidence_rows_becomes_one_node():
    inv = _investigation(
        evidence=[_evidence("domain", "evil-c2.example"), _evidence("domain", "evil-c2.example")],
    )
    graph = build_attack_graph(inv)

    domain_nodes = [n for n in _nodes_by_type(graph, NodeType.IP_DOMAIN) if n.label == "evil-c2.example"]
    assert len(domain_nodes) == 1

    # No duplicate incident->node edge either, even though the value
    # was recorded twice.
    related_to = [e for e in _edges_by_relationship(graph, EdgeType.RELATED_TO) if e.target == domain_nodes[0].id]
    assert len(related_to) == 1


def test_ioc_enrichment_is_preserved_on_the_canonical_node():
    inv = _investigation(
        evidence=[_evidence("ip", "185.220.101.4")],
        timeline_events=[_event(5, "Login from watched IP", actor="185.220.101.4")],
    )

    def ioc_lookup(ioc_type, value):
        if (ioc_type, value) == ("ip", "185.220.101.4"):
            return {
                "tags": ["tor-exit-node", "known-malicious"],
                "confidence": 92,
                "sightings_count": 2,
                "enrichment": {"reputation": "malicious"},
                "verdict": "malicious",
                "provenance": "internal",
                "is_watched": True,
            }
        return None

    graph = build_attack_graph(inv, ioc_lookup=ioc_lookup)

    ip_nodes = _nodes_by_type(graph, NodeType.IP_DOMAIN)
    assert len(ip_nodes) == 1
    data = ip_nodes[0].data
    assert data["tags"] == ["tor-exit-node", "known-malicious"]
    assert data["confidence"] == 92
    assert data["sightings_count"] == 2
    assert data["enrichment"] == {"reputation": "malicious"}
    assert data["verdict"] == "malicious"
    assert data["provenance"] == "internal"
    assert data["is_watched"] is True


def test_edges_from_all_sources_point_to_the_same_canonical_node():
    inv = _investigation(
        evidence=[_evidence("ip", "9.9.9.9")],
        timeline_events=[
            _event(10, "First sighting", actor="9.9.9.9"),
            _event(5, "Second sighting", actor="9.9.9.9"),
        ],
    )
    graph = build_attack_graph(inv)

    ip_nodes = _nodes_by_type(graph, NodeType.IP_DOMAIN)
    assert len(ip_nodes) == 1
    canonical_id = ip_nodes[0].id

    originated_from = _edges_by_relationship(graph, EdgeType.ORIGINATED_FROM)
    assert len(originated_from) == 2  # one per event — each event genuinely names this actor
    assert all(e.target == canonical_id for e in originated_from)

    related_to_ip = [e for e in _edges_by_relationship(graph, EdgeType.RELATED_TO) if e.target == canonical_id]
    assert len(related_to_ip) == 1


def test_no_duplicate_node_ids_are_emitted():
    inv = _investigation(
        confidence=85,
        mitre_techniques=["T1078"],
        attack_chain=[{"phase": "Initial Access", "description": "..."}],
        evidence=[
            _evidence("ip", "185.220.101.4"),
            _evidence("ip", "185.220.101.4"),
            _evidence("domain", "evil-c2.example"),
            _evidence("asset", "jump-host-03"),
        ],
        timeline_events=[
            _event(10, "Login", actor="185.220.101.4", affected_asset="jump-host-03", mitre_technique="T1078"),
        ],
    )
    graph = build_attack_graph(inv)

    node_ids = [n.id for n in graph.nodes]
    assert len(node_ids) == len(set(node_ids)), f"duplicate node ids: {node_ids}"

    edge_ids = [e.id for e in graph.edges]
    assert len(edge_ids) == len(set(edge_ids)), f"duplicate edge ids: {edge_ids}"


def test_unrelated_indicators_are_not_merged():
    inv = _investigation(
        evidence=[_evidence("ip", "1.2.3.4"), _evidence("domain", "example.com")],
        timeline_events=[_event(5, "Login", actor="5.6.7.8")],
    )
    graph = build_attack_graph(inv)

    ip_domain_nodes = _nodes_by_type(graph, NodeType.IP_DOMAIN)
    labels = {n.label for n in ip_domain_nodes}
    assert labels == {"1.2.3.4", "example.com", "5.6.7.8"}
    assert len(ip_domain_nodes) == 3  # three distinct values -> three distinct nodes, none merged
