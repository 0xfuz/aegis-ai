# Runtime secret materialization

Production credentials belong in an operator-controlled persistent directory, not `/tmp`. After a reboot, materialize the fixed bind-file allowlist into a new runtime directory without printing values:

```bash
./scripts/release/materialize-runtime-secrets.sh \
  --source-dir /protected/persistent/aegis-secrets \
  --runtime-dir /protected/runtime/aegis-secrets --preflight-only
./scripts/release/materialize-runtime-secrets.sh \
  --source-dir /protected/persistent/aegis-secrets \
  --runtime-dir /protected/runtime/aegis-secrets
```

The source and runtime directories must be explicit, non-symlinked, non-broad paths. Directories are `0700`; source and copied files are `0600`. The helper accepts only `postgres_password`, `jwt_signing_secret`, `wazuh_ingest_secret`, `bootstrap_email`, and `bootstrap_password`; it refuses missing/unsafe inputs and existing targets. It never creates credentials or overwrites persistent credentials. Use the separately documented credential-rotation procedure before deliberately replacing a source secret.

Start stateful services first (PostgreSQL, then Redis), run the one-shot migration, then API and frontend; start optional worker/beat and Ollama only after their dependencies are healthy. For a controlled shutdown, first stop ingress/Wazuh forwarding, then worker and beat, API/frontend/Ollama, Redis, and PostgreSQL last. Use `docker compose stop`; never use `down -v`, volume deletion, or prune for an ordinary restart.

After an operator password recovery, rotate the JWT signing secret through the supported credential-rotation procedure to invalidate existing sessions before or with the recovery window. A password reset alone cannot revoke already-issued short-lived access tokens.
