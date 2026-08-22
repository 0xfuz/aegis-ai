# Aegis AI

A self-hosted security alert intelligence and investigation platform, validated end-to-end with Wazuh and suitable for controlled pilot use.

## Release-candidate scope

The current candidate is `v1.0.0-rc1`. Its verified path is:

`Wazuh → durable forwarder → authenticated webhook → RawEvent → CanonicalAlert → deduplication → correlation-v2 → triage-v1 → analyst promotion → Investigation → reconstruction → grounded AI claim → typed citation → analyst review`.

AI output is reviewable and citation-linked, never automatically authoritative. Findings, MITRE mappings, promotions, and actions remain separately analyst controlled.

## Not a claim

Aegis AI is not an Enterprise SIEM replacement, SaaS platform, compliance-certified product, supported Splunk/Sentinel/Elastic integration, or autonomous SOC. Wazuh 4.9.2 is the only end-to-end validated integration.

## Controlled-pilot deployment

Production Compose—not `docker-compose.yml`—is authoritative for pilots. Development Compose and `.env.example` are development-only conveniences. Start with [Deployment quickstart](docs/release/DEPLOYMENT_QUICKSTART.md), then follow [Production deployment](docs/release/PRODUCTION_DEPLOYMENT.md), [Admin bootstrap](docs/release/PRODUCTION_ADMIN_BOOTSTRAP.md), [Wazuh operations](docs/release/WAZUH_OPERATIONS.md), and [Backup and recovery](docs/release/BACKUP_AND_RECOVERY.md).

Production secrets are file-mounted. Intelligence execution is optional and disabled by default; deliberate local Ollama enablement uses the pinned runtime/model described in [Image inventory](docs/release/PRODUCTION_IMAGE_INVENTORY.md).

## Capabilities and boundaries

- Organization-scoped RBAC, bounded canonical evidence provenance, replay/deduplication, version-isolated correlation-v2, triage, and explicit promotion.
- Investigation workspaces for factual evidence, timeline, entities, indicators, relationships, audit, notes, reports, reconstruction, and analyst review.
- Wazuh durable spool/retry/quarantine and TLS-verified forwarding.

See [release scope](docs/release/V1_0_RELEASE.md), [changelog](CHANGELOG.md), [security policy](SECURITY.md), [license](LICENSE), [notice](NOTICE), [launch drafts](docs/release/LAUNCH_POSTS.md), and [RC1 certification](docs/release/RC1_B_LIVE_CERTIFICATION.md). Final v1.0.0 remains contingent on V1-B2 bounded pilot performance evidence.
