# Phase 1 Implementation Report — Additive Provenance Schema

## Outcome

Phase 1 added the canonical FACT/audit schema as an additive Alembic revision.
No existing Aegis table, API response, frontend page, connector behavior,
timeline behavior, graph behavior, legacy Investigation field, or AI endpoint
was changed. The active local Aegis database remains at revision `0009`; the
new revision was validated only in an isolated disposable database.

## Locked decisions recorded

- Canonical evidence-derived facts use restrictive foreign keys; no Phase 1 FK
  cascades from Investigation or factual parent records.
- Retention/tombstoning/legal hold are deferred.
- `evidence_parse_runs.status` uses a stable check constraint. Parser,
  normalizer, event, and relationship identifiers are extensible strings.
- Migration indexes use ordinary Alembic creation. Concurrent production index
  creation remains a future operational concern.
- CIOS data migration and generic external-reference mappings are deferred.

## Models and tables added

| Model | Table | Role |
|---|---|---|
| `EvidenceItem` | `evidence_items` | Immutable evidence metadata/hash and Investigation ownership |
| `EvidenceParseRun` | `evidence_parse_runs` | Versioned deterministic parser attempt |
| `RawRecord` | `raw_records` | Immutable source segment/line/object |
| `Event` | `events` | Deterministic normalized event, future canonical timeline source |
| `Indicator` | `indicators` | Organization-scoped canonical observable identity |
| `IndicatorOccurrence` | `indicator_occurrences` | Provenanced observation of an Indicator |
| `Entity` | `entities` | Investigation-scoped factual identity |
| `EntityObservation` | `entity_observations` | Provenanced observation of an Entity |
| `EntityRelationship` | `entity_relationships` | Factual entity graph edge with required supporting source |
| `AuditEvent` | `audit_events` | Append-only audit schema; no Phase 1 writer/API |

The models are isolated in `backend/app/modules/evidence/`; no service or API
router was introduced. `backend/alembic/env.py` imports that metadata solely so
Alembic sees the new tables.

## Constraints and indexes

- Restrictive FKs target existing `investigations`/`users` and new factual
  parents. An Investigation with canonical EvidenceItem/Event/occurrence/entity
  facts cannot be deleted by database cascade.
- Evidence uniqueness: `(investigation_id, sha256)` and globally unique
  `storage_key`; SHA-256 must be 64 lowercase hexadecimal characters.
- Parse run uniqueness: `(evidence_id, parser_name, parser_version,
  run_sequence)`; status check allows only pending/parsing/complete/failed/
  rejected.
- Raw record uniqueness: `(parse_run_id, ordinal)`; content or content locator
  is required.
- Event uniqueness: `(raw_record_id, normalizer_name, normalizer_version,
  ordinal)`.
- Indicator uniqueness: `(org_id, type, normalized_value)`.
- Entity uniqueness: `(investigation_id, type, canonical_value)`.
- Occurrence/observation uniqueness preserves extractor/version/ordinal.
- Relationship constraint requires distinct entities and at least one factual
  support FK; relationship type remains an extensible string.
- Case-scoped indexes cover event time/type/host/user, occurrence/observation
  time, relationship source/target, evidence import time, and audit time.

## Alembic migration

- Revision: `0010_canonical_provenance_facts`
- Revision ID: `0010`
- Down revision: `0009`
- Behavior: one additive migration; no backfill, rename, data migration,
  legacy-table alteration, or cascade policy change.

## Tests added

`backend/tests/test_provenance_models.py` adds five PostgreSQL integration
tests covering:

1. complete EvidenceItem → ParseRun → RawRecord → Event provenance plus
   indicator/entity observations, relationship, and audit linkage;
2. duplicate evidence uniqueness and invalid parse-status check;
3. FK integrity and restrictive Investigation deletion;
4. RawRecord content/locator and EntityRelationship factual-support checks;
5. organization/investigation-scoped Indicator and Entity uniqueness.

## Verification results

| Verification | Result |
|---|---|
| Python syntax compilation for new model, migration, and tests | Passed |
| Upgrade clean/current schema through `0009 → 0010` in `aegis_phase1_verify` | Passed |
| Alembic downgrade `0010 → 0009` | Passed; `evidence_items` and `audit_events` absent afterward |
| Alembic re-upgrade `0009 → 0010` | Passed; revision reported `0010 (head)` |
| New provenance test suite | 5 passed |
| Complete backend suite | 28 passed, 6 pre-existing dependency deprecation warnings |
| Active local Aegis database revision | Confirmed unchanged at `0009` |
| Frontend typecheck/lint | Not applicable to additive backend-only schema contract; attempted existing container commands could not run because its image lacks `tsc` and `next` executables |

`alembic check` now reports only two **pre-existing** metadata differences:
`ix_iocs_org_watched` and `ix_iocs_org_verdict` were created by legacy revision
`0009` but are absent from the legacy IOC SQLAlchemy model. The new Phase 1
tables produce no autogenerate drift. This was not corrected because it would
modify unrelated legacy model metadata outside Phase 1 scope.

## Compatibility verification

- No existing router, Pydantic response schema, domain service, frontend page,
  seed, report, attack graph, or AI implementation was changed.
- Existing backend auth/security/graph tests passed unchanged.
- Current running services still target the unchanged revision `0009` database.
- No parser, upload, normalizer, data import, API route, or audit writer was
  added; the new tables are intentionally unused at runtime.

## Known risks

- Cross-record organization/investigation consistency is represented by required
  scope columns and must be enforced by future service-layer write validation;
  Phase 1 does not add database triggers or alter existing parent constraints.
- Existing foreign keys on legacy Investigation children still retain their own
  historical cascade behavior; Phase 1 introduces restrictive semantics only
  for canonical tables.
- The active development database has not been upgraded. Deployment of revision
  `0010` requires normal release/change approval.
- Frontend tooling needs a build/test environment with dependencies installed
  before a future frontend-affecting phase.

## Exact Phase 2 scope

Phase 2 may implement secure evidence storage and deterministic parser/
normalizer services that write the new tables, with no AI/graph/UI cutover.
It must add acquisition authorization, hash calculation, bounded parser limits,
transactional parse-run lifecycle, and provenance-write tests. It must not
replace legacy API/UI behavior until the separately approved compatibility
read-model phase.
