# Generic Connector Contract

Connectors are adapters from external source format to a canonical alert intake command. They authenticate, validate source-specific payloads, preserve raw provenance, and normalize. The Phase 7.6 generic webhook then delegates deduplication, correlation, and triage to their existing domain services; it never promotes Investigations, calls AI, or creates Findings/MITRE mappings.

## Proposed adapter interface

```text
authenticate(request) -> ConnectorContext(org_id, connector_id, type, configuration version)
validate_and_bound(raw request) -> RawPayload
persist_raw_intake(context, raw payload) -> RawIntakeReference
normalize(context, raw payload, raw reference) -> CanonicalAlertInput
submit(input) -> IntakeResult(alert_id, occurrence_id, dedupe disposition)
```

`CanonicalAlertInput` supplies source alert identity/times, detection fields, observable candidates, source metadata, raw intake reference, and normalizer version. It has no `organization_id` supplied by the caller and no Investigation/cluster/priority/Finding fields.

## Source adapters

- **Generic Webhook**: first future alert adapter. Its versioned documented JSON schema maps to CanonicalAlertInput. The existing `/ingest/webhook/{connector_id}` endpoint is legacy and remains unchanged until an explicit migration/versioned endpoint is approved.
- **Wazuh, Splunk, Elastic, Suricata, Defender/Sentinel**: translate their native API/webhook/poll result into the same input. Polling cursor/checkpoint handling belongs to the adapter/job layer, not the correlation service.

Each connector record should eventually carry type, active state, secret/certificate reference, safe configuration metadata, normalizer version, and source identity policy. Existing `Connector` and hashed secret approach are reusable; avoid duplicating a second connector credential store.

## Security and reliability requirements

- Authenticate before accepting content; use constant-time secret verification already established by the connector service. Add rate limits, allowed content type, maximum request body/JSON depth, and optional IP/mTLS policy in the implementation phase.
- Persist only encrypted/controlled raw payloads and digests appropriate to the storage policy. Never log plaintext secrets or unbounded payloads.
- Source names and connector types are server-configured. A payload cannot claim to be Sentinel/Wazuh or select another tenant.
- The adapter assigns an idempotency/replay key and emits a stable source identity. Return a disposition for retries without exposing other organizations’ alert IDs.
- Treat all description, command line, URL, hostname, and MITRE values as untrusted data. Source MITRE is advisory detection metadata only.

## Implemented generic webhook

`POST /api/v1/ingest/alerts/v1/{connector_id}/{source}` is the additive generic ingress route. It uses the existing connector secret (`X-Ingest-Secret`), derives organization from the connector, requires the body `source` to match the path source, persists existing `RawEvent` provenance, and delegates to Phase 7.1–7.4 services. The legacy `/ingest/webhook/{connector_id}` route remains unchanged.

The exact payload, response, limits, replay behavior, and deferred production scaling controls are documented in [GENERIC_WEBHOOK.md](GENERIC_WEBHOOK.md).

## API direction

Admin connector management can extend the existing `/connectors` surface through backward-compatible fields/routes. Analyst alert/cluster API routes should be authenticated and organization-scoped under `/api/v1/alert-triage`; public ingestion must never expose those operations.
