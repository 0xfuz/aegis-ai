# Security Re-test S1.2

## Results

- **S1-001: CLOSED.** Production Settings rejects demo seeding; explicit development opt-in is the only bootstrap path. The production entrypoint invokes the guarded bootstrap, not direct seeding. No predictable credential or password logging path remains in production startup.
- **S1-002: CLOSED.** Production rejects debug mode, default application/database credentials, and demo seeding. Production Compose requires supplied secret variables and has no PostgreSQL, Redis, or Ollama host ports; internal service URLs use the Docker network.
- **S1-003: PARTIALLY CLOSED.** Application-layer bounded ASGI streaming rejects above-limit and chunked bodies before collecting their tails, returns safe `422`, and creates no RawEvent/CanonicalAlert/cluster state. A reverse proxy/ingress body and connection limit is still required before deployment to bound network/ASGI ingress resource use.

## Bypass review

No S1.1 bypass or Phase 7 regression was demonstrated: connector authentication/source matching, tenant isolation, replay idempotency, no webhook FACT mutation, and no automatic investigation promotion remain intact.

## Backlog

Distributed rate limiting/backpressure, access-token invalidation, connector source allowlisting, and CI SCA/SBOM policy remain hardening work. They do not block the Phase 7.7 synthetic benchmark provided it is isolated/disposable and production ingress requirements for S1-003 are tracked.
