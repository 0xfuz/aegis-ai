# Phase 1 Implementation Specification — Additive Provenance Schema

## Scope and non-goals

Phase 1 introduces the canonical provenance schema into Aegis-AI **without
replacing any existing behavior**. It is additive only. It does not change the
current Investigation API response, frontend, connector webhook behavior, AI
analysis behavior, legacy fields, reports, graph output, or existing tables.

Phase 1 does not implement CIOS data import, evidence upload UI, parsing,
normalization, AIAnalysis persistence, graph cutover, or legacy removal. Those
are subsequent approved phases.

## Locked Phase 1 decisions

- All canonical evidence-derived facts use restrictive foreign keys. Deleting an
  Investigation that has canonical facts is blocked; no canonical fact table
  uses `CASCADE` from Investigation or its factual parent records.
- Retention, tombstoning, archival, and legal-hold workflows are deferred.
- Parsing lifecycle uses a small stable database check constraint. Parser,
  normalizer, event, and relationship identifiers remain validated strings,
  not rigid database enums.
- Indexes are created with ordinary Alembic operations. Concurrent production
  index deployment is a future operational concern.
- CIOS migration references/mapping tables are deferred unless later proven
  technically necessary; Phase 1 implements none.

## Exact new SQLAlchemy models

All tenant-owned models inherit `UUIDPrimaryKeyMixin`, `TimestampMixin` where
creation/update timestamps are needed, and `OrgScopedMixin`. FK target table
names below are normative. Model/field spelling may only vary after a design
review update to this specification.

### `EvidenceItem` (`evidence_items`)

Columns: `id`, `org_id`, `investigation_id` FK `investigations.id` (restrict/no
automatic historical erasure policy), `original_filename`, `storage_key`
(globally unique), `sha256` (64-char lowercase), `byte_size`, `detected_mime`,
`extension`, `source_description`, `acquisition_source`, `imported_by_id` FK
`users.id` nullable for connector/system intake, `imported_at`, `parsing_status`,
`created_at`, `updated_at`.

Constraints/indexes: unique `(investigation_id, sha256)`; indexes `(org_id)`,
`(investigation_id, imported_at)`, `sha256`, `storage_key` unique.

Relationships: Investigation; importer User; parse runs; raw records; events;
indicator occurrences; entity observations; relationship supports.

### `EvidenceParseRun` (`evidence_parse_runs`)

Columns: `id`, `org_id`, `evidence_id` FK `evidence_items.id`, `parser_name`,
`parser_version`, `run_sequence`, `status`, `started_at`, `ended_at` nullable,
`warnings` JSONB nullable, `error_summary` nullable, `config_fingerprint`
nullable, timestamps.

Constraints/indexes: unique `(evidence_id, parser_name, parser_version,
run_sequence)`; indexes `(org_id)`, `(evidence_id, started_at)`, `(status)`.

Relationships: EvidenceItem; RawRecords.

### `RawRecord` (`raw_records`)

Columns: `id`, `org_id`, `evidence_id` FK `evidence_items.id`, `parse_run_id`
FK `evidence_parse_runs.id`, `ordinal`, `content` Text or protected
`content_locator` (one must be present), `content_type`, `byte_offset` nullable,
`line_start`/`line_end` nullable, `encoding` nullable, timestamps.

Constraints/indexes: unique `(parse_run_id, ordinal)`; indexes `(org_id)`,
`(evidence_id, parse_run_id, ordinal)`.

Relationships: EvidenceItem, ParseRun, Events, IndicatorOccurrences,
EntityObservations, EntityRelationship support records.

### `Event` (`events`)

Columns: `id`, `org_id`, `investigation_id` FK `investigations.id`, `evidence_id`
FK `evidence_items.id`, `raw_record_id` FK `raw_records.id`,
`normalizer_name`, `normalizer_version`, `ordinal`, `timestamp` nullable,
`source`, `host`, `user`, `process`, `source_ip`, `destination_ip`,
`source_port`, `destination_port`, `event_type`, `action`,
`deterministic_severity` nullable, `normalized` JSONB, timestamps.

