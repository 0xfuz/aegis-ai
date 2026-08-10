# Wazuh Manager Forwarder

Phase 7.8.3 adds the standalone package `integrations/wazuh/forwarder.py`. It is intended as the executable behind a Wazuh custom integration script: Wazuh supplies an alert JSON file path, the forwarder queues the unchanged JSON, then posts it to `POST /api/v1/ingest/wazuh/v1/{connector_id}`.

Configuration is environment-only: `AEGIS_WAZUH_BASE_URL`, `AEGIS_WAZUH_CONNECTOR_ID`, `AEGIS_WAZUH_INGEST_SECRET`, and `AEGIS_WAZUH_SPOOL_DIR` are required. Retry timing, maximum attempts/age/bytes, timeout, and TLS verification are configurable with the corresponding `AEGIS_WAZUH_*` variables. HTTPS verification is on by default; disabling it requires explicit `AEGIS_WAZUH_VERIFY_TLS=false` for local development.

The forwarder sends `Content-Type: application/json` and `X-Ingest-Secret`; it never adds an organization ID, changes the Wazuh payload, maps fields, or generates an alternative identity. Do not put the secret in command-line arguments or source-controlled files.

Installation and Wazuh `ossec.conf` integration configuration remain deployment work. No live Wazuh Manager/lab was started in this phase.
