# Phase 7.7 Benchmark Methodology

Synthetic, reproducible HTTP benchmark only. Ground-truth labels stay in `tests/test_alert_benchmark.py`, never in webhook payloads. Each group delivers: initial alert, exact replay, semantic duplicate, related distinct alert, and rotating-IP-only alert. Expected truth: one exact replay, one semantic duplicate, one true correlation, and no merge for rotating-IP-only traffic.

Datasets: SMALL=2 groups/10 deliveries, MEDIUM=10/50, LARGE=24/120. Requests use the real Phase 7.6 generic webhook and valid connector authentication. Connector assignment changes only between 12-group batches to respect the unchanged 60/minute connector rate limit.

Metrics use persisted CanonicalAlert/Occurrence/Deduplication/Cluster/Membership/Assessment records. Dedup precision/recall and correlation precision/recall/F1 are computed against the deterministic harness labels; false merges and missed correlations are expected zero for this corpus. Latency is wall-clock TestClient request time and includes bcrypt connector-secret verification, so it is not a network production latency measurement.
