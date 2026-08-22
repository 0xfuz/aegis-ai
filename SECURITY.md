# Security policy

## Supported version

Security fixes are evaluated for the current `v1.0.0-rc1` line and the next final v1.0.0 release. Earlier snapshots have no support commitment.

## Private reporting

Do not publish vulnerabilities in public issues. Send a private report to **<security-contact@example.invalid>**; the repository owner must replace this placeholder before public distribution. Include a bounded reproduction, affected version, impact, and safe contact method. Never include credentials, tokens, private keys, raw telemetry, customer data, prompts, provider output, or database dumps.

No response-time or remediation SLA is promised.

## Secure operation

Use file-mounted production secrets, disabled demo seeding, `DEBUG=false`, private/TLS ingress, restricted CORS, active-user RBAC, and the documented Wazuh and backup/restore procedures.
