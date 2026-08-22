#!/usr/bin/env bash
# Bounded, local-only V1-B2 controlled-pilot performance harness.
# It intentionally uses public HTTP contracts; it never writes directly to
# PostgreSQL and never starts provider, worker, beat, Ollama, or Wazuh.
set -euo pipefail

readonly PROJECT_DEFAULT="aegis-v1b2-pilot"
readonly API_PORT_DEFAULT="18100"
readonly FRONTEND_PORT_DEFAULT="13100"
readonly MIN_FREE_KIB=$((15 * 1024 * 1024))
readonly MIN_MEM_AVAILABLE_KIB=$((2 * 1024 * 1024))
readonly BASELINE_EVENTS=300 BASELINE_RATE=5 BASELINE_CONCURRENCY=5 BASELINE_TIMEOUT=180
readonly BURST_EVENTS=150 BURST_RATE=10 BURST_CONCURRENCY=10 BURST_TIMEOUT=90
readonly READ_CONCURRENCY=10 READ_TIMEOUT=180
readonly FORWARDER_EVENTS=25 FORWARDER_TIMEOUT=180

PROJECT="${AEGIS_V1B2_PROJECT:-$PROJECT_DEFAULT}"
API_PORT="${AEGIS_V1B2_API_PORT:-$API_PORT_DEFAULT}"
FRONTEND_PORT="${AEGIS_V1B2_FRONTEND_PORT:-$FRONTEND_PORT_DEFAULT}"
API_ORIGIN="http://127.0.0.1:${API_PORT}"
FRONTEND_ORIGIN="http://127.0.0.1:${FRONTEND_PORT}"
RUNTIME_DIR=""
RESULT_DIR="${AEGIS_V1B2_RESULT_DIR:-}"
PREFLIGHT_ONLY=false
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"

fail() { printf '%s\n' "pilot-performance: $*" >&2; exit 2; }

usage() {
  cat <<'EOF'
Usage: ./scripts/release/run-pilot-performance.sh --result-dir /absolute/specific/path [--preflight-only]

Runs the bounded V1-B2 synthetic pilot harness from the repository root.
Maximum measured workload is approximately 12 minutes plus serialized image
builds and startup. Require at least 15 GiB root free disk and 2 GiB
MemAvailable. Result files are aggregate-only and written with mode 0600:
status.json, aggregate.json, exit-code, and operator-summary.txt.

--preflight-only checks the repository, namespace, result directory, Docker
availability, disk, and memory without building or starting containers.
Interrupt safely with Ctrl-C; the exact aegis-v1b2-* Compose project is
removed while aggregate status remains in the requested result directory.
Verify cleanup with: docker ps -a --filter label=com.docker.compose.project=aegis-v1b2-pilot
EOF
}

parse_args() {
  while (($#)); do
    case "$1" in
      --result-dir) (($# >= 2)) || fail "--result-dir requires an absolute path"; RESULT_DIR="$2"; shift 2 ;;
      --preflight-only) PREFLIGHT_ONLY=true; shift ;;
      --help|-h) usage; exit 0 ;;
      *) fail "unsupported argument" ;;
    esac
  done
  [[ -n "$RESULT_DIR" ]] || fail "--result-dir is required"
}

