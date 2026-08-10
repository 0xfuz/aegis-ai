# Security Remediation S1.1

## S1-001 — REMEDIATED

Root cause: every backend startup directly ran demo seeding. Fix: `SEED_DEMO_DATA=false` by default, an explicit development/demo bootstrap, and production configuration rejection for demo seeding. Tests prove disabled development mode does not seed, enabled development mode does, and production configuration cannot enable it.

## S1-002 — REMEDIATED

Root cause: development fallback secrets and published service ports could be deployed unchanged. Fix: production Settings reject unsafe defaults/debug/demo seed; `docker-compose.production.yml` requires supplied secrets and publishes no PostgreSQL, Redis, or Ollama ports. Tests prove bad production configuration fails and explicit non-default test configuration succeeds.

## S1-003 — PARTIALLY REMEDIATED

Root cause: webhook used `Request.body()` before its application cap. Fix: bounded ASGI chunk consumption stops collecting at 256 KiB. Tests cover below, exactly-at, above, and chunked-above limit cases. Residual risk: only an ingress/proxy can reject network payloads before ASGI receives them; production deployment must configure that matching cap.

## Verification and deferred items

S1.1 runs dedicated security/config/webhook tests, authentication/authorization tests, Phase 7.1–7.6 regression, and the complete Docker/PostgreSQL backend suite. No S1 hardening-only items (distributed rate limiting, token invalidation, source allowlisting, SCA policy) were remediated.
