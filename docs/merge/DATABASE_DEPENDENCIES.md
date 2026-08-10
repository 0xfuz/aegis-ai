# Database Dependencies

## Global conventions

All IDs are PostgreSQL UUIDs. `TimestampMixin` adds `created_at` and
`updated_at`; `OrgScopedMixin` adds indexed `org_id`. Tenant filtering is
application-enforced, not PostgreSQL RLS. Fields below list inherited columns
in parentheses. Endpoint/page references identify direct current consumers.

## Identity tables

| Model / table | Columns, keys, indexes, relationships | Endpoint/page consumers | Classification and migration difficulty |
|---|---|---|---|
| `Organization` / `organizations` | `id`, `name`, `slug`, timestamps. Unique/index: `slug`. Relationship: `users`. | Indirectly every authenticated endpoint through JWT `org_id`; no direct UI route. | KEEP; Low schema difficulty, **critical identity impact**. |
| `Permission` / `permissions` | `id`, `code`, `description`. Unique/index: `code`. M2M with `Role` via `role_permissions`. | Auth JWT claims, user API, frontend permission checks. | KEEP; Low change difficulty, high authorization compatibility impact. |
| `Role` / `roles` | `id`, `name`, `description`. Unique/index: `name`. Relationships: permissions, users. | `/auth/me`, `/users/*`; sidebar/admin UI. | KEEP; Low schema difficulty, high behavioral risk. |
| `role_permissions` | Composite PK/FKs: `role_id → roles`, `permission_id → permissions`, both cascade delete. | Identity services/JWT generation. | KEEP; Low difficulty. |
| `User` / `users` | `id`, `org_id → organizations` cascade, `role_id → roles`, `email`, `hashed_password`, `full_name`, `is_active`, timestamps. Unique `(org_id,email)`; indexes `org_id,email`. Relationships organization, role. Referenced by `Investigation.assignee_id` and `Note.author_id`. | `/auth/*`, `/users/*`, all frontend authenticated state. | KEEP; Medium due to foreign-key fan-out. |
| `RevokedToken` / `revoked_tokens` | PK `jti`; `revoked_at`, `expires_at`. | `/auth/refresh`, `/auth/logout`. | KEEP; Low difficulty. |

## Investigation and intelligence tables

| Model / table | Columns, keys, indexes, relationships | Endpoint/page consumers | Classification and migration difficulty |
|---|---|---|---|
| `Investigation` / `investigations` | `id`, `(org_id)`, timestamps; `title`, `source`, severity/status enums, `assignee_id → users`; mutable AI fields: confidence, root_cause, `mitre_techniques[]`, blast-radius, false-positive probability, JSONB attack chain/hypotheses/reasoning. Relationships timeline, evidence, evidence records, notes, actions. | All investigation APIs; connectors, AI, graph, reporting; dashboard/list/workspace/sidebar/assets/IOC UI. | REFACTOR; **Very high**. Preserve IDs and core lifecycle while extracting inference fields. |
| `TimelineEvent` / `investigation_timeline_events` | `id`; indexed `investigation_id → investigations` cascade; occurred time, description, optional severity, MITRE string, source, asset, actor. Relationship investigation. | Investigation detail, graph, reporting, workspace timeline. | REPLACE as timeline source; High. Map only evidence-backed records to canonical events. |
| `Evidence` / `investigation_evidence` | `id`; indexed `investigation_id → investigations` cascade; type enum (`ip/hash/domain/url/asset`), value. Relationship investigation. | Detail API, workspace IOC chips, connector ingest, graph, reporting. | DEPRECATE/REPLACE; High API fan-out. It is an indicator reference, not immutable evidence. |
| `EvidenceRecord` / `investigation_evidence_records` | `id`; indexed `investigation_id → investigations`; indexed `category`; occurred time, summary, JSONB details. Relationship investigation. | Detail API, EvidenceExplorer, graph. | REPLACE; High. No raw record, file, hash, parse-run, or event FK provenance. |
| `IOC` / `iocs` | `id`, `(org_id)`, timestamps; type, value, tags array, confidence, JSONB enrichment, verdict, provenance, watch state/timestamp, first/last seen, sighting count. Unique `(org_id,type,value)`; index value. No ORM relationship to case evidence. | IOC APIs; threat-intel page/overlay; connector ingestion; graph lookup; asset detail logic. | REFACTOR; Medium/High. Retain org identity but add occurrence/provenance join model. |
| `Note` / `investigation_notes` | `id`, timestamps; indexed `investigation_id → investigations` cascade; `author_id → users`; body. Relationship investigation. | Detail API, workspace, reports. | KEEP/REFACTOR; Medium due to user and investigation FKs; add audit linkage later. |
| `RecommendedAction` / `investigation_recommended_actions` | `id`; indexed `investigation_id → investigations` cascade; title/description, action status, confidence, impact, side effects, rollback, ETA, approval tier. Relationship investigation. | Detail API, workspace decisions, AI, reports/graph. | REPLACE; High. Current AI deletes rows on re-analysis, losing decision history. |

## Connector and asset tables

| Model / table | Columns, keys, indexes, relationships | Endpoint/page consumers | Classification and migration difficulty |
|---|---|---|---|
| `Connector` / `connectors` | `id`, `(org_id)`, timestamps; name, type, status, secret hash, last event time, active flag. Relationship raw events. | `/connectors*`; settings page; webhook ingest. | KEEP/REFACTOR; Medium. Preserve secrets/IDs and reroute processing. |
| `RawEvent` / `connector_raw_events` | `id`; indexed `connector_id → connectors` cascade; received time, JSONB payload, nullable `investigation_id → investigations` set-null. Relationship connector. | Ingest endpoint indirectly; no direct frontend presentation. | REFACTOR; High semantic overlap. It is connector payload, not CIOS RawRecord; retain as intake/raw alert payload or rename conceptually. |
| `Asset` / `assets` | `id`, `(org_id)`, timestamps; name, type, OS, owner, department, criticality/health/risk; JSONB lists/maps; AI risk summary; last seen. Unique `(org_id,name)`; index name. | `/assets*`; assets page; graph asset lookup; connector mention; IOC details. | KEEP/REFACTOR; Medium. Preserve registry and remove/segregate `ai_risk_summary` inference. |

## Table-to-endpoint dependency map

| Tables | Endpoints |
|---|---|
| organizations/users/roles/permissions/revoked_tokens | `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/me`, `/users*` |
| investigations + child collections | `/investigations`, dashboard summary, detail, status, notes, action decisions, analyze, report, attack graph |
| iocs (+ loose investigation/evidence queries) | IOC list/watchlist/lookup/watch/verdict; graph and connector side effects |
| connectors/raw events | connector list/create/delete; public webhook ingest |
| assets + investigations | assets list/detail/update; graph and IOC related-asset lookup |

## Migration constraints

1. Never change, recompute, or treat an existing source hash/payload as AI output.
2. Preserve `organizations`, `users`, roles, and all existing UUIDs before touching
   tenant-owned investigation data.
3. Add canonical provenance tables beside—not in place of—the current case tables.
4. Backfill only when lineage is demonstrable. Existing `EvidenceRecord` and AI
   fields lacking raw provenance must remain labelled legacy context/inference.
5. Cut over reads using compatibility projections; delete legacy tables only after
   endpoint and report consumers are removed and migration reconciliation passes.
