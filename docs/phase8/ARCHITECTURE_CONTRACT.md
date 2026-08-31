# Phase 8 Alert Intelligence Architecture Contract

## Status and vision

Phase 8 enriches an existing Aegis Investigation so that an analyst can understand the incident behind an alert. It is a Security Decision / Alert Intelligence Layer above security sources; it is not a SIEM replacement.

The authoritative flow remains:

```text
Security source → CanonicalAlert → Deduplication → Correlation → Triage
→ analyst-controlled promotion → Investigation → Phase 8 Intelligence Run
→ bounded context and evidence-linked claims → analyst review → analyst decision
```

Phase 8 does not create a parallel alert, case, evidence, entity, indicator, Finding, or MITRE system. PostgreSQL remains authoritative. Redis/Celery may transport work later but never becomes the source of truth.

## Protected Phase 7 baseline

The `phase7-certified` baseline protects CanonicalAlert ingestion, Wazuh and generic webhook contracts, deduplication, correlation-v2, triage-v1, analyst-controlled promotion, canonical evidence provenance, organization authorization, MITRE analyst review, and synthetic benchmark semantics.

Phase 8 reads persisted correlation-v2 membership reasons and triage ledgers to explain them. It must never recompute, tune, or replace their decisions. Synthetic/adversarial correlation results remain synthetic and must not be represented as production accuracy.

## Component and model boundaries

| Component | Ownership and boundary |
| --- | --- |
| Intelligence Run | Extend `IntelligenceAnalysis`; PostgreSQL-authoritative lifecycle, context snapshot, versions, hashes, timing, and safe errors. |
| Claim | Extend `IntelligenceItem`; the canonical derived-claim record. It references authoritative records and never duplicates them. |
| Claim evidence link | Evolve `IntelligenceFactLink` into the typed claim-to-evidence reference mechanism. |
| Review history | Reuse/extend `IntelligenceReviewEvent` as append-only claim-review history. |
| ContextBuilder | New deterministic `ai_reasoning` domain service. It selects only permitted, bounded factual context. |
| Explainable correlation | Read-only adapter over persisted `AlertClusterMembership` reasons for `correlation-v2`. |
| Entity ambiguity | AI may propose uncertain relationships as claims; canonical entity identity stays deterministic. |
| Findings, MITRE, actions | Existing models retain their current authority and review workflows. A recommendation begins as a claim and may become `RecommendedAction` only through explicit analyst promotion. |

Existing Evidence, Event, RawRecord, CanonicalAlert, Finding, MITRE, Asset, and Audit records remain authoritative in their present roles. `ReasoningService` is frozen: its legacy Investigation fields remain readable for compatibility but Phase 8 must not write or extend them.

## Claim semantics

Every claim has independent type, origin, and review axes.

| Axis | Values |
| --- | --- |
| Claim type | `FACT`, `OBSERVATION`, `INFERENCE`, `HYPOTHESIS`, `RECOMMENDATION` |
| Origin | `SOURCE`, `DETERMINISTIC_ENGINE`, `AI`, `ANALYST` |
| Review status | `PENDING`, `CONFIRMED`, `REJECTED`, `UNRESOLVED`, `SUPERSEDED` |

Rules:

- Sensor telemetry normally creates a `SOURCE` / `OBSERVATION` claim, never an automatic FACT.
- Only a deterministic, versioned rule grounded in authoritative Aegis records may create a `FACT` claim.
- AI may never create a FACT, a confirmed MITRE mapping, a Finding, a CanonicalAlert, a canonical entity, or an action.
- Analyst confirmation changes review status only. It does not change type or origin.
- Reclassification creates a new claim with a self-reference to the claim it supersedes. The prior claim remains auditable.
- Phase 8.1 supports the FACT schema and invariants but introduces no FACT-producing engine.

### Claim creation matrix

| Origin | Allowed types |
| --- | --- |
| `SOURCE` | `OBSERVATION` |
| `DETERMINISTIC_ENGINE` | `FACT`, `OBSERVATION`, `INFERENCE` |
| `AI` | `OBSERVATION`, `INFERENCE`, `HYPOTHESIS`, `RECOMMENDATION` |
| `ANALYST` | `OBSERVATION`, `INFERENCE`, `HYPOTHESIS`, `RECOMMENDATION` |

Initial state is `CONFIRMED` only for a deterministic FACT with authoritative support. All other claims begin `PENDING` or `UNRESOLVED`.

### Claim review transitions

```text
PENDING    → CONFIRMED | REJECTED | UNRESOLVED | SUPERSEDED
UNRESOLVED → CONFIRMED | REJECTED | SUPERSEDED
CONFIRMED  → SUPERSEDED
REJECTED   → SUPERSEDED
SUPERSEDED → terminal
```

Each transition creates immutable review/audit history. Claim type, origin, statement, and evidence links do not change after creation.

