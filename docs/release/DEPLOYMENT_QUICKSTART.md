# Deployment quickstart

Use `docker-compose.production.yml` for controlled pilots; development Compose is not a production profile.

1. Copy `.env.production.example` outside the repository and replace placeholders with deployment identifiers and paths to protected secret files. Never place secret values in it or on command lines.
2. Keep API and frontend loopback-bound unless a separately operated TLS ingress is configured. `localhost` and `127.0.0.1` are distinct browser origins: CORS and `NEXT_PUBLIC_API_URL_REQUIRED` must match the chosen origin exactly.
3. Start production Compose with the external environment file. `migrate` is the sole migration writer and must complete before API, worker, or beat.
4. Verify API health and frontend `/healthz`; invoke the operator-only bootstrap profile and complete the required first password rotation.
5. Configure Wazuh separately through [Wazuh operations](WAZUH_OPERATIONS.md). Do not manually post alerts to Aegis.

Intelligence execution/Ollama is optional and disabled by default. For detailed secret, health, restart, shutdown, and recovery guidance use [production deployment](PRODUCTION_DEPLOYMENT.md), [admin bootstrap](PRODUCTION_ADMIN_BOOTSTRAP.md), and [backup/restore](BACKUP_AND_RECOVERY.md). Shutdown pauses ingress first, then worker/beat, API/frontend/optional Ollama, Redis, and PostgreSQL last; restart reverses that order.
