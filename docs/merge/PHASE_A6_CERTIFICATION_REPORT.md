# Phase A6 Certification Report

## PHASE A6 — CERTIFIED

Final certification ran on a freshly recreated disposable Docker Compose project, `aegisa6closure`, with PostgreSQL, Redis, and backend services. Every command explicitly used `DEBUG=true`. No host Python environment was used.

## Migration and schema

- Alembic round-trip: **passed** — `0012 → 0013 → 0012 → 0013`.
- Schema inspection: **passed** — Findings, MITRE mappings, copied fact-link tables, foreign keys, indexes, and constraints were present after re-upgrade.

## Backend verification

- Focused A6 backend suite (`tests/test_a6_workflow.py`): **6 passed**.
- Full backend PostgreSQL suite: **81 passed**.
- HTTP authorization: **passed** — anonymous Findings, MITRE, Overview, and Audit access is denied; wrong-organization and wrong-investigation scopes are denied; an authorized analyst is allowed.
- Exact Overview and isolation: **passed** — real authenticated HTTP assertions cover exact evidence, raw-record, event, indicator, entity, relationship, Finding, confirmed-MITRE, and latest-AIIE counts. Legacy records, a different investigation, and a different organization do not affect scoped canonical totals.
- HTTP E2E: **passed** — approved eligible AIIE item → HTTP Finding conversion → retrieval → analyst status update → MITRE proposal retrieval → confirm/reject with rationale → Overview → Audit → provenance assertions.

## Integrity and contract verification

- FACT remains immutable canonical evidence-derived data: **passed**.
- AIIE remains append-only, reviewable inference output: **passed**.
- AI cannot directly create a confirmed Finding or confirm MITRE: **passed**.
- Only approved eligible AIIE observation, hypothesis, and recommendation items convert to Findings; unreviewed and rejected items are rejected: **passed**.
- Finding copied FACT provenance survives conversion without mutating IntelligenceFactLink or canonical facts: **passed**.
- MITRE source references and supporting provenance survive analyst review: **passed**.
- Investigation-scoped audit history records analyst Finding and MITRE actions: **passed**.
- Organization/investigation isolation and legacy API compatibility: **passed**.

## Frontend verification

- Dedicated A6 workspace suite: **9 passed**.
- Full frontend suite: **24 passed** across 6 files.
- Typecheck: **passed**.
- Lint: **passed**.
- Production Docker frontend build: **passed** (`aegisa6closure-frontend`).

The dedicated frontend tests cover Finding states, source/provenance, status submission, loading/empty/error states; approved intelligence conversion and failure handling; MITRE proposed/confirmed/rejected rendering, source/provenance, confirm/reject rationale interactions, and loading/empty/error states; plus exact canonical Overview metrics and latest AIIE status.

## Defects fixed during certification

- Restricted Finding status transitions to the approved workflow: `OPEN → CONFIRMED|DISMISSED`, then `CONFIRMED → RESOLVED`.
- Made repeated Overview fixture runs collision-safe by generating run-specific evidence storage keys.
- Rendered the existing MITRE Finding/AIIE source reference in the workspace so provenance is visible to analysts.

## Non-blocking technical debt

- Test output includes upstream deprecation warnings from `pytest-asyncio`, `passlib`/`crypt`, `reportlab`, and `python-jose`; no certification behavior is affected.
- The Vite CJS API deprecation warning is emitted by the frontend test toolchain; it does not affect the production build.
