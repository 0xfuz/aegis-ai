#!/usr/bin/env bash
# Restores only into a new, explicit isolated Compose namespace. It never
# removes data and refuses existing target containers, volumes, or spool paths.
set -euo pipefail
umask 077

usage() { echo "usage: $0 --backup-dir DIR --compose-file FILE --project aegis-restore-NAME --wazuh-spool-dir NEW_ABSOLUTE_DIR --confirm-destructive-restore" >&2; exit 64; }
backup_dir=""; compose_file=""; project=""; spool_dir=""; confirmed=false
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --backup-dir) backup_dir="${2:-}"; shift 2 ;;
    --compose-file) compose_file="${2:-}"; shift 2 ;;
    --project) project="${2:-}"; shift 2 ;;
    --wazuh-spool-dir) spool_dir="${2:-}"; shift 2 ;;
    --confirm-destructive-restore) confirmed=true; shift ;;
    *) usage ;;
  esac
done
[[ "$confirmed" == true && "$project" =~ ^aegis-restore-[a-z0-9-]+$ && -d "$backup_dir" && -f "$compose_file" ]] || usage
[[ -f "$backup_dir/SHA256SUMS" && -f "$backup_dir/postgresql.dump" && -f "$backup_dir/evidence-storage.tar.gz" && -f "$backup_dir/wazuh-forwarder-spool.tar.gz" ]] || usage
[[ "$spool_dir" == /* && "$spool_dir" != / && ! -e "$spool_dir" ]] || usage
[[ -z "$(docker compose -p "$project" -f "$compose_file" ps -aq)" ]] || { echo "Target namespace has containers." >&2; exit 65; }
[[ -z "$(docker volume ls -q --filter "label=com.docker.compose.project=$project")" ]] || { echo "Target namespace has volumes." >&2; exit 65; }
(cd "$backup_dir" && sha256sum -c SHA256SUMS)
mkdir "$spool_dir"
tar -C "$spool_dir" -xzf "$backup_dir/wazuh-forwarder-spool.tar.gz"
docker compose -p "$project" -f "$compose_file" up -d postgres
ready=false
for _ in $(seq 1 30); do
  user="$(docker compose -p "$project" -f "$compose_file" exec -T postgres printenv POSTGRES_USER)"
  database="$(docker compose -p "$project" -f "$compose_file" exec -T postgres printenv POSTGRES_DB)"
  if docker compose -p "$project" -f "$compose_file" exec -T postgres pg_isready -U "$user" -d "$database" >/dev/null; then ready=true; break; fi
  sleep 1
done
[[ "$ready" == true ]] || { echo "Target PostgreSQL did not become ready." >&2; exit 66; }
docker compose -p "$project" -f "$compose_file" exec -T postgres sh -c 'exec pg_restore --clean --if-exists -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$backup_dir/postgresql.dump"
docker compose -p "$project" -f "$compose_file" up -d migrate api
api_id="$(docker compose -p "$project" -f "$compose_file" ps -q api)"
[[ -n "$api_id" ]] || { echo "Target API did not start." >&2; exit 66; }
docker cp "$backup_dir/evidence-storage.tar.gz" "$api_id:/tmp/evidence-storage.tar.gz"
docker compose -p "$project" -f "$compose_file" exec -T --user root api sh -c 'mkdir -p /app/storage && tar -C /app/storage -xzf /tmp/evidence-storage.tar.gz && chown -R 1000:1000 /app/storage/evidence && rm -f /tmp/evidence-storage.tar.gz'
printf '%s\n' "Restore completed in isolated namespace $project"
