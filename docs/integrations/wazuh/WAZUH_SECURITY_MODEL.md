# Wazuh Integration Security Model

## Trust boundary

```
Untrusted Wazuh alert content
  → authenticated connector boundary (connector ID + secret)
  → request bounds and syntax validation
  → immutable RawEvent provenance
  → allowlisted Wazuh mapping and CanonicalAlert validation
  → tenant-scoped dedupe/correlation-v2/triage
```

The connector row supplies `org_id`; the payload has no organization, connector-status, canonical ID, cluster ID, priority, analyst, or promotion fields. Wazuh descriptions, decoder fields, labels, `full_log`, and MITRE annotations are source assertions, never Aegis facts or commands.

## Required controls

| Risk | Required design control |
| --- | --- |
| Connector authentication | HTTPS only; `X-Ingest-Secret` verified against the connector’s stored hash; uniform unauthorized response; inactive connector rejected. |
| Network source | Ingress restricted to Wazuh manager/forwarder egress CIDRs at load balancer/firewall; optional mTLS between forwarder and Aegis. IP allowlisting supplements, never replaces, connector-secret authentication. |
| Oversized/malformed input | JSON-only content type; stream body with the existing 256 KiB limit before parse; schema/depth/metadata bounds; return 4xx without creating a canonical alert. |
| Hostile text | Never interpolate into queries, logs, HTML, shell commands, or prompt instructions. Length-bound title/description/metadata; keep raw content as data only. |
| Replay flood | Canonical source identity provides exact replay handling; rate limit per connector before expensive processing; forwarder exponential backoff with jitter and bounded spool. |
| Tenant isolation | Connector lookup derives org; every canonical, dedupe, correlation, triage, and promotion query remains org-scoped. Separate connector secret per tenant/deployment. |
| Secret lifecycle | Show secret once, store only hash, redact it from logs/config dumps, support overlap-based rotation (new secret active before old revocation), and deactivate compromised connectors. |
| Availability | Forwarder uses encrypted/restricted local spool with byte/count/age limits and operator-visible overflow alarms; no silent drop. |
| Network placement | Aegis ingress is reachable only from forwarders; neither Aegis nor agents require inbound access to Wazuh manager. Do not expose Wazuh API for the initial design. |

## Retry and failure semantics

| Condition | Forwarder / Aegis behavior |
| --- | --- |
| Aegis unavailable, timeout, TLS failure, 5xx, temporary DB failure | Do not acknowledge as delivered; retain the exact JSON in local spool; retry exponential backoff with jitter. Alert operators before spool limits are reached. |
| 201 accepted | Mark spooled item delivered only after response; resulting canonical/cluster data may be returned for logging. |
| 200 replayed | Mark delivered. Existing exact-replay occurrence semantics remain authoritative. |
| 400 malformed mapping or invalid canonical field | Non-retryable quarantine with reason/payload digest; alert operator. Do not silently discard. |
| 401/403 | Stop rapid retries, quarantine/alert; indicates bad or rotated credentials/allowlist. |
| 429 | Respect `Retry-After` if supplied; otherwise retry with backoff. |
| Partial processing crash | Aegis transaction rollback means no accepted state; retry exact payload. If RawEvent/canonical creation committed before a response loss, retry becomes exact replay rather than duplicate canonical state. |
| Out-of-order alert | Accept with its source timestamp; canonical identity/replay is independent of arrival order. Existing time-window semantics determine whether correlation occurs. |

The implementation must emit security/audit telemetry for authentication failures, bounds rejections, rate limits, mapping failures, spool depth, and retry exhaustion without exposing secrets or raw hostile content.

## Phase 7.8.2 implemented ingress controls

The dedicated route now enforces JSON content type, streamed 256 KiB request limiting before parsing, object-only JSON, authenticated active connector, and existing per-connector rate limiting. It returns bounded machine responses and does not log secrets or raw payloads. Network allowlisting/mTLS, a Manager forwarder, spool/retry telemetry, and proxy configuration remain deferred infrastructure work.
