# U4 Release Authority Surface Certification

## Certified baseline

- Branch: `release-readiness`
- U4-C2 baseline: `480e35042cf0aa194fe8bb60266bda4001d427fb`
- Alembic: one head, `0024 (head)`
- Phase 8 certification tag: `phase8-certified` → `35014ff47878b95d1b0a7a08bba45e66f1c885a9` (unchanged)
- R4 acceptance services: inspected only; all remain stopped and were not started, rebuilt, or modified for this certification.

## Authority-surface result

| Acceptance area | Executable evidence | Result |
| --- | --- | --- |
| Intelligence run ownership | `test_intelligence_run_api.py`, `test_intelligence_run_claim_contracts.py`, `test_reconstruction_explanation_contract.py`, run-history and citation frontend tests prove a latest failed run remains visible, a completed run is selectable, and selected claims/citations remain run-scoped. Foreign or unavailable run selection is anti-enumerating. | PASS |
| AI authority | Run, claim-review, executor, and frontend controls keep AI items reviewable observations. Review changes only the authorized review state; it does not create Findings, MITRE mappings, actions, promotions, correlation, or triage state. | PASS |
| Findings authority | `test_finding_contract_api.py` proves active-user/RBAC checks, deterministic bounded list/review, strict requests, atomic audit behavior, scope isolation, inert hostile text, and the retired claim-to-Finding route is unavailable. | PASS |
| MITRE authority | `test_mitre_contract_api.py` and `mitre-workspace.test.tsx` prove bounded `/mitre` reads, canonical `PROPOSED` review only, required bounded rejection rationale, scope isolation, and inert rendering. | PASS |
| Reconstruction authority | ContextBuilder and reconstruction suites use confirmed Findings and confirmed MITRE mappings only. Typed citations remain references and never elevate AI claims to facts. | PASS |
| Security and exposure | API tests enforce principal-derived organization/actor scope, active-user checks, permissions, strict validation, and anti-enumerating 404. Response and UI contracts exclude raw payloads, normalized telemetry, prompts, snapshots, secrets, provider output, and arbitrary audit metadata. | PASS |

## Exact validation evidence

### PostgreSQL-backed authority matrix

Fresh disposable PostgreSQL was upgraded from an empty database through `0024`. The following focused suites completed successfully:

```text
177 passed, 101 warnings in 12.59s
```

The matrix included run API/claim contracts, executor and lease contracts, reconstruction explanation/API/read/gap contracts, ContextBuilder contracts, typed-reference schema constraints, Findings and MITRE APIs, authentication, promotion, and correlation-version isolation. Warnings were existing dependency and UTC deprecations; no test failed.

### Frontend

```text
Focused authority suite:  38 passed, 9 files
Complete frontend suite: 116 passed, 26 files
Typecheck:               PASS
Lint:                    PASS — no warnings or errors
Production build:        PASS
```

Focused coverage included Intelligence run history/progress, claim citation and review semantics, deterministic reconstruction seam, Findings, MITRE, shared release UI states, and WorkspaceNav.

### Static audits

- Registered API routes include the bounded Investigation MITRE route: `GET /api/v1/investigations/{investigation_id}/mitre`.
- No registered route ends in `/analyze`.
- No registered public claim-to-Finding route exists, including the retired `.../intelligence/items/{item_id}/finding` path.
- The frontend MITRE workspace reads only `/mitre`; it uses the existing bounded canonical review endpoint and does not read the legacy `/mitre-mappings` collection.
- Workspace navigation promotes only `/relationships` as Investigation Attack Graph. The compatibility `/attack-graph` route is not a WorkspaceNav destination.
- U4 clients contain no `dangerouslySetInnerHTML`, browser authority storage, synchronous-analysis request, or retired claim-to-Finding request.
- `git diff --check`: PASS.

## Boundary and behavior notes

- Organization and actor identity are derived from the authenticated principal; caller-supplied authority fields are rejected.
- Findings and MITRE mappings remain distinct analyst-controlled authorities. Confirming either does not create the other, an AI claim, a recommendation, or an action.
- A failed most-recent Intelligence Run does not suppress a selected completed run. Claims and typed citations are rendered only for the selected run; citation aliases are never mixed between completed runs.
- Deterministic reconstruction is factual and separate from AI claims. Only confirmed Finding/MITRE records enter its authoritative context under the certified policy.
- All displayed persisted text is rendered as escaped text. UI and response models intentionally omit raw evidence bodies and internal/provider material.

## Exclusions and non-blocking limitations

- This increment adds no provider execution, prompt construction, claim generation, automatic authority conversion, correlation/triage recomputation, migration, or R4 deployment.
- The frozen internal legacy synchronous reasoning code may remain in the repository for historical compatibility, but it is not registered by the application and has no public route.
- The legacy `/mitre-mappings` compatibility read path remains outside the U4 frontend; removing it is intentionally deferred because no removal necessity was demonstrated.
- This certification does not make claims FACTs, create new Findings or MITRE mappings, or alter existing R4 evidence.

## Certification decision

All U4 release authority-surface acceptance rows have executable proof, the migration remains at one `0024` head, and no R4 service was started or modified.
