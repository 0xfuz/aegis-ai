# Canonical FACT Graph Contract

`GET /api/v1/investigations/{investigation_id}/graph` is the canonical, read-only investigation graph. It is a projection, not a graph database and not a second relationship store.

## Source of truth

- Entity nodes come from canonical `Entity` rows.
- Indicator nodes come from canonical `Indicator` rows scoped through `IndicatorOccurrence` to the selected investigation.
- Every edge comes only from `EntityRelationship`. The projection may aggregate rows with identical source entity, target entity, and relationship type.
- `EvidenceItem`, `RawRecord`, `Event`, `EntityObservation`, and `IndicatorOccurrence` are represented as provenance references. The service never invents convenience edges between them.

All nodes and edges have `status: FACT`. Phase 4 has no inference node/edge type, confidence calculation, AI output, or AI-derived relationship.

## Edge aggregation and provenance

An aggregated edge retains occurrence count, first/last observed timestamps, and a complete list of relationship IDs, evidence IDs, raw-record IDs, event IDs, and observation IDs. Thus the UI can traverse:

```text
Graph edge -> EntityRelationship -> Event / RawRecord -> EvidenceItem
Graph node -> Entity / Indicator -> Observation / Occurrence -> EvidenceItem
```

The endpoint accepts additive filters for `entity_type`, `relationship_type`, `evidence_id`, `start_at`, and `end_at`. Filters restrict the projection; they never alter facts.

## Legacy compatibility

`/api/v1/investigations/{id}/attack-graph` and `/investigations/{id}/attack-graph` remain the legacy mixed graph. The Phase 4 workspace route `/investigations/{id}/relationships` is canonical and FACT-only.
