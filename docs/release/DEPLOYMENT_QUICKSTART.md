# Core-mode deployment quickstart

This is the supported clean-clone path for a controlled pilot. It starts the private Core stack (PostgreSQL, Redis, migration, API, frontend, worker, and beat) without a Wazuh Manager or Ollama. Wazuh is configured separately; AI execution and Ollama remain disabled unless an operator explicitly enables the documented optional profile.

This guide does not certify a throughput envelope. The unchanged V1-B3 baseline failed to complete 300/300 events at five events per second on its single-machine host. Aegis is suitable for controlled pilot use, not a production-scale SaaS or Enterprise SIEM replacement.

## Prerequisites

- Git, Docker Engine with Docker Compose v2, `openssl`, and `curl`.
- At least the disk and memory margins described in [V1 pilot performance](V1_0_PILOT_PERFORMANCE.md). No supported rate should be inferred from that failed campaign.
- A private, operator-managed TLS reverse proxy before exposing loopback ports beyond the host. This quickstart intentionally uses loopback only.

Clone the intended release commit, not a copied working directory:

```sh
git clone <approved-aegis-repository-url> aegis-ai
cd aegis-ai
git checkout <approved-release-commit>
```

## Create protected local inputs

Choose a persistent directory outside the clone. The example uses a local operator state directory; replace it with an approved protected location when required by your operating environment. Do not reuse R4, benchmark, or other deployment files.

```sh
export AEGIS_STATE_DIR="$HOME/.local/state/aegis-core"
export AEGIS_RUNTIME_DIR="$AEGIS_STATE_DIR/runtime-secrets"
install -d -m 0700 "$AEGIS_STATE_DIR/secrets"
```

Generate fresh database, JWT, and connector inputs. The fixed prefixes only ensure the deployment strength checks see required character classes; each complete value contains fresh cryptographic randomness and is never a default credential.

```sh
umask 077
printf 'Db1!%s\n' "$(openssl rand -hex 28)" > "$AEGIS_STATE_DIR/secrets/postgres_password"
printf 'Jwt1!%s\n' "$(openssl rand -hex 32)" > "$AEGIS_STATE_DIR/secrets/jwt_signing_secret"
printf 'Wz1!%s\n' "$(openssl rand -hex 28)" > "$AEGIS_STATE_DIR/secrets/wazuh_ingest_secret"
```

Every operator supplies their own bootstrap identity and password. Do not use a documented, demo, R4, or shared administrator identity. The password prompt does not echo input or put it in shell history.

```sh
read -r -p 'Bootstrap administrator email: ' AEGIS_BOOTSTRAP_EMAIL
read -r -s -p 'Bootstrap administrator password (12–128 characters): ' AEGIS_BOOTSTRAP_PASSWORD
printf '\n'
printf '%s\n' "$AEGIS_BOOTSTRAP_EMAIL" > "$AEGIS_STATE_DIR/secrets/bootstrap_email"
printf '%s\n' "$AEGIS_BOOTSTRAP_PASSWORD" > "$AEGIS_STATE_DIR/secrets/bootstrap_password"
unset AEGIS_BOOTSTRAP_PASSWORD
chmod 0600 "$AEGIS_STATE_DIR/secrets"/*
```

Materialize the fixed secret-file allowlist into a fresh runtime directory. The helper refuses broad paths, symlinks, unsafe modes, missing files, and overwrites; it never prints or generates credentials.

```sh
./scripts/release/materialize-runtime-secrets.sh \
  --source-dir "$AEGIS_STATE_DIR/secrets" \
  --runtime-dir "$AEGIS_RUNTIME_DIR"
```

## Configure Core mode

Copy the placeholder-only template outside the repository. It contains paths and identifiers, never secret values. Set the organization and administrator identifiers to the values chosen above, and keep the three intelligence flags `false`.

```sh
cp .env.production.example "$AEGIS_STATE_DIR/core.env"
chmod 0600 "$AEGIS_STATE_DIR/core.env"
${EDITOR:-vi} "$AEGIS_STATE_DIR/core.env"
```

For a loopback-only pilot, use matching origins such as:

