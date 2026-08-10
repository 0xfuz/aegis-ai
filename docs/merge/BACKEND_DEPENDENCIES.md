# Backend Dependency Analysis

## Dependency direction

```text
API routers → domain services → repositories/models → shared database
                       ↓
                identity dependencies/RBAC

attack_graph → investigation service + IOC repository + asset repository
reporting    → investigation service
ai_reasoning → investigation repository + LLM provider
connectors   → investigation + IOC + asset services/repositories
```

The documented module rule is not fully preserved by current implementation:
connectors and AI import Investigation ORM models directly. Migration work must
first introduce public application/service contracts, then remove these direct
cross-module model writes.

## Module implementation inventory

### identity — KEEP

- **Models/repository:** Organization, User, Role, Permission, RevokedToken and
  role-permission association; repositories retrieve users/roles/org scope.
- **Services:** `AuthService` authenticates, rotates refresh tokens and logs out;
  `UserService` lists/invites/changes role/deactivates/reactivates.
- **API dependencies:** `get_current_principal`, `require_permission`, and
  `require_any_role` parse JWT permissions on every protected route.
- **Consumers:** every protected module; Next.js `AuthProvider`, login, dashboard
  group layout, sidebar/topbar, user management.
- **Risk:** unchanged identity is the prerequisite for every safe migration.

### investigations — REFACTOR

- **Models:** Investigation, TimelineEvent, Evidence, IOC, EvidenceRecord, Note,
  RecommendedAction.
- **Services:** `InvestigationService` list/detail/dashboard/status/note/action
  decisions; `IOCService` list, lookup, watch, verdict. Repositories implement
  org scoping and related investigations/assets/evidence lookup.
- **Dependencies:** identity auth; assets and connector logic query it; AI and
  graph consume its ORM shape; reporting serializes it.
- **Risk:** it is both the core user contract and an overloaded data container.
  Do not alter it first. Introduce canonical fact/inference models and adapters.

### connectors — REFACTOR

- **Models:** Connector and RawEvent.
- **Services:** `ConnectorService` manages webhook connectors; `IngestService`
  authenticates connector secret and synchronously writes RawEvent, Investigation,
  Evidence rows, IOC sightings, Assets and TimelineEvent rows.
- **Dependencies:** security hashing, settings public base URL, Investigation,
  IOC, Asset repositories.
- **Consumers:** settings page and external integrations.
- **Risk:** public ingest compatibility and transaction side effects. Keep the
  webhook envelope/secret contract while replacing the downstream write path.

### assets — KEEP/REFACTOR

- **Models:** Asset.
- **Services:** list/detail/update, record asset mentions, investigation lookup.
- **Dependencies:** identity/RBAC and investigation repository for relations.
- **Consumers:** assets page, attack graph, connectors, IOC detail.
- **Risk:** medium. Asset identity is valuable; inference field `ai_risk_summary`
  must not remain a silently authoritative fact.

### attack_graph — REFACTOR

- **Models:** no persisted model; `AttackGraph`, `GraphNode`, `GraphEdge` DTOs.
- **Services:** graph builder creates nodes/edges from investigation timeline,
  evidence, evidence records, AI attack chain/MITRE/hypotheses/findings and
  asset/IOC enrichments; service loads current data.
- **Dependencies:** InvestigationService, IOCRepository, AssetRepository.
- **Consumers:** graph endpoint, graph page, React Flow/Dagre UI and pytest tests.
- **Risk:** high. Preserve API shape and renderer but make factual relationships
  read from canonical `EntityRelationship` and make AI overlay explicitly distinct.

### ai_reasoning — REPLACE

- **Models:** none of its own; writes Investigation and RecommendedAction.
- **Services:** provider selection, prompt construction, strict Pydantic JSON
  validation, direct mutable write and action replacement.
- **Dependencies:** LLM provider configuration, InvestigationRepository, identity
  write permission.
- **Consumers:** workspace Analyze action, reasoning panel, graph and reports.
- **Risk:** critical. It violates the approved trust model and must be isolated
  into immutable analysis runs before any evidence migration reaches production.

### reporting — REFACTOR

- **Models:** none; on-demand output only.
- **Services:** `ReportService` builds Markdown/PDF with ReportLab.
- **Dependencies:** InvestigationService, current mutable case/AI fields and
  current user permissions.
- **Consumers:** workspace report-download controls.
- **Risk:** medium/high. Snapshot data cutoffs and analyst verdicts are absent;
  preserve rendering capability but change input projection after stable facts exist.

## Shared technical dependencies

| Dependency | Current users | Treatment |
|---|---|---|
| PostgreSQL / SQLAlchemy session | all repositories/services | KEEP |
| Pydantic schemas | all API routers, AI output validation | KEEP |
| FastAPI dependency injection | all protected endpoints | KEEP |
| Redis/Celery config | compose/config only | DEFER |
| `httpx` | LLM provider adapters | KEEP |
| ReportLab | reporting service | KEEP |
| bcrypt/JWT | user auth and connector secret auth | KEEP |

## Safe backend sequencing rules

1. Identity/shared kernel are frozen during initial provenance work.
2. Add ingestion and fact services with no dependency on AI output.
3. Route connector data to intake/fact services through an adapter; do not alter
   the external webhook endpoint until its replacement is verified.
4. Build a graph projection from facts before retiring old graph derivation.
5. Replace AI writes only after the frontend/reporting can read immutable analysis
   results and analyst verdicts.
