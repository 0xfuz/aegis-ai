# Local AI evaluator guide

This optional path begins only after the [Core-mode quickstart](DEPLOYMENT_QUICKSTART.md)
is healthy. It reuses the existing production Compose contract; it does not
download a model, create demo data, or change an Investigation's authority.

## Scope and prerequisites

- Core API and frontend health checks must already pass, with PostgreSQL and
  Redis state preserved.
- The only trusted provider is local Ollama. The exact configured and
  allowlisted model is `llama3.2:latest`.
- There is no certified RAM, disk, or throughput envelope for local AI. Keep
  the documented 2 GiB `MemAvailable` and 15 GiB free-disk safety floors; they
  are not a capacity guarantee. The optional Ollama model volume needs
  separately planned local capacity.
- The model must already be present in the Compose Ollama volume. **Do not
  download or substitute a model during evaluation.**

Previously certified R4 behavior established bounded local-provider readiness
and analyst-reviewed claim handling. This guide is documentation only; an
owner walkthrough remains required before treating optional AI as available on
a new evaluator host.

## Enable the existing opt-in contract

In the protected external `core.env` created by the Core quickstart, change
only these existing defaults from `false` to `true`:

```text
INTELLIGENCE_EXECUTION_ENABLED=true
INTELLIGENCE_DISPATCH_ENABLED=true
INTELLIGENCE_PROVIDER_ENABLED=true
```

Do not add a provider URL, model name, port, API key, or alternative queue.
Production Compose fixes the provider to `ollama`, the base URL to the private
Compose service, and both the configured and allowed model identity to
`llama3.2:latest`.

Start the runtime in order from the repository root. These commands retain the
existing PostgreSQL, Redis, evidence, and secret volumes:

```sh
docker compose --project-name aegis-core --env-file "$AEGIS_STATE_DIR/core.env" \
  -f docker-compose.production.yml --profile ollama up -d ollama
docker compose --project-name aegis-core --env-file "$AEGIS_STATE_DIR/core.env" \
  -f docker-compose.production.yml --profile ollama exec ollama ollama list
docker compose --project-name aegis-core --env-file "$AEGIS_STATE_DIR/core.env" \
  -f docker-compose.production.yml --profile ollama up -d --build api
docker compose --project-name aegis-core --env-file "$AEGIS_STATE_DIR/core.env" \
  -f docker-compose.production.yml --profile ollama up -d intelligence-worker
docker compose --project-name aegis-core --env-file "$AEGIS_STATE_DIR/core.env" \
  -f docker-compose.production.yml --profile ollama up -d intelligence-beat
docker compose --project-name aegis-core --env-file "$AEGIS_STATE_DIR/core.env" \
  -f docker-compose.production.yml --profile ollama ps \
  ollama api intelligence-worker intelligence-beat
```

`ollama list` is an inventory-only readiness check: confirm that it lists the
exact `llama3.2:latest` identity. It does not print an environment file or a
prompt. The worker must report its existing Celery readiness health check, and
beat must report its existing scheduler-process health check. A healthy
frontend/API does not by itself prove provider readiness.

## One bounded evaluator flow

Use an evaluator-owned, analyst-promoted Investigation. The bounded benign
rule-100500 path in the [Wazuh evaluator guide](WAZUH_EVALUATOR_GUIDE.md) can
produce one; do not create an Investigation by database insertion or a manual
ingest request.

1. Open that Investigation's **Intelligence** workspace.
2. An active user with the existing `investigation:write` permission selects
   **Run analysis** once. The UI disables duplicate submission and shows the
   authoritative queued/running/terminal status.
3. On completion, select the completed run and inspect only its typed
   citations and reviewable claims. A failed latest run does not hide an older
   selected completed run.
4. Review a claim only through the existing analyst review control. Claims are not FACTs and never
   automatically create Findings, canonical MITRE mappings,
   promotions, or actions.

Do not paste prompts, evidence, provider output, credentials, or run tokens
into a ticket. If the model is missing, Ollama is unavailable, or worker/beat
is unhealthy, preserve the bounded status/category, leave the run unreviewed,
and return to Core mode rather than retrying or changing provider settings.

## Return to Core-only mode

Stop optional execution before changing the flags back to their safe defaults:

```sh
docker compose --project-name aegis-core --env-file "$AEGIS_STATE_DIR/core.env" \
  -f docker-compose.production.yml --profile ollama stop intelligence-worker intelligence-beat
docker compose --project-name aegis-core --env-file "$AEGIS_STATE_DIR/core.env" \
  -f docker-compose.production.yml --profile ollama stop api ollama
```

Set the same three `INTELLIGENCE_*_ENABLED` values in `core.env` back to
`false`, then restore only the Core API/frontend services:

```sh
docker compose --project-name aegis-core --env-file "$AEGIS_STATE_DIR/core.env" \
  -f docker-compose.production.yml up -d --build api frontend
```

Do not combine the Compose shutdown operation with the volume-removal flag
(`-v`); doing so removes named volumes. Do not delete the Ollama model volume,
remove PostgreSQL/Redis, or alter evidence or secret files when returning to
Core mode.
