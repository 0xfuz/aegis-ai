# Wazuh Alert Adapter Architecture

## Decision

Phase 7.8 should use **a Wazuh Manager custom integration script that pushes one JSON alert to a dedicated Aegis Wazuh alert endpoint over HTTPS**. It is the smallest reliable first integration: Wazuh already supports custom integrations, passes an alert-file location to the script, and can emit JSON alerts. It avoids giving Aegis Wazuh API credentials, polling state, and a second alert cursor to operate. See the [Wazuh external integration documentation](https://documentation.wazuh.com/current/user-manual/manager/integration-with-external-apis.html).

The script is a bounded transport and mapping adapter, not a decision-maker. It sends the full Wazuh alert as the preserved raw payload and sends only the deterministic projection defined in the mapping contract. It must not create investigations, select an Aegis organization, assign a verdict, or declare MITRE facts.

```
Wazuh agent/event → Wazuh Manager rule/decoder → custom forwarder
  → HTTPS + connector secret + network allowlist → Aegis Wazuh endpoint
  → RawEvent (original Wazuh JSON) → Wazuh mapping/CanonicalAlert validation
  → exact replay → semantic deduplication → correlation-v2 → triage-v1
  → analyst-controlled promotion only
```

## Existing Aegis components to reuse

| Component | Reuse in Phase 7.8 |
| --- | --- |
| `Connector` / `ConnectorService.create_webhook_connector` | One connector per tenant/Wazuh deployment; secret is shown once and organization derives solely from connector ID. |
| `IngestService.authenticate_connector` | Existing connector-secret verification and inactive-connector rejection. |
| bounded generic-alert ingress controls | Reuse JSON-only handling, 256 KiB request limit, and per-connector rate limit; Wazuh gets a vendor-specific endpoint and schema rather than bypassing them. |
| `RawEvent` | Store original received Wazuh JSON before canonical mapping; connector provenance remains immutable. |
| `CanonicalAlertCreate` / `CanonicalAlertService` | Sole canonical creation boundary, normalization, source identity uniqueness, and exact replay occurrence recording. |
| `AlertDeduplicationService` | Existing semantic duplicate treatment, unchanged. |
| `AlertCorrelationV2Service` | Invoke after a unique canonical alert, with no Wazuh-specific algorithm change. |
| `AlertClusterTriageService` | Existing deterministic assessment only. |
| `AlertClusterPromotionService` | No automatic call. Promotion remains an authenticated analyst action. |

The current generic webhook orchestrator uses correlation-v1. Phase 7.8 must add a separate Wazuh orchestration boundary which explicitly calls v2; it must not silently alter the generic endpoint’s existing versioned behavior.

## Delivery alternatives

| Option | Assessment |
| --- | --- |
| A. Wazuh custom webhook/integration script | **Recommended.** Minimal state, immediate delivery, preserves native alert JSON, and fits Wazuh’s documented integration model. The script needs a durable local spool for retries. |
| B. Aegis polling Wazuh API | Not first choice: adds privileged Wazuh API credentials, cursor/outage semantics, API-version coupling, and more exposed control-plane access. |
| C. Queue/forwarder intermediary | Suitable later for multi-manager/high-volume deployments; adds operations and does not replace the canonical boundary. Start only if measured volume or availability requirements justify it. |

## Operational shape

- Configure Wazuh `jsonout_output=yes`; filter the custom integration by a documented minimum rule level/group only when the SOC explicitly chooses that coverage.
- Run the forwarder on each Wazuh manager node; its outbound route reaches only the Aegis ingress/load balancer.
- Provision a distinct Aegis connector per tenant and Wazuh deployment. A connector never accepts an organization ID from a vendor payload.
- Keep the Wazuh endpoint separate from the legacy investigation webhook and generic v1 alert endpoint. Its request schema accepts only the Wazuh envelope and mapping-supported fields.
- Retain response status, alert ID, and payload digest in forwarder logs without logging connector secrets or full hostile payloads.
