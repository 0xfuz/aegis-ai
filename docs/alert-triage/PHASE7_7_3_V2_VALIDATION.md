# Correlation-v2 Validation

**CORRELATION-V2 ACCEPTED FOR EXTERNAL INTEGRATION**

Validation ran with `DEBUG=true` against disposable, organization-isolated PostgreSQL fixtures. Each of the 12 benchmark scenarios materializes its telemetry through `CanonicalAlertService`; benchmark truth remains only in the test scenario definition. The adapters invoke the real engine and derive predicted groups only from persisted, version-filtered `AlertClusterMembership` rows.

| Engine | Precision | Recall | F1 | False merges | Missed correlations |
| --- | ---: | ---: | ---: | ---: | ---: |
| correlation-v1 | 0.4000 | 1.0000 | 0.5714 | 6 | 0 |
| correlation-v2 | 1.0000 | 1.0000 | 1.0000 | 0 | 0 |

| Scenario | V1 | V2 |
| --- | --- | --- |
| same_host_different_user | FAIL (1 false merge) | PASS |
| same_host_different_process | FAIL (1 false merge) | PASS |
| same_host_unrelated_rule | FAIL (1 false merge) | PASS |
| rotating_ip_identity_behavior | PASS | PASS |
| shared_nat | PASS | PASS |
| common_service_account | PASS | PASS |
| parallel_incidents_same_host | FAIL (1 false merge) | PASS |
| bridge_abc | FAIL (2 false merges) | PASS |
| noisy_interleaving | PASS | PASS |
| delayed_continuation | PASS | PASS |
| multi_source_telemetry | PASS | PASS |
| cross_org_lookalikes | PASS | PASS |

Acceptance gates passed: same-host false merge eliminated; rotating-IP continuity preserved; shared-NAT separation preserved; bridge-chain merge blocked; zero cross-org associations; zero v1/v2 membership-history contamination; zero adversarial v2 false merges; v2 recall is 1.0000 (>= 0.90); and valid v1 correlations remain present (v1 recall 1.0000). The version-isolation regression remains green.

Executed after metrics existed, with `DEBUG=true`:

- focused adapter and version-isolation regression
- Phase 7.7 benchmark regression
- focused Phase 7 correlation tests
- full backend Docker/PostgreSQL regression
