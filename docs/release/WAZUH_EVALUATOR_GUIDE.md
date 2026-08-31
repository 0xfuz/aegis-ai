# Wazuh evaluator guide

This optional path begins only after the [Core-mode quickstart](DEPLOYMENT_QUICKSTART.md)
is healthy. It documents the existing Wazuh 4.9.2 TLS-forwarder contract. Wazuh
is the only external integration validated end-to-end; this guide does not add
Splunk, Sentinel, Elastic, public ingress, or a second connector type.

Previously certified R4 acceptance established the real Wazuh path. This guide
is documentation only: an evaluator must perform its own approved Wazuh and
TLS walkthrough. Do not run these steps against R4 or an unrelated Manager.

## Preconditions

- Core API and frontend health checks pass, migration is at `0024`, and the
  evaluator owns the Core PostgreSQL/evidence state.
- A private TLS-terminating endpoint is available to the Manager network. It
  must route to the loopback-bound Aegis API, present a trusted CA chain, and
  use a hostname in the certificate SAN. Do not expose a public destination.
- The scope is Wazuh Manager `4.9.2`, `integratord`, the repository's
  `custom-aegis` wrapper, and `forwarder.py`. Vulnerability Detection is not
  required for this delivery path.
- An active analyst with `settings:manage_connectors` can create the connector.

## Configure the private Aegis TLS endpoint

Keep frontend CORS and loopback ports from Core mode. In the protected external
`core.env`, set `PUBLIC_API_BASE_URL_REQUIRED` to the private HTTPS origin used
by the TLS proxy, then recreate only the API so newly created connector URLs
use that origin:

```sh
docker compose --project-name aegis-core --env-file "$AEGIS_STATE_DIR/core.env" \
  -f docker-compose.production.yml up -d --build api
curl --fail http://127.0.0.1:18000/api/v1/health
```

The proxy certificate/private key lifecycle belongs to the evaluator. Keep the
private key `0600` and its directory `0700`; validate the CA, exact hostname,
and expiry from the Manager network. Never use plaintext HTTP, a TLS bypass,
or a wildcard hostname.

## Create the authenticated connector

Sign in to the healthy Aegis frontend as the active permitted user. Go to
**Settings**, enter an evaluator-specific connector name, and select **Add
webhook connector**. This uses the existing authenticated
`POST /api/v1/connectors/webhook` authority; organization scope is derived from
the signed-in principal.

The UI shows the connector ID, ingest URL, and one-time secret exactly once.
Record the ID and write the secret directly into the Manager's protected secret
file. Do not put the secret in a shell argument, URL, environment file,
repository file, screenshot, ticket, or the UI's generic curl example. The
secret is not retrievable later; create/rotate through the same connector
authority if it is lost.

## Install the existing Manager integration

On the evaluator-owned Wazuh Manager, install only the repository-provided
files and protect their permissions:

```sh
sudo install -o root -g wazuh -m 0750 -D \
  integrations/wazuh/forwarder.py /opt/aegis/integrations/wazuh/forwarder.py
sudo install -o root -g wazuh -m 0750 \
  operations/wazuh/custom-aegis /var/ossec/integrations/custom-aegis
sudo install -o root -g wazuh -m 0750 -d /etc/aegis
sudo install -o wazuh -g wazuh -m 0700 -d /var/ossec/var/aegis-forwarder-spool
```

Create `/etc/aegis/wazuh-forwarder.conf` with non-secret values only. Use the
private HTTPS origin and the ID shown by Settings; retain TLS verification:

```text
AEGIS_WAZUH_BASE_URL=https://PRIVATE_AEGIS_HOSTNAME
AEGIS_WAZUH_CONNECTOR_ID=<connector-id>
AEGIS_WAZUH_INGEST_SECRET_FILE=/etc/aegis/wazuh-ingest-secret
AEGIS_WAZUH_SPOOL_DIR=/var/ossec/var/aegis-forwarder-spool
AEGIS_WAZUH_VERIFY_TLS=true
```

Write the one-time connector credential alone to
`/etc/aegis/wazuh-ingest-secret` through the evaluator's approved local secret
method, then set the config and secret files to `root:wazuh 0640` (or
`wazuh:wazuh 0600`). Do not print the secret while creating or verifying the
file.

Add the approved `<integration>` entry to the Manager's
`/var/ossec/etc/ossec.conf` using `custom-aegis` as its name and retaining the
Manager-provided alert-file argument. The exact XML surrounding that entry is
owned by the evaluator's deployed Wazuh 4.9.2 configuration; do not add
credentials, endpoints, or arbitrary arguments there. Restart the private TLS
proxy first, then use the Manager's normal package/container lifecycle to
restart the integration.

## One bounded benign delivery

In an isolated evaluator Manager only, use the existing demo rule
`operations/wazuh/demo/aegis-agentless-demo.xml` through the Manager's local
4.9.2 demo-rule loading convention. Emit exactly one harmless agentless/syslog
line containing `AEGIS_R3_AGENTLESS_DEMO_LITERAL`; do not manually invoke the
forwarder or post to Aegis.

Verify in the Aegis UI, using the connector-scoped alert/triage surfaces, that
one delivery produces a RawEvent, CanonicalAlert, correlation-v2 membership
when applicable, and version-aware triage. The exact replay must increase
occurrence history rather than CanonicalAlert count. Promotion remains an
explicit analyst action; the delivery must not create a Finding, confirmed
MITRE mapping, provider run, claim, or action.

Use bounded local operational checks only:

```sh
sudo find /var/ossec/var/aegis-forwarder-spool/pending \
  /var/ossec/var/aegis-forwarder-spool/quarantine -maxdepth 1 -type f -printf '%f\n'
docker compose --project-name aegis-core --env-file "$AEGIS_STATE_DIR/core.env" \
  -f docker-compose.production.yml logs --tail=50 api
```

Do not print alert files, secret files, payloads, headers, or environment
values. Acknowledged `200` replay or `201` accepted delivery removes its
pending record. Timeout/network/`429`/`5xx` conditions retry from pending;
other `4xx`, corrupt records, or exhausted retry limits enter quarantine. Fix
TLS, path, or credential issues before any separately approved replay; never
rewrite a spool record or manually post its payload.

## Stop and evaluator-only removal

Stop the Manager integration first, then the private TLS proxy. Stop Aegis Core
only through the [Core-mode quickstart](DEPLOYMENT_QUICKSTART.md) when the
evaluator is also ending that local deployment.

Before removal, record which integration files existed before the evaluation.
Remove only evaluator-created copies of the wrapper, forwarder, config, secret,
demo rule, and spool directory after the Manager integration is stopped. Do
not delete an existing Manager configuration, TLS materials, alert history,
Wazuh rules, Aegis PostgreSQL/evidence volumes, or another evaluator's spool.