## Intelligence Run lifecycle

```text
QUEUED → RUNNING → COMPLETED
                 ↘ FAILED
QUEUED → CANCELLED
RUNNING → CANCELLED
```

Runs are organization and Investigation scoped. An analyst-origin claim uses an explicit analyst-created Intelligence Run; `analysis_id` remains non-null. A retry creates a new queued run linked to its terminal predecessor rather than reopening it.

Runs are idempotent using organization, Investigation, bounded context fingerprint, orchestration version, and request identity. They record provider, model, prompt version, schema version, input/output hashes, duration, and safe error metadata. Alert ingestion must not wait for model execution.

## ContextBuilder contract

The default context boundary is exactly one organization and one Investigation.

Permitted inputs are promoted alert evidence, canonical evidence, RawRecord/Event references, Investigation entities and indicators, deterministic triage ledgers, persisted correlation-v2 membership reasons, and analyst-approved Findings or MITRE mappings. Assets are excluded until a safe, explicit Investigation-to-Asset relationship exists; no asset association is inferred from names or telemetry.

The ContextBuilder must prohibit unrelated Investigations, other organizations, similarity-based cross-case retrieval, unbounded raw telemetry, and arbitrary organization-wide queries. It creates a bounded, sanitized, versioned, hashed snapshot with stable fact aliases.

Snapshot retention is configurable later. Phase 8.1 implements no automatic deletion and persists only bounded sanitized snapshots and validated structured output.

## Evidence-reference integrity

Every claim evidence link must be organization scoped, use an allowed factual type, verify server-side ownership, and verify Investigation scope except for an explicitly linked asset. It records support role (`SUPPORTS`, `CONTRADICTS`, or `CONTEXT`), factual type/ID, and a source locator where available.

Unknown, cross-organization, or out-of-context IDs are rejected before claim persistence. Model aliases are deterministic snapshot aliases, not authority. Claims reference facts rather than copying source telemetry.

## Organization isolation and auditability

Every run, claim, evidence link, and review event carries `org_id` and is read through the authenticated principal's organization. Cross-Investigation and cross-organization reasoning are out of scope for initial Phase 8.

Claim semantic content is append-only. Review state is represented by immutable review events plus a current-state projection. Supersession uses an `IntelligenceItem` self-reference. Snapshots, hashes, versions, and safe error metadata are auditable. Existing Phase 7 records are read-only intelligence inputs.

## AI trust boundary and degraded mode

All alert and telemetry text is untrusted data. Instructions remain separate from bounded evidence. Context applies secret/token redaction, stable aliases, and field/size limits. Model output is strictly structured and validated, may cite only known evidence aliases, cannot invoke tools or commands, and cannot trigger automatic actions.

Invalid output creates no claims. Unvalidated raw model output is not retained. Provider or model failure marks the run `FAILED`, preserves the Investigation, and leaves evidence, correlation, triage, promotion, and analyst workflow usable. No automatic containment or remediation is permitted in Phase 8.

## Phase plan

| Section | Scope |
| --- | --- |
| 8.1 | Intelligence foundation, provenance, lifecycle, claims, context contract, and migration/test contracts. |
| 8.2 | Deterministic evidence and context reconstruction. |
| 8.3 | Read-only explainable correlation-v2. |
| 8.4 | Evidence-linked activity and attack-chain reconstruction. |
| 8.5 | Hypotheses and AI reasoning with degraded-mode handling. |
| 8.6 | Proposed MITRE, gaps, blast radius, and recommendations. |
| 8.7 | Analyst review and decision workflow. |
| 8.8 | Adversarial evaluation and certification. |

## Phase 8.1 scope

Phase 8.1 establishes additive Intelligence Run and Claim schema contracts, independent semantic axes, review and supersession semantics, organization isolation, deterministic bounded-context rules, idempotency/versioning, and safe failure behavior. It adds contract-level tests and preserves all Phase 7 regression gates.

### Exclusions

- No changes to Phase 7 ingestion, Wazuh, generic webhook, deduplication, correlation-v2, triage-v1, promotion, or canonical evidence behavior.
- No ContextBuilder implementation, AI prompt changes, cross-case retrieval, entity merge, automatic action, UI/demo work, or Phase 8.2+ functionality.
- No new parallel alert, Investigation, evidence, entity, Finding, or MITRE authority system.

### Acceptance criteria

- Claim type, origin, and review status are independent and validated.
- AI cannot create FACT or confirmed conclusions.
- Claims cannot reference unknown, cross-org, or out-of-context records.
- Runs support queued, failed, cancelled, idempotent, retry-safe, versioned behavior.
- Snapshots are bounded, sanitized, reproducible, and auditable.
- Invalid or unavailable AI leaves no partial claims and does not block Investigation access.
- Claim review and supersession history remain auditable.
- All Phase 7 regression gates remain protected.
