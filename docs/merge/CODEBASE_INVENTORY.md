# Aegis-AI Codebase Inventory

**Scope:** read-only inventory of the Aegis-AI repository at analysis time. No
application source, schema, API, or deployment configuration was changed.

## Repository shape

| Area | Technology | Classification | Dependency impact |
|---|---|---|---|
| `backend/` | Python, FastAPI, SQLAlchemy 2, Alembic, Pydantic | KEEP | Canonical application/API boundary |
| `frontend/` | Next.js 14 App Router, React 18, TypeScript, Tailwind | KEEP | Canonical Aegis user interface shell |
| Graph UI | React Flow 11 + Dagre | REFACTOR | Reusable renderer; factual graph input must change |
| Database | PostgreSQL 16, JSONB, UUID, arrays | KEEP | System of record; schema evolves only after approval |
| Cache/async config | Redis 7; Celery URLs configured | DEFER | No worker implementation/service currently present |
| Local AI | Ollama service; Gemini/Anthropic/Ollama providers | REFACTOR | Provider abstraction remains; persistence trust model changes |
| Reporting | ReportLab + Markdown generation | REFACTOR | Renderer reusable; reports need persisted snapshots |
| Tests | pytest only: auth, security, attack graph | REFACTOR | Add ingestion/provenance/UI coverage before migration |

## Backend modules

| Module | Purpose and persisted models | Public routes | Direct dependencies | Consumers / what depends on it | Classification / merge risk |
|---|---|---|---|---|---|
| `identity` | Organizations, users, roles, permissions, revoked refresh tokens; JWT/RBAC | `/auth/*`, `/users/*` | core security/config; shared database; SQLAlchemy | Every authenticated route; frontend auth context, dashboard layout, sidebar, login, user management | KEEP — **high blast radius**; do not alter identity IDs, JWT claims, or permission codes during data-foundation work |
| `investigations` | Core case-like object; timeline, evidence chips/records, notes, recommendations, IOC registry | `/investigations/*`, `/investigations/iocs/*` | identity dependencies; investigation/IOC repositories; optional enrichment provider | Dashboard, investigation list/workspace, threat intel, IOC overlay, sidebar, reporting, AI, graph, connectors, assets | REFACTOR — **highest risk**; mutable AI fields and two evidence models are central couplings |
| `connectors` | Connector registration, webhook authentication, raw webhook intake | `/connectors`, `/ingest/webhook/{id}` | identity; investigations; assets; IOC repository; password hashing | Settings UI; external webhook senders; creates investigation/timeline/evidence/IOC records | REFACTOR — **high risk**; must redirect to immutable evidence/alert pipeline without breaking webhook contract |
| `assets` | Org-wide asset registry and incident associations | `/assets/*` | identity; assets repository; investigations repository for related cases | Assets page; graph asset lookup; connector asset sightings; IOC detail | KEEP / REFACTOR — **medium risk**; preserve org-wide asset identity, add evidence observations later |
| `attack_graph` | Pure graph DTO, builder, API adapter | `/investigations/{id}/attack-graph` | identity; investigation service; IOC and asset repositories | Investigation graph page, graph UI components/tests | REFACTOR — **high risk**; retain display contract where possible; replace loose event/evidence derivation with relationship projection |
| `ai_reasoning` | Structured single-pass LLM analysis, provider adapters | `/investigations/{id}/analyze` | identity; investigation repository/models; LLM provider/config | Investigation workspace, AI panel, report service, attack graph | REPLACE — **critical trust risk**; currently writes inference into factual case fields and deletes prior actions |
| `reporting` | On-demand technical/executive Markdown or PDF generation | `/investigations/{id}/report` | identity principal; investigation service; ReportLab | Investigation workspace download action | REFACTOR — **medium/high risk**; output depends on mutable AI fields and is not persisted |

## Cross-cutting backend inventory

| Component | Purpose | Classification | Migration dependency |
|---|---|---|---|
| `app/main.py` | Router registration, CORS, health endpoint | KEEP | Register new routes only after their services are complete |
| `core/config.py` | Database, JWT, CORS, provider configuration | KEEP | Add settings only with a concrete approved service |
| `core/security.py` | bcrypt hashing, JWT creation/verification | KEEP | Connector secret verification and user auth depend on it |
| `shared/base.py` | Declarative base and UUID/timestamp/org mixins | KEEP | All tenant-owned canonical tables must use these mixins |
| `shared/database.py` | SQLAlchemy engine/session dependency | KEEP | All API/service persistence flows depend on it |
| `shared/exceptions.py` | API exception translation | KEEP | New ingestion/AI errors must use this boundary |
| `seed/seed_data.py` | Demo org/roles/users/mock domain data | REFACTOR | Existing seeded AI conclusions must not seed canonical facts as AI after trust migration |
| `workers/` | Empty package only | DEFER | Do not introduce asynchronous execution until an approved analysis-run contract exists |

## Runtime and deployment inventory

`docker-compose.yml` runs PostgreSQL, Redis, Ollama, FastAPI backend, and
Next.js frontend. PostgreSQL is the only persisted application store. Redis
and Celery connection strings are configured but no Celery worker/beat service
or task implementation exists. There is no RabbitMQ, object-store service,
vector database, or evidence-storage volume today.

## High-risk dependency chains

```text
Identity/RBAC
  └─ Investigation service and repositories
      ├─ Connectors ingest directly into Investigation + Timeline + Evidence + IOC
      ├─ AI analysis overwrites Investigation AI fields + replaces RecommendedAction rows
      ├─ Attack graph derives facts and inference nodes from those same fields
      ├─ Reporting renders those same fields on demand
      └─ Frontend Investigation Workspace renders and mutates them
```

This chain is the primary regression boundary. The evidence foundation must be
introduced alongside adapters/read models before the current Investigation
contract is retired.

## Classification summary

- **KEEP:** repository/branding, identity, shared kernel, PostgreSQL,
  FastAPI/Next.js shells, asset registry, graph rendering primitives.
- **REFACTOR:** investigations, connector ingestion, graph builder, reporting,
  frontend workspace, tests.
- **REPLACE:** mutable AI persistence and re-analysis action replacement.
- **REMOVE:** no immediate physical deletion. Mark legacy `Evidence`,
  `EvidenceRecord`, mutable investigation AI fields, and MITRE string arrays
  for later deprecation only after compatibility adapters are removed.
- **DEFER:** worker queue, RAG/vector DB, external connectors beyond webhook,
  real-time updates, and external remediation execution.
