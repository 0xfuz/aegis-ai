# Phase 8.2 Certification

## Certified baseline

Phase 8.2 is certified on `phase8-alert-intelligence` at commit
`520039f9a56c4cd3584ba34597331c4b1a5bbd74`.  The migration graph has one
head: `0021`.  This certification covers typed evidence-reference contracts,
server-resolved citation integrity, deterministic activity reconstruction,
reconstruction-gap analysis, and the bounded analyst reconstruction read API.

The reconstruction capability is a scoped, read-only analyst view.  It builds
from persisted, authoritative organization and Investigation records and does
not execute a provider, construct a prompt, dispatch work, generate claims,
recompute correlation or triage, or initiate actions.

## Trust and response boundary

- Organization identity comes from the authenticated principal.  The route
  checks that the principal is an active user in that organization and resolves
  the Investigation through the scoped Investigation service.
- The only Phase 8.2 reconstruction route is `GET
  /api/v1/investigations/{investigation_id}/intelligence/reconstruction`.
  It requires `investigation:read`; foreign or inactive-principal access fails
  as a non-enumerating not-found response.
- The response is bounded by a server policy, deterministically ordered, and
  exposes summaries, provenance identifiers, versions, safe locator metadata,
  omissions, activity uncertainty, and gap classifications only.
- It excludes raw bodies and normalized payloads, full ContextBuilder
  snapshots, credentials/secrets, prompts, provider output, legacy AI output,
  audit payloads, and SQL/exception detail.  Persisted text and locator
  metadata are redacted and bounded before projection.
- Typed citations resolve only aliases from an immutable persisted run
  snapshot.  Target identifiers, scope, status, correlation version, locator,
  hashes, and producer metadata are server-derived.  Exact v2 promotion,
  membership, and triage lineage is required; there is no v1/v2 fallback.

## Migration evidence

- Fresh disposable PostgreSQL/Redis database upgraded successfully from an
  empty state through `0021`; `alembic heads` and `alembic current` each
  reported only `0021 (head)`.
- The required Phase 8.2 tables resolved after upgrade:
  `organizations`, `investigations`, `intelligence_analyses`,
  `intelligence_evidence_references`, and
  `intelligence_claim_evidence_links`.
- Empty-state `0021 -> 0020 -> 0021` completed successfully.
- Representative Phase 8.1 legacy backfill was verified from `0019`: a
  persisted completed legacy analysis received
  `request_key=legacy:<analysis-id>` and
  `output_schema_version=aiie-output-v1` on upgrade through `0021`.
- Populated downgrade safety was verified with a persisted typed evidence
  reference.  Downgrade to `0020` refused with the intentional migration error
  `cannot safely downgrade typed evidence references with Phase 8.2 data` and
  left the database at `0021`.
- No `0022` migration exists.

## Executable adversarial evidence

| Acceptance area | Executable evidence | Result |
| --- | --- | --- |
| Typed references | `test_typed_evidence_reference_schema.py` covers all 12 target/FK pairs, alias/type/scope forgery rejection, FK and uniqueness constraints, claim roles, atomicity, idempotency, immutable metadata, and legacy-link preservation. | PASS |
| Temporal reconstruction | `test_activity_window.py` and `test_activity_window_db.py` cover promoted-v2 interval resolution, single-event and receipt fallbacks, future/skew/equal/out-of-order ambiguity, version isolation, foreign scope exclusion, and read-only deterministic output. | PASS |
| Context and gap taxonomy | `test_context_builder_contracts.py`, `test_context_builder_db_contracts.py`, and `test_reconstruction_gaps.py` cover bounded deterministic aliases, raw-record sanitization, LIMIT/TOTAL_SIZE omissions, parser/raw/locator distinction, complete-chain no-false-gap behavior, explicit contradiction provenance, and the promotion/version negative matrix. | PASS |
| Reconstruction read model | `test_reconstruction_read_service.py` covers bounded sections, total-byte removal, scoped deterministic projection, redaction, and no writes. | PASS |
| API authorization and exclusions | `test_reconstruction_api.py` covers the sole GET route, authorization, anti-enumeration, UUID validation, safe response projection, and no mutations. | PASS |
| Phase 7 preservation | Promotion and correlation version-isolation tests in the complete suite verify exact v1/v2 separation; reconstruction reads do not recompute either engine. | PASS |
| No-side-effects | Typed-reference, activity, gap, read-service, and API tests record unchanged runs, claims, references, Findings, MITRE, memberships, assessments, promotions, and actions. | PASS |

The complete isolated backend certification run completed with durable evidence:
`325 passed, 64 warnings in 71.95s`; pytest and container exit codes were both
zero.  Its durable log was retained during certification at
`/tmp/aegis-825-durable-results/pytest-rerun.log`.

A certification collection of the focused typed-reference, temporal, context,
gap, reconstruction-read/API, promotion, and correlation-isolation modules
identified 86 executable tests.  Those modules are included in the complete
325-test backend result above; collection was used here only to record the
focused coverage size without duplicating the verified full run.

## Frontend evidence

- `npm test`: 7 test files and 25 tests passed (exit code 0).
- `npm run typecheck`: passed (exit code 0).
- `npm run lint`: passed with no ESLint warnings or errors (exit code 0).
- `npm run build`: Next.js production build passed, generating 15 static pages
  (exit code 0).

## Scope and limitations

The adversarial correlation benchmark remains synthetic-only evidence.  It is
not a production accuracy, latency, or real-world performance claim.

The following remain explicitly deferred: provider/Ollama execution, prompt
construction, worker/lease/dispatch, automatic AI claim generation, Alert
Intelligence UI, live Wazuh end-to-end validation, cross-case retrieval,
automatic containment/remediation, and SaaS/billing.  Phase 8 is not complete;
this document certifies only Phase 8.2.
