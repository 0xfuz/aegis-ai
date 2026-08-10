# Aegis AI — System Architecture
### AI-Powered Security Decision Engine
Version 0.1 (Architecture Baseline) — Prepared for phased, module-by-module implementation

---

## 1. Product Framing

Aegis AI is a **decision layer**, not a data collector. It ingests findings that already exist in Sentinel/Splunk/Elastic/CrowdStrike/etc., correlates and enriches them, and produces a structured judgment: root cause, blast radius, severity, confidence, and a ranked remediation plan. The UI and API are built around **one core object**: the `Investigation` (formerly "alert"), which is a living case file the AI keeps enriching as new evidence arrives.

Everything below is designed so each module can be built, tested, and shipped independently — no module blocks another.

---

## 2. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                          CLIENT (Next.js 14 App Router)              │
│  Dashboard · Attack Graph · Investigation Workspace · Reports · Admin │
└───────────────────────────────┬────────────────────────────────────-─┘
                                 │ HTTPS / WSS (real-time updates)
┌───────────────────────────────▼──────────────────────────────────────┐
│                          API GATEWAY (FastAPI)                       │
│   AuthN/AuthZ (JWT+OAuth2) · Rate limiting · Request validation       │
│   Routes: /investigations /assets /graph /rules /reports /ti /auth   │
└───────┬───────────────┬────────────────┬────────────────┬────────────┘
        │               │                │                │
┌───────▼─────┐ ┌───────▼──────┐ ┌───────▼──────┐ ┌───────▼──────────┐
│  Ingestion  │ │ Correlation  │ │  AI Reasoning│ │  Case Management  │
│  Service    │ │  Engine      │ │  Service     │ │  Service          │
│ (connectors)│ │ (dedupe,     │ │ (LangGraph   │ │ (investigations,  │
│             │ │  graph build)│ │  agents, RAG)│ │  notes, IoCs)     │
└───────┬─────┘ └───────┬──────┘ └───────┬──────┘ └───────┬───────────┘
        │               │                │                │
        └───────┬───────┴────────┬───────┴────────┬───────┘
                 │                │                │
         ┌───────▼─────┐  ┌───────▼──────┐  ┌──────▼───────┐
         │  PostgreSQL │  │  Redis        │  │ Vector DB    │
         │  (system of │  │ (cache, pub/  │  │ (pgvector or │
         │  record)    │  │  sub, celery) │  │  Qdrant)     │
         └─────────────┘  └───────┬──────┘  └──────────────┘
                                  │
                          ┌───────▼──────┐
                          │  RabbitMQ +  │
                          │  Celery      │
                          │  workers     │
                          └──────────────┘
```

**Async-first design**: ingestion, correlation, and AI reasoning are all queue-driven (RabbitMQ + Celery). The API never blocks on an LLM call — the client polls or subscribes via WebSocket for the `Investigation` to move through states: `new → correlating → analyzing → enriched → actioned`.

---

## 3. Domain-Driven Module Map

Each module is a **bounded context** with its own models, repository, service layer, and API router. No module imports another module's internals — only its public service interface (Dependency Injection via FastAPI `Depends`).

| Module | Responsibility | Key Entities |
|---|---|---|
| `identity` | AuthN/AuthZ, users, roles, orgs (multi-tenant) | User, Role, Permission, Org |
| `connectors` | Pull/push adapters for external data sources | Connector, ConnectorRun, RawEvent |
| `assets` | Asset inventory & identity graph nodes | Asset, Identity, CloudResource |
| `correlation` | Dedup, cluster, and link raw events into candidate incidents | Signal, Correlation, GraphEdge |
| `investigations` | Case management, the core `Investigation` object | Investigation, Note, Evidence, IoC |
| `ai_reasoning` | LangGraph agent orchestration, RAG, scoring | AgentRun, Finding, ConfidenceScore |
| `attack_graph` | Graph construction & traversal (blast radius, lateral movement) | GraphNode, GraphEdge, Path |
| `detections` | MITRE mapping, detection rule suggestions | Technique, RuleSuggestion |
| `threat_intel` | IoC enrichment, TI feed ingestion | IoC, TIFeed, Reputation |
| `reporting` | Executive/technical report generation (PDF/MD/JSON) | ReportTemplate, ReportRun |
| `analytics` | Risk heatmaps, KPIs, trend data | Metric, RiskScoreHistory |

### Suggested repo layout (backend)
```
backend/
  app/
    core/               # config, security, logging, DI container
    shared/              # cross-cutting kernel (base repo, base entity, events)
    modules/
      identity/
        domain/          # entities, value objects
        application/     # use-cases / services
        infrastructure/  # SQLAlchemy repos, external clients
        api/             # FastAPI router + schemas
      connectors/
      assets/
      correlation/
      investigations/
      ai_reasoning/
      attack_graph/
      detections/
      threat_intel/
      reporting/
      analytics/
    workers/             # Celery tasks per module
    main.py
  tests/
  alembic/
```

Frontend mirrors this with a feature-based structure (`app/(dashboard)/investigations/...`, `app/(dashboard)/attack-graph/...`), each feature owning its own components, hooks, and API client.

---

## 4. AI Reasoning Pipeline (LangGraph)

The AI reasoning service is a **graph of specialized agents**, not one giant prompt. Each node has a narrow job and structured output (Pydantic schema), which keeps outputs auditable and testable — critical for a security product where analysts need to trust *why* a verdict was reached.

```
        ┌───────────────┐
        │  Triage Agent │  → classifies signal type, pulls relevant context
        └───────┬───────┘
                │
        ┌───────▼────────┐
        │ Context Builder│  → RAG over: asset inventory, past investigations,
        │ (retrieval)    │     TI feeds, detection rules, org policies
        └───────┬────────┘
                │
   ┌────────────┼─────────────┬───────────────┐
