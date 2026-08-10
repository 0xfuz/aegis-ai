# Phase 7 Implementation Plan

Status: proposed sequence after Phase 7.0 architecture approval. No stage authorizes work before its predecessor acceptance criteria pass.

## 7.1 Canonical Alert Foundation

**Completed:** additive Alembic `0014`, models, service boundary, and focused tests were implemented as specified in `CANONICAL_ALERT_CONTRACT.md`. No public routes or downstream workflow changes were made.

- **Database/models:** additive `canonical_alerts`, `canonical_alert_occurrences`, and immutable dedupe-decision records; org IDs, foreign keys to connector intake, unique external identity/fallback key, indexes, check constraints.
- **Services/APIs/UI:** internal normalization/intake service only; a minimal authenticated alert list/read surface may wait until 7.3. No connector changes yet.
- **Tests:** source identity uniqueness/replay, immutability, malformed/oversize rejection, tenant isolation, raw provenance retention, migration upgrade/downgrade.
- **Acceptance:** same source alert never loses receipt provenance or creates a cross-org record; no FACT/Investigation/AIIE write.
- **A6 risk:** adding an incorrect generic `org_id` filter could leak scope. Mitigate with existing Principal/Connector-derived org and authorization tests.

## 7.2 Deterministic Deduplication

**Completed:** Alembic `0015`, immutable exact-replay and semantic decision records, and an internal deterministic read/process service. Semantic matching is intentionally limited to same organization, connector, and source with matching normalized detection/entity tuple and an inclusive 60-second observed-time window. No public API or downstream action was added.

- **Database/models:** derived first/last seen/count and decision history only; no cluster schema yet.
- **Services/APIs/UI:** exact dedupe/fingerprint service behind intake; optional operational disposition response.
- **Tests:** exact duplicate, repeat occurrence, no external-ID fallback, time-window boundaries, concurrent replay, no provenance loss.
- **Acceptance:** deterministic result/reason/version; duplicates do not inflate source diversity or create investigations.
- **A6 risk:** none if no canonical FACT table is touched.

## 7.3 Correlation and Alert Clusters

**Completed:** Alembic `0016`, OPEN/CLOSED AlertClusters, immutable membership/merge history, and internal deterministic `correlation-v1` process/read service. It accepts only non-semantic-duplicate CanonicalAlerts, uses an inclusive 180-second observed-time window and documented strong/weak signal guards, and has no public API, triage, promotion, or AI behavior.

- **Database/models:** `alert_clusters`, membership, correlation-decision/event records and merge successor links.
- **Services/APIs/UI:** deterministic candidate/score engine and read-only Alert Triage list/detail with reasons; do not call AIIE.
- **Tests:** same-org candidate correlation, cross-org non-correlation, threshold/temporal controls, stable ordering, merge/split audit, promoted cluster protection.
- **Acceptance:** every member has an explanation; category-only correlation is rejected; analysts can inspect reasons before any promotion.
- **A6 risk:** never include cluster nodes/edges in the canonical Attack Graph.

## 7.4 Triage Scoring and Analyst Lifecycle

**Completed (scoring only):** Alembic `0017` and append-only `triage-v1` cluster assessments. It uses bounded source severity, trusted Asset/IOC context, distinct-member and source-diversity counts, deterministic correlation/sequence evidence, and explicit recency. No analyst lifecycle transition, override, suppression, promotion, HTTP API, or UI was added.

- **Database/models:** scoring snapshot/version, manual override/audit fields, lifecycle constraints; reuse `AuditEvent` for analyst actions.
- **Services/APIs/UI:** priority explanation, triage/close/suppress/override actions with new narrowly scoped permissions.
- **Tests:** exact ledger/bands, missing values, independent-source counting, override rationale, authorization and audit.
- **Acceptance:** “Why priority?” is fully reproducible; AI confidence never contributes as a risk score.
- **A6 risk:** no status change creates Finding/MITRE or modifies canonical Overview semantics.

## 7.5 Investigation Promotion

