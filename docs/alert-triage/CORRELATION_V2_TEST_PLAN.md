# Correlation-v2 Adversarial Test Plan

| Case | Expected decision |
| --- | --- |
| Same host, different users | Separate unless independent continuity evidence overrides. |
| Same host/user, different process families | Separate when process conflict is evidenced. |
| Same host/user/time, unrelated rule families | Separate absent process/destination/sequence continuity. |
| Rotating IP with same host/user/process sequence | Merge. |
| Shared NAT/public gateway | Separate. |
| Common admin/service account | Separate absent target/behavior corroboration. |
| Parallel attacks against one host | Separate; eliminates confirmed v1 false merge. |
| A-B-C bridge where A/C incompatible | No transitive cluster fusion. |
| Noisy alerts between true events | Preserve true continuity without noise absorption. |
| Delayed continuation beyond 180 seconds | Separate unless a separately approved continuity window exists. |
| Multi-source equivalent telemetry | Merge only with independent observable/behavior evidence. |
| Cross-org look-alikes | Never associate. |

Candidate acceptance gates: zero cross-org associations; eliminate the documented same-host parallel false merge; preserve current rotating-IP positive and NAT negative cases; no regression on current v1 positive corpus; false-merge rate 0 on the current adversarial corpus; correlation recall no lower than 0.90 on labeled true-continuity cases. Targets are proposed, not achieved.
