# Phase 5.2 Verification & Test Coverage Report

## Result: complete for the authorized Phase 5.2 scope

All Docker/test commands used `DEBUG=true`; the host `DEBUG=release` value was not changed.

| Verification | Result | Evidence |
| --- | --- | --- |
| Alembic round-trip | passed | Fresh disposable PostgreSQL: `0011 -> 0012 -> 0011 -> 0012`; final revision `0012 (head)` |
| Dedicated AIIE suite | passed | `15 passed` against PostgreSQL |
| AIIE coverage | passed | `pytest-cov`: `intelligence_service.py` 57/57 statements, 100% |
| Backend regression | passed | `59 passed` |
| Frontend typecheck | passed | `npm run typecheck` |
| Frontend lint | passed | `npm run lint`, no warnings/errors |
| Frontend unit suite | passed | `npm test`: 4 files, 9 tests |
| Production frontend build | passed | clean `docker compose build --no-cache frontend` |
| AIIE end-to-end HTTP workflow | passed | deterministic provider fixture: run, read notebook, approve item |
| Ollama model download | not run by design | requirement was inspected only; no model pulled |

## Dedicated AIIE contracts

`backend/tests/test_aiie_persistence.py` and `backend/tests/test_aiie_validation.py` prove:

- analysis, item, and factual-link persistence;
- strict malformed/extra-field output validation;
- rejection of malformed and hallucinated factual IDs with no partial item persistence;
- organization and investigation scoping;
- append-only executions and unchanged FACT snapshots;
- immutable review-transition records and audit history;
- review-state transition enforcement;
- route-level read/write authorization;
- an HTTP run/read/review workflow using a deterministic local provider double.

## Corrective fix found during verification

The initial persistence test exposed one real atomicity defect: the summary item could be written before a later invalid fact reference rejected the output. `InvestigationIntelligenceService.run` now validates the full output before inserting any AIIE item or factual link. The behavior is covered by the dedicated suite. No migration or FACT model was changed.

## Ollama assessment

Configuration requests `llama3.2`. The recommended minimum is `llama3.2:3b` / default `llama3.2` (2.0 GB); `llama3.2:1b` is 1.3 GB but is not recommended for this structured analytical workload. A real Ollama inference remains intentionally unverified until a separately authorized model pull.

## Phase 5.3 real-provider certification

| Verification | Result | Evidence |
| --- | --- | --- |
| Container-to-host Ollama connectivity | passed | Docker host-gateway mapping; `GET http://host.docker.internal:11435/api/tags` returned HTTP 200 and `llama3.2:latest` |
| Disposable database migration | passed | fresh PostgreSQL upgraded through `0012 (head)` |
| Real AIIE provider lifecycle | not certified | Ollama returned a response that strict AIIE validation rejected: `summary` was `null` rather than a string |
| Failure atomicity | passed | certification database contained `FAILED: 1`, `items: 0`, `fact_links: 0` |

A second diagnostic call confirmed the model-output issue rather than a network failure: it returned malformed JSON and incompatible field shapes. The model was not downloaded or changed. No AIIE validation, architecture, migration, or canonical FACT model was altered. Phase 5.3 requires a model/prompt configuration capable of consistently satisfying the existing strict AIIE schema before it can be certified.

## Phase 5.4 structured provider reliability

| Verification | Result | Evidence |
| --- | --- | --- |
| Ollama constrained-output adapter | passed | Pydantic `Output` JSON Schema supplied to `/api/chat` `format`; schema also included in prompt; `temperature: 0` |
| Dynamic canonical ID constraint | passed | Each fact-reference array schema is constrained to the current compact-context UUIDs |
| Bounded repair behavior | passed | Exactly one repair request only for JSON/schema errors; no retry for fact-reference failures |
| Focused reliability tests | passed | `21 passed`: null, malformed JSON, extra field, invalid enum, hallucinated ID, corrected retry, failed retry atomicity |
| Real model certification | not certified | `llama3.2:latest`: 0 successful fact-cited outputs in 3 analyses |

Real-run metrics: first-pass success 0/3 (0%); retry success 0% (no run was structurally invalid, so no repair retry was eligible); total success 0/3 (0%). End-to-end latencies were 73.117 s, 74.255 s, and 80.940 s, for a 76.104 s mean. Every failed run was rejected for unknown factual support IDs and persisted no AIIE items or fact links.

Result: stop Phase 5.4. The adapter controls requested in this phase are in place and strict validation remains unchanged. Recommendation **B**: select a stronger local model before attempting certification again; do not download one automatically.

## Phase 5.5 canonical FACT alias certification

| Verification | Result | Evidence |
| --- | --- | --- |
| Alias contract tests | passed | deterministic aliases for `E`, `RR`, `EV`, `IN`, `EN`, `REL`; no UUIDs in LLM projection; resolution and duplicate prevention |
| Alias security/atomicity | passed | unknown, malformed, and cross-map aliases rejected; canonical UUID links persisted only after resolution |
| Focused AIIE + alias suite | passed | `29 passed` |
| Full backend regression | passed | `73 passed` |
| Real Ollama certification | passed | `llama3.2:latest`, 3/3 valid fact-cited analyses |

Phase 5.5 metrics: first-pass success 3/3 (100%); retry success 0% (no retries were needed); invalid alias rate 0%; total success 3/3 (100%). End-to-end latencies were 52.690 s, 22.887 s, and 23.199 s, mean 32.925 s. Each successful run persisted real canonical UUID values in `IntelligenceFactLink`, never aliases.

Compared with Phase 5.4's 0/3 success caused by unsupported UUID citations, alias citations eliminated the observed real-provider failure mode without weakening strict validation or downloading another model. See `FACT_ALIAS_CONTRACT.md` for the complete boundary and resolution contract.
