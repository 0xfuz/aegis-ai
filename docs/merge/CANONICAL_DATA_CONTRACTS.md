# Canonical Data Contracts

All canonical IDs are UUIDs and timestamps are UTC `timestamptz`. “Required”
means required at creation unless the lifecycle explicitly permits a pending
state. `org_id` is required for all tenant-owned records. The contracts are
Phase-0 design, not current database/API definitions.

## Trust classes

| Class | Records | Authority and mutability |
|---|---|---|
| FACTS | Alert, EvidenceItem, EvidenceParseRun, RawRecord, Event, Indicator, IndicatorOccurrence, Entity, EntityObservation, EntityRelationship, AttackTechnique | Deterministic source/derivation. Immutable source and lineage fields. AI cannot mutate them. |
| INFERENCES | AIAnalysis, Hypothesis, Recommendation, ReasoningStep | AI-generated proposals. Append-only/versioned; review state may change without changing generated content. |
| VERDICTS | Finding, analyst review/decision records, ReportSnapshot, AuditEvent | Analyst-confirmed or governance artifact. Amend only through a new version/audit event; identity, time, and rationale required. |

## Containers and intake

| Model | Purpose / ownership | Lifecycle and mutability | Required fields | Optional fields | Source of truth / provenance | Legacy / donor / migration policy |
|---|---|---|---|---|---|---|
| Investigation | Security matter container; org-scoped. “Case” is UI synonym. | `NEW → TRIAGING → INVESTIGATING → CONTAINED → RESOLVED`; status/assignment/tags may change through audited analyst actions. | id, org_id, title, status, severity, source/creation metadata, created/updated timestamps | case number, description, assignee, tags, closure metadata | Aegis Investigation is source of truth for container state; it owns links, not raw facts. | Aegis `Investigation`; CIOS `Case`; merge and preserve Aegis PKs. |
| Alert | Org-scoped external signal associated with zero/one/many Investigations by explicit link. | Immutable source payload/received time; correlation/attachment is an auditable derived action. | id, org_id, source connector, received_at, raw payload/hash, normalized alert fields | external ID, severity, status, linked investigation | Connector acquisition record; references connector/RawEvent intake. | Aegis connector payload/RawEvent; no CIOS equivalent; introduce beside existing webhook flow. |
| EvidenceItem | Org + Investigation scoped immutable original evidence. | `PENDING → ACCEPTED/PARSING → COMPLETE/FAILED/REJECTED`; source bytes/hash never update. | id, org_id, investigation_id, storage key, SHA-256, byte size, filename, detected MIME, extension, imported_at, acquisition actor/source | source description, external source ID, retention metadata | Controlled storage + metadata; hash calculated at ingestion. | No Aegis equivalent; CIOS EvidenceItem; new table, never map IOC chips as bytes. |
| EvidenceParseRun | One parser attempt for an EvidenceItem. | Pending/running/complete/failed/rejected; terminal output immutable. Multiple runs allowed. | id, org_id, evidence_id, parser name/version, status, started_at | ended_at, warnings, error summary, limits/config fingerprint | Deterministic parser execution log. | No Aegis equivalent; CIOS parse run; new table. |
| RawRecord | Exact source line/object/segment emitted by ParseRun. Evidence/investigation scoped through parents. | Immutable; a parser correction produces new run/records. | id, org_id, evidence_id, parse_run_id, ordinal, content or protected locator, content type | byte offset, line range, encoding, structured source locator | EvidenceParseRun output; never AI-created. | Aegis RawEvent only partially similar; CIOS RawRecord; preserve connector payload separately. |

## Deterministic observations

