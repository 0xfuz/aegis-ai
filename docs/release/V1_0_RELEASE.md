# Aegis AI v1.0 release scope

`v1.0.0-rc1` is a self-hosted controlled-pilot candidate, not a final v1.0.0 announcement.

## Supported profile

Production Compose with file-mounted secrets, secure admin bootstrap, private TLS ingress, and the separately configured Wazuh 4.9.2 durable forwarder. Wazuh is the only end-to-end validated integration.

Optional local Ollama execution is disabled by default. When deliberately enabled, it is trusted-configured, bounded, citation-linked, and analyst reviewed.

## Limits and responsibilities

Operators own ingress/TLS, capacity, secret lifecycle, Wazuh installation, spool monitoring, backups, and recovery drills. Aegis is not a SIEM replacement, SaaS, compliance product, universal connector platform, or autonomous remediation system. Findings, MITRE mappings, actions, and promotion remain analyst authority decisions.

Use [backup/restore](BACKUP_AND_RECOVERY.md) and [Wazuh operations](WAZUH_OPERATIONS.md). [V1-B2](V1_0_PILOT_PERFORMANCE.md) is currently blocked by the original local baseline, so it does not supply a supported throughput envelope and final v1.0.0 certification remains blocked.
