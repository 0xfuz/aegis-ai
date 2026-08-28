# V1.0 controlled-pilot performance acceptance

## V1-B2 STATUS: BLOCKED

Measured on branch `release-readiness` at commit `af3f683`, the original
single-machine ingestion baseline did not complete: 300 target events at 5
events/second, concurrency ≤5. This host therefore does **not** certify 5
events/second, and no smaller sustained pilot rate or supported throughput
envelope has been measured.

The aggregate-only record reports 300 Futures scheduled; 211 HTTP starts; 206
returned and accepted requests; zero rejected/failed returned requests; 89
Futures cancelled before HTTP submission; and five requests still running at
the deadline. Cleanup completed. This is a bounded local capacity-gate failure,
not evidence of lost submitted events, HTTP 5xx, or a product defect. No
p50/p95/p99 result is reported because the workload was incomplete.

The controlled burst, bounded read-path suite, forwarder recovery, restart
validation, and complete resource-envelope certification are **NOT RUN** after
this blocker. RC1 remains available only for controlled functional evaluation;
V1-C and promotion to v1.0.0 remain blocked. No raw payloads, responses,
credentials, or logs were retained.

This is an operator-run harness checkpoint, not a performance claim. Run it
from the repository root in a normal local terminal:

```sh
./scripts/release/run-pilot-performance.sh \
  --result-dir /home/omar/.local/state/aegis-v1b2-performance
```

Use `--preflight-only` to verify the safe namespace, Docker prerequisite,
15 GiB root-disk floor, and 2 GiB `MemAvailable` floor without starting any
container. The result directory must be a specific non-symlink path outside
the repository and R4 paths. It is mode `0700`; its aggregate-only files are
mode `0600`: `status.json`, `aggregate.json`, `exit-code`, and
`operator-summary.txt`. Safe interruption is `Ctrl-C`; the harness retains
only those aggregate files and removes only its own `aegis-v1b2-*` resources.

## Scope and safety boundary

This report is produced only by the bounded V1-B2 harness at
`scripts/release/run-pilot-performance.sh`. It is a single-machine,
synthetic, local measurement for a controlled small-SOC pilot—not a
production, Enterprise, high-availability, cloud-scale, or compliance claim.

The harness uses a fresh `aegis-v1b2-*` Compose project, synthetic test-only
organizations and identities, synthetic benign Wazuh-shaped records, and
loopback HTTP endpoints. It does not start the preserved R4 environment,
Ollama, a provider, a Wazuh Manager, or Intelligence worker/beat services.
Intelligence execution, dispatch, and provider gates remain disabled.

It exercises the certified Wazuh webhook/mapper contract; that synthetic load
exercise does not replace the separately certified live Wazuh 4.9.2 evidence.
No raw request or response bodies, credentials, tokens, prompts, provider
output, database dumps, or secrets are retained by the harness.

## Fixed scenario limits

| Scenario | Fixed workload | Bound |
| --- | --- | --- |
| Ingestion baseline | 300 distinct events at 5 events/s | concurrency ≤5; ≤180 s |
| Controlled burst | 150 distinct events at 10 events/s | concurrency ≤10; ≤90 s |
| Bounded reads | authenticated bounded read endpoints | concurrency ≤10; ≤180 s |
| Durable forwarder recovery | 25 synthetic local deliveries | ≤180 s; TLS and secret-file authentication required |
| Restart stability | disposable API/frontend/Redis/PostgreSQL only | no authority workload |

The harness refuses public/non-loopback API targets, non-`aegis-v1b2-*`
project names, R4-like project names, root free disk below 15 GiB, or
`MemAvailable` below 2 GiB. It removes its containers, networks, volumes,
temporary secrets, aggregate logs, and generated test data on exit.

## Acceptance targets

- Baseline: 300/300 accepted, zero 5xx, no lost events, p95 ≤2 s.
- Burst: zero 5xx and no lost events; latency is reported without expanding
  the envelope automatically.
- Bounded reads: zero 5xx, no cross-organization data, p95 ≤2 s.
- Forwarder: all 25 acknowledged after recovery; pending/quarantine 0/0;
  no v1 membership or automatic authority effects.
- Restart: migration, record counts, authentication, and bounded reads remain
  consistent with no duplicate dispatch, membership, assessment, or authority
  records.
- Resource stop conditions: host root free disk stays at least 15 GiB,
  `MemAvailable` stays at least 2 GiB, no sustained swap pressure/OOM/restart
  pattern, and no service exceeds its declared Compose memory limit.

## Measurement record

The report is intentionally not populated until the harness has run exactly
once in its disposable namespace. Results must include the exact Git commit,
CPU/RAM class without host identifiers, relevant Compose configuration,
dataset limits, aggregate status classes, p50/p95/p99, throughput, resource
peaks, before/after disk, and pass/fail classification for every scenario.

If a stop condition or acceptance target fails, the result remains a bounded
measurement; it must not be tuned by changing correlation, triage, authority,
provider, schema, or certified behavior. The recommended pilot envelope may
never exceed a successfully measured scenario.

## Operator monitoring

Observe loopback health endpoints and only aggregate CPU/memory, disk,
evidence-volume, and forwarder spool/quarantine sizes. Stop the run once when
any stated resource floor or scenario duration is exceeded. Do not retain
event bodies or secret-bearing configuration to diagnose a result.
