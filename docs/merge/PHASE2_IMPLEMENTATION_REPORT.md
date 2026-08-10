# Phase 2 Implementation Report — Secure Evidence Ingestion

## Outcome

Phase 2 adds a bounded, synchronous, deterministic, AI-free pipeline that
accepts `.log`, `.txt`, `.json`, and `.csv` evidence and persists canonical
FACT records through the Phase 1 schema:

```text
upload → EvidenceItem → EvidenceParseRun → RawRecord → Event
       → IndicatorOccurrence → Indicator
       → EntityObservation → Entity → EntityRelationship
```

No legacy API/UI behavior, timeline, graph, AI endpoint, legacy Investigation
field, data migration, or schema revision was replaced or removed.

## Modules/files added or changed

- `backend/app/modules/evidence/domain/{types,parsers,indicators,service}.py`
- `backend/app/modules/evidence/infrastructure/{storage,repository}.py`
- `backend/app/modules/evidence/api/{schemas,router}.py`
- `backend/app/main.py` — registers additive canonical-evidence router only.
- `backend/app/core/config.py`, `.env.example`, `.gitignore`,
  `backend/.dockerignore` — bounded local evidence storage configuration.
- `backend/tests/test_evidence_parsers.py`
- `backend/tests/test_evidence_ingestion.py`
- harmless fixtures under `backend/tests/fixtures/evidence/`.

## Parser registry and formats

The `ParserRegistry` selects extensible string-identified versioned parsers:
`plain-text@1.0.0` for `.log/.txt`, `json@1.0.0` for `.json`, and `csv@1.0.0`
for `.csv`. Parsers have no AI or external dependency. They preserve RawRecord
content, normalize only fields explicitly represented in source input, and
derive only same-record factual entities/relationships.

Detailed contract: [PARSER_CONTRACT.md](PARSER_CONTRACT.md).

## Storage and limits

Evidence is streamed to `EVIDENCE_STORAGE_DIR` in 64 KiB chunks under an opaque
server-generated key. SHA-256 is calculated while streaming; original filename
is metadata only. The path is resolved/verified beneath the configured root.
Default limits: 5 MiB input, 64 KiB record, 10,000 records/events, 50,000
indicators/entities, JSON depth 32.

Detailed security controls: [EVIDENCE_INGESTION_SECURITY.md](EVIDENCE_INGESTION_SECURITY.md).

## Provenance and failure guarantees

- Every Event references its EvidenceItem and RawRecord.
- Every IndicatorOccurrence and EntityObservation references EvidenceItem and
  RawRecord, and references Event when one exists.
- Every EntityRelationship carries factual support from its source record/event.
- Initial accepted evidence + ParseRun are committed before parsing. Derived
  facts are written in a later transaction; any parse/limit/encoding failure
  rolls that transaction back, marks the ParseRun/EvidenceItem failed, and
  retains only the original accepted bytes.
- Duplicate SHA-256 evidence within an Investigation is rejected and its staged
  file is removed.
- AI does not participate anywhere in this pipeline.

## Additive API endpoints

All are organization/investigation scoped and leave existing routes unchanged:

- `POST /api/v1/investigations/{id}/evidence`
- `GET /api/v1/investigations/{id}/evidence`
- `GET /api/v1/investigations/{id}/evidence/{evidenceId}`
- `GET /api/v1/investigations/{id}/evidence/{evidenceId}/download`
- `GET /api/v1/investigations/{id}/evidence/{evidenceId}/raw-records`
- `GET /api/v1/investigations/{id}/events`
- `GET /api/v1/investigations/{id}/indicators`
- `GET /api/v1/investigations/{id}/entities`
- `GET /api/v1/investigations/{id}/relationships`

Upload requires `investigation:write`; retrieval/download requires
`investigation:read`. Audit events cover acceptance, rejection, duplicate,
parse start/completion/failure, and download.

## Tests and results

New parser/ingestion tests cover deterministic text/JSON/CSV parsing,
malformed JSON/CSV, path traversal, empty/oversized/unsupported/deceptive MIME
uploads, invalid UTF-8, JSON-depth and raw-record limits, duplicate handling,
storage cleanup, failed parse rollback, provenance chain, relationship support,
and cross-org/cross-investigation repository scoping.

| Check | Result |
|---|---|
| Phase 2 parser/ingestion tests | 13 passed |
| Full backend suite | 41 passed, 6 pre-existing dependency deprecation warnings |
| Schema migration | No Phase 2 revision required; existing `0010` schema was used |
| Existing metadata drift | Unchanged: legacy IOC index metadata drift from `0009` remains technical debt |

## Compatibility verification

Existing endpoints, Pydantic schemas, frontend pages, AI reasoning, graph
builder, reporting, legacy Evidence/EvidenceRecord, and timeline code were not
modified. The new router is additive and no existing frontend consumer calls it.

## Known limitations

- No parser worker/queue, streaming parser runtime watchdog, archive support,
  binary forensic format, or retention/tombstone workflow.
- Declared MIME compatibility is checked conservatively; deeper magic-byte
  detection is deferred because supported formats are bounded UTF-8 text.
- Canonical FACT tables are used by the new APIs only; UI/graph/timeline cutover
  remains intentionally deferred.
- Existing revision `0009` ORM metadata drift is not addressed in this phase.

## Deferred Phase 3 scope

Phase 3 may introduce compatibility read models and case workspace factual
retrieval integration. It must not alter AI trust behavior or graph semantics
until their dedicated approved phases.
