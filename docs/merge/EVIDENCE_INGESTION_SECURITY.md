# Evidence Ingestion Security — Phase 2

## Storage controls

- Evidence root is `EVIDENCE_STORAGE_DIR` (default `/app/storage/evidence`),
  outside public/static frontend paths and ignored by source control.
- The storage key is a server-generated 128-bit opaque hexadecimal token.
  Original filenames are metadata only and never become a filesystem path.
- Storage paths are resolved and required to have the configured evidence root
  as direct parent. Paths containing traversal components are rejected before
  writing.
- Files are streamed in 64 KiB chunks, SHA-256 is calculated during the same
  stream, size is enforced while reading, and empty files are rejected.
- Writes use exclusive create. A failed storage/initial persistence attempt
  removes the stored bytes. A parse failure retains accepted original bytes and
  marks the parse lifecycle failed; partial derived FACT records roll back.

## Content controls

- Only `.log`, `.txt`, `.json`, `.csv` are accepted.
- Declared MIME must be compatible with extension; image/archive MIME claims are
  rejected. Parser validation still treats all content as untrusted.
- Input must be UTF-8 text. There is no execution, shell-out, archive
  extraction, unpacking, malware detonation, browser HTML rendering, or external
  lookup.
- Raw evidence is returned as data through authenticated case-scoped APIs only.
  Controlled download resolves an opaque DB storage key after auth and sends an
  attachment response; no storage-key route exists.

## Authorization and audit

- Upload requires `investigation:write`; factual retrieval/download requires
  `investigation:read` and filters by both organization and Investigation ID.
- AuditEvent records evidence accepted, rejected, duplicate, parse started,
  parse completed, parse failed, and controlled download.
- Canonical evidence FK relationships remain restrictive. No destructive case
  deletion can cascade through canonical facts.

## Resource limits

Defaults: 5 MiB evidence, 64 KiB raw record, 10,000 raw records/events,
50,000 extracted indicators/entities, and JSON depth 32. They are environment
settings and should be reduced for constrained deployments. Parser execution is
synchronous only because these bounded files are Phase 2 scope; worker/queue
is deferred.
