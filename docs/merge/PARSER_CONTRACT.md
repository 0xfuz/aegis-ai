# Parser Contract — Phase 2

## Boundary

Phase 2 parsers are deterministic, local, synchronous Python components. They
have no AI, shell, external-network, archive, executable, or reputation API
dependency. Their output is factual only.

## Interface

Every parser provides:

- `parser_id`: extensible stable string;
- `parser_version`: extensible stable string;
- `supported_extensions` and `supports(filename, detected_mime)`;
- `parse(content) -> list[ParsedRecord]`;
- deterministic normalization into a `NormalizedEvent` only for defensible
  fields present in source content.

`ParsedRecord` contains immutable source content/reference fields, optional
normalized Event data, Entity candidates, and evidence-supported relationship
candidates. Parser output does not write the database; the ingestion service
owns persistence and provenance.

## Registered parsers

| Parser | Version | Inputs | Deterministic behavior |
|---|---:|---|---|
| `plain-text` | 1.0.0 | `.log`, `.txt` | Preserves non-empty lines; recognizes narrow SSH authentication and process-log forms; does not invent syslog year/timestamp. |
| `json` | 1.0.0 | `.json` | Accepts object or array of objects, serializes each RawRecord in sorted-key JSON form, maps known field aliases only. |
| `csv` | 1.0.0 | `.csv` | Requires non-empty headers, rejects over-wide rows, maps known field aliases only. |

Supported normalized fields are timestamp (only timezone-aware ISO input),
source, host, user, process, source/destination IP and port, event type,
action, directly supplied severity, and parser-specific JSON. Missing or
ambiguous values remain null.

## Extraction rules

- Indicators: IPv4, IPv6, domain, URL, email, MD5, SHA-1, SHA-256; normalized
  deterministically and written with occurrence-level RawRecord/Event links.
- Entities: host, user, IP, domain, file, process. Canonicalization is
  conservative lowercase normalization for host/user/domain/process/file only.
- Relationships: only `logged_into`, `executed_on`, `connected_to`, and
  `resolved_to` when both endpoint Entities arise from the same source record.

No parser assigns maliciousness, confidence, ATT&CK technique, attack stage,
root cause, or AI output. Parser/normalizer IDs and relationship/event types are
validated strings, not database enums.

## Bounds and failure behavior

The ingestion service applies configured limits before persistence becomes
active: evidence bytes, raw record length/count, events, extracted indicators,
entities, and JSON nesting depth. Parser exceptions or limit failures roll back
all derived facts from that run, retain the original accepted EvidenceItem, and
record a failed ParseRun plus audit event.
