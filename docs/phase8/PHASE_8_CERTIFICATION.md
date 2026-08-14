# Phase 8 Certification

Certified commit: pending final certification commit.  This record certifies the
bounded Investigation Intelligence path; it does not certify autonomous
response, arbitrary-provider operation, or production performance.

## Live-lab evidence

The isolated final lab validated the automatic, agentless Wazuh path:

`benign synthetic syslog -> Wazuh Manager 4.9.2 -> Integrator -> durable forwarder -> Aegis Wazuh webhook -> RawEvent -> CanonicalAlert -> correlation-v2 -> triage-v1`.

Two manager alerts resulted in two `RawEvent` rows and two `CanonicalAlert`
rows.  They resulted in one correlation-v2 membership because the second alert
was a deterministic semantic-deduplication occurrence of the first (same rule
100500/category/severity/manager hostname within 38.327 seconds).  The first
alert formed cluster `078c620a-2419-497a-bc0e-179a2c647b4e`; the second did not
create another membership.  No correlation-v1 membership was created.

The analyst-controlled promotion was
`4e48682c-b620-4fa9-8130-d6c1a9c644c6`, creating Investigation
`f073b0b7-afc5-4750-9008-7bc4e7450fa4`.  Its persisted reconstruction recorded
five bounded activities with zero reconstruction gaps and zero warnings,
including correlation-v2 and triage-v1 provenance.  This is a live integration
observation, not a production latency benchmark.

## Execution lineage and safe degradation

The terminal predecessors are preserved and unchanged:

| Run | Predecessor | Result |
| --- | --- | --- |
| `1fe857bf-fb3b-44f5-b24b-92decde102ce` | — | `EXECUTION_FAILED` before provider invocation because the lab hostname was not trusted. |
| `1bc7c468-fafb-4c57-8614-c312891345fe` | first run | `PROVIDER_TIMEOUT`; one actual attempted call; no claims or authority writes. |
| `cf93251f-03b8-4191-a835-f6ffc4faa628` | second run | `PROVIDER_TIMEOUT`; one actual attempted call; no claims or authority writes. |
| `f2ecba95-6c83-4de7-a01e-c85a284d570b` | third run | `COMPLETED`; one `PENDING` AI `OBSERVATION`, one `SUPPORTS` typed evidence link, candidate fingerprint present, lease cleared. |

The provider timing diagnostic rebuilt the persisted prompt without retaining
content and performed one discarded bounded request: 7,658 prompt bytes,
382 response bytes, 55.607 seconds time-to-first-byte/total, and `VALID`
candidate validation.  The explicit fixed policies used by the successful
successor are `provider-timeout-v2` (connect 5 seconds, read 90 seconds, total
105 seconds) and `intelligence-lease-v2` (150-second lease, 30-second
heartbeat).  The trusted runtime was the official
`ollama/ollama@sha256:4dea9fb511947e24a84237bb636b0203abcb2ff0d3fbc7b4ff865deb91362131`
image with the already-installed exact allowlisted model `llama3.2:latest`.

The internal Celery acknowledgement wrapper was corrected after the successful
run exposed that `GroundedResult` has no fake-executor `outcome` attribute.  It
now emits only a bounded lifecycle category and does not read or return prompt,
candidate, citation, provider, or claim content.

## Certification gates

| Gate | Result |
| --- | --- |
| Fresh PostgreSQL migration | `0023 (head)`; one Alembic head |
| Empty migration round trip | `0023 -> 0022 -> 0023` passed |
| Legacy safeguards | existing `0020`/`0021` populated downgrade refusals and no-backfill schema coverage remain passing; `0022` requeues only legacy `RUNNING` rows rather than inventing ownership |
| Focused task/grounded/dispatch/lease/persistence tests | 30 passed, then 35 passed after lease-v2 expectation alignment |
| Complete backend suite | 407 passed, 62 warnings, 133.84 seconds; durable exit code 0 |
| Frontend suite | 12 files, 51 tests passed |
| Frontend typecheck | passed |
| Frontend lint | passed with no warnings/errors |
| Frontend production build | passed |
| Compose configuration | valid with execution/provider disabled and trusted-enabled settings |

The frontend Intelligence workspace tests exercise the authenticated page
boundary: deterministic reconstruction, promoted correlation-v2 and triage
provenance, a completed `PENDING` observation with a `SUPPORTS` citation,
escaped hostile text, and absence of raw evidence content.  The UI exposes no
prompt, provider output, full snapshot, secret, or raw telemetry.  `PENDING`
claims do not expose a conversion control; no Finding, MITRE mapping,
RecommendedAction, promotion, or Phase 7 correlation/triage write occurred.

## Trust boundaries and exclusions

Only the established run queue/get/list/cancel/retry, reconstruction GET, and
analyst review routes are public.  There is no registered public synchronous
`/analyze` route, no public lease acquire/heartbeat/complete/fail route, and
no public provider or worker route.  The legacy synchronous router remains
unregistered.  The worker accepts only run ID plus protocol and selects only
the configured, exact allowlisted trusted Ollama model.  Organization and
Investigation scope are server-authoritative; full backend isolation and API
anti-enumeration tests passed.

Phase 8 is deliberately not a claim of production model performance.  The
Wazuh alerts and provider timing run are controlled synthetic/lab evidence.
Deferred work includes broader production load testing, provider/model
operations, additional model families, SaaS/billing, and any autonomous
containment or remediation authority.
