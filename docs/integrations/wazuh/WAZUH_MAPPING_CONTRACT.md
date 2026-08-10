# Wazuh → CanonicalAlert Mapping Contract

## Contract rules

The adapter receives a Wazuh JSON alert, stores that original JSON in `RawEvent`, then builds `CanonicalAlertCreate`. It rejects malformed required structure; optional fields that fail canonical type/length validation are omitted and recorded as bounded mapping diagnostics, not coerced into a different fact. Wazuh MITRE data is source-asserted metadata only.

| Wazuh path | Canonical target | Trust classification | Deterministic rule |
| --- | --- | --- | --- |
| `id` | `source_alert_id` | Trusted structural data | Required non-empty string, max 255. Use exactly `wazuh:<manager.name>:<id>` after bounded manager normalization. |
| `timestamp` | `observed_at` | Source-asserted data | Required ISO-8601 timestamp with offset; reject absent/naive/unparseable values. |
| `rule.id` | `rule_id` | Source-asserted data | Stringify bounded numeric/string ID; never infer one from description. |
| `rule.description` | `title`, `rule_name` | Untrusted text | Trim/bound; title is description or `Wazuh rule <id>` fallback. It never becomes a verdict. |
| `rule.level` | `severity` | Source-asserted data | Fixed documented mapping: 0–3 `INFO`, 4–6 `LOW`, 7–9 `MEDIUM`, 10–12 `HIGH`, 13–16 `CRITICAL`; reject levels outside 0–16 rather than clamp. |
| `rule.groups` | `category`, `source_metadata.rule_groups` | Source-asserted data | Preserve bounded list in metadata. Deterministically select an approved category from an allowlist; otherwise `wazuh_unclassified`. |
| `agent.name`, then `agent.id` | `hostname` | Source-asserted data | Prefer non-empty name; fall back to `agent-<id>`. Canonical text normalization applies. |
| `agent.id`, `agent.ip`, `manager.name`, `decoder.name`, `location` | `source_metadata` | Trusted structural / optional context | Preserve typed, bounded values with namespace `wazuh`. They are provenance/context, not correlation fields except agent name above. |
| decoded `srcip`/`src_ip` and `dstip`/`dest_ip` | `source_ip`, `destination_ip` | Source-asserted data | Use an explicit ordered alias list; accept only valid IP literals through `AlertObservables`. |
| decoded source/destination ports | `source_metadata.network` | Optional context | Integer 1–65535 only. No CanonicalAlert port field exists; never concatenate port into IP. |
| decoded `user`, `srcuser`, `dstuser`, `win.eventdata.*User*` | `username` | Source-asserted data | Profile-specific ordered aliases; one normalized account only. Preserve all source candidates in metadata. |
| decoded process/image/command field | `process` | Source-asserted data | Prefer executable/image path over command line; bounded string, with full raw value remaining in RawEvent. |
| `syscheck.path`, decoded file/path/hash | `file`; hash metadata | Source-asserted data | Map a path/file to `file`; retain algorithm-qualified hashes in `source_metadata.wazuh.hashes`. Do not treat a hash as a file path. |
| decoded URL/domain fields | `url`, `domain` | Source-asserted data | URL must pass canonical absolute HTTP(S) validation; domain is normalized by CanonicalAlert. Invalid optional values are omitted. |
| `rule.mitre` | `source_metadata.wazuh.mitre` | Source-asserted data | Preserve IDs/tactics/techniques as received, bounded and type checked. Never write Aegis MITRE mappings, Findings, FACT, or a confirmed technique. |
| complete Wazuh JSON / `full_log` / dynamic decoded fields | `RawEvent.payload`; selected `source_metadata.wazuh` subset | Untrusted text / optional context | Raw event is authoritative provenance; metadata is an allowlisted, size-bounded diagnostic subset. |

`source` is the constant `wazuh`; `normalizer_version` is proposed as `wazuh-alert-v1`; `signature` is `wazuh:<rule.id>` when a rule ID exists; `description` is a bounded, untrusted rendering of Wazuh description/location, never a raw `full_log` dump.

## Phase 7.8.1 implementation status

Implemented in the pure `wazuh_mapper.py` foundation: required manager/alert identity, timestamp and level rejection, exact level-to-severity conversion, approved profile extraction, agent hostname fallback, safe optional observable omission with diagnostics, bounded Wazuh metadata, and source-asserted MITRE retention. The mapper creates a validated `CanonicalAlertCreate` only; it performs no persistence or downstream action. The dedicated endpoint and forwarder remain intentionally unimplemented.

## Field-profile precedence

Wazuh dynamic fields vary by decoder. The implementation must use documented, reviewed profiles (`windows_eventchannel`, `syslog`/Linux, `syscheck`, network/Suricata-like JSON) rather than a recursive “find any key named user/IP” search. Unknown decoder fields remain raw provenance. This keeps mappings deterministic and prevents hostile payload keys from selecting trusted canonical fields.

## Correlation-v2 compatibility and limitations

Useful v2 observables are `hostname`, `username`, `process`, `destination_ip`, and `domain`. Rule ID and category remain useful deduplication/triage context but are not a vendor-specific correlation extension. Agent IP belongs in metadata by default; it is a management/agent address and must not be misrepresented as event source IP.

Wazuh can provide a useful behavioral sequence only when multiple correctly mapped alerts occur within v2’s existing window and have existing triage categories. No adapter may manufacture a sequence from a single alert. Sparse rule data, shared service accounts, NAT, missing process fields, and non-IP endpoints reduce correlation evidence; the safe outcome is separate clusters, not adapter-side joining.
