# Canonical Alert Deduplication Contract

Status: **implemented in Phase 7.2**. Deduplication is deterministic, organization-scoped, provenance-preserving, and has no AI/LLM, correlation, cluster, triage, promotion, FACT, AIIE, Finding, or MITRE side effect.

## Exact replay semantics

Exact identity is `(org_id, connector_id, source, source_alert_id)`. Re-submitting that identity through `CanonicalAlertService.create` returns the original CanonicalAlert and creates one new immutable CanonicalAlertOccurrence with disposition `REPLAY`. The original alert's source payload reference, digest, title, detection fields, observed time, and ingest time are never overwritten.

Each replay receives an `AlertDeduplicationDecision` with type `EXACT_REPLAY`, version `exact-v1`, representative alert ID, duplicate occurrence ID, and a reason containing the exact connector/source/source-alert identity. Reusing the same RawEvent is rejected; no duplicate occurrence or decision is created.

Occurrence count, `first_seen`, and `last_seen` in the read model are derived from immutable occurrence receipt times. They do not mutate CanonicalAlert.

## Semantic duplicate semantics

`semantic-v1` is deliberately conservative. Two distinct CanonicalAlerts are semantic duplicates only if all of the following are true:

1. they have the same organization, connector, and source;
2. their normalized detection key matches: `rule_id`, else `signature`, else normalized title;
3. category and normalized severity match;
4. their complete non-empty entity tuple matches exactly over available hostname, source IP, destination IP, domain, URL, and file values; and
5. absolute difference between `observed_at` values is **at most 60 seconds**, inclusive.

The connector/source restriction is intentional for this first conservative release. It prevents cross-source false merging; independent-source association belongs to the later correlation phase. Same source ID in another connector or source is never an exact replay.

Representative selection is stable: the earliest `observed_at` candidate wins; UUID lexical order breaks an equal-time tie. Existing semantic decisions are immutable and idempotent. Reprocessing the same duplicate alert returns the existing decision. The service does not revise a representative; an algorithm change must use a new decision version.

## Persistence and explainability

Alembic `0015` adds `alert_deduplication_decisions`. It has organization scope, `RESTRICT` foreign keys to representative/duplicate alert or occurrence, type/version/subject uniqueness, timestamp, and structured reason list. A check constraint requires exactly one duplicate subject: a CanonicalAlert for semantic decisions or an occurrence for exact replay decisions.

The domain read model exposes duplicate state, representative alert ID, decision type/version, reasons, occurrence count, and derived first/last seen. Typical semantic explanation: “same rule ID, category, severity, host and source IP within 30 seconds under semantic-v1.” No source CanonicalAlert or RawEvent is deleted or merged.

## Boundaries

No public endpoint was added. The service is a domain boundary for later authenticated intake workflows. It only writes occurrence/decision records and does not write EvidenceItem, RawRecord, Event, Indicator, Entity, EntityRelationship, Investigation, IntelligenceAnalysis, Finding, or MitreMapping.
