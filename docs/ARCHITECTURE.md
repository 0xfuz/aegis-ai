# Aegis AI architecture overview

Aegis AI is a private, self-hosted controlled-pilot project. This overview is
intended for a technical evaluator; it does not describe a public SaaS,
high-availability deployment, or a certified capacity envelope.

## Core mode

Core mode starts five services in one private Docker Compose network:

```text
browser → loopback frontend → loopback API → PostgreSQL
                                      └──→ Redis
```

`migrate` is a one-shot gate before the API starts. PostgreSQL stores the
authoritative application state and canonical evidence volume; Redis is a
non-authoritative broker/cache. API and frontend ports bind to loopback only.
No Wazuh Manager, Ollama, worker, beat, or AI execution is required to inspect
the Core-mode UI.

## Alert and investigation path

The validated Wazuh path is deliberately synchronous through authoritative
ingestion stages:

```text
Wazuh Manager → TLS forwarder → authenticated Wazuh webhook
  → RawEvent → CanonicalAlert → deterministic deduplication
  → correlation-v2 → triage → analyst-controlled promotion → Investigation
```

The forwarder keeps a bounded durable spool for delivery recovery. Wazuh is
the only external integration validated end-to-end. The forwarder, its TLS
materials, and Wazuh Manager are configured separately from Core mode.

## Investigation authority boundary

Evidence, timeline, entities, indicators, relationships, audit, notes, and
reports are bounded Investigation-scoped views. Organization scope, active-user
checks, and RBAC are enforced by the API.

Optional local AI execution is disabled by default. When explicitly enabled,
it produces reviewable claims with typed citations. An AI claim never becomes a
Finding, MITRE mapping, promotion, or action automatically. Analysts control
Finding review, canonical MITRE confirmation, promotion, and actions.

## Deployment boundary

Production secrets are protected files mounted into the relevant services;
they are not committed or passed as command-line values. A separately operated
TLS-terminating reverse proxy is required before loopback UI/API ports are
made reachable beyond the host. Consult the [Core-mode quickstart](release/DEPLOYMENT_QUICKSTART.md)
and [production deployment guide](release/PRODUCTION_DEPLOYMENT.md) for exact
operator commands and limits.

The V1-B3 local test did not complete 300/300 events at five events per second.
This project therefore makes no supported throughput, production-scale, or
zero-loss capacity claim.
