# ID Strategy

## Principles

- Use UUID primary keys for every persisted canonical model, matching existing
  Aegis SQLAlchemy conventions.
- Never change existing Aegis primary keys. New foreign keys reference those
  UUIDs directly.
- Do not overload a source-system ID as an Aegis primary key. Store it as a
  namespaced external reference with source system/connector metadata.
- All tenant-owned records carry `org_id`, indexed, even when organization can
  be reached through Investigation. This supports secure direct access checks.

## Scope and identity

| Record | Primary ID / scope | Natural-key or uniqueness rule | Notes |
|---|---|---|---|
| Organization | existing `organizations.id` / global | existing unique slug | Frozen canonical tenant identity |
| Investigation | existing `investigations.id` / org | optional future unique `(org_id, case_number)` | Preserve current ID; case number is display identity only |
| Alert | UUID / org | `(org_id, connector_id, external_id)` when external ID exists; otherwise ingestion idempotency key | Alert links are explicit |
| EvidenceItem | UUID / org+investigation | `(investigation_id, sha256)` initially | Storage key must be opaque and unique globally |
| EvidenceParseRun | UUID / org | `(evidence_id, parser_name, parser_version, run_sequence)` | Multiple same-version retries require sequence or attempt UUID |
| RawRecord | UUID / org | `(parse_run_id, ordinal)` | Ordinal is zero/one-based by documented parser contract, fixed per run |
| Event | UUID / org+investigation | `(raw_record_id, normalizer_name, normalizer_version, ordinal)` if multiple events/record allowed | Never use timestamp as identity |
| Indicator | UUID / org | `(org_id, type, normalized_value)` | Preserve/mapping-link existing Aegis IOC UUID where exact identity matches |
| IndicatorOccurrence | UUID / org+investigation | `(indicator_id, raw_record_id, extractor_name, extractor_version, occurrence_ordinal)` | Allows repeated token in one record |
| Entity | UUID / org+investigation | `(investigation_id, type, canonical_value)` | Phase 1 deliberately case scoped; org-wide reconciliation later |
| EntityObservation | UUID / org+investigation | `(entity_id, raw_record_id, extractor_name, extractor_version, occurrence_ordinal)` | Provenance is not collapsed |
| EntityRelationship | UUID / org+investigation | `(source_entity_id,target_entity_id,relationship_type,derivation_version,source_locator)` | Multiple evidence observations remain distinguishable |
| AIAnalysis | UUID / org+investigation | immutable run ID; optional `(investigation_id,input_snapshot_hash,provider,model,prompt_version,run_sequence)` | Re-analysis always a new UUID |
| Hypothesis/Recommendation/ReasoningStep | UUID / AIAnalysis | `(ai_analysis_id, ordinal)` | Generated content has no global identity |
| Finding/ReportSnapshot/AuditEvent | UUID / org (and Investigation where relevant) | report: `(investigation_id, generated_at, content_hash)`; audit append-only UUID | No reuse after supersession |

## Legacy and donor references

Migration/import mapping must use a dedicated mapping table or immutable
`external_references` pattern with `source_system`, `source_id`,
`target_type`, `target_id`, and import timestamp. CIOS IDs and Aegis legacy IDs
are retained as references; only Aegis current IDs become canonical primary keys.
This avoids key collision, permits idempotent re-runs, and makes data lineage
auditable.
