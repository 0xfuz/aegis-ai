# Phase 7.7 Synthetic Alert-Triage Benchmark Report

No production algorithm or webhook security control was changed.

| Dataset | Deliveries | Canonical | Exact replay reduction | Semantic reduction | Clusters | Analyst-visible | Low/Med/High/Critical | Errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| SMALL | 10 | 8 | 2 (20%) | 2 (25% of canonical) | 4 | 6 | 4/2/0/0 | 0 |
| MEDIUM | 50 | 40 | 10 (20%) | 10 (25% of canonical) | 20 | 30 | 20/10/0/0 | 0 |
| LARGE | 120 | 96 | 24 (20%) | 24 (25% of canonical) | 48 | 72 | 48/24/0/0 | 0 |

SMALL measured 3.95 req/s, median 250.91 ms, p95/p99 258.40 ms. MEDIUM measured 4.05 req/s, median 245.96 ms, p95 280.25 ms, p99 285.20 ms. LARGE uses the same deterministic corpus and HTTP path; benchmark execution is constrained by deliberate bcrypt authentication and unchanged connector rate limits.

Ground-truth dedup precision/recall/F1: 1.00/1.00/1.00. Correlation precision/recall/F1: 1.00/1.00/1.00. False merges: 0. Missed correlations: 0. Rotating-IP/proxy-like alerts formed independent clusters as designed; replay storms did not inflate canonical membership or triage. Cross-organization isolation remains covered by Phase 7 tests.

Candidate later research item: this corpus yields no HIGH/CRITICAL priority due to frozen triage-v1 inputs; this is a measurement, not a tuning request. No automated investigation promotion occurred.
