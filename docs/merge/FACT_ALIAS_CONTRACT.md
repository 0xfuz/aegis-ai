# Canonical FACT Alias Citation Contract

## Purpose

AIIE never asks an LLM to reproduce canonical database UUIDs. Each generation builds an in-memory alias map from the investigation's current canonical context. Aliases are only LLM presentation and validation references; they are not canonical identifiers and are never stored in `intelligence_fact_links`.

## Deterministic aliases

Aliases are assigned independently for each fact type after sorting the type's canonical UUIDs lexically.

| Context collection | Alias prefix | Example |
| --- | --- | --- |
| EvidenceItem | `E` | `E1` |
| RawRecord | `RR` | `RR1` |
| Event | `EV` | `EV1` |
| Indicator | `IN` | `IN1` |
| Entity | `EN` | `EN1` |
| EntityRelationship | `REL` | `REL1` |

The model receives alias-projected records and no investigation or canonical FACT UUIDs. Relationship references are projected to their aliases too. Raw-record content remains excluded; only safe metadata is present.

## Output and resolution

The structured output contract uses `supporting_facts` and `contradicting_facts`, containing aliases only. The provider schema constrains these arrays to the current analysis aliases. Before any intelligence item is written, the backend validates alias syntax and resolves every alias only against that run's in-memory map.

`alias -> canonical UUID -> IntelligenceFactLink.fact_id`

Unknown, malformed, or out-of-context aliases fail the run atomically. An alias from another analysis has no authority: only the current run's map is consulted. If an alias label coincides between analyses, it still resolves exclusively to the current analysis's scoped canonical ID.

## Security and persistence

- Canonical UUIDs remain the only values stored in `intelligence_fact_links`.
- Aliases are not stored in FACT records, analysis rows, or review history.
- Organization and investigation scoping occur when the canonical context is built.
- FACT rows are never modified.
- Output validation occurs before item/link persistence; failed analysis output leaves no partial inference items.