Constraints/indexes: unique `(raw_record_id, normalizer_name, normalizer_version,
ordinal)`; indexes `(org_id)`, `(investigation_id, timestamp)`,
`(investigation_id, event_type)`, `(investigation_id, host)`,
`(investigation_id, user)`, `source_ip`, `destination_ip`.

Relationships: Investigation, EvidenceItem, RawRecord, occurrences,
observations, relationship supports.

### `Indicator` and `IndicatorOccurrence`

`Indicator` (`indicators`): `id`, `org_id`, `type`, `normalized_value`,
`display_value` nullable, `first_seen_at`/`last_seen_at` nullable,
`occurrence_count` default 0, timestamps. Unique `(org_id,type,normalized_value)`;
indexes `(org_id)`, `(org_id, normalized_value)`.

`IndicatorOccurrence` (`indicator_occurrences`): `id`, `org_id`,
`investigation_id` FK, `indicator_id` FK `indicators.id`, `evidence_id` FK,
`raw_record_id` FK, `event_id` FK nullable, `extractor_name`,
`extractor_version`, `occurrence_ordinal`, `observed_at` nullable,
`source_locator` JSONB nullable, timestamps. Unique `(indicator_id,raw_record_id,
extractor_name,extractor_version,occurrence_ordinal)`; indexes `(org_id)`,
`(investigation_id,observed_at)`, `(event_id)`, `(evidence_id)`.

### `Entity`, `EntityObservation`, and `EntityRelationship`

`Entity` (`entities`): `id`, `org_id`, `investigation_id` FK, `type`,
`canonical_value`, `display_name`, `attributes` JSONB nullable,
`first_seen_at`/`last_seen_at` nullable, timestamps. Unique
`(investigation_id,type,canonical_value)`; indexes `(org_id)`,
`(investigation_id,type,canonical_value)`.

`EntityObservation` (`entity_observations`): `id`, `org_id`,
`investigation_id` FK, `entity_id` FK `entities.id`, `evidence_id` FK,
`raw_record_id` FK, `event_id` nullable FK, `extractor_name`,
`extractor_version`, `occurrence_ordinal`, `observed_at` nullable,
`source_locator` JSONB nullable, timestamps. Unique `(entity_id,raw_record_id,
extractor_name,extractor_version,occurrence_ordinal)`; indexes `(org_id)`,
`(investigation_id,observed_at)`, `(event_id)`, `(evidence_id)`.

`EntityRelationship` (`entity_relationships`): `id`, `org_id`,
`investigation_id` FK, `source_entity_id`/`target_entity_id` FK `entities.id`,
`relationship_type`, `derivation_name`, `derivation_version`, `evidence_id` FK
nullable, `raw_record_id` FK nullable, `event_id` FK nullable,
`source_observation_id`/`target_observation_id` FK nullable,
`source_locator` JSONB nullable, `observed_at` nullable, timestamps.

Constraint: require at least one factual support FK through a PostgreSQL CHECK
constraint; unique `(source_entity_id,target_entity_id,relationship_type,
derivation_name,derivation_version,source_locator_hash)` where a deterministic
locator hash is stored. Indexes `(org_id)`, `(investigation_id,source_entity_id)`,
`(investigation_id,target_entity_id)`, `(event_id)`, `(observed_at)`.

### `AuditEvent` (`audit_events`)

Columns: `id`, `org_id`, `investigation_id` FK `investigations.id` nullable,
`actor_id` FK `users.id` nullable, `actor_type`, `action`, `target_type`,
`target_id`, `occurred_at`, `rationale` nullable, `metadata` JSONB nullable,
`correlation_id` nullable, `created_at`.

Constraints/indexes: indexes `(org_id, occurred_at)`,
`(investigation_id, occurred_at)`, and `(target_type, target_id)`.
`actor_type`, `action`, and target identifiers are extensible validated strings.
Records are append-only by service policy; Phase 1 introduces no writer.

