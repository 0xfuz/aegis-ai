# Production deployment (R2)

R2 supplies a private-by-default Docker Compose topology. It is not a public
Internet ingress solution: place a separately operated, TLS-terminating reverse
proxy in front of the loopback-bound frontend and API ports.

## Secret files

Copy `.env.production.example` outside the repository and replace its
placeholders with identifiers and paths only. Create the PostgreSQL password
and JWT-signing-secret files in the deployment secret manager or a root-readable
host location. They must not be committed, passed as CLI values, or placed in
an environment file.

`docker-compose.production.yml` mounts these files as Docker secrets. The
database consumes `POSTGRES_PASSWORD_FILE`; Aegis reads the corresponding
`DATABASE_PASSWORD_FILE` and `JWT_SECRET_KEY_FILE` only at process start.
Production rejects missing, default, or weak file-backed secrets, enables
neither demo seeding nor debug mode, and has no environment-value fallback.

Connector and Wazuh ingest credentials are per-connector values generated and
stored as hashes by the application. They are not a global backend setting and
therefore are not mounted into API/worker containers. Keep the one-time
plaintext value in the external Wazuh forwarder's own secret-file mechanism;
never put it in this Compose project, environment template, or logs.

## Startup

From the deployment directory, with actual secret-file paths supplied:

```sh
docker compose --env-file /secure/aegis-production.env \
  -f docker-compose.production.yml up -d
```

`migrate` is the only Alembic writer. It runs `alembic upgrade head` once and
must exit successfully before the API, worker, or beat starts. It does not seed
data. PostgreSQL and Redis have health checks; the worker and beat also require
Redis health. The API requires only the completed migration, so it stays
available if Redis, Ollama, or workers are unavailable.

PostgreSQL data and canonical evidence storage use named volumes. Redis is a
non-authoritative broker/cache: it may be rebuilt; queued runs are reconciled
from PostgreSQL. The optional Ollama runtime retains a separate named model
volume and never downloads or changes a model during startup.

## Health and optional subsystem semantics

The frontend exposes unauthenticated `GET /healthz` solely to prove that its
deployed Next runtime is reachable. It returns the bounded response
`{"status":"ok","service":"frontend"}` and does not probe the API, database,
Redis, workers, Ollama, or any user-scoped records. The API liveness endpoint
is likewise independent of Redis, workers, Ollama, Wazuh, and provider
readiness. A healthy API or frontend therefore does not claim that optional
Intelligence execution is available.

Interpret optional Intelligence states separately:

- **Execution disabled**: runs remain persisted but workers must not execute
  them.
- **Dispatch disabled**: no new broker delivery is requested; PostgreSQL stays
  authoritative for queued work.
- **Provider disabled**: execution cannot call a provider.
- **Ollama absent or provider unavailable**: the optional provider path is
  unavailable; this is not an API/frontend deployment failure.
- **Infrastructure unavailable**: Redis/worker unavailability affects
  dispatch/execution, not ordinary API liveness.

The worker health check uses a Celery control ping scoped to the
`intelligence-execution` worker; beat health checks its scheduler process.
Neither is an HTTP-port probe. Production Compose uses `/healthz` for the
frontend container health check.

## Intelligence and bootstrap

Intelligence execution, dispatch, and provider access are all disabled by
default. When an operator enables them deliberately, the trusted configuration
is fixed to `llama3.2:latest` and the exact same allowlist entry. Start the
runtime only with `--profile ollama`; ensure the model already exists in the
preserved volume.

The `admin-bootstrap` service is an operator-only, one-shot profile and never
runs during normal startup. Supply its password via
`BOOTSTRAP_ADMIN_PASSWORD_FILE` and invoke it explicitly with
`--profile bootstrap`. See [PRODUCTION_ADMIN_BOOTSTRAP.md](PRODUCTION_ADMIN_BOOTSTRAP.md)
for the mandatory first-login rotation flow.

No database, Redis, worker, migration, beat, or Ollama port is published to
the host. API and frontend bind to loopback by default. Do not expose either
without an authenticated, TLS-terminating reverse proxy and restricted CORS.
# Restart secret files

Before a host reboot recovery, follow [runtime secret materialization](RUNTIME_SECRET_MATERIALIZATION.md). It restores only protected bind files; it does not generate or replace production credentials.