| Model | Purpose / ownership | Lifecycle and mutability | Required fields | Optional fields | Source of truth / provenance | Legacy / donor / migration policy |
|---|---|---|---|---|---|---|
| Event | Normalized security event, Investigation scoped; canonical timeline item. | Immutable normalized observation under a parse/normalizer version; supersede via new derivation. | id, org_id, investigation_id, evidence_id, raw_record_id, normalizer name/version, normalized payload | timestamp, source, host, user, process, network tuple, event type/action, deterministic severity | RawRecord + deterministic normalizer. | Aegis TimelineEvent/EvidenceRecord; CIOS Event; new canonical model, old views dual-read. |
| Indicator | Org-scoped normalized observable identity. | Identity fields immutable except audited canonical merge; counts/times derived from occurrences. Verdict is not a fact field. | id, org_id, type, normalized_value, first_seen_at/last_seen_at (derived) | display value, source-independent enrichment, tags | IndicatorOccurrence aggregation; exact occurrences are source of truth. | Aegis IOC; CIOS Indicator; merge, preserve Aegis IOC identity through mapping. |
| IndicatorOccurrence | Observation of Indicator in an Investigation source. | Immutable. | id, org_id, investigation_id, indicator_id, evidence_id, raw_record_id, extractor name/version | event_id, observed_at, source field locator | RawRecord/Event deterministic extraction. | No equivalent beyond Aegis IOC counters; CIOS occurrence; new table. |
| Entity | Investigation-scoped canonical actor/object identity in Phase 1. | Canonical value/type immutable except audited reconciliation; attributes are deterministic/attributed observations, not AI claims. | id, org_id, investigation_id, type, canonical_value, display_name | first/last seen, attributes summary | EntityObservation aggregation. | Aegis assets/graph node partial equivalent; CIOS Entity; new table. |
| EntityObservation | Observation of Entity in evidence source. | Immutable. | id, org_id, investigation_id, entity_id, evidence_id, raw_record_id, extractor name/version | event_id, observed_at, source locator | RawRecord/Event deterministic extraction. | No Aegis equivalent; CIOS observation; new table. |
| EntityRelationship | Factual graph edge between entities, Investigation scoped. | Immutable observation; aggregate views may calculate count. New evidence creates new link/observation, not rewritten edge. | id, org_id, investigation_id, source_entity_id, target_entity_id, relationship_type, derivation rule/version | evidence_id, raw_record_id, event_id, source/target observation IDs, observed_at | Event and/or EntityObservation with supporting source IDs. | Aegis ephemeral GraphEdge; CIOS EntityRelationship; canonical factual graph, no duplicate graph table. |
| AttackTechnique | Versioned ATT&CK reference catalog, global or org-visible reference scope. | Dataset import/version creates records/supersession; not a case assertion. | id, external_id, name, tactic, dataset_version | description, revoked/deprecated metadata | ATT&CK dataset import/version. | Aegis MITRE strings; CIOS catalog; retain catalog only. |

## Inferences and verdicts

| Model | Purpose / ownership | Lifecycle and mutability | Required fields | Optional fields | Source of truth / provenance | Legacy / donor / migration policy |
|---|---|---|---|---|---|---|
| AIAnalysis | Org/Investigation-scoped, immutable model-run envelope. | `QUEUED/RUNNING/COMPLETED/FAILED`; completed output append-only. Review status is separate or additive, never output rewrite. | id, org_id, investigation_id, provider, model, model/version, generated_at, input snapshot/version/hash, status | prompt/template version, token/cost data, error, confidence/calibration | Recorded factual support links; provider response validated against schema. | Aegis mutable fields; no CIOS donor; replace write path. |
| Hypothesis | Candidate explanation owned by AIAnalysis. | Generated content immutable; `UNREVIEWED/CONFIRMED/REJECTED` review transition audited. | id, ai_analysis_id, ordinal, statement, confidence, review status | likelihood, impact, analyst review metadata | AIAnalysis + factual support/contradiction links. | Aegis alternative hypotheses JSON; replace. |
| Recommendation | Proposed action owned by AIAnalysis. | Immutable generated proposal; analyst decision is a new decision/review record. | id, ai_analysis_id, ordinal, title, description, confidence, review status | business impact, side effects, rollback, ETA, approval tier | AIAnalysis + factual support links. | Aegis RecommendedAction; replace without deleting history. |
| ReasoningStep | Ordered explanatory step owned by AIAnalysis. | Immutable content; reviewed status/audit separate. | id, ai_analysis_id, ordinal, statement, step type | confidence, supports/contradicts references | AIAnalysis support links, ordered processing trace. | Aegis reasoning_chain JSON; replace. |
| Finding | Analyst-confirmed conclusion, Investigation scoped. | Draft/confirmed/rejected/superseded; any correction creates version/audit history. | id, org_id, investigation_id, title, description, severity, status, confirmed_by, confirmed_at, rationale | confidence assessment, analyst notes, references to AI analysis/proposals | Analyst verdict with factual and reviewed-inference links. | No Aegis dedicated model; CIOS Finding; new canonical verdict. |
| ReportSnapshot | Immutable generated artifact, Investigation scoped. | Generated then retained; regenerate creates new snapshot. | id, org_id, investigation_id, format, content or artifact pointer/hash, generated_at, generated_by, data cutoff/snapshot ID | template/version, report type, signed/export metadata | Declared factual + verdict + optionally reviewed-inference selection. | Aegis on-demand report; CIOS snapshot; merge renderer with persistence. |
| AuditEvent | Append-only governance event, org scoped; Investigation scoped when applicable. | Immutable; no update/delete through application behavior. | id, org_id, actor type/id, action, target type/id, occurred_at | investigation_id, rationale, metadata, correlation ID | Application/security/analyst action log. | No Aegis case audit; CIOS AuditLog; new table. |

## Review contract shared by inference-derived artifacts

`Hypothesis`, `Recommendation`, AI-proposed technique mapping, and an
AIAnalysis itself expose `UNREVIEWED`, `CONFIRMED`, or `REJECTED`. A transition
requires reviewer user ID, reviewed timestamp, rationale, and AuditEvent. Only
a confirmed inference can be cited by a Finding, and even then the Finding must
carry its own analyst confirmation.