## Relationship rules

- Every Event references exactly one EvidenceItem and RawRecord.
- Every occurrence/observation references exactly one EvidenceItem and
  RawRecord, with Event optional because extraction can precede/avoid
  normalization.
- Every EntityRelationship references two distinct Entities in the same
  Investigation/org and at least one factual support record.
- Phase 1 has no FK from these FACT models to AIAnalysis or legacy mutable AI
  fields.
- Existing Investigation, IOC, Asset, Connector, and RawEvent tables remain
  untouched. No relationship is added that changes their current ORM behavior.

## Alembic migration strategy

1. Create one additive revision after the current head; no modifications,
   renames, data backfills, or drops of existing tables/columns.
2. Create enum/check constraints deliberately. Prefer varchar + application
   validation for extensible parser/normalizer/relationship types; use stable
   enums only for parsing status and fixed entity/indicator types if approved.
3. Create tables in FK order: EvidenceItem → EvidenceParseRun → RawRecord →
   Event → Indicator/Entity → occurrence/observation → EntityRelationship →
   AuditEvent.
4. Create indexes in the same revision. For production-sized databases, assess
   concurrent index creation separately; the development revision must remain
   transactional and reversible.
5. Downgrade drops only the new tables in reverse dependency order. It must not
   touch existing Aegis data. In production, downgrade is allowed only before
   canonical fact data is accepted; thereafter restore/forward-fix policy wins.

## Compatibility requirements

- Do not import the new models into existing Investigation detail schemas,
  routers, services, graph builder, reporting, connector service, or frontend.
- Existing tests must keep their current expected response bodies.
- New model classes may live in a dedicated `ingestion`/`evidence` bounded
  module, not the legacy investigations infrastructure file, so no accidental
  API serialization occurs.
- Do not add runtime parsing/jobs in Phase 1. Empty tables are an accepted
  result; functionality begins only with a separately approved Phase 2.

## Test plan

1. Schema migration upgrade from a clean database and downgrade before data.
2. ORM construction tests for all required fields, FK and unique constraints.
3. Tenant isolation query tests for each org-scoped model.
4. Provenance invariant tests: Event cannot omit evidence/raw record;
   occurrence/observation cannot omit raw source; relationship cannot omit
   factual support or join entities across cases.
5. Index/constraint introspection tests against PostgreSQL where practical.
6. Regression suite: existing auth/security/attack-graph tests and OpenAPI
   endpoint response snapshots are unchanged.
7. Negative tests: duplicate hash per investigation, duplicate parse ordinal,
   duplicate canonical indicator/entity, cross-org FK attempts, invalid source
   locator support.

## Rollback strategy

- Before data ingestion: Alembic downgrade removes only additive tables/indexes
  in reverse order.
- After any canonical records exist: stop writes, retain evidence bytes, take a
  backup, and issue a forward corrective migration rather than deleting
  provenance. This protects auditability.
- Existing Aegis behavior remains independently operable because no old table,
  route, response, or frontend dependency changes in Phase 1.

## Expected files to change during implementation (not changed in Phase 0)

- `backend/app/modules/<new evidence or ingestion module>/infrastructure/models.py`
- `backend/app/modules/<new evidence or ingestion module>/__init__.py` and any
  model-registration import required by Alembic
- `backend/alembic/versions/<new additive provenance revision>.py`
- `backend/tests/test_provenance_models.py` and migration/constraint tests
- Potentially `backend/alembic/env.py` only if it currently lacks import-based
  metadata registration for the new module
- `docs/merge/*` updates to record the approved implementation outcome

No existing API router, service, model file, frontend page, Docker file, seed,
or legacy Alembic revision is expected to change in Phase 1.

## Final approval gate

Implementation may begin only after approval of: model/table names, use of
check constraints, `investigation_id` relationship deletion policy, evidence
storage retention/encryption policy, and the test/rollback conditions above.