```text
CORS_ORIGINS_REQUIRED=http://127.0.0.1:13000
PUBLIC_API_BASE_URL_REQUIRED=http://127.0.0.1:18000
NEXT_PUBLIC_API_URL_REQUIRED=http://127.0.0.1:18000
API_PORT=18000
FRONTEND_PORT=13000
POSTGRES_PASSWORD_FILE_REQUIRED=/absolute/path/to/runtime-secrets/postgres_password
JWT_SECRET_KEY_FILE_REQUIRED=/absolute/path/to/runtime-secrets/jwt_signing_secret
BOOTSTRAP_ADMIN_PASSWORD_FILE=/absolute/path/to/runtime-secrets/bootstrap_password
```

Use the actual absolute runtime paths in `core.env`; do not copy the placeholder text. `localhost` and `127.0.0.1` are different browser origins, so do not mix them. Production demo seeding and demo credentials are not supported. There is no production synthetic-demo loading path.

## Start, bootstrap, and verify

The migration service is the sole writer and reaches head `0024` before API, worker, or beat starts. Core mode does not enable the `ollama` or `bootstrap` profiles during normal startup.

```sh
docker compose --project-name aegis-core --env-file "$AEGIS_STATE_DIR/core.env" \
  -f docker-compose.production.yml config -q
docker compose --project-name aegis-core --env-file "$AEGIS_STATE_DIR/core.env" \
  -f docker-compose.production.yml up -d --build
docker compose --project-name aegis-core --env-file "$AEGIS_STATE_DIR/core.env" \
  -f docker-compose.production.yml ps
curl --fail http://127.0.0.1:18000/api/v1/health
curl --fail http://127.0.0.1:13000/healthz
```

Bootstrap exactly one administrator as an explicit operator action. This is the only use of the `bootstrap` profile and it never retries automatically.

```sh
docker compose --project-name aegis-core --env-file "$AEGIS_STATE_DIR/core.env" \
  -f docker-compose.production.yml --profile bootstrap run --rm admin-bootstrap
```

Open `http://127.0.0.1:13000/login`, sign in with the operator-supplied bootstrap credentials, and complete the required first password rotation. Later self-service changes are available at **Settings → Security**. A password change clears the browser session and requires a new sign-in; verify that the old password fails and the new password succeeds.

MITRE entries labeled **AI-suggested / not canonical** remain suggestions. Only an analyst review of the canonical MITRE surface can confirm or reject a mapping; an AI suggestion never becomes a fact automatically.

## Controlled restart and cleanup

For an ordinary restart, preserve named volumes. Stop ingress/forwarding first when configured, then stop worker and beat, API/frontend, Redis, and PostgreSQL last. `stop` and ordinary `down` preserve volumes; never use `down -v`, volume deletion, or Docker prune for an ordinary restart.

```sh
docker compose --project-name aegis-core --env-file "$AEGIS_STATE_DIR/core.env" \
  -f docker-compose.production.yml stop intelligence-worker intelligence-beat api frontend redis postgres
# After a reboot that removes the runtime directory, materialize it again into
# a fresh empty target. The helper intentionally refuses overwrites.
if [ ! -e "$AEGIS_RUNTIME_DIR" ]; then
  ./scripts/release/materialize-runtime-secrets.sh \
    --source-dir "$AEGIS_STATE_DIR/secrets" \
    --runtime-dir "$AEGIS_RUNTIME_DIR"
fi
docker compose --project-name aegis-core --env-file "$AEGIS_STATE_DIR/core.env" \
  -f docker-compose.production.yml up -d
```

Repeat the two health checks and sign in with the rotated password after the restart. For an intentionally disposable test deployment only, stop the exact project and remove its exact project volumes after confirming no evidence must be preserved:

```sh
docker compose --project-name aegis-core --env-file "$AEGIS_STATE_DIR/core.env" \
  -f docker-compose.production.yml down -v --remove-orphans
```

For Wazuh deployment, durable forwarding, TLS lifecycle, backup/restore, and credential rotation, follow [Wazuh operations](WAZUH_OPERATIONS.md), [production deployment](PRODUCTION_DEPLOYMENT.md), [admin bootstrap](PRODUCTION_ADMIN_BOOTSTRAP.md), and [backup and recovery](BACKUP_AND_RECOVERY.md).
