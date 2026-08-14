#!/usr/bin/env bash
# Creates a non-destructive, checksumed operational backup. It never reads or
# archives Docker secret files, environment files, or host configuration.
set -euo pipefail
umask 077

usage() { echo "usage: $0 --compose-file FILE --wazuh-spool-dir DIR --output-dir NEW_ABSOLUTE_DIR" >&2; exit 64; }
compose_file=""; spool_dir=""; output_dir=""
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --compose-file) compose_file="${2:-}"; shift 2 ;;
    --wazuh-spool-dir) spool_dir="${2:-}"; shift 2 ;;
    --output-dir) output_dir="${2:-}"; shift 2 ;;
    *) usage ;;
  esac
done
[[ -f "$compose_file" && -d "$spool_dir" && -d "$spool_dir/pending" && -d "$spool_dir/quarantine" ]] || usage
[[ "$output_dir" == /* && "$output_dir" != / && ! -e "$output_dir" ]] || usage
mkdir "$output_dir"

docker compose -f "$compose_file" exec -T postgres sh -c 'exec pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$output_dir/postgresql.dump"
docker compose -f "$compose_file" exec -T api tar -C /app/storage -czf - evidence > "$output_dir/evidence-storage.tar.gz"
tar -C "$spool_dir" -czf "$output_dir/wazuh-forwarder-spool.tar.gz" pending quarantine
{
  printf 'created_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'repository_commit=%s\n' "$(git rev-parse HEAD)"
  printf 'compose_sha256=%s\n' "$(sha256sum "$compose_file" | awk '{print $1}')"
  printf 'alembic_current='
  docker compose -f "$compose_file" exec -T api alembic current | tail -n 1
} > "$output_dir/manifest.txt"
(cd "$output_dir" && sha256sum postgresql.dump evidence-storage.tar.gz wazuh-forwarder-spool.tar.gz manifest.txt > SHA256SUMS)
printf '%s\n' "Backup written to $output_dir"
