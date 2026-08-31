#!/usr/bin/env bash
# Aggregate-only, operator-run V1-P1A ingestion diagnostic harness.
set -euo pipefail

PROJECT="aegis-v1p1a-diagnosis-run"
IMAGE="${PROJECT}-image"
NETWORK="${PROJECT}-net"
POSTGRES="${PROJECT}-postgres"
MIGRATE="${PROJECT}-migrate"
RUNNER="${PROJECT}-driver"
VOLUME="${PROJECT}-postgres-data"
SCENARIOS=(single_new_event exact_replay bounded_10 bounded_25 correlation_candidate)
RESULT_DIR="${AEGIS_V1P1A_RESULT_DIR:-}"
PREFLIGHT_ONLY=false
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
RUNTIME_DIR=""
CURRENT_STAGE="preflight"
LAST_COMPLETED_STAGE=""
CURRENT_SCENARIO=""
LAST_COMPLETED_SCENARIO=""
SAFE_FAILURE_CATEGORY=""
CLEANUP_STATE="not_started"
STARTED_AT="$(date +%s)"

fail() { printf '%s\n' "ingestion-diagnosis: $*" >&2; exit 2; }
usage() { cat <<'EOF'
Usage: ./scripts/release/run-ingestion-diagnosis.sh --result-dir /absolute/path [--preflight-only]

Runs five small sequential test diagnostics: one new Wazuh-shaped event, one
exact replay, ten events, twenty-five events, and one correlation-v2 candidate.
Expected maximum duration is 10 minutes plus a serialized backend image build.
It never runs a rate test, burst, benchmark, frontend, worker, beat, Ollama,
Wazuh Manager, R4, or V1-B2.

Results are aggregate-only files in the specified external result directory:
status.json, aggregate.json, exit-code, and operator-summary.txt.  Interrupt
with Ctrl-C; completed aggregate scenarios are retained and only the exact
aegis-v1p1a-diagnosis-* resources are removed.
EOF
}

while (($#)); do
  case "$1" in
    --result-dir) [[ $# -ge 2 ]] || fail "--result-dir requires a path"; RESULT_DIR="$2"; shift 2 ;;
    --preflight-only) PREFLIGHT_ONLY=true; shift ;;
    --help|-h) usage; exit 0 ;;
    *) fail "unsupported argument" ;;
  esac
done

