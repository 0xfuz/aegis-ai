# Security Findings — S1

## Confirmed vulnerabilities

### S1-001 — Predictable privileged demo account is seeded on every container startup — CLOSED (S1.2 re-test)

- **Severity:** HIGH
- **Affected component:** backend container entrypoint / seed process
- **Attack prerequisite:** API reachable and default startup behavior retained.
- **Impact:** An attacker can authenticate as the seeded administrator and gain all configured permissions.
- **Evidence:** The entrypoint unconditionally runs seed data; the seed module defines a fixed demo administrator credential. Sensitive value intentionally redacted here.
- **Root cause:** Development bootstrap behavior is not gated from production startup.
- **Fix:** `SEED_DEMO_DATA` now defaults false and bootstrap runs only when explicitly enabled outside production. Production settings reject any attempt to enable demo seeding. The entrypoint no longer directly invokes the seed script.
- **Residual risk:** Operators must use a separate initial-admin provisioning process; no privileged credential is supplied by Aegis production startup.
- **Regression recommendation:** Production configuration test proving no demo user/data is created.

### S1-002 — Deployable defaults include known authentication/database secrets and externally published internal ports — CLOSED (S1.2 re-test)

- **Severity:** HIGH
- **Affected component:** Compose/default configuration
- **Attack prerequisite:** Deployment uses repository defaults or exposes default Compose ports outside a trusted host.
- **Impact:** Forged JWTs and unauthorized database access are possible with known defaults; exposed Redis/Ollama expand attack surface.
- **Evidence:** Tracked Compose/config templates provide development fallback values for JWT/database configuration and publish PostgreSQL, Redis, and Ollama host ports. Values are redacted.
- **Root cause:** One Compose profile serves both development convenience and potential deployment.
- **Fix:** production Settings reject debug mode, demo seeding, known default JWT secret, and default database credentials. `docker-compose.production.yml` requires operator-provided secrets and keeps PostgreSQL, Redis, and Ollama on the internal Docker network without host ports.
- **Residual risk:** The development Compose file remains intentionally convenient and must never be used as a production deployment manifest.
- **Regression recommendation:** CI policy rejects production startup with defaults and published internal ports.

### S1-003 — Generic webhook reads complete request body before enforcing its size limit — PARTIALLY CLOSED (S1.2 re-test)

- **Severity:** MEDIUM
- **Affected component:** Phase 7.6 generic webhook route
- **Attack prerequisite:** Network access to the public generic webhook route; no connector secret needed to force body read.
- **Impact:** Large requests can consume application memory before the 256 KiB logical limit is evaluated, enabling resource exhaustion.
- **Evidence:** Route executes `await request.body()` and checks `len()` afterward; authentication also happens after body parsing.
- **Root cause:** Application-layer size enforcement occurs after framework buffering.
- **Fix:** the application now consumes `Request.stream()` incrementally and stops as soon as cumulative bytes exceed 256 KiB; oversized tails are not accumulated.
- **Residual risk:** ASGI server/proxy still receives network bytes before application code runs. Production ingress must enforce a matching request-body cap and connection limits.
- **Regression recommendation:** Integration test through production ingress rejecting oversized bodies without application buffering.

## Hardening / defense-in-depth

- **S1-H01 (MEDIUM):** In-process connector rate limiting is per worker and memory-only; use shared gateway/rate-limit state in production.
- **S1-H02 (MEDIUM):** Access tokens are self-contained; user deactivation/role changes do not invalidate already-issued access tokens until expiry. Keep access lifetime short or add token-version/session checks for SOC deployments.
- **S1-H03 (LOW):** Generic webhook source is path/body-consistent but not server-registered per connector. Add an allowlist when multiple sources share a connector.
- **S1-H04 (LOW):** Dependency inventory was reviewed statically only; schedule authenticated SCA/SBOM scanning in CI. Package age alone was not classified as a vulnerability.

## Verified controls / unverified risks

No confirmed SQL injection, XSS, path traversal, SSRF, unsafe deserialization, cross-tenant IDOR, FACT mutation by alerts, or AI-to-analyst-authority bypass was found in the reviewed paths. This is an assessment result, not a proof of absence across all future code.
