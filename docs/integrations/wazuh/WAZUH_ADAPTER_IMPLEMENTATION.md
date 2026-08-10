# Wazuh Adapter Foundation — Phase 7.8.1

Implemented scope ends at a pure, deterministic conversion:

```
sanitized Wazuh JSON → WazuhAlert validation → CanonicalAlertCreate
```

The implementation is [wazuh_mapper.py](../../../backend/app/modules/alert_triage/domain/wazuh_mapper.py). It has no database session, HTTP endpoint, connector authentication call, forwarder, correlation invocation, or downstream write.

## Phase 7.8.2 HTTP orchestration

Implemented endpoint: `POST /api/v1/ingest/wazuh/v1/{connector_id}`. It is separate from generic/legacy alert ingestion and accepts JSON only with the existing 256 KiB streaming body limit and `X-Ingest-Secret` authentication. Its source is fixed by the route/service to `wazuh`; neither a source nor organization supplied by the body is used for tenancy.

The actual path is: authenticated connector-derived organization → original JSON `RawEvent` → pure `map_wazuh_alert` → `CanonicalAlertService` → existing exact replay/semantic dedupe → `AlertCorrelationV2Service` only → unchanged triage-v1. Exact replay returns `200 replayed`, preserves occurrence history, and does not create another v2 membership or assessment. New accepted alerts return `201 accepted` with bounded canonical/cluster/triage state.

The scoped triage compatibility fix reads memberships using the root cluster's explicit `correlation_version`; it never performs an any-version read. This enables v2 triage without changing scoring rules, thresholds, or correlation behavior.

## Delivered files

- `backend/app/modules/alert_triage/domain/wazuh_mapper.py`
- `backend/tests/test_wazuh_mapper.py`
- `backend/tests/fixtures/wazuh/{windows_authentication,linux_process,network_event,file_integrity,mitre_metadata,sparse_valid}.json`

## Supported profiles

| Wazuh decoder | Supported deterministic projection |
| --- | --- |
| `windows_eventchannel` | Windows event account, executable/image, source/destination IP, file, domain, URL. |
| `syslog`, `linux`, `ossec` | Linux account, process/program, source/destination IP, file, domain, URL. |
| `syscheck` | File-integrity path and algorithm-qualified hashes. |
| `json`, `suricata`, `zeek`, `network` | Explicit network aliases for IPs, ports (metadata only), file, domain, and URL. |
| any other/missing decoder | Structurally valid alert is accepted with manager/agent/rule metadata but no dynamic canonical observables. |

## Exact implemented behavior

- Identity is `wazuh:<manager-name-casefolded-without-trailing-dot>:<alert-id>`; manager name and alert ID are required. No timestamp/content fallback exists.
- Wazuh levels map exactly: 0–3 `INFO`, 4–6 `LOW`, 7–9 `MEDIUM`, 10–12 `HIGH`, 13–16 `CRITICAL`; anything else rejects.
- Agent name is hostname; agent ID yields `agent-<id>` only if name is absent. Agent IP is metadata, not event source IP.
- Rules/groups, manager, agent, decoder, location, valid ports, hashes, and Wazuh MITRE values go only into bounded `source_metadata.wazuh`.
- MITRE values remain source assertions. The mapper does not import or write Aegis MITRE mappings, Findings, FACT, AIIE, Investigation, cluster, or promotion data.
- Invalid optional IP/URL/other observable values are omitted and recorded in bounded mapping diagnostics. Invalid/missing structural identity, timestamp, or severity rejects.
- The output relies on the existing `CanonicalAlertCreate`/`AlertObservables` validators; no canonical validation was weakened.

## Mapping limitations

- Dynamic Wazuh fields outside the reviewed decoder profiles remain preserved raw provenance, not guessed canonical facts.
- Port has no CanonicalAlert observable and is metadata only.
- Wazuh MITRE labels are not confirmed Aegis MITRE facts.
- Sparse alerts can be canonicalized but do not manufacture correlation evidence.
- This phase intentionally provides no public endpoint, Wazuh manager forwarder, retry spool, connector changes, or lab deployment.

## Validation completed

With `DEBUG=true`, the dedicated mapper suite passed **13 tests**. The mapper plus CanonicalAlert and correlation-v2/version-isolation regression passed **31 tests**. The full backend Docker/PostgreSQL regression completed successfully; the collected suite contains **166 tests**.
