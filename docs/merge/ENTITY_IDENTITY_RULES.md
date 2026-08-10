# Entity Identity Rules — Phase 4

The canonical graph does not reconcile or merge entity records at projection time. It uses the immutable canonical entity IDs emitted by the Phase 2 deterministic parser.

- Entity node identity is `entity:{Entity.id}`.
- An entity's canonical value is display metadata, not a cross-case merge key.
- Indicator node identity is `indicator:{Indicator.id}`; organization-level indicators are included only when an `IndicatorOccurrence` scopes them to the selected investigation.
- Existing organization Assets and legacy IOCs are not added to the graph in Phase 4. No exact-match reconciliation is performed yet, so unrelated records cannot silently merge.
- `EntityRelationship` source and target IDs are authoritative. The projection never joins two entities merely because labels, hostnames, IP strings, or display values look similar.

Future reconciliation may add only documented, deterministic exact identity mappings (for example normalized hostname-to-asset identity within the same organization). It must retain both original IDs and provenance and requires separate approval.
