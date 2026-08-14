# Backup, recovery, rotation, and shutdown (R3)

## Backup

Use `scripts/release/backup-aegis.sh` from the repository root. It writes a new
absolute output directory only and records SHA-256 checksums for: PostgreSQL
logical dump, canonical evidence-storage archive, Wazuh `pending/` and
`quarantine/` spool archive, and a version/config hash manifest. It deliberately
does not archive Docker secrets, environment files, private keys, or host
configuration. Evidence itself remains sensitive provenance and must be stored
encrypted with access control; it is not silently filtered because exact
provenance is required.

Redis is non-authoritative and rebuildable from PostgreSQL-backed run
reconciliation. The optional Ollama model volume is a preserved deployment
dependency, not authoritative application state; either preserve it separately
or rebuild it under the approved model-operating procedure. Do not include
model data in the logical backup bundle.

## Restore

`scripts/release/restore-aegis.sh` requires both a project name beginning
`aegis-restore-` and `--confirm-destructive-restore`. It refuses any namespace
with existing containers or Compose-labelled volumes, refuses an existing spool
target, verifies checksums first, and never calls `down`, `rm`, or a volume
delete command. Supply a fresh isolated Compose namespace only; it must never
be a normal development or production namespace.

After restore verify: `alembic current` is `0024`, the organization and rotated
administrator can authenticate, Investigation counts match the manifest,
sampled evidence hashes match, Wazuh RawEvent-to-CanonicalAlert provenance is
intact, and Intelligence Run states/leases are sensible. Do not start provider
execution as part of a restore drill.

## Credential rotation

Rotation has a bounded interruption window because the architecture supports
one active JWT/connector secret at a time:

- JWT signing secret: stop API, worker, and beat; replace the Docker secret;
  start migrate/API, then worker/beat. Existing sessions are invalidated.
- PostgreSQL credential: stop API/worker/beat, rotate the database role and
  Docker secret together, then start migrate/API/worker/beat. Never rotate one
  side first and leave services repeatedly failing authentication.
- Wazuh connector credential: create/rotate through the connector authority,
  write the new value only to the Manager secret file, verify permissions, then
  restart/reload the integration. Existing forwarder records stay unchanged.
- Administrator password: use the authenticated self-rotation route from R1;
  verify the old credential is rejected and the new credential authenticates.

## Controlled shutdown and startup

Pause ingress/forwarder first and allow or account for every pending spool
record. Drain or explicitly record queued/running Intelligence Runs, then stop
worker/beat, API/frontend, and only then PostgreSQL/Redis/Ollama. Named volumes
are preserved by `docker compose stop` and normal `docker compose down`.
`docker compose down -v` destroys named volumes and requires a separate,
explicit operator confirmation after backup verification. Startup reverses the
order: stateful services, one-shot migration, API/frontend, then worker/beat;
start Ollama only when explicitly required.

## Repository secret scan

Run `scripts/release/scan-secrets.sh` from the repository root before a release.
It scans tracked HEAD files and up to 500 reachable history commits for
high-confidence private-key/AWS/GitHub-token formats. It emits candidate paths
and revision identifiers only, never matched values. Any candidate blocks the
release pending security review. Synthetic fixtures are allowed only when they
are clearly non-routable test markers, documented in the review, and do not
match a high-confidence credential format. Rotate and purge a real secret
through the approved incident process; never paste it into issue comments or
scan output.
