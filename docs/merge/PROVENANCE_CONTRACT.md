# Provenance Contract

## Invariants

1. Evidence bytes, their SHA-256 hashes, EvidenceItems, ParseRuns, RawRecords,
   normalized Events, IndicatorOccurrences, EntityObservations, and
   EntityRelationships are **FACTS**.
2. FACT records are created only by authenticated acquisition, deterministic
   parsing/normalization/extraction, or approved analyst data entry paths that
   explicitly identify their source. AI has no create/update/delete authority
   over FACT records.
3. Every inference references factual records by immutable UUID. Textual
   citations alone are insufficient provenance.
4. Every analyst verdict records analyst user ID, timestamp, rationale, review
   disposition, and an AuditEvent. A verdict does not mutate the referenced fact.
5. Retention/deletion of evidence is policy-controlled and auditable. Cascade
   deletion must never be used to silently erase the lineage of a reviewed
   inference or verdict.
6. In Phase 1, canonical evidence-derived facts use restrictive deletion
   semantics. If an Investigation owns any such facts, destructive deletion is
   rejected at the database/service boundary. Retention and tombstoning are
   deferred rather than simulated by cascade behavior.

## Required lineage

```text
EvidenceItem
  └─ EvidenceParseRun
      └─ RawRecord
          └─ Event

RawRecord or Event
  └─ IndicatorOccurrence ──→ Indicator

RawRecord or Event
  └─ EntityObservation ────→ Entity

Event and/or EntityObservation
  └─ EntityRelationship (source Entity → target Entity)

Factual IDs from any of the above
  └─ AIAnalysis support links → Hypothesis / Recommendation / ReasoningStep
                                      └─ analyst review → Finding / decision
```

## Provenance cardinality and rules

| Derived record | Minimum parent/reference | Required provenance fields |
|---|---|---|
| EvidenceParseRun | exactly one EvidenceItem | parser name/version, status, started/ended time, warnings/error summary |
| RawRecord | exactly one EvidenceItem and one ParseRun | ordinal, content or protected source pointer, content type, byte offset when known |
| Event | exactly one EvidenceItem and RawRecord | normalization version/source, normalized payload, observed timestamp if known |
| IndicatorOccurrence | exactly one Indicator and RawRecord; optional Event | EvidenceItem FK, RawRecord FK, event FK when normalized, observed time, extractor version |
| EntityObservation | exactly one Entity and RawRecord; optional Event | EvidenceItem FK, RawRecord FK, event FK when normalized, observed time, extractor version |
| EntityRelationship | source/target Entity plus at least one Event or EntityObservation | evidence/raw/event/observation support IDs, relationship type, observed time, deterministic rule/version |
| AI support link | exactly one AIAnalysis and one factual target | target type/UUID, role (`supports`/`contradicts`/`context`), optional locator/rationale |

## Immutability and correction protocol

- Source bytes and hash: immutable. A replacement upload is a distinct
  EvidenceItem.
- Parse result correction: create a new EvidenceParseRun with a new parser or
  normalization version. Do not rewrite RawRecords from an old run.
- Event extraction correction: derive Events under the new run. Earlier runs
  remain historically visible and may be superseded.
- Entity/indicator canonicalization: canonical identity can be corrected only
  through an explicit, audited merge/reconciliation record; occurrences remain
  unchanged and retain original provenance.
- Relationship correction: supersede an erroneous deterministic relationship;
  never convert it into an AI assertion or erase its creation history.

## Access and disclosure

Every provenance query is organization-scoped through its Investigation and
EvidenceItem. Download/display of raw evidence must require the same or stricter
authorization as the Investigation. Raw content is untrusted and must never be
HTML-rendered or passed to AI without bounded, recorded context selection.