- **Completed:** additive Alembic `0018`, immutable `alert_cluster_promotions`, `PROMOTED` cluster lifecycle, and an internal analyst-controlled promotion service.
- **Boundary:** explicit active same-org user + `OPEN` root cluster + latest immutable triage assessment; no priority-based automation and no public route/UI.
- **Idempotency:** PostgreSQL root-cluster lock plus unique promotion cluster/investigation constraints; repeated requests return the one completed promotion.
- **Evidence/FACT path:** deterministic `alert-promotion-export-v1` JSON is stored as `EvidenceItem(acquisition_source=alert_cluster_promotion)` and processed only through `EvidenceIngestionService` and its dedicated parser. Promotion never writes FACT rows directly.
- **Atomicity:** promotion-specific ingestion is one DB transaction; failures remove generated storage and leave no Investigation, promotion, FACTs, or `PROMOTED` cluster state.
- **Provenance:** manifest/export retain canonical alert, connector, raw-event, source identity, digest, timestamps, normalized fields, assessment, and membership explanations. `ALERT_CLUSTER_PROMOTED` uses the existing `AuditEvent` architecture.
- **Deferred:** HTTP/API/UI, generic ingress/connectors, automatic promotion, AIIE execution, Findings/MITRE confirmation, response, and reporting.
- **Verification:** Alembic `0017 → 0018 → 0017 → 0018` succeeded; schema inspection confirmed the five restrictive foreign keys, unique cluster/investigation idempotency constraints, immutable completion check, and organization/promotion index. Focused promotion tests cover successful parser-derived FACT provenance, exact replay history, semantic-duplicate exclusion, tenant/actor/assessment eligibility, idempotency/export snapshot, failure atomicity, audit, and no automatic AIIE/Finding/MITRE creation. Full Docker/PostgreSQL backend regression: 127 passed.

## 7.6 Generic Webhook Connector

- **Completed:** additive `POST /api/v1/ingest/alerts/v1/{connector_id}/{source}`. No migration or frontend change was required.
- **Boundary:** existing hashed connector secret authenticates the request and determines organization. Body/path source identities must match; no caller-controlled organization or internal IDs are accepted.
- **Pipeline:** existing `RawEvent` → CanonicalAlert → semantic deduplication → correlation → triage-v1. Exact replays add an occurrence and return current state without rerunning/scoring a member. No automatic promotion occurs.
- **Security:** JSON-only, 256 KiB request cap, canonical observable/metadata/timestamp validation, inert untrusted text, active/connected connector enforcement, and in-process connector-local 60/minute burst limiting.
- **Compatibility:** legacy `/ingest/webhook/{connector_id}` is untouched. Generic webhook never creates Investigation/FACT/AIIE/Finding/MITRE rows.
- **Deferred:** durable outbox/retry/dead-letter processing, distributed rate limits/backpressure, connector source registration, and all vendor-specific adapters.
- **Verification:** no migration required; focused Phase 7.1–7.6 Docker/PostgreSQL tests: 53 passed. HTTP E2E confirms related alerts correlate, replay creates an occurrence without a new alert/member, triage is returned, and no Investigation is created. Full backend Docker/PostgreSQL regression: 134 passed.

## 7.7 Synthetic Benchmark and Operations

- **Database/models:** optional metrics rollups/outbox only after evidence of need.
- **Services/APIs/UI:** repository-owned synthetic source streams, metric dashboard/read export, bounded processing instrumentation.
- **Tests:** 10k-like reproducible benchmark fixture, latency/reduction metrics, no false cross-org matches.
- **Acceptance:** reports measured alert/unique/cluster/promotion counts and latency; no predetermined reduction claim.
- **A6 risk:** benchmark data must use disposable organization/investigation fixtures.

## 7.7.2 Correlation-v2 Research and Design

**Completed (design only):** Phase 7.7.1 demonstrated a same-host parallel-incident false merge in `correlation-v1`. The proposed conservative v2 ledger, hard discriminators, representative/quorum cluster guard, benchmark targets, and adversarial matrix are documented in `CORRELATION_V2_*`. No correlation, triage, schema, or API implementation changed. A separately approved implementation phase is required before Wazuh integration.

## 7.8 Wazuh Adapter

- **Database/models:** none expected beyond connector configuration reviewed in 7.6.
- **Services/APIs/UI:** Wazuh adapter/poller/webhook translator only; checkpointing as durable state if polling.
- **Tests:** fixture-based Wazuh mappings, source ID replay, malformed vendor payload, expected canonical fields.
- **Acceptance:** adapter has no dedupe/correlation/promotion logic and passes generic connector contract tests.
- **A6 risk:** vendor MITRE/source severity remain untrusted metadata.

## Deferred production-scale work

Introduce a durable outbox/worker/dead-letter path only after 7.7 measures an ingestion/latency need. If introduced, it is a separately reviewed infrastructure change with delivery, retry, lease, and recovery tests; Redis alone must not be the authoritative queue.

## Required regression gate per implementation stage

Every stage runs the relevant migration round-trip, focused alert-triage tests, full backend PostgreSQL suite, frontend typecheck/lint/unit suite and production Docker build. 7.5+ additionally run A6 HTTP workflow/provenance/authorization tests to protect certified behavior.
