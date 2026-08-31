#!/usr/bin/env bash
# Restore only operator-approved runtime secret bind files after a reboot.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: materialize-runtime-secrets.sh --source-dir ABSOLUTE --runtime-dir ABSOLUTE [--preflight-only]

Copies the fixed production secret allowlist from protected persistent storage
to an empty runtime directory. It never generates, prints, or overwrites a secret.
EOF
}

SOURCE_DIR=""; RUNTIME_DIR=""; PREFLIGHT=false
while (($#)); do
  case "$1" in
    --source-dir) SOURCE_DIR=${2:?}; shift 2 ;;
    --runtime-dir) RUNTIME_DIR=${2:?}; shift 2 ;;
    --preflight-only) PREFLIGHT=true; shift ;;
    --help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

[[ -n "$SOURCE_DIR" && -n "$RUNTIME_DIR" && "$SOURCE_DIR" = /* && "$RUNTIME_DIR" = /* ]] || { usage >&2; exit 2; }
[[ "$SOURCE_DIR" != "$RUNTIME_DIR" ]] || { echo "Source and runtime directories must differ." >&2; exit 2; }
for path in "$SOURCE_DIR" "$RUNTIME_DIR"; do
  [[ "$path" != / && "$path" != /home && "$path" != /tmp && "$path" != *"aegis-r4"* ]] || { echo "Unsafe directory." >&2; exit 2; }
  [[ ! -L "$path" ]] || { echo "Symlink directories are not accepted." >&2; exit 2; }
done
[[ -d "$SOURCE_DIR" ]] || { echo "Persistent source directory is missing." >&2; exit 2; }
[[ ! -e "$RUNTIME_DIR" || -d "$RUNTIME_DIR" ]] || { echo "Runtime target is invalid." >&2; exit 2; }

safe_mode() { local mode; mode=$(stat -c '%a' "$1"); (( (8#$mode & 8#077) == 0 )); }
safe_mode "$SOURCE_DIR" || { echo "Persistent source permissions are unsafe." >&2; exit 2; }
if [[ -e "$RUNTIME_DIR" ]]; then safe_mode "$RUNTIME_DIR" || { echo "Runtime directory permissions are unsafe." >&2; exit 2; }; fi

# These names are the only bind-file inputs recognized by production Compose.
ALLOWLIST=(postgres_password jwt_signing_secret wazuh_ingest_secret bootstrap_email bootstrap_password)
for name in "${ALLOWLIST[@]}"; do
  source_file="$SOURCE_DIR/$name"
  [[ -f "$source_file" && ! -L "$source_file" ]] || { echo "Required secret file is invalid." >&2; exit 2; }
  safe_mode "$source_file" || { echo "Secret file permissions are unsafe." >&2; exit 2; }
  [[ ! -e "$RUNTIME_DIR/$name" ]] || { echo "Refusing to overwrite runtime secret." >&2; exit 2; }
done

if "$PREFLIGHT"; then exit 0; fi
install -d -m 0700 "$RUNTIME_DIR"
for name in "${ALLOWLIST[@]}"; do
  temp=$(mktemp "$RUNTIME_DIR/.${name}.XXXXXX")
  chmod 0600 "$temp"
  < "$SOURCE_DIR/$name" cat > "$temp"
  mv -f "$temp" "$RUNTIME_DIR/$name"
done
