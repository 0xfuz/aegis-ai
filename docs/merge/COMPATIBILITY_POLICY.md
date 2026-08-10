# Compatibility Policy

## Guarantee

During introduction of canonical models, existing Aegis-AI API routes, response
shapes, deep links, authentication, frontend pages, and legacy Investigation
fields continue to work. New tables are additive. No Phase-1 work deletes,
renames, or changes the semantics of existing tables/fields/endpoints.

## Legacy-field treatment

| Legacy Aegis field/table | Early-phase policy | Target treatment | Removal condition |
|---|---|---|---|
| `investigations.id/org_id/title/source/severity/status/assignee_id` | Canonical container; normal writes remain | KEEP | None planned |
| `confidence`, `root_cause`, `blast_radius_summary`, `false_positive_probability` | Compatibility read-only projection for future canonical AI output; current legacy writer retained unchanged until cutover | Deprecated write path after new AI endpoint/read model | No API/UI/report/graph consumer and historical export migration approved |
| `mitre_techniques` array | Temporary dual-read with catalog/proposal/confirmed mapping projection | Deprecated write path | All MITRE consumers use catalog relationships |
| `attack_chain`, `alternative_hypotheses`, `reasoning_chain` JSONB | Compatibility read-only projection; temporary dual-read | Deprecated write path | AI panel/graph/report use AIAnalysis child records |
| `investigation_recommended_actions` | Continue current behavior before cutover | Temporary dual-read to versioned Recommendations + review decisions | Decisions/history migrated and workspace no longer writes legacy rows |
| `investigation_timeline_events` | Current timeline remains readable | Temporary dual-read beside canonical Event timeline | All timeline callers support Event provenance and historic records are classified |
| `investigation_evidence` | Continue IOC-chip rendering | Compatibility read-only projection to Indicators when possible | Frontend/API no longer treats it as evidence |
| `investigation_evidence_records` | Continue EvidenceExplorer response | Temporary dual-read with canonical Events | Historical provenance reconciliation complete |
| `iocs` | Continue org-wide intelligence APIs | Dual-read with Indicator occurrences; preserve Aegis IDs via mapping | IOC API migration and consumer cutover completed |
| `connector_raw_events` | Retain external intake history and webhook behavior | Compatibility intake record; distinct from RawRecord | Retention/import decision, never automatic deletion |
| on-demand reporting | Preserve download endpoint and formats | Dual-read current model then ReportSnapshot | Snapshot reports verified and old endpoint is backed by snapshot projection |

## API and UI rules

1. Existing `/api/v1` route paths and response fields are frozen through Phase 1.
2. New canonical APIs are additive and versioned under the existing API prefix
   only after approved design; no endpoint silently changes fact/inference
   semantics.
3. Existing Investigation detail remains a compatibility aggregate. It may gain
   additive fields only when clients tolerate them.
4. Existing Next.js pages and `/investigations/[id]` deep links remain active.
   New workspace routes are introduced alongside them, then redirected only
   after approved UI migration.
5. The public webhook request/response and secret header remain unchanged until
   sender compatibility tests establish a versioned replacement.
6. Legacy values without factual provenance are presented as “legacy context”
   or “legacy AI assessment,” never silently upgraded to FACTS.

## Dual-read precedence

When a view has both canonical and legacy data:

1. Canonical fact with explicit provenance is authoritative for evidence,
   timeline, indicator, entity, and relationship displays.
2. Canonical reviewed verdict is authoritative for conclusions/MITRE mappings.
3. Canonical immutable AIAnalysis is authoritative for new AI output.
4. Legacy values remain visible only as clearly labelled compatibility context
   until their consumers are migrated or data reconciliation says otherwise.
