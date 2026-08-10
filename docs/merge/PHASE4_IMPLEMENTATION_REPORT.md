# Phase 4 Implementation Report — Attack Graph Unification

## Canonical graph architecture

Phase 4 replaces only the case-workspace Attack Graph placeholder (`/investigations/{id}/relationships`) with a FACT-only projection. `CanonicalGraphProjectionService` reads canonical SQLAlchemy FACT models directly and writes nothing. It does not introduce a graph database or a second relationship store.

- Entity nodes are canonical `Entity` records.
- Indicator nodes are canonical organization indicators only when occurrence-scoped to the selected investigation.
- Edges are derived exclusively from `EntityRelationship` records.
- `EvidenceItem`, `RawRecord`, `Event`, `EntityObservation`, and `IndicatorOccurrence` remain provenance, not invented visual edges.

All returned nodes and edges use `status: FACT`. No AI nodes, confidence inference, attack path, hypothesis, finding, MITRE inference, or enrichment was added.

## Endpoint

`GET /api/v1/investigations/{id}/graph` is additive and protected by `investigation:read`. It supports optional `entity_type`, `relationship_type`, `evidence_id`, `start_at`, and `end_at` projection filters.

The original `/api/v1/investigations/{id}/attack-graph` endpoint and `/investigations/{id}/attack-graph` route remain unchanged as the explicitly legacy mixed graph.

## UI

The canonical workspace graph uses existing React Flow and Dagre dependencies for pan, zoom, minimap, controls, fit view, and restrained layout. It adds entity-type, relationship-type, and evidence filters plus node and edge inspectors. Edge inspectors retain graph edge → relationship → event/raw record → evidence references. The evidence link preserves the active investigation ID.

## Aggregation and identity

Rows with identical source entity, target entity, and relationship type aggregate into one edge. Each aggregation retains count, first/last timestamps, and every source relationship/provenance reference. Identity is never reconciled at projection time; see `ENTITY_IDENTITY_RULES.md`.

## Verification

| Check | Result |
| --- | --- |
| Python compile | passed |
| Focused backend tests | passed: 19 (canonical graph, parsers, legacy graph) |
| Frontend typecheck | passed |
| Frontend lint | passed |
| Frontend unit tests | passed: 9 (including canonical graph empty state, inspectors, provenance link, and failure state) |
| Production frontend build | passed via `docker compose build frontend` |
| Playwright/e2e | not present in repository |

The full backend suite remains host-environment blocked by the pre-existing invalid ambient `DEBUG=release` setting and unavailable `python-jose` package. No backend behavior was modified to work around that host-only issue.

## Known limitations

- The initial graph query includes canonical indicators as disconnected factual nodes because Phase 4 is forbidden from fabricating convenience edges from occurrences to entities/evidence.
- Server-side filters apply to the projection; the UI uses equivalent client-side filters on the loaded graph for immediate interaction.
- No Asset/IOC reconciliation is done until a separately approved deterministic mapping phase.

## Exact Phase 5 scope (not implemented)

Phase 5 may introduce the approved AI trust model for append-only, provenance-linked INFERENCES and analyst VERDICTS. It must not mutate FACT records or cause AI outputs to appear as factual graph edges.
