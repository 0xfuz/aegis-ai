# U6 Release UI Certification

## Certified baseline and scope

- Branch: `release-readiness`
- U6-A baseline: `f71df4d3811f21bdb81a147eab45f77d099588cc`
- Migration: one Alembic head, `0024 (head)`
- Phase 8 tag: `phase8-certified` → `35014ff47878b95d1b0a7a08bba45e66f1c885a9` (unchanged)
- R4 acceptance environment: all services were inspected as stopped and were not started, rebuilt, queried for data, or modified.

This is a release-presentation certification. It adds smoke coverage and no
authority-policy, correlation, triage, promotion, provider, or migration
behavior.

## Supported presentation surface

The authenticated shell presents only permission-backed primary navigation:

- Dashboard, Cases, Alert Triage;
- Assets and Threat Intelligence when their permissions are granted;
- Settings and User management only for an administrator.

Detections, Analytics, Global Reports, and the global Attack Graph remain
hidden from primary navigation. The Investigation WorkspaceNav is the sole
Investigation navigation authority: Overview, Evidence, Timeline, Indicators,
Entities, Attack Graph (`/relationships`), Intelligence, Findings, MITRE
ATT&CK, Notes, Reports, and Audit Trail. The legacy Investigation
`/attack-graph` path is compatibility-only and redirects to `/relationships`.

## Presentation and authority invariants

- `GET /healthz` returns only HTTP `200` and
  `{"status":"ok","service":"frontend"}` with `Cache-Control: no-store`.
  It does not contact optional subsystems or reveal runtime configuration.
- Production login contains no demo credentials. Unauthenticated routing and
  bounded login failures retain the existing authentication boundary.
- Dashboard, Cases, Alert Triage, factual workspaces, Notes, Reports, and
  Audit Trail use bounded server projections, preserve server order, and use
  the shared loading, empty, permission, not-found, retry, and degraded
  states.
- Alert Triage eligibility remains server-authored; no browser calculation of
  correlation, deduplication, triage, or promotion eligibility occurs.
- Intelligence claims remain reviewable AI content and never become FACTs.
  A latest failed run remains visible while a selected completed run keeps its
  own claims, typed citations, and reconstruction context. Findings and MITRE
  are separate analyst-controlled authorities.
- No public synchronous `/analyze`, public claim-to-Finding conversion, or
  automatic MITRE conversion route is registered. The frontend reads the
  bounded `/mitre` collection; its existing canonical review POST is not a
  legacy collection read.
- Investigation UI renders persisted values as escaped text. It excludes raw
  and normalized payload bodies, prompts, provider output, snapshots, secrets,
  arbitrary audit payloads, and browser-owned authority state.

## Health and Compose topology

Production Compose uses `/healthz` for frontend health, while the frontend
runtime image uses the same exact-200 probe. API liveness remains independent
of Redis, Celery, Ollama, Wazuh, and provider readiness. The one-shot
`migrate` service remains the sole Alembic writer; worker and beat require
PostgreSQL migration completion and Redis health, use process-appropriate
Celery checks, and the worker is fenced to the `intelligence-execution` queue.
Ollama is optional, pinned, and execution/dispatch/provider settings remain
disabled by default.

## Exact validation evidence

| Gate | Result |
| --- | --- |
| Fresh disposable PostgreSQL migration | `0024 (head)` |
| Focused backend presentation/auth/route/triage/reconstruction/authority/Notes/Reports/Audit matrix | `88 passed, 126 warnings in 7.81s` |
| Focused frontend presentation smoke/workspace matrix | `81 passed, 20 files` |
| Full frontend suite | `120 passed, 28 files` |
| Frontend typecheck | PASS |
| Frontend lint | PASS — no warnings |
| Frontend production build | PASS |
| Disabled-default Compose rendering | PASS |
| Explicitly enabled Ollama-profile Compose rendering | PASS |
| Registered-route audit | PASS |
| Frontend route/client exposure audit | PASS |
| Tracked and reachable-history high-confidence secret signature scan | PASS |
| `git diff --check` | PASS |

The warnings in the backend matrix are existing dependency and UTC API
deprecations; no test failed. Compose validation used synthetic, short-lived
secret files and did not start a service.

## Exclusions and remaining RC1 gates

- This is not RC1 certification and does not create an RC tag.
- No R4 deployment, health restart, credential access, Wazuh emission/replay,
  promotion, report generation, note creation, provider/model execution, AI
  run, or analyst review was performed.
- No new browser-testing dependency or visual screenshot baseline was added.
- RC1 remains responsible for its separately approved clean-clone/live
  acceptance, backup/restore, and final operational evidence gates.
