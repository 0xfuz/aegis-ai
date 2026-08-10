# S1 Attack Surface Inventory

| Surface | Trust level | Control/result |
| --- | --- | --- |
| `/api/v1/health`, `/auth/login`, `/auth/refresh` | Public | Expected public routes; health exposes only service status. |
| Legacy `/ingest/webhook/{connector_id}` | Connector | Existing secret authentication; legacy behavior intentionally remains separate. |
| `/ingest/alerts/v1/{connector_id}/{source}` | Connector | Secret authentication, path/body source match, JSON/schema limits, RawEvent provenance; body is buffered before cap (S1-003). |
| Investigation/evidence/FACT/AIIE/Finding/MITRE/audit | Authenticated user | Route dependencies and scoped service/repository queries reviewed; controlled cross-org tests pass. |
| Connector/admin/user management | Privileged user | Permission-guarded. |
| Evidence storage/download | Authenticated user | Opaque DB storage key resolved only after org/investigation authorization; filename path components rejected on ingest. |
| Frontend | Browser | No `dangerouslySetInnerHTML`/DOM `innerHTML` use found; React escapes displayed text. |
| Ollama | Backend provider | Model output passes strict structured validation; it cannot directly approve Findings/MITRE or promote clusters. |
| Compose deployment | Operator | Development defaults expose services and seed a predictable account (S1-001/S1-002). |
