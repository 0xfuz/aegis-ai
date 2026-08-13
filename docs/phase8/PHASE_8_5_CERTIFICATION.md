# Phase 8.5 Certification

Certified implementation commit: `7aaf635f30fd10f2922ff58b85812af406b7800c`.
Migration head remains `0023`; no migration was added during certification.

## Execution boundary

A queued Intelligence Run is acquired under its fenced lease, rebuilt from its
persisted authoritative snapshot, rendered through the deterministic grounded
prompt contract, and sent only to the trusted configured Ollama provider. The
whole provider response is strictly validated before alias resolution. Candidate
claims and typed citations are persisted atomically by the candidate-persistence
authority; only then can the run become `COMPLETED`. Claims remain `AI` / pending
for analyst review. The worker payload is the fenced run identity and protocol,
not a prompt, raw telemetry, provider body, or authority fields.

The legacy synchronous `/investigations/{id}/analyze` router remains in source
only as frozen compatibility code and is not registered by `app.main`; it is not
publicly reachable. The registered intelligence surface contains the certified
queue/run/review/reconstruction routes. No public route selects a provider or
writes legacy analysis, Finding, MITRE, promotion, action, correlation, or
triage state.

## Live bounded proof

The initial bounded live run failed safely as `CANDIDATE_SCHEMA_INVALID`, with
one real provider attempt and zero persisted claims, references, or links. It
was left terminal. One analyst-retry successor, built with a fresh authoritative
snapshot, then completed under the same read-only `llama3.2:latest` model
inventory. It recorded real provider start/finish timestamps, a candidate
fingerprint, one pending AI claim and one resolved snapshot citation; its lease
was cleared. No confirmed claim, legacy fact link, Finding, or MITRE mapping was
created. Raw prompts and provider output were never persisted or logged.

The corrective compatibility change preserves explicitly allowlisted provider,
prompt, and candidate failure categories (including
`CANDIDATE_SCHEMA_INVALID`) while unknown exceptions remain the generic safe
`EXECUTION_FAILED` category. It does not add repair prompts, markdown
extraction, fallback schemas, or partial-candidate acceptance.

## Certification results

- Focused prompt/provider/persistence/orchestration/lease suite: **53 passed**
  in **4.95s**.
- Detached full backend suite: **398 passed, 62 warnings** in **144.05s**.
  Its durable log, exit-code file, completion marker, and container exit code
  all agreed on exit code zero.
- Frontend: **12 files / 51 tests passed**; TypeScript typecheck, ESLint, and
  production Next.js build all passed.
- Compose validation: execution and dispatch default to `false`; the same
  configuration accepts only explicit `true` opt-in values.

The test matrix covers strict malformed/schema-invalid candidates, provider
failure, cancellation, lease ownership and recovery, atomic candidate
persistence, alias/role validation, transaction rollback, authorization and
organization boundaries, reconstruction/read-model exclusions, and the
Phase 7 correlation-version isolation regressions included by the full backend
suite.

## Security and deferred scope

Persisted run failures are bounded categories only. Prompt, raw telemetry,
provider output, credentials, SQL details, endpoint URLs, full snapshots, and
provider responses are excluded from public responses and execution audit
metadata. The worker neither recomputes Phase 7 correlation/triage nor creates
Findings, MITRE mappings, actions, or promotions.

Deferred work remains live Wazuh end-to-end validation, additional provider
integrations, analyst UX expansion, and any post-Phase-8 authority workflow.
