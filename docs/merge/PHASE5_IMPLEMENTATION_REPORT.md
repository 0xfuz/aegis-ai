# Phase 5 — Aegis Investigation Intelligence Engine

## Implementation status: Phase 5.5 real-provider certification complete

Phase 5 adds AIIE as an additive, append-only inference boundary. `intelligence_analyses`, `intelligence_items`, `intelligence_fact_links`, and immutable `intelligence_review_events` remain separate from canonical FACT data and legacy AI fields.

## Implemented

- Compact factual context from evidence metadata, events, entities, indicators, and factual relationships; raw ORM objects and raw-record content are not sent to the LLM.
- Strict JSON-only output validation with forbidden extra fields and required, known factual support for every non-summary item.
- Separate persisted analyses, items, and fact links; failed validation produces a failed analysis without persisting a partial item set.
- Append-only inference execution and immutable factual source records.
- Review transitions `UNREVIEWED -> APPROVED|REJECTED` and `APPROVED -> SUPERSEDED`, each recorded as immutable review history and an `AuditEvent`.
- Provider/model/duration schema support from Alembic `0012`.
- Case-scoped Investigation Intelligence notebook UI.

## Verification completed

- Disposable PostgreSQL Compose project (`aegisphase52verify`, `DEBUG=true`): `0011 -> 0012 -> 0011 -> 0012` passed and finished at `0012 (head)`.
- Dedicated AIIE PostgreSQL suite: 15 passed. It covers persistence, factual-reference validation, hallucinated and malformed IDs, cross-investigation and cross-organization isolation, append-only execution, review/audit history, FACT snapshots, HTTP authorization, and a deterministic HTTP run/read/review workflow.
- AIIE service coverage: 100% line coverage (57 statements) using `pytest-cov`.
- Full backend regression suite: 59 passed, including legacy graph, evidence/timeline, reporting, auth, and legacy AI behavior.
- Frontend: typecheck passed; lint passed with no warnings; unit suite passed (9 tests); clean production Docker frontend image build passed.

## Model assessment (no pull performed)

The configured local provider model is `OLLAMA_MODEL=llama3.2`. The smallest suitable model for this fact-cited structured-output workflow is `llama3.2:3b` (the default `llama3.2` tag, 2.0 GB). `llama3.2:1b` is smaller (1.3 GB), but its documented use is lightweight retrieval/rewriting; the 3B model is the appropriate minimum for instruction following and summarization. No Ollama model was downloaded.

## Phase 5.3 real-provider verification

The existing `llama3.2:latest` host model was reached from the experimental backend container through Docker's Linux host-gateway mapping at `http://host.docker.internal:11435`; `GET /api/tags` returned HTTP 200 and listed that model. The real AIIE generation request reached Ollama but failed strict output validation (`summary` was `null`, where the schema requires a string). A diagnostic second response was malformed JSON and used incompatible field shapes. The failed run left one `FAILED` analysis and no intelligence items or fact links, confirming the atomic validation boundary.

Phase 5.3 real-provider certification is therefore not complete. No model was downloaded, no migration or FACT model was changed, and validation was not weakened to accommodate the model output.

## Phase 5.4 structured provider reliability

The Ollama adapter now uses the existing Pydantic `Output` schema in both the prompt and Ollama's supported `format` schema field, sets temperature to `0`, explicitly prohibits nulls/extra fields/markdown, and constrains fact-reference array items to the UUIDs in the canonical context. The server keeps the same strict validation and atomic persistence boundary. A single repair attempt is available only for malformed JSON or schema-validation errors; factual-ID failures are never retried.

The reliability suite covers null required fields, malformed JSON, extra fields, invalid recommendation enum values, hallucinated fact IDs, a successful corrected retry, and a failed retry that remains atomic. All 21 focused AIIE tests pass.

Real certification with `llama3.2:latest` was repeated three times after these controls. All three replies were structurally acceptable but cited IDs outside the canonical context and were rejected by the unchanged fact validator. Success rate: 0/3 (0%); first-pass success: 0%; retry success: 0% (no structural retry was eligible); end-to-end latencies: 73.117 s, 74.255 s, and 80.940 s (mean 76.104 s). No inference item or fact link was persisted for any failed run.

**Recommendation: B — a stronger local model is required for certification.** The provider adapter now uses Ollama's schema mechanism, deterministic sampling, explicit instructions, and dynamic ID enums; `llama3.2:latest` still cannot reliably select valid fact citations. Do not download a replacement automatically.

## Phase 5.5 canonical FACT alias citation layer

Phase 5.5 replaces UUID citations at the LLM boundary with deterministic, run-local aliases: `E`, `RR`, `EV`, `IN`, `EN`, and `REL`. Alias maps are generated server-side from the canonical compact context, sorted by canonical UUID within type, and are never persisted as canonical IDs. The LLM sees only the alias-projected context; relationships are projected to aliases and raw-record content remains excluded.

Structured output now uses `supporting_facts` and `contradicting_facts`. Ollama's schema constrains those values to the aliases in the current analysis, and the server checks syntax plus current-map membership before resolving aliases back to canonical UUIDs for unchanged `IntelligenceFactLink` persistence. This preserves tenant/case isolation, FACT immutability, and atomic append-only inference writes.

Real `llama3.2:latest` certification passed 3/3 analyses: all succeeded on the first request with valid canonical fact links. First-pass success: 100%; retry success: 0% (no retries needed); invalid-alias rate: 0%; total success: 100%. End-to-end latency was 52.690 s, 22.887 s, and 23.199 s (mean 32.925 s). This improves the Phase 5.4 baseline from 0/3 successful UUID-citation analyses to 3/3 valid alias-citation analyses.

## Preserved boundaries

Migrations `0011` and `0012` were not modified. Canonical FACT models, legacy `POST /investigations/{id}/analyze`, timeline, graph, and report behavior were not redesigned or changed.