┌──▼───┐  ┌─────▼──────┐  ┌────▼─────┐  ┌──────▼──────┐
│ Root │  │ MITRE      │  │ Blast    │  │ False Pos.  │
│ Cause│  │ Mapping    │  │ Radius   │  │ Probability │
│ Agent│  │ Agent      │  │ Agent    │  │ Agent       │
└──┬───┘  └─────┬──────┘  └────┬─────┘  └──────┬──────┘
   └────────────┴──────┬───────┴───────────────┘
                        │
                ┌───────▼────────┐
                │ Severity/Risk  │  → combines sub-agent outputs into
                │ Synthesis Agent│    Severity, Confidence, Business Impact
                └───────┬────────┘
                        │
                ┌───────▼────────┐
                │ Remediation    │  → ranked containment/recovery steps
                │ Planner Agent  │    with operational-risk scoring
                └───────┬────────┘
                        │
                ┌───────▼────────┐
                │ Report Writer  │  → executive + technical summaries
                └────────────────┘
```

Design principles:
- **Every agent returns a typed Pydantic object**, never free text, so the API/UI can render structured fields (severity badges, confidence bars) instead of parsing prose.
- **Model-agnostic**: an `LLMProvider` interface abstracts OpenAI/Claude so either can back any node; some orgs will require Claude-only or OpenAI-only for compliance.
- **RAG sources**: vector DB holds embeddings of past investigations, detection rules, and org runbooks; a separate knowledge graph (assets/identities/edges) is queried directly (graph traversal), not embedded — graphs answer "what's connected to X" far better than vector search.
- **Human-in-the-loop by default**: no agent output auto-executes a containment action; the Remediation Planner proposes, an analyst approves, and only then does an action connector fire (this is a hard product/safety boundary, not just a technical one).
- **Every AgentRun is logged** with the prompt, inputs, model, and output for auditability — SOC tooling must be explainable.

---

## 5. Data Architecture Highlights

- **PostgreSQL** is system of record: investigations, assets, users, correlations, evidence, IoCs. Use `pgvector` extension initially (avoids running a second DB) — migrate to standalone Qdrant only if scale requires it later.
- **Redis**: Celery broker/result backend, session cache, real-time pub/sub for WebSocket investigation updates.
- **RabbitMQ**: durable task queue for connector polling, correlation jobs, and AI reasoning runs (these can be slow/retryable — don't put them on Redis alone).
- **Graph data**: modeled relationally (`GraphNode`, `GraphEdge` tables with adjacency queries) rather than a separate graph DB for v1 — simpler ops, and Postgres recursive CTEs handle blast-radius/path queries fine at moderate scale. A dedicated graph DB (Neo4j) is a documented future upgrade path, not a v1 dependency.
- **Multi-tenancy**: every table carries `org_id`; row-level security policies in Postgres enforce tenant isolation as a second line of defense beyond application-layer checks.

---

## 6. Security & Access Architecture

- **AuthN**: OAuth2 (SSO via Entra ID/Okta) + JWT access/refresh tokens.
- **AuthZ**: RBAC with roles like `soc_analyst`, `incident_responder`, `security_architect`, `ciso`, `admin`; permissions are resource-scoped (`investigation:read`, `investigation:approve_remediation`, `reports:generate_executive`).
- **Action safety**: any connector action that changes external state (isolate host, disable account) requires an explicit approval step and is itself logged as an `Evidence` entry on the investigation.
- **Secrets**: connector credentials stored via a secrets manager (Vault or cloud KMS), never in the app DB in plaintext.
- **Audit log**: every state change on an `Investigation` is append-only (who/what/when), independent of the AI reasoning log.

---

## 7. Deployment

- Docker Compose for local dev (Postgres, Redis, RabbitMQ, API, worker, frontend).
- Kubernetes manifests (or Helm chart) for production: separate deployments for `api`, `celery-worker`, `celery-beat` (scheduled connector polls), `frontend`; HPA on worker pods since AI reasoning load is bursty.
- CI: lint + type-check + test per module independently (this is where the modular structure pays off — a change in `threat_intel` shouldn't require re-testing `reporting`).

---

## 8. Implementation Roadmap (build order)

Per your instruction to build module-by-module rather than everything at once, this is the suggested sequence — each phase produces something runnable and demoable:

1. **Foundations**: `identity` (auth/RBAC/multi-tenant), core DB schema, project scaffolding (Docker Compose, FastAPI skeleton, Next.js skeleton with shadcn/ui theme).
2. **Core case object**: `investigations` module (CRUD, state machine, evidence/notes/IoCs) + basic dashboard + investigation workspace UI. This is the spine everything else attaches to.
3. **Ingestion**: `connectors` module — start with one connector (e.g., a generic webhook/JSON ingest, then Sentinel or Elastic) feeding raw events into `investigations`.
4. **Correlation**: `correlation` module — dedup + clustering of raw signals into candidate investigations.
5. **AI reasoning v1**: LangGraph pipeline with Triage → Root Cause → Severity/Risk agents only (smallest useful slice), wired to one LLM provider.
6. **Attack graph**: `assets` + `attack_graph` modules, React Flow visualization.
7. **MITRE mapping + detection suggestions**, **threat intel enrichment**.
8. **Reporting**: executive/technical report generation.
9. **Analytics/risk heatmaps**, polish, hardening, load testing.

---

### Next step

Tell me which phase to start implementing first — I'd recommend **Phase 1 (Foundations) → Phase 2 (Investigations core)**, since every other module depends on having a real `Investigation` entity and auth system to attach to. I'll build that as working, tested code (not scaffolding) rather than sketching all modules shallowly.
