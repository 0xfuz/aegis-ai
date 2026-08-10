from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.modules.evidence.domain.graph_projection import build_canonical_graph

NOW = datetime.now(timezone.utc)

def entity(label="host-a", entity_type="HOST"):
    return SimpleNamespace(id=uuid4(), type=entity_type, display_name=label, canonical_value=label.lower(), observations=[object()], first_seen_at=NOW, last_seen_at=NOW, attributes={})

def relationship(source, target, rel_type="CONNECTS_TO", evidence_id=None, when=NOW):
    return SimpleNamespace(id=uuid4(), source_entity_id=source.id, target_entity_id=target.id, relationship_type=rel_type, evidence_id=evidence_id or uuid4(), raw_record_id=uuid4(), event_id=uuid4(), source_observation_id=None, target_observation_id=None, observed_at=when)

def test_graph_nodes_are_factual_and_edges_only_come_from_relationships():
    source, target = entity("host-a"), entity("10.0.0.1", "IP")
    graph = build_canonical_graph(uuid4(), [source, target], [], [relationship(source, target)])
    assert {node["status"] for node in graph["nodes"]} == {"FACT"}
    assert len(graph["edges"]) == 1
    edge = graph["edges"][0]
    assert edge["source"] == f"entity:{source.id}"
    assert edge["target"] == f"entity:{target.id}"
    assert edge["status"] == "FACT"

def test_duplicate_relationships_aggregate_without_losing_provenance():
    source, target = entity(), entity("user-a", "USER")
    first = relationship(source, target, when=NOW - timedelta(minutes=2))
    second = relationship(source, target, when=NOW)
    edge = build_canonical_graph(uuid4(), [source, target], [], [first, second])["edges"][0]
    assert edge["occurrence_count"] == 2
    assert edge["first_seen_at"] == first.observed_at
    assert edge["last_seen_at"] == second.observed_at
    assert {item["relationship_id"] for item in edge["provenance"]} == {str(first.id), str(second.id)}

def test_empty_factual_graph_stays_empty_and_contains_no_inference_edges():
    graph = build_canonical_graph(uuid4(), [], [], [])
    assert graph["nodes"] == []
    assert graph["edges"] == []
