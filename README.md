# Aegis AI — Phase 1 (Foundations)

AI-Powered Security Decision Engine. This phase ships the monorepo scaffolding,
database schema, authentication, and RBAC that every later module (Investigations,
AI Reasoning, Attack Graph, Reporting, …) builds on top of.

See `AEGIS_AI_ARCHITECTURE.md` and `AEGIS_AI_UIUX_SPEC.md` (shared earlier in this
build) for the full system design this scaffolding implements.

## What's in Phase 1

- **Monorepo**: `backend/` (FastAPI, clean architecture) + `frontend/` (Next.js/TS)
- **Database schema**: organizations, users, roles, permissions, role-permission
  mapping, revoked-token list — via Alembic migration `0001`
- **Authentication**: JWT access (30 min) + refresh (7 day, rotated on use,
  individually revocable) token pairs
- **RBAC**: five baseline roles (`soc_analyst`, `incident_responder`,
  `security_architect`, `ciso`, `admin`), each mapped to a fixed permission set
  seeded on startup
- **Backend foundation**: DI-based FastAPI app, repository + service layers,
  centralized exception handling, auto-generated OpenAPI docs
- **Frontend foundation**: Next.js App Router, Tailwind theme matching the design
  system, auth context with silent token refresh, sidebar/topbar shell, login flow

## Quick start

```bash
cp .env.example .env
# edit .env if you want non-default ports/credentials — the defaults work as-is

docker compose up --build
```

- Frontend: http://localhost:3000 (redirects to `/login`)
- Backend API docs: http://localhost:8000/api/docs
- Demo login: `admin@aegis.demo` / `ChangeMe123!` (seeded automatically on first boot)

The backend entrypoint waits for Postgres, runs migrations, seeds baseline
roles/permissions/demo org/admin user, then starts the API — `docker compose up`
alone gets you to a working login on a clean checkout.

## Repo layout

```
aegis-ai/
  backend/
    app/
      core/            # config, JWT security primitives, logging
      shared/           # DB session, declarative Base + mixins, exception hierarchy
      modules/
        identity/       # auth, users, roles, permissions — the only module built so far
          domain/        # service layer (business logic)
          infrastructure/# SQLAlchemy models + repositories
          api/            # FastAPI router, schemas, RBAC dependencies
      seed/             # idempotent baseline data seeding
    alembic/            # migrations
    tests/              # pytest — unit (security) + integration (auth API)
  frontend/
    app/
      login/
      (dashboard)/      # authenticated route group — sidebar + topbar shell
    components/
      ui/               # Button, Input, Card primitives
      layout/           # Sidebar, Topbar
    lib/
      api-client.ts     # fetch wrapper with silent 401 → refresh → retry
      auth-context.tsx  # login/logout/current-user React context
  docker-compose.yml
  .env.example
```

Every later module (`investigations`, `ai_reasoning`, `attack_graph`, `reporting`, …)
follows the exact same `domain/infrastructure/api` shape as `identity` — that
consistency is what the architecture doc means by "every module must be
independent."

## Design decisions worth knowing about

- **Token strategy**: access tokens are short-lived and carry the caller's
  flattened permission list, so most requests authorize with zero DB round
  trips. Refresh tokens are rotated on every use and individually revocable via
  the `revoked_tokens` table (logout invalidates that specific session, not
  every session).
- **RBAC is enforced at the API layer**, not just hidden in the UI — every
  sensitive backend endpoint requires a specific permission or role via FastAPI
  `Depends`, so hiding a button client-side is a UX nicety, not a security
  boundary.
- **Multi-tenancy** is `org_id`-scoped at the application layer for now
  (every repository method takes/filters by `org_id`). Postgres row-level
  security policies are a documented hardening step once the schema has
  settled across more modules, not a Phase 1 requirement.
- **Frontend auth storage**: tokens live in `localStorage`, not cookies, so
  `middleware.ts` is honestly a no-op placeholder — real route protection
  happens client-side via `AuthProvider` once `/auth/me` resolves. If this
  later moves to httpOnly cookie sessions (recommended before a real
  production launch, since httpOnly cookies aren't readable by XSS), that
  file is where server-side verification would go.
- **No connector modules exist yet, by design** — Phase 1 has nothing for
  Sentinel/Splunk/Elastic/CrowdStrike/cloud APIs to plug into. That's correct:
  those arrive as the `connectors` module in the MVP build, and per the
  architecture doc, each will be a swappable adapter behind a common interface.

## Running tests

```bash
docker compose exec backend pytest
```

## What's next

Per the agreed MVP scope: Investigations module (the core case object) and its
dashboard/workspace UI, using mock security event data — no external SIEM/EDR/cloud
integrations until v2.
