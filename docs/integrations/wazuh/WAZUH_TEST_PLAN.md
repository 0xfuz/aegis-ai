# Wazuh Adapter Test Plan

All tests use a PostgreSQL-backed disposable organization and a real connector. Assertions cover RawEvent preservation, CanonicalAlert validation, source identity/replay, deduplication, correlation-v2 memberships, triage assessment, and absence of Investigation/FACT/Finding/MITRE/promotion writes unless an analyst explicitly promotes.

| Test | Primary assertions |
| --- | --- |
| Valid representative Wazuh alert | Accepted through Wazuh endpoint; exact raw JSON stored; canonical fields match contract. |
| Windows authentication alert | Agent/Windows account and event source IP map through the reviewed Windows profile. |
| Linux process alert | Hostname, account, executable/process map through Linux/syslog profile. |
| Network alert | Valid source/destination IPs map; ports retained only as metadata. |
| File-integrity alert | `syscheck.path` maps to `file`; hash metadata retains algorithm/value. |
| Wazuh MITRE metadata | Preserved under source metadata; no Aegis MITRE/FACT/Finding writes. |
| Exact replay/restart/retry | Same Wazuh source identity yields one canonical alert plus replay occurrence, no membership inflation. |
| Missing/invalid alert ID | Rejected/quarantined before canonical creation; no fallback timestamp-derived identity. |
| Malformed JSON and invalid timestamp/IP | 4xx; no RawEvent/canonical state according to transaction policy. |
| Oversized payload | Rejected before JSON parse at byte limit. |
| Hostile strings | Stored as bounded data; no executable interpretation, template injection, or unbounded metadata. |
| Missing optional fields / unknown decoder | Accepted with only available canonical fields; unknown data stays raw. |
| Rotating IP | Same host/account/process inputs retain existing v2 continuity; no engine change. |
| Multiple agents / shared NAT | Separate agent identities and IP-only/NAT cases do not false merge. |
| Cross-org connectors | Same Wazuh alert shape under two connectors cannot associate, replay, or query across organizations. |
| Correlation-v2 integration | Unique Wazuh alerts invoke only v2 membership writes; v1 membership history is untouched. |
| Triage output | A v2 cluster receives a deterministic triage-v1 assessment with source-derived severity only. |
| No automatic Investigation creation | Wazuh ingestion creates no Investigation, promotion, AIIE, FACT, Finding, or MITRE record. |
| Retries/out-of-order delivery | Retry is idempotent; timestamp ordering affects only existing deterministic windows. |
| Authentication/rate limit/rotation | Bad secret, inactive connector, source denial, rate limit, and rotated secret are rejected/auditable. |

Add contract fixtures from captured, sanitized Wazuh JSON for each decoder profile. Golden tests must assert the complete projected `CanonicalAlertCreate` payload and approved metadata subset. Property/fuzz tests should generate nested/hostile optional fields while preserving request and metadata limits.
