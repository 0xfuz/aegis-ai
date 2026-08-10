# Canonical Alert Contract

Status: proposed Phase 7.1 contract. A CanonicalAlert is an immutable, source-independent detection record. It is not an Investigation, EvidenceItem, RawRecord, Event, or analyst conclusion.

## Phase 7.1 implementation record

Implemented in Alembic `0014` and `app.modules.alert_triage`:

- `canonical_alerts` with connector/raw-event `RESTRICT` provenance, exact organization + connector + source + source-alert-ID uniqueness, UTC observed/ingested timestamps, validated detection fields, normalized observable JSON, bounded source metadata, payload digest, normalizer version, and lifecycle default `NEW`.
- `canonical_alert_occurrences` with one immutable history row per RawEvent and `INITIAL` / `REPLAY` disposition. An exact source identity returns the original alert and appends a replay occurrence; it does not overwrite original alert content or payload reference.
- `CanonicalAlertService.create`, `get`, and `list_occurrences`. There is deliberately no FastAPI intake route or update/delete/lifecycle-transition method.

Phase 7.1 requires a non-empty `source_alert_id`. The approved no-source-ID fallback requires a deterministic fingerprint/time-bucket decision and is therefore deferred with deduplication in 7.2; accepting it now would silently implement semantic deduplication.

## Proposed model

| Group | Fields | Rule |
| --- | --- | --- |
| Identity | `id`, `org_id`, `connector_id`, `source_system`, `source_alert_id`, `source_identity_version` | `org_id` derives from Connector. `source_system` is configured connector metadata, not caller text. |
| Times | `observed_at`, `ingested_at`, optional source created/updated times | Keep source time and receipt time distinct; UTC only. |
| Detection | `title`, `description`, normalized `severity`, `category`, `rule_id`, `rule_name`, `signature` | Preserve source values separately when normalization loses detail. Severity is source-provided metadata, not Aegis risk. |
| Observable projection | normalized optional source/destination IP, host, user, process, file hash/path, domain, URL | Values use type-specific normalizers. Absence is explicit; unknown data is never fabricated. |
| Source provenance | `raw_event_id` (or immutable intake reference), `payload_digest`, connector metadata snapshot | The source payload remains recoverable through controlled access. |
| Lifecycle | `NEW`, `DEDUPLICATED`, `CORRELATED`, `PROMOTED`, `SUPPRESSED` | Lifecycle records routing state, not a truth assessment. |
| Derived fields | `exact_identity_key`, `dedupe_fingerprint`, `first_seen`, `last_seen`, `occurrence_count` | All are deterministic and versioned. |

`source_alert_id` may be absent for sources that do not provide one. In that case the system creates a deterministic ingestion identity from connector ID, payload digest, normalized rule/observables, and a source-time bucket. The input must retain a reason/value indicating this fallback; it must never pretend the source supplied an ID.

## Proposed persistence additions

| Table | Purpose | Key constraints / indexes |
| --- | --- | --- |
| `canonical_alerts` | Immutable normalized alert identity and current derived lifecycle summary | unique `(org_id, connector_id, source_system, source_alert_id)` when ID exists; indexed `(org_id, observed_at)`, `(org_id, dedupe_fingerprint, observed_at)`, `(org_id, lifecycle)` |
| `canonical_alert_occurrences` | Every receipt/replay/repeated source occurrence, linked to raw intake | unique `(canonical_alert_id, raw_event_id)`; preserve source receipt, payload digest, received time |
| `alert_dedupe_decisions` | Deterministic exact/semantic dedupe decision and fingerprint/rule version | immutable, indexed by alert and survivor |

These tables need an Alembic migration only in 7.1. They must have `org_id`, UUID primary keys, `RESTRICT` foreign keys to required provenance, timestamp/index conventions matching the canonical models, and no cascade path that can silently erase provenance.

## Identity, immutability, and replay

1. Authenticate connector; set `org_id` from Connector.
2. Persist an immutable raw intake record before normalization succeeds or fails (within size/validation policy).
3. Normalize using a versioned adapter; retain the normalized output/version and a payload digest.
4. If exact identity exists, append an occurrence and update only derived `last_seen` / `occurrence_count` through a recorded dedupe decision. Do not overwrite detection text or source payload.
5. If no exact identity exists, persist a new immutable CanonicalAlert.
6. Correction/re-enrichment creates a new normalization/derived-decision record; it does not mutate original source facts.

Semantic duplicates are not the same as identity duplicates. They may be associated with an existing alert/cluster by an auditable decision, while retaining their own CanonicalAlert and occurrence provenance.

## Validation and limits

- Reject/park malformed payloads without attempting correlation; record a safe failure reason and digest where possible.
- Apply a connector-specific allowlist, JSON depth/field count/string length limits, and a maximum payload size before persistence/parsing.
- Normalize IP/domain/URL/hash identifiers defensively; retain original field values only as untrusted payload context.
- Never use alert description/title as prompt instructions. Any later AI use must pass data as quoted untrusted context and remain fact-cited through promoted FACT only.

## Lifecycle permissions

Automated processing may set `NEW`, `DEDUPLICATED`, or `CORRELATED` based on deterministic outcomes. `SUPPRESSED` requires an explicit policy/analyst action with rationale and audit trail. `PROMOTED` requires analyst authorization and a successful promotion link. No lifecycle change confirms a Finding or MITRE mapping.
