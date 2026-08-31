# Wazuh Manager operations (R3)

This runbook targets the certified **Wazuh Manager 4.9.2** path only. It uses
the established delivery chain, never a manual Aegis `POST`:

`Wazuh alert JSON -> integratord custom-aegis -> durable forwarder -> authenticated Aegis Wazuh webhook`.

## Verified Manager layout and installation

The official local `wazuh/wazuh-manager:4.9.2` image was inspected at digest
`sha256:b906ebfc77d78446e9b676e1a0b3cd78e2bf3ac2341688f1726b09c29e0aa826`.
It creates user/group `wazuh` (`999:999`), runs manager components as
`wazuh:wazuh`, and initializes `/var/ossec/integrations` as `root:root 0755`.
`/var/ossec` is `root:wazuh 0750`; `etc` and `logs` are `wazuh:wazuh 0770`.

Install the repository's `integrations/wazuh/forwarder.py` as
`/opt/aegis/integrations/wazuh/forwarder.py`, and install
`operations/wazuh/custom-aegis` as `/var/ossec/integrations/custom-aegis`.
Set both integration files `root:wazuh 0750`. Create `/etc/aegis` as
`root:wazuh 0750`; its config and secret files are `root:wazuh 0640` (or
`wazuh:wazuh 0600`). Create the forwarder spool root as `wazuh:wazuh 0700` so
the unprivileged `integratord` process can create its private `pending/` and
`quarantine/` directories. This gives the Wazuh process only the access it
needs without making credentials or delivery records world-readable. Recheck
these owners on package upgrades.

Create `/etc/aegis/wazuh-forwarder.conf` with only non-secret settings:

```sh
AEGIS_WAZUH_BASE_URL=https://aegis.example.invalid
AEGIS_WAZUH_CONNECTOR_ID=<connector-id>
AEGIS_WAZUH_INGEST_SECRET_FILE=/etc/aegis/wazuh-ingest-secret
AEGIS_WAZUH_SPOOL_DIR=/var/ossec/var/aegis-forwarder-spool
AEGIS_WAZUH_VERIFY_TLS=true
```

The secret file holds the connector credential alone; it is not an argument,
environment-file value, integration XML value, or repository file. The wrapper
fails closed unless the target is HTTPS and the file is readable. For a
non-loopback Aegis endpoint, use a trusted CA and leave TLS verification on.
`AEGIS_WAZUH_VERIFY_TLS=false` is limited to disposable localhost development.

Add the approved Wazuh `<integration>` entry in the Manager's
`/var/ossec/etc/ossec.conf` according to the deployed 4.9.2 configuration;
use `custom-aegis` as the integration name and retain the Manager-provided
alert file argument. Wazuh 4.9.2 appends Manager integration arguments; the
wrapper selects the single readable alert artifact and ignores all other
arguments. Restart the Manager using its package/container lifecycle.
Do not invoke `forwarder.py` by hand against an Aegis endpoint as acceptance
evidence.

## Delivery operations

The forwarder preserves the original JSON. It atomically writes `0600` records
in a `0700` spool with `pending/` and `quarantine/`. It acknowledges only HTTP
`200` (replay) or `201` (accepted), then removes the pending record. Timeout,
network, `429`, and `5xx` results retry with jittered exponential delay: 5
seconds initial, 300-second cap, 20 attempts or 24 hours. Other `4xx`, corrupt
records, and exhausted retries move to quarantine; quarantine has no automatic
resend.

Inspect records locally as the authorized operator. Do not paste payloads into
tickets. Record the digest, reason, timestamps, and attempt count. Validate a
fixed credential/path/TLS issue first, then perform an explicitly approved
replay workflow; do not rewrite the payload or manually send it to Aegis.

## Separate benign demonstration

`operations/wazuh/demo/aegis-agentless-demo.xml` is demo-only and must not be
copied into production detection-rule directories. It is rule `100500`, level
3, and matches the exact bounded literal `AEGIS_R3_AGENTLESS_DEMO_LITERAL`.
It deliberately does **not** use the rejected `decoded_as=syslog` condition.

In an isolated Manager, place it in a demo-only rules directory, enable it by
the local 4.9.2 rule-loading convention, and emit exactly one harmless
agentless/syslog line containing that literal. Verify, in order:

1. Manager produces alert JSON with rule `100500`.
2. `integratord` invokes `custom-aegis`, which queues the unchanged JSON.
3. Acknowledged delivery creates a connector-scoped RawEvent and CanonicalAlert.
4. Exact replay increases occurrence history rather than CanonicalAlert count.
5. Any correlation is `correlation-v2` only; triage is version-aware.
6. Promotion remains an explicit analyst action.

The demonstration must create no automatic Finding, confirmed MITRE mapping,
action, provider run, or claim.

## TLS certificate expiry and rotation

Before starting a Manager integration, inspect the proxy certificate subject,
issuer, SANs, validity window, and fingerprint. The configured forwarder
hostname must appear as an exact SAN; do not use wildcard certificates. Keep
the proxy private key `0600` and the containing rotation directory `0700`.

Back up the current certificate and key to a protected operator-only location
before replacement. Rotate the trust anchor and server certificate together
when the existing CA is expired or otherwise unsuitable. Validate the new
chain from the forwarder network context with normal CA and hostname
verification: the configured hostname must succeed, while an unrelated CA and
wrong hostname must fail. Do not disable TLS verification, use plaintext HTTP,
or add a bypass endpoint.

Restart the proxy first, then the Manager integration. Allow any existing
durable pending record to receive its normal retry opportunity and inspect the
acknowledgement, pending, and quarantine counters. Do not rewrite the record
or manually POST its payload. Keep expired material only as protected
diagnostic evidence for the defined retention period.

When a Manager restart follows a retained pending startup alert, two Rule 502
records can be legitimate: one is the acknowledged alert from the earlier
Manager process start, and one is the alert from the current process start.
Each must have a distinct authoritative Wazuh alert identity and exactly one
RawEvent, CanonicalAlert, correlation-v2 membership, and triage assessment.
A loop is instead an additional Rule 502 without another Manager start,
repeated delivery of one source identity, duplicate membership, or unexpected
spool growth. Establish a baseline after the expected current-start append and
observe it before treating the path as stable.

## Vulnerability Detection operational boundary

Wazuh Vulnerability Detection is not required for the durable `custom-aegis`
integration path. Monitor Manager disk capacity and
`/var/ossec/queue/vd_updater/tmp` during operation: the `vd_updater` temporary
workspace can grow independently of alert forwarding. Never delete the
Vulnerability Detection feed, alerts, integrations, rules, TLS material, or
forwarder spool as a space-recovery shortcut.

For a disposable capacity-constrained lab, disable Vulnerability Detection only
through the Manager's locally verified configuration workflow, after backing
up its configuration and validating it before restart. Recheck analysisd,
integratord, the custom integration, TLS configuration, and spool ownership
afterward. Production enablement or disablement is an operator capacity
decision and must be monitored; it does not change Aegis ingestion semantics.
