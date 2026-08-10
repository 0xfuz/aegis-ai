# Phase 7.7.1 Adversarial Accuracy Benchmark

Frozen `dedup-v1`, `correlation-v1`, and `triage-v1` were measured with synthetic ground truth outside payloads. Cases covered rotating public IPs, shared NAT, common accounts, parallel same-host incidents, similar unrelated attacks, noise, replay/semantic floods, multi-source and cross-org look-alikes, and benign/severe priority expectations.

## Results

The deliberately difficult corpus confirms a known correlation-v1 limitation: two independent incidents sharing a strong hostname inside 180 seconds are merged. This is a false merge, not hidden by aggregate accuracy. Public-IP-only shared-NAT alerts remain separate. Rotating-IP alerts with shared hostname/user group correctly because hostname is a strong signal; IP changes neither prevent nor cause that grouping. Semantic replay/flood items are excluded from cluster membership and cannot inflate triage.

Deduplication on exact/semantic labeled flood cases: precision/recall/F1 1.00/1.00/1.00. Correlation has a documented false merge in the parallel-incident scenario; pairwise precision is therefore below 1.00 on the adversarial corpus. Severe synthetic source fields alone did not reliably reach HIGH/CRITICAL without the fixed trusted-context inputs required by triage-v1; this is a missed-high/critical measurement for an external-source-only severe scenario, not a tuning change.

Recommendation: **B. targeted correlation-v2 research is required first** before Wazuh integration. Triage-v1 research is also warranted for externally severe scenarios, but the demonstrated blocking accuracy defect is correlation false merge behavior.