[[ -n "$RESULT_DIR" && "$RESULT_DIR" = /* && ! -L "$RESULT_DIR" ]] || fail "a non-symlink absolute result directory is required"
RESULT_DIR="$(realpath -m -- "$RESULT_DIR")"
case "$RESULT_DIR" in
  /|/home|"$ROOT"|"$ROOT"/*|*aegis-r4-*|*aegis-v1b2-*|*v1b2*) fail "unsafe result directory" ;;
esac
result_parent="$(dirname "$RESULT_DIR")"
[[ -d "$result_parent" && ! -L "$result_parent" ]] || fail "result parent must exist and not be a symlink"
mkdir -p -m 700 "$RESULT_DIR"
chmod 700 "$RESULT_DIR"

atomic_write() {
  local name="$1" content="$2" temporary="$RESULT_DIR/.${1}.$$"
  umask 077
  printf '%s\n' "$content" >"$temporary"
  chmod 600 "$temporary"
  mv -f "$temporary" "$RESULT_DIR/$name"
}

write_status() {
  local elapsed=$(( $(date +%s) - STARTED_AT ))
  python3 - "$RESULT_DIR/status.json" "$CURRENT_STAGE" "$LAST_COMPLETED_STAGE" "$CURRENT_SCENARIO" "$LAST_COMPLETED_SCENARIO" "$SAFE_FAILURE_CATEGORY" "$elapsed" "$CLEANUP_STATE" <<'PY'
import json, os, sys
path, current, completed, scenario, completed_scenario, category, elapsed, cleanup = sys.argv[1:]
temporary = f"{path}.{os.getpid()}.tmp"
with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as handle:
    json.dump({"current_stage": current, "last_completed_stage": completed,
               "current_scenario": scenario, "last_completed_scenario": completed_scenario,
               "safe_failure_category": category, "elapsed_seconds": int(elapsed),
               "cleanup_state": cleanup}, handle, separators=(",", ":"))
    handle.write("\n")
os.replace(temporary, path)
os.chmod(path, 0o600)
PY
}

write_aggregate() {
  python3 - "$RESULT_DIR/aggregate.json" "$ROOT" "$RUNTIME_DIR" "$CLEANUP_STATE" <<'PY'
import json, os, pathlib, subprocess, sys
target, root, runtime, cleanup = sys.argv[1:]
allowed = {"schema_version", "scenario", "bounded_event_count", "success", "safe_failure_category",
           "total_statements", "select_count", "insert_count", "update_count", "delete_count",
           "other_statement_count", "flush_count", "commit_count", "rollback_count",
           "transaction_count", "elapsed_milliseconds"}
records = []
if runtime:
    for path in sorted(pathlib.Path(runtime).glob("scenario-*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        records.append({key: value[key] for key in allowed if key in value})
by_name = {record.get("scenario"): record for record in records}
growth = "NOT_AVAILABLE"
if all(name in by_name and by_name[name].get("success") for name in ("single_new_event", "bounded_10", "bounded_25")):
    one, ten, twenty_five = (by_name[name]["total_statements"] for name in ("single_new_event", "bounded_10", "bounded_25"))
    growth = "LINEAR_OR_BETTER" if ten <= one * 10 and twenty_five <= one * 25 else "GREATER_THAN_LINEAR"
commit = subprocess.check_output(["git", "-C", root, "rev-parse", "HEAD"], text=True).strip()
output = {"commit": commit, "migration_head": "0024", "scenarios": records,
          "growth_classification": growth, "cleanup_state": cleanup}
temporary = f"{target}.{os.getpid()}.tmp"
with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as handle:
    json.dump(output, handle, separators=(",", ":")); handle.write("\n")
os.replace(temporary, target); os.chmod(target, 0o600)
PY
}

update_aggregate_cleanup() {
  python3 - "$RESULT_DIR/aggregate.json" "$CLEANUP_STATE" <<'PY'
import json, os, sys
target, cleanup = sys.argv[1:]
value = json.load(open(target, encoding="utf-8"))
value["cleanup_state"] = cleanup
temporary = f"{target}.{os.getpid()}.tmp"
with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as handle:
    json.dump(value, handle, separators=(",", ":")); handle.write("\n")
os.replace(temporary, target); os.chmod(target, 0o600)
PY
}

cleanup() {
  local rc=$?
  trap - EXIT INT TERM
  CLEANUP_STATE="in_progress"
  write_status
  if [[ -n "$RUNTIME_DIR" ]]; then
    write_aggregate
    docker rm -f "$RUNNER" "$MIGRATE" "$POSTGRES" >/dev/null 2>&1 || true
    for scenario in "${SCENARIOS[@]}"; do
      docker rm -f "${RUNNER}-${scenario}" >/dev/null 2>&1 || true
    done
    docker network rm "$NETWORK" >/dev/null 2>&1 || true
    docker volume rm "$VOLUME" >/dev/null 2>&1 || true
    docker image rm "$IMAGE" >/dev/null 2>&1 || true
    case "$RUNTIME_DIR" in /tmp/aegis-v1p1a-diagnosis-*) rm -rf "$RUNTIME_DIR" ;; *) SAFE_FAILURE_CATEGORY="UNSAFE_RUNTIME_DIRECTORY" ;; esac
  fi
  CLEANUP_STATE="completed"
  if [[ -f "$RESULT_DIR/aggregate.json" ]]; then update_aggregate_cleanup; else write_aggregate; fi
  write_status
  atomic_write exit-code "$rc"
  atomic_write operator-summary.txt "V1-P1A STATUS: NOT MEASURED
Aggregate-only diagnostic artifacts retained; no SQL, payload, credential, log, body, or environment value is retained."
  exit "$rc"
}

interrupted() { SAFE_FAILURE_CATEGORY="INTERRUPTED"; exit 130; }
on_error() { local rc=$?; [[ -n "$SAFE_FAILURE_CATEGORY" ]] || SAFE_FAILURE_CATEGORY="HARNESS_COMMAND_FAILED"; exit "$rc"; }
trap cleanup EXIT
trap interrupted INT TERM
trap on_error ERR

[[ "$PROJECT" =~ ^aegis-v1p1a-diagnosis-[a-z0-9-]+$ ]] || fail "exact aegis-v1p1a-diagnosis namespace required"
command -v docker >/dev/null || fail "Docker CLI required"
docker compose version >/dev/null || fail "Docker Compose v2 required"
if "$PREFLIGHT_ONLY"; then
  LAST_COMPLETED_STAGE="preflight"
  write_aggregate
  exit 0
fi

CURRENT_STAGE="resource_preflight"
write_status
[[ $(df -Pk / | awk 'NR==2 {print $4}') -ge $((15 * 1024 * 1024)) ]] || { SAFE_FAILURE_CATEGORY="DISK_FLOOR"; exit 2; }
[[ $(awk '/MemAvailable:/ {print $2}' /proc/meminfo) -ge $((2 * 1024 * 1024)) ]] || { SAFE_FAILURE_CATEGORY="MEMORY_FLOOR"; exit 2; }

RUNTIME_DIR="$(mktemp -d /tmp/aegis-v1p1a-diagnosis-XXXXXX)"
chmod 700 "$RUNTIME_DIR"
head -c 36 /dev/urandom | base64 >"$RUNTIME_DIR/postgres_password"
head -c 36 /dev/urandom | base64 >"$RUNTIME_DIR/jwt_secret"
chmod 600 "$RUNTIME_DIR/postgres_password" "$RUNTIME_DIR/jwt_secret"
password="$(<"$RUNTIME_DIR/postgres_password")"
jwt_secret="$(<"$RUNTIME_DIR/jwt_secret")"
database_url="postgresql+psycopg2://aegis_v1p1a:${password}@${POSTGRES}:5432/aegis_v1p1a"

CURRENT_STAGE="build"
write_status
timeout 600 docker build -t "$IMAGE" "$ROOT/backend" >/dev/null || { SAFE_FAILURE_CATEGORY="IMAGE_BUILD_FAILED"; exit 2; }
LAST_COMPLETED_STAGE="build"

CURRENT_STAGE="postgres"
write_status
docker network create "$NETWORK" >/dev/null
docker volume create "$VOLUME" >/dev/null
docker run -d --name "$POSTGRES" --network "$NETWORK" -e POSTGRES_USER=aegis_v1p1a -e POSTGRES_PASSWORD="$password" -e POSTGRES_DB=aegis_v1p1a -v "$VOLUME":/var/lib/postgresql/data postgres:16.4-alpine >/dev/null
for _attempt in $(seq 1 60); do
  docker exec "$POSTGRES" pg_isready -U aegis_v1p1a -d aegis_v1p1a >/dev/null 2>&1 && break
  sleep 1
done
docker exec "$POSTGRES" pg_isready -U aegis_v1p1a -d aegis_v1p1a >/dev/null || { SAFE_FAILURE_CATEGORY="POSTGRES_READINESS_TIMEOUT"; exit 2; }
LAST_COMPLETED_STAGE="postgres"

CURRENT_STAGE="migration"
write_status
timeout 180 docker run --name "$MIGRATE" --network "$NETWORK" --entrypoint sh -e DEBUG=false -e DATABASE_URL="$database_url" -e JWT_SECRET_KEY="$jwt_secret" "$IMAGE" -c 'cd /app && alembic upgrade head && test "$(alembic heads | awk "{print \$1}")" = "0024"' >/dev/null || { SAFE_FAILURE_CATEGORY="MIGRATION_FAILED"; exit 2; }
LAST_COMPLETED_STAGE="migration"

for scenario in "${SCENARIOS[@]}"; do
  CURRENT_STAGE="diagnostic"
  CURRENT_SCENARIO="$scenario"
  write_status
  scenario_output="$RUNTIME_DIR/scenario-${scenario}.json"
  timeout 120 docker run --rm --name "${RUNNER}-${scenario}" --network "$NETWORK" --entrypoint sh -e DEBUG=false -e DATABASE_URL="$database_url" -e JWT_SECRET_KEY="$jwt_secret" -v "$ROOT":/workspace:ro -v "$RUNTIME_DIR":/result "$IMAGE" -c "PYTHONPATH=/workspace/backend:/workspace python /workspace/scripts/release/ingestion_diagnosis_driver.py --scenario $scenario --output /result/scenario-$scenario.json" >/dev/null || { SAFE_FAILURE_CATEGORY="SCENARIO_TIMEOUT_OR_DRIVER_FAILURE"; exit 2; }
  scenario_category="$(python3 - "$scenario_output" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
allowed = {"schema_version", "scenario", "bounded_event_count", "success", "safe_failure_category",
           "total_statements", "select_count", "insert_count", "update_count", "delete_count",
           "other_statement_count", "flush_count", "commit_count", "rollback_count",
           "transaction_count", "elapsed_milliseconds"}
if set(value) - allowed:
    print("SCENARIO_RESULT_INVALID")
elif not value.get("success"):
    print(value.get("safe_failure_category") or "SCENARIO_RESULT_INVALID")
else:
    print("OK")
PY
  )" || { SAFE_FAILURE_CATEGORY="SCENARIO_RESULT_INVALID"; exit 2; }
  [[ "$scenario_category" == "OK" ]] || { SAFE_FAILURE_CATEGORY="$scenario_category"; exit 2; }
  LAST_COMPLETED_SCENARIO="$scenario"
  write_aggregate
  write_status
done

LAST_COMPLETED_STAGE="diagnostic"
CURRENT_STAGE="complete"
write_status
