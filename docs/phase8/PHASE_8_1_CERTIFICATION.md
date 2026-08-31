# Phase 8.1 Certification

## Certified baseline

Phase 8.1 is certified on branch `phase8-alert-intelligence` at the local
`phase8.1-certified` tag.  The certification includes the Phase 8.1 run and
claim contracts, deterministic ContextBuilder, version-aware promotion
compatibility, orchestration lifecycle/race boundary, and analyst-facing run
API.  Migration head is `0020`; no `0021` migration is included.

Included Phase 8.1 commits include `0609f75`, `bc8a647`, `2ecf58d`,
`ac630b0`, `c48f585`, and `c007f08`, plus final API coverage certification.

## Properties certified

- Intelligence runs and claims have PostgreSQL-backed contracts, scoped
  lineage, and append-only review/audit behavior.
- Context snapshots are deterministic, byte-bounded, organization/investigation
  scoped, and redact credential-shaped persisted telemetry while retaining
  approved observables.
- Promotion reads are explicitly correlation-version aware; no v1/v2 fallback
  was introduced.
- Orchestration queue/retry uniqueness races recover the identical winner;
  competing lifecycle transitions, audit failures, and bounded PostgreSQL lock
  failures leave one authoritative state without SQL detail leakage.
- Analyst routes expose only queue, get, list, cancel, and retry.  Principal
  identity supplies organization and actor scope.  Responses exclude complete
  snapshots, raw telemetry, prompts, provider responses, and audit payloads.
- AI remains unable to create FACT claims.  No automatic promotion, action,
  provider invocation, prompt construction, or Phase 7 algorithm change is
  part of this phase.

## Validation record

- Fresh PostgreSQL/Redis upgrade: `0019 -> 0020`; Alembic head `0020`.
- Representative legacy backfill: a `0019` COMPLETED run retained its status,
  received `legacy:<run-id>` and `aiie-output-v1`; a legacy AI item mapped
  `UNREVIEWED` to `PENDING` while retaining origin `AI`.
- Empty-state supported downgrade/upgrade round trip: `0020 -> 0019 -> 0020`
  passed.  A populated Phase 8 database intentionally rejects downgrade to
  prevent silent loss of Phase 8-only state.
- Secure run API: 11 passed.
- A2 PostgreSQL race suite: 14 passed twice during final certification.
- Complete backend PostgreSQL suite: 261 passed.  This includes synthetic-only
  Phase 7 adversarial/correlation evidence, version isolation, deduplication,
  triage, promotion, Wazuh mapper/webhook, generic webhook/security,
  evidence/provenance, AIIE/review, Findings/MITRE, reporting/audit,
  authentication, and organization isolation coverage.
- Frontend: 25 tests passed; TypeScript typecheck, lint, and production build
  passed.

The correlation benchmark remains synthetic adversarial evidence only.  It is
not a statement of production accuracy or real-world performance.

## Deferred scope

The following are explicitly deferred to the worker/Phase 8.2 scope: leases
and worker execution, Redis/Celery dispatch, provider execution, prompt
construction, AI claim generation, UI work, cross-case retrieval, and
migration `0021`.
