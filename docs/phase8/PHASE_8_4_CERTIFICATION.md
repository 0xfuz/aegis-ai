# Phase 8.4 Certification — Intelligence Execution Foundation

Certified implementation commit: `00750f130bd205cc233425c09ca36e1845710e18` plus the narrowly-scoped certification corrections recorded by this document's parent commit.  Migration head is `0022`.

## Authority and lifecycle

PostgreSQL is the sole authority for an Intelligence Run.  Celery/Redis carries only a run UUID and the fixed `intelligence-run-v1` protocol; it is not a state store or a result authority.  Execution and dispatch are disabled by default.  A trusted worker-generated attempt identity acquires a fenced, generation-numbered 60-second lease.  Cooperative execution checkpoints renew it every 20 seconds.  Cancellation, expiry, takeover, terminal completion, safe failure, and ownership loss fence stale workers; a run has at most three execution attempts.  An analyst retry instead creates a linked successor run.

The worker adapter is intentionally fake and transport-independent in this phase.  It contains no provider, prompt, model output, claim, citation, action, raw telemetry, or snapshot propagation path.  Lease loss or checkpoint failure prevents terminal result persistence.

## Operational boundary

Compose has one one-shot `migrate` service as the only migration/bootstrap writer.  API, worker, and beat wait for its successful completion.  The API does not require Redis readiness; worker and beat require PostgreSQL, Redis, and the migration boundary.  Worker and beat publish no host ports.  Queue dispatch is best-effort after the database commit; Redis loss leaves the authoritative run queued for bounded, ordered reconciliation.

The legacy Intelligence POST endpoint is queue-only.  No public acquire, heartbeat, complete, fail, dispatch, or reconcile endpoint exists.  Public organization and actor scope is server-derived; no task input can choose a provider, model, prompt, context, organization, or lease owner.

## Certification evidence

| Gate | Result |
| --- | --- |
| Lease/executor/dispatch/API focused PostgreSQL suite | 112 passed, 41 warnings |
| Cooperative multi-heartbeat and lease-loss regressions | 10 passed |
| Complete detached backend suite | 364 passed, 62 warnings in 87.69s; exit file and container exit code both `0` |
| Frontend suite | 50 passed in 12 files |
| Frontend typecheck/lint/production build | passed / passed / passed |
| Compose validation, disabled and enabled | passed |
| Migration fresh upgrade and populated `0022 → 0021 → 0022` round trip | passed; current `0022 (head)` |

The backend suite includes the Phase 7 correlation/Wazuh/security and Phase 8.1–8.3 regression coverage.  Correlation/adversarial results remain synthetic-only evidence.

Lease and recovery tests cover one-winner concurrent acquisition, duplicate delivery fencing, wrong owner/generation rejection, cancellation and completion races, expiry recovery/reacquisition generation increments, attempt exhaustion, ordered bounded reconciliation, Redis dispatch failure, and disabled execution.  Executor tests capture protected-state counts before and after and prove no Intelligence items/reviews, typed links, legacy fact links, Findings, MITRE mappings, actions, canonical alerts, memberships, assessments, promotions, Events, or relationships are created or mutated.

## Migration 0022

Migration `0022` adds lease ownership, generation, heartbeat/expiry, execution attempt and timestamps plus bounded PostgreSQL checks and recovery/reconciliation indexes.  Existing `RUNNING` rows normalize to `QUEUED` because they lack a trustworthy lease owner; queued and terminal rows remain otherwise preserved.  There is one migration head and no `0023`.

## Security and privacy

Safe audits persist only status, request identity/hash and approved bounded categories.  Worker/task responses and logs do not carry raw payloads, full snapshots, prompts, provider configuration, credentials, authorization headers, SQL/exception details, or worker-supplied scope.  No shell, tool, containment, promotion, correlation, or triage recomputation path exists in this foundation.

## Deferred to Phase 8.5

- Real Ollama/provider invocation, prompt construction/versioning, structured output parsing, provider idempotency, and model timeout/token/cost handling.
- Automatic AI claim/citation creation.
- Live Wazuh end-to-end validation, automatic containment/remediation, cross-case retrieval, and SaaS/billing.

## Post-certification erratum

During Phase 8.5.0 inspection, a frozen legacy synchronous `POST /investigations/{id}/analyze` route was found still registered.  It could invoke the old provider path and mutate legacy Investigation fields and recommendations outside the certified queue/lease boundary.  It was retired in the corrective commit `fix(phase8): retire legacy synchronous reasoning route`; the historical `phase8.4-certified` tag is intentionally unchanged.  The execution foundation and migration `0022` are unchanged.  Future `0023` design must rely on atomic run-fenced persistence (or a genuinely non-redundant deterministic candidate key), not the redundant unique tuple `(id, lease_generation, provider_request_fingerprint)`.
