# Generic Alert Webhook (Phase 7.6)

`POST /api/v1/ingest/alerts/v1/{connector_id}/{source}` accepts one versioned generic alert. It is an ingestion boundary only: it never creates an Investigation, EvidenceItem, FACT, AIIE analysis, Finding, or MITRE mapping.

## Authentication and scope

Send the connector secret in `X-Ingest-Secret`. The endpoint derives the organization exclusively from the authenticated active, `connected` Connector; `organization_id` is not accepted in the payload. The URL `source` must exactly match the required payload `source`, preventing a request from claiming a different source identity for the endpoint.

## Payload

`application/json` is required. The body uses this v1 contract (all unknown fields are rejected):

```json
{
  "source": "suricata",
  "source_alert_id": "external-123",
  "observed_at": "2026-08-09T12:00:00Z",
  "title": "Suspicious outbound connection",
  "description": "Untrusted source text",
  "severity": "high",
  "category": "network",
  "rule_id": "rule-42",
  "rule_name": "Optional rule name",
  "signature": "Optional signature",
  "source_ip": "198.51.100.22",
  "destination_ip": "203.0.113.20",
  "hostname": "web-01",
  "username": "analyst",
  "process": "curl",
  "file": "/tmp/file",
  "domain": "example.test",
  "url": "https://example.test/path",
  "source_metadata": {"vendor_field": "untrusted metadata"}
}
```

`source_alert_id`, timezone-aware `observed_at`, title, severity, and source identity are required. Severity normalizes to the frozen canonical enum. Existing canonical validators enforce IP/URL syntax, observable lengths, metadata JSON size (64 KiB) and depth (32), and timestamp awareness.

## Provenance and pipeline

The received, validated JSON is stored in the existing `connector_raw_events` row. The existing `CanonicalAlertService` links it to `CanonicalAlert.raw_event_id`; no second raw store is created.

For a new alert the domain orchestration is: CanonicalAlert → deterministic semantic deduplication → deterministic correlation → triage-v1 assessment. For an exact replay, existing occurrence/replay history is appended and existing cluster/assessment state is returned without rerunning correlation or inflating membership/score. Semantic duplicates remain canonical/provenanced but receive no cluster membership.

Responses expose only `accepted`/`replayed`, canonical alert ID, dedupe status, current cluster ID, score/priority, and correlation/triage versions. They do not expose raw payloads, secrets, or cross-tenant data.

## Limits and errors

- `application/json` only; malformed/invalid input is `422`.
- Body limit is 256 KiB before parsing.
- Invalid/inactive/disabled connector secret is `401`.
- Connector-local, in-process rate control permits 60 requests per 60 seconds and returns `429` beyond that burst.
- All text and metadata are data only; the webhook does not execute, render, template, or prompt on source content.

Canonicalization commits `RawEvent` and CanonicalAlert provenance before deterministic downstream processing. If a later dedupe/correlation/triage stage fails, the accepted source record remains recoverable and no partial cluster/promotion/FACT state is fabricated. Production-scale delivery needs a durable outbox/queue, multi-process distributed rate limiter, retry lease, and dead-letter/reconciliation worker; those are deliberately deferred.
