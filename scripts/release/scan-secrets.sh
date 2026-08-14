#!/usr/bin/env bash
# Reports candidate paths/revisions only; it deliberately never prints a match.
set -euo pipefail
readonly MAX_COMMITS=500
readonly PATTERN='-----BEGIN ([A-Z ]*PRIVATE KEY|OPENSSH PRIVATE KEY)-----|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{20,}'

[[ "$(git rev-parse --show-toplevel)" == "$(pwd -P)" ]] || { echo "Run from repository root." >&2; exit 64; }
mapfile -t commits < <(git rev-list --all --max-count="$MAX_COMMITS")
[[ "${#commits[@]}" -lt "$MAX_COMMITS" ]] || { echo "History scan bound reached; use an approved archival scanner." >&2; exit 65; }
found=0
while IFS= read -r path; do printf 'HEAD candidate: %s\n' "$path"; found=1; done < <(git grep -IlE -e "$PATTERN" || true)
for commit in "${commits[@]}"; do
  while IFS= read -r path; do printf 'History candidate: %s:%s\n' "$commit" "$path"; found=1; done < <(git grep -IlE -e "$PATTERN" "$commit" || true)
done
[[ "$found" -eq 0 ]] || { echo "Candidates require security review; values were not printed." >&2; exit 1; }
printf '%s\n' "No high-confidence secret candidates in tracked files or reachable history."