validate_result_dir() {
  [[ "$RESULT_DIR" = /* ]] || fail "result directory must be absolute"
  [[ ! -L "$RESULT_DIR" ]] || fail "result directory must not be a symlink"
  local resolved parent
  resolved=$(realpath -m -- "$RESULT_DIR")
  parent=$(dirname "$resolved")
  [[ -d "$parent" && ! -L "$parent" ]] || fail "result directory parent must be an existing non-symlink directory"
  case "$resolved" in /|/home|"$HOME"|"$REPO_ROOT"|"$REPO_ROOT"/*|*aegis-r4-*|*r4-acceptance*) fail "unsafe result directory";; esac
  [[ "$(basename "$resolved")" != "." && "$(basename "$resolved")" != ".." ]] || fail "result directory must be specific"
  RESULT_DIR="$resolved"
  if [[ -e "$RESULT_DIR" ]]; then
    [[ -d "$RESULT_DIR" && ! -L "$RESULT_DIR" ]] || fail "result path must be a non-symlink directory"
  else
    mkdir -m 700 -- "$RESULT_DIR"
  fi
  chmod 700 "$RESULT_DIR"
}

write_result() {
  local name="$1" value="$2" temporary
  temporary="$RESULT_DIR/.${name}.$$"
  umask 077
  printf '%s\n' "$value" >"$temporary"
  chmod 600 "$temporary"
  mv -f -- "$temporary" "$RESULT_DIR/$name"
}

cleanup() {
  local status=$?
  if [[ -n "${RUNTIME_DIR}" && -d "${RUNTIME_DIR}" ]]; then
    # The generated env/secret files and aggregate-only measurements are
    # disposable; never leave them in the repository or host temp space.
    docker compose --project-name "$PROJECT" --env-file "$RUNTIME_DIR/compose.env" \
      -f docker-compose.production.yml down --volumes --remove-orphans >/dev/null 2>&1 || true
    rm -rf -- "$RUNTIME_DIR"
  fi
  if [[ -n "${RESULT_DIR}" && -d "${RESULT_DIR}" ]]; then
    write_result exit-code "$status"
    write_result status.json "{\"v1_b2_status\":\"NOT_MEASURED\",\"harness_exit_code\":$status,\"cleanup\":\"attempted\"}"
    write_result operator-summary.txt "V1-B2 STATUS: NOT MEASURED\nHarness exit category: $status\nDisposable cleanup: attempted\nNo credentials, payloads, or response bodies are retained."
  fi
  trap - EXIT
  exit "$status"
}
trap cleanup EXIT INT TERM

assert_disposable_target() {
  [[ "$PROJECT" =~ ^aegis-v1b2-[a-z0-9-]+$ ]] || fail "project must use the aegis-v1b2-* namespace"
  [[ "$PROJECT" != *r4* ]] || fail "preserved R4 resources are never a harness target"
  [[ "$API_ORIGIN" =~ ^http://127\.0\.0\.1:[0-9]+$ ]] || fail "API target must be loopback"
  [[ "$FRONTEND_ORIGIN" =~ ^http://127\.0\.0\.1:[0-9]+$ ]] || fail "frontend target must be loopback"
}

assert_host_safety() {
  local disk mem
  disk=$(df -Pk / | awk 'NR==2 {print $4}')
  mem=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)
  (( disk >= MIN_FREE_KIB )) || fail "root free space is below the 15 GiB safety floor"
  (( mem >= MIN_MEM_AVAILABLE_KIB )) || fail "MemAvailable is below the 2 GiB safety floor"
}

wait_http() {
  local url="$1" deadline=$((SECONDS + 120))
  until curl --fail --silent --show-error --max-time 3 "$url" >/dev/null; do
    (( SECONDS < deadline )) || fail "timed out waiting for bounded local service readiness"
    sleep 2
  done
}

write_runtime() {
  RUNTIME_DIR=$(mktemp -d /tmp/aegis-v1b2-XXXXXX)
  chmod 700 "$RUNTIME_DIR"
  umask 077
  head -c 36 /dev/urandom | base64 >"$RUNTIME_DIR/postgres_password"
  head -c 48 /dev/urandom | base64 >"$RUNTIME_DIR/jwt_signing_secret"
  printf '%s\n' 'Pilot-Initial-Password-2!A' >"$RUNTIME_DIR/bootstrap_password"
  printf '%s\n' 'Pilot-Rotated-Password-2!B' >"$RUNTIME_DIR/rotated_password"
  printf '%s\n' 'pilot-admin@example.invalid' >"$RUNTIME_DIR/admin_email"
  chmod 600 "$RUNTIME_DIR"/*
  cat >"$RUNTIME_DIR/compose.env" <<EOF
POSTGRES_USER_REQUIRED=aegis_v1b2
POSTGRES_DB_REQUIRED=aegis_v1b2
POSTGRES_PASSWORD_FILE_REQUIRED=$RUNTIME_DIR/postgres_password
JWT_SECRET_KEY_FILE_REQUIRED=$RUNTIME_DIR/jwt_signing_secret
BOOTSTRAP_ADMIN_PASSWORD_FILE=$RUNTIME_DIR/bootstrap_password
BOOTSTRAP_ORGANIZATION_NAME_REQUIRED=V1 B2 Synthetic Pilot
BOOTSTRAP_ORGANIZATION_SLUG_REQUIRED=v1b2-synthetic-pilot
BOOTSTRAP_ADMIN_EMAIL_REQUIRED=pilot-admin@example.invalid
BOOTSTRAP_ADMIN_FULL_NAME_REQUIRED=Pilot Administrator
CORS_ORIGINS_REQUIRED=$FRONTEND_ORIGIN
PUBLIC_API_BASE_URL_REQUIRED=$API_ORIGIN
NEXT_PUBLIC_API_URL_REQUIRED=$API_ORIGIN/api/v1
API_PORT=$API_PORT
FRONTEND_PORT=$FRONTEND_PORT
INTELLIGENCE_EXECUTION_ENABLED=false
INTELLIGENCE_DISPATCH_ENABLED=false
INTELLIGENCE_PROVIDER_ENABLED=false
EOF
  chmod 600 "$RUNTIME_DIR/compose.env"
}

start_core() {
  # Builds are deliberately serialized to keep the bounded host envelope.
  docker compose --project-name "$PROJECT" --env-file "$RUNTIME_DIR/compose.env" -f docker-compose.production.yml build migrate
  docker compose --project-name "$PROJECT" --env-file "$RUNTIME_DIR/compose.env" -f docker-compose.production.yml build api
  docker compose --project-name "$PROJECT" --env-file "$RUNTIME_DIR/compose.env" -f docker-compose.production.yml build frontend
  docker compose --project-name "$PROJECT" --env-file "$RUNTIME_DIR/compose.env" -f docker-compose.production.yml up -d postgres redis migrate api frontend
  wait_http "$API_ORIGIN/api/v1/health"
  wait_http "$FRONTEND_ORIGIN/healthz"
  # Bootstrap does not receive plaintext on its command line. Preserve only
  # its bounded process result in the harness log so a failed disposable run
  # is diagnosable without exposing the mounted secret value.
  docker compose --project-name "$PROJECT" --env-file "$RUNTIME_DIR/compose.env" -f docker-compose.production.yml --profile bootstrap run --rm admin-bootstrap
}

measure() {
  # The driver records only aggregate timing/status/count data to stdout. It
  # uses authenticated HTTP and never emits request/response bodies or secrets.
  local aggregate_tmp="$RESULT_DIR/.aggregate.json.$$"
  python3 scripts/release/pilot_performance_driver.py \
    --api "$API_ORIGIN/api/v1" --email-file "$RUNTIME_DIR/admin_email" \
    --initial-password-file "$RUNTIME_DIR/bootstrap_password" --rotated-password-file "$RUNTIME_DIR/rotated_password" \
    --baseline-events "$BASELINE_EVENTS" --baseline-rate "$BASELINE_RATE" --baseline-concurrency "$BASELINE_CONCURRENCY" --baseline-timeout "$BASELINE_TIMEOUT" \
    --burst-events "$BURST_EVENTS" --burst-rate "$BURST_RATE" --burst-concurrency "$BURST_CONCURRENCY" --burst-timeout "$BURST_TIMEOUT" \
    --read-concurrency "$READ_CONCURRENCY" --read-timeout "$READ_TIMEOUT" --forwarder-events "$FORWARDER_EVENTS" --forwarder-timeout "$FORWARDER_TIMEOUT" >"$aggregate_tmp"
  chmod 600 "$aggregate_tmp"
  mv -f -- "$aggregate_tmp" "$RESULT_DIR/aggregate.json"
}

main() {
  parse_args "$@"
  validate_result_dir
  assert_disposable_target
  assert_host_safety
  write_result aggregate.json "{\"v1_b2_status\":\"NOT_MEASURED\",\"aggregate_only\":true,\"scenarios\":[]}"
  write_result status.json "{\"v1_b2_status\":\"NOT_MEASURED\",\"stage\":\"preflight\"}"
  write_result operator-summary.txt "V1-B2 STATUS: NOT MEASURED\nNo benchmark result has been recorded."
  if "$PREFLIGHT_ONLY"; then
    command -v docker >/dev/null || fail "Docker CLI is required"
    docker compose version >/dev/null || fail "Docker Compose v2 is required"
    write_result status.json "{\"v1_b2_status\":\"NOT_MEASURED\",\"stage\":\"preflight_passed\"}"
    write_result exit-code "0"
    return 0
  fi
  write_runtime
  start_core
  measure
}

main "$@"
