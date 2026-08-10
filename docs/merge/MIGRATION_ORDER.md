# Zero-Risk Migration Order

## Dependency graph

```text
0. Freeze contracts and establish acceptance fixtures
        ↓
1. Identity/RBAC and shared persistence remain unchanged
        ↓
2. Canonical immutable fact schema + provenance service contracts
        ↓
3. Secure evidence ingestion / deterministic normalization
        ↓
4. Case read-model compatibility projection
        ├─ 5a. Connector adapter → canonical intake/facts
        ├─ 5b. Timeline/indicator/entity/relationship read APIs
        └─ 5c. Workspace evidence/timeline pages
        ↓
6. Attack graph factual projection (then AI overlay)
        ↓
7. Immutable AI analysis, hypotheses, reasoning, recommendations, review
        ↓
8. Findings/MITRE/report snapshots/audit completion
        ↓
9. Data reconciliation, compatibility removal, legacy retirement
```

## Ordered phases

| Order | Work unit | Prerequisites | Regression controls | Complexity | Classification |
|---:|---|---|---|---|---|
| 0 | Contract freeze: capture OpenAPI, current UI route/API matrix, seeded-record checks, fixtures | Approval | No source changes; define baseline response snapshots | Medium | KEEP |
| 1 | Preserve identity, organizations, permissions, shared DB/session, Aegis repository/history | 0 | Auth/API tests must remain green | Low | KEEP |
| 2 | Add canonical evidence/fact and inference model design, IDs, ownership, provenance invariants | 1 | Design review: immutable facts, no AI FK write path | High | REFACTOR |
| 3 | Implement evidence storage and parser/normalizer pipeline with deterministic fixture tests | 2 | Hash/parse/raw/event/relationship reconciliation; failure atomicity | High | REPLACE legacy evidence path |
| 4 | Expose compatibility read projection for an Investigation backed by facts plus labelled legacy context | 3 | Existing list/detail/report/graph endpoint snapshots remain compatible | High | REFACTOR |
| 5 | Route webhook ingestion through the new intake/fact pipeline behind existing public endpoint | 3–4 | Contract tests for secret auth, status, response ID, transaction rollback | High | REFACTOR |
| 6 | Migrate UI workspace incrementally: Overview → Evidence → Timeline → Indicators → Entities | 4 | Keep `/investigations/[id]` working; e2e case workflow fixtures | High | REFACTOR |
| 7 | Replace graph data adapter: EntityRelationships are factual base, AI overlay is distinct | 3–6 | Graph node/edge count/provenance tests and old visual regression checks | Medium–High | REFACTOR |
| 8 | Introduce immutable AIAnalysis/Proposal/Review flow; retire direct mutation behavior | 3–7 | Assert AI cannot update evidence/raw records/events/hashes; preserve prior analysis versions | High | REPLACE |
| 9 | Migrate findings, confirmed ATT&CK mappings, recommendations decisions, report snapshots and audit events | 6–8 | Analyst attribution/reproducible report tests | Medium–High | REFACTOR |
| 10 | Migrate historical CIOS data and classify historic Aegis data; reconcile counts/hashes/IDs | 2–9 | Dry runs, idempotency, exception ledger, sampled source verification | High | DEFER until all reads stable |
| 11 | Remove compatibility projections and deprecate legacy tables/routes/components | 10 | No consumer references; backup/reconciliation approval | Medium–High | REMOVE last |

## Non-negotiable stop gates

Do not start a phase when its predecessor has unresolved failures. In
particular:

1. No AI migration before immutable fact/provenance records exist.
2. No graph migration before factual entity relationships exist.
3. No legacy table deletion while an API, report, graph, or frontend page reads
   it.
4. No CIOS data migration before identities/org mappings and evidence storage
   retention policy are approved.
5. No public webhook request/response change without an explicitly versioned API
   decision and external sender compatibility test.

## Immediate next approved action

The next implementation authorization should be narrowly scoped to Phase 0:
create baseline contract/fixture tests and the migration design specification.
It should not yet create database migrations or alter production behavior.
