# Phase 3 Implementation Report — Investigation Workspace Cutover

## Delivered scope

Phase 3 adds case-scoped, canonical FACT read views while retaining all existing Aegis investigation routes, APIs, legacy timeline, attack graph, AI behavior, and report behavior.

### Routes and components

- Added factual routes for overview, evidence, timeline, indicators, entities, and relationship/graph placeholder.
- Added compatibility placeholders for findings, MITRE ATT&CK, notes, reports, and audit trail.
- Added `WorkspaceNav` and `factual-workspace` components in the existing authenticated design system.
- Updated the existing sidebar to organize current entry points under Operations, Investigation, Aegis Intelligence, and Workspace. Case-specific sections remain in case workspace navigation.

### APIs consumed or extended

- Consumed Phase 2 canonical endpoints for evidence, raw records, events, indicators, entities, and relationships.
- Added additive, scoped read endpoints for indicator occurrences and entity observations.
- Added safe parser name/version fields to canonical evidence responses. No storage path/key is returned.
- Updated the common API client to preserve browser multipart boundaries for `FormData` evidence upload. JSON behavior remains unchanged.

## Compatibility status

- Legacy `/investigations/{id}` and its attack-graph route are unchanged.
- No legacy API response, legacy model, database table, migration, AI endpoint, report, or graph behavior was removed or replaced.
- Canonical timeline explicitly excludes legacy manually authored timeline entries.

## Verification

| Check | Result |
| --- | --- |
| Python compile of backend application | passed |
| Frontend TypeScript check | passed |
| Frontend unit tests | passed (4 focused workspace tests: navigation, evidence/raw-record inspection, duplicate feedback, timeline filtering/provenance) |
| Frontend lint | passed |
| Frontend production build | passed via the repository Docker build (`docker compose build frontend`); the host-only Next invocation remains environment-sensitive |
| Focused backend tests | passed: 16 parser and legacy attack-graph tests |
| Full backend test suite | blocked in host environment: ambient `DEBUG=release` fails Settings validation and `python-jose` is unavailable; the bare host invocation also lacks the application import path |
| Playwright/e2e | not available in this repository |

The frontend test harness was added as development-only tooling (`vitest`, jsdom, Testing Library); it has no production runtime dependency.

## Known limitations

- Overview obtains the exact raw-record total by summing the already-authorized evidence raw-record endpoints. A summary endpoint is intentionally deferred to avoid inventing a new backend feature during cutover.
- Relationship/graph, findings, MITRE, notes, reports, and audit are explicit placeholders; no graph or AI migration was started.
- Parser errors are intentionally not exposed in this first UI pass; only safe failed status is shown.

## Exact Phase 4 scope (not implemented)

Phase 4 may implement the approved AI trust migration: separate, versioned, provenance-linked INFERENCE and analyst VERDICT records and their UI. It must not unify the attack graph or retire legacy APIs unless separately approved.
