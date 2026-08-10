# Phase 7.8 Implementation Plan

This plan remains design-led; Phase 7.8.1 has implemented only the pure mapper foundation described below. No public ingress or downstream production behavior has been added.

## Phase 7.8.1 status

The fixture-first pure mapper foundation is complete. Six sanitized fixtures and focused mapping tests cover Windows authentication, Linux process/authentication, network, file-integrity, source MITRE metadata, and sparse alerts. This is not public ingestion: no HTTP route, Wazuh Manager script, connector mutation, retry spool, or live lab has been added. The next implementation step remains the reviewed Wazuh-specific ingress boundary from step 3 below.

## Phase 7.8.2 status

The dedicated Wazuh HTTP boundary is complete: bounded authenticated ingress, RawEvent provenance, pure mapping, CanonicalAlert exact replay/semantic dedupe, correlation-v2-only membership, and version-aware triage reads. No Wazuh Manager forwarder, durable spool, live lab, reverse proxy, UI, rollout, or correlation/triage scoring change was introduced.

## Phase 7.8.3 status

The standalone Manager-side forwarder and durable disk spool are complete in `integrations/wazuh`. It posts unchanged Wazuh JSON to the frozen v2 endpoint, uses environment-supplied connector secrets, atomically persists retry state, and quarantines permanent/corrupt/exhausted deliveries. Wazuh installation configuration, a live manager, lab, proxy policy, and rollout remain deferred.

## Phase 7.8.4 status

Disposable Manager/Agent validation completed with a real Agent SCA alert, end-to-end v2/triage delivery, replay, outage recovery, and permanent-failure quarantine. Lab-only resources are cleaned up after evidence capture. Production rollout, forwarder installation, proxy/mTLS policy, and operational monitoring remain deferred.

## Exact proposed implementation sequence

1. Confirm supported Wazuh manager version(s), collect sanitized JSON fixtures for Windows, Linux/syslog, FIM, and network decoders, and approve the mapping contract/profile precedence.
2. Add a Wazuh connector type/configuration only if necessary; preserve existing webhook connector authentication, one-time secret disclosure, and tenant derivation.
3. Add a Wazuh-specific bounded request schema and endpoint. It accepts no tenant, cluster, priority, verdict, or promotion fields.
4. Implement a pure, deterministic Wazuh mapper from the reviewed envelope to `CanonicalAlertCreate`; preserve original JSON in `RawEvent`; add bounded mapping diagnostics.
5. Add Wazuh orchestration: authenticate connector, persist raw event, canonical-create, existing exact replay, existing semantic dedupe, **correlation-v2 only**, then triage-v1. Do not touch generic v1 webhook behavior.
6. Implement the Wazuh manager custom forwarder with HTTPS, secret handling, timeouts, an encrypted/restricted durable spool, exponential retry/jitter, 4xx quarantine, and delivery telemetry.
7. Add the full test matrix in `WAZUH_TEST_PLAN.md`, including no-auto-investigation and v1/v2 isolation regressions; run focused Docker/PostgreSQL tests with `DEBUG=true`.
8. Deploy a disposable lab (below), observe normal/retry/replay flows, and document measured behavior and limits before any production rollout.
9. Conduct security review for ingress CIDRs/mTLS, secret rotation, logging redaction, spool permissions/retention, and tenant-isolation tests.
10. Roll out to one non-production tenant with explicit operations runbook and rollback (disable connector/forwarder); only then consider broader integration.

## Disposable live-lab plan

Run isolated containers or VMs for a Wazuh manager, one Wazuh agent, and Aegis with a dedicated PostgreSQL database. Put the forwarder on the manager network and expose only Aegis HTTPS ingest to that network. Use a throwaway connector and secret.

Generate only safe, benign events: failed login to a dedicated test account, successful login to that account, a harmless shell command/process execution, a temporary-file create/modify/delete in a lab directory monitored by FIM, and a local test HTTP request. Do not run exploit payloads, persistence, credential attacks, destructive commands, or active response.

For every event, record and verify:

1. Wazuh alert JSON and forwarder delivery status.
2. Aegis `RawEvent` payload digest and connector provenance.
3. Canonical normalized projection and replay behavior.
4. v2-only cluster membership/reasons and absence of cross-org or v1 contamination.
5. Triage-v1 assessment.
6. Zero automatic Investigation/promotion/FACT/Finding/AIIE/MITRE-fact creation.

Induce a controlled Aegis outage and a malformed fixture in the lab to verify spool, retry, quarantine, and recovery observability. Destroy the lab database, connector secret, spool, and test data after sign-off.
