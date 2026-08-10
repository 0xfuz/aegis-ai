# API Dependency Inventory

All paths below are prefixed `/api/v1`. Authentication marked **JWT** uses a
Bearer access token; permissions are checked from the authenticated principal.
The public ingest path uses the connector secret header instead.

## Identity endpoints

| Endpoint | Request → response | Consumers | Tables | Auth / side effects | Classification |
|---|---|---|---|---|---|
| `POST /auth/login` | email/password → access + refresh token | Login page/AuthProvider | users, roles, permissions | Public; verifies password | KEEP |
| `POST /auth/refresh` | refresh token → rotated token pair | API client automatic retry | users, roles, permissions, revoked_tokens | Public; revokes presented JTI | KEEP |
| `POST /auth/logout` | refresh token → 204 | AuthProvider | revoked_tokens | JWT not required; revokes refresh JTI | KEEP |
| `GET /auth/me` | none → current user/role/permissions | AuthProvider | users, roles, permissions | JWT | KEEP |
| `GET /users` | none → org users | User-management page | users, roles, permissions | JWT; admin or CISO | KEEP |
| `POST /users` | email/full name/role → user | User-management page | users, roles | JWT admin; creates temp-password user | KEEP |
| `PATCH /users/{id}/role` | role name → user | No current frontend caller | users, roles | JWT admin; updates role | KEEP |
| `POST /users/{id}/deactivate` | none → user | No current frontend caller | users | JWT admin; changes active flag | KEEP |
| `POST /users/{id}/reactivate` | none → user | No current frontend caller | users | JWT admin; changes active flag | KEEP |

## Investigation and IOC endpoints

| Endpoint | Request → response | Consumers | Tables | Auth / side effects | Classification |
|---|---|---|---|---|---|
| `GET /investigations` | status/limit/offset → summaries | Dashboard, investigations page | investigations | `investigation:read` | KEEP with compatibility projection |
| `GET /investigations/dashboard-summary` | none → counts/average FP probability | Dashboard, sidebar | investigations | `investigation:read`; read-only | REFACTOR; average depends on legacy AI field |
| `GET /investigations/{id}` | id → detail including timeline/evidence/AI/actions | Workspace | investigations and all child tables | `investigation:read` | REFACTOR; central legacy aggregate response |
| `PATCH /investigations/{id}/status` | `{status}` → detail | Workspace | investigations | `investigation:write`; status mutation | KEEP / adapt to canonical case state |
| `POST /investigations/{id}/notes` | `{body}` → detail | Workspace | investigation_notes | `investigation:write`; inserts note | KEEP / return narrower resource later |
| `POST /investigations/actions/{id}/approve` | none → detail | Workspace | recommended_actions | `investigation:approve_remediation`; updates action | REPLACE with analyst decision on recommendation version |
| `POST /investigations/actions/{id}/dismiss` | none → detail | Workspace | recommended_actions | same; updates action | REPLACE |
| `GET /investigations/iocs` | verdict/watched filters → IOC summaries | Threat-intel page | iocs | `threat_intel:read` | REFACTOR; retain org indicator identity |
| `GET /investigations/iocs/watchlist` | none → IOC summaries | Threat-intel page | iocs | `threat_intel:read` | KEEP / relocate conceptually if desired |
| `GET /investigations/iocs/lookup` | type/value/exclude-case → IOC details/relations | IOC overlay | iocs, investigations, evidence records, assets | `threat_intel:read` | REFACTOR; replace loose related-evidence lookup with occurrences |
| `POST /investigations/iocs/watch` | type/value/watched → IOC detail | IOC overlay | iocs | `threat_intel:write`; updates/creates watch entry | KEEP / audit required |
| `POST /investigations/iocs/verdict` | type/value/verdict → IOC detail | No current frontend caller | iocs | `threat_intel:write`; changes verdict | REFACTOR; preserve analyst actor/audit |

## Connectors, assets, graph, AI, and reports

| Endpoint | Request → response | Consumers | Tables | Auth / side effects | Classification |
|---|---|---|---|---|---|
| `GET /connectors` | none → connector list | Settings page | connectors | `settings:manage_connectors` | KEEP |
| `POST /connectors/webhook` | `{name}` → connector + one-time secret/URL | Settings page | connectors | same; creates connector/secret hash | KEEP |
| `DELETE /connectors/{id}` | none → 204 | Settings page | connectors, raw events cascade | same; deletes connector and raw events | REFACTOR; deletion/retention policy must precede evidence pipeline |
| `POST /ingest/webhook/{id}` | title/severity/description/indicators + `X-Ingest-Secret` → investigation ID | External system | connectors, raw_events, investigations, evidence, iocs, assets, timeline | Connector secret; synchronous multi-table create | REFACTOR; preserve endpoint contract, replace writes with intake/fact workflow |
| `GET /assets` | none → assets | Assets page | assets | `investigation:read` | KEEP |
| `GET /assets/{id}` | id → asset plus related cases | Assets page detail selection | assets, investigations | `investigation:read` | KEEP / relationship query adapts |
| `PATCH /assets/{id}` | asset fields → asset | No current frontend caller | assets | `investigation:write`; updates asset | KEEP |
| `GET /investigations/{id}/attack-graph` | id → graph nodes/edges | Investigation graph page | investigations, timeline/evidence/evidence records, iocs, assets | `attack_graph:read`; derived read | REFACTOR; source factual edges from relationships |
| `POST /investigations/{id}/analyze` | no body → full investigation detail | Workspace Analyze control | investigations, recommended_actions | `investigation:write`; LLM call, overwrites AI fields, deletes/recreates actions | REPLACE; create immutable analysis run instead |
| `GET /investigations/{id}/report` | type/format → Markdown/PDF attachment | Workspace download control | investigations and children (read only) | current principal + report permission | REFACTOR; persist immutable report snapshot |

## Endpoint migration policy

1. Do not remove or alter existing routes during initial fact-model deployment.
2. Add new canonical resource endpoints only after fact tables and service
   contracts are tested.
3. Keep current aggregate Investigation response as a compatibility projection
   while the workspace is migrated incrementally.
4. Treat public webhook ingestion as an externally versioned contract. New
   internal pipeline stages must be hidden behind its existing request contract.
5. The first deliberately breaking semantic change must be `/analyze`: replace
   mutation response with an analysis-run resource only after the UI reads it.
