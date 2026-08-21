# RC1-A Offline Reproducibility and Regression Certification

## Scope and provenance

- Source branch: `release-readiness`
- Initial RC1-A source commit: `bef4d4db834ab4a49e03480fdee0abfabb390a1e`
- Clean-clone regression commit: `595e1c4b20fe35599593a8a3f306e3222ad649c3`
- Migration: one Alembic head at `0024`
- `phase8-certified`: `35014ff47878b95d1b0a7a08bba45e66f1c885a9` (unchanged)

The local `origin/release-readiness` tracking ref resolved to the initial
expected RC1-A commit. No authenticated remote fetch was attempted, so this is
local remote-tracking-ref evidence rather than a claim of live GitHub
authentication.

Acceptance used a fresh `git clone --no-local` in `/tmp` from the committed
source. The final clone was recreated after the fixture correction and had no
tracked or inherited `.env`, credential, `node_modules`, `.next`, cache,
database, log, screenshot, provider-output, or R4 artifact.

## Narrow corrections discovered during certification

The first durable full-backend run found two fixture failures, not a product
failure: `test_evidence_parsers.py` referenced ignored and absent
`tests/fixtures/evidence/auth.log`. A two-line synthetic syslog fixture was
added using only synthetic labels and documentation-range addresses. The parser
module then passed `3/3`, and the final full backend rerun passed.

The release documentation audit also found no Wazuh Vulnerability Detection
(`vd_updater`) storage guidance. `WAZUH_OPERATIONS.md` now documents the
separate operational boundary, bounded temp-workspace monitoring, and the
prohibition on deleting feed, alert, integration, TLS, or spool state as a
space-recovery shortcut. This changes no Manager or Aegis behavior.

## Migration certification

Using a fresh disposable PostgreSQL namespace:

- empty upgrade through `0024`: PASS;
- exactly one Alembic head and `alembic current`: `0024 (head)`;
- empty `0024 → 0023 → 0024` round trip: PASS;
- populated user with `must_rotate_password=true` downgrade to `0023`: safely
  refused with the migration's bounded pending-rotation safeguard;
- typed-evidence-reference foreign keys, check constraints, unique alias, and
  28 indexes were present; typed-reference populated downgrade protection is
  exercised by the final backend suite;
- production database URL secret-file behavior and sole-migrate-writer topology
  are covered by the production Compose regression suite.

## Durable regression evidence

| Gate | Result |
| --- | --- |
| Final full backend pytest | `492 passed, 0 failed, 0 skipped, 0 errors, 235 warnings in 91.06s` |
| Backend pytest exit file | `0` |
| Backend test-container exit | `0` |
| Complete frontend Vitest | `120 passed, 28 files` |
| Frontend install/test/typecheck/lint/build exit files | `0, 0, 0, 0, 0` |
| Frontend certification-container exit | `0` |
| Frontend lint | PASS — no warnings |
| Frontend production build | PASS; includes dynamic `/healthz` |
| Focused release operations documentation test | `4 passed` |
| Evidence parser fixture regression | `3 passed` |

The backend warning total consists of existing dependency and UTC API
deprecations. No assertion was skipped or weakened.

## Production configuration and safety audits

- Default production Compose rendering: PASS — execution, dispatch, and
  provider remain disabled; Ollama is optional.
- Explicit enabled configuration plus Ollama profile: PASS — fixed model and
  allowlist are `llama3.2:latest`; runtime remains digest-pinned; no model was
  downloaded or invoked.
- Compose topology: PASS — `migrate` is the sole writer; API has no Redis or
  Ollama health dependency; frontend probes `/healthz`; worker uses
  `intelligence-execution`, concurrency `1`, prefetch `1`; beat uses a process
  health check; internal services have no host ports; production secrets are
  file-backed.
- `GET /healthz`: bounded HTTP `200` frontend liveness response only.
- Registered/OpenAPI audit: no public synchronous `/analyze`, public
  claim-to-Finding conversion, or arbitrary internal authority transition.
- Client/navigation audit: no frontend legacy MITRE collection read, duplicate
  promoted Attack Graph route, unsupported primary navigation, raw/normalized
  payload body, snapshot, prompt, provider output, or browser authority
  calculation.
- The repository's bounded release scanner found no high-confidence secret
  candidates in tracked files or reachable history. Template `.env.example`
  files are intentional placeholders, not credentials.

## No-side-effect confirmation

RC1-A did not start or inspect R4 application state, credentials, database, or
evidence. It did not emit Wazuh events, invoke Ollama/provider generation,
create or review authority records, promote clusters, generate reports, or
create actions. All containers, database, Redis, Node volumes, temporary
Compose secrets, logs, and clean-clone files used for RC1-A are disposable and
must be removed after this record is committed.

## Remaining RC1-B live gates

RC1-B remains separately required for preserved R4 live acceptance: controlled
startup, authenticated human workflow, non-destructive restart/persistence,
backup/restore rehearsal, Wazuh durable delivery/replay evidence, and any
owner-approved live presentation checks. This document does not create an RC
tag or certify RC1.
