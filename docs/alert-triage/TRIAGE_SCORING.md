# Deterministic Alert Cluster Triage Scoring

Status: **implemented in Phase 7.4**. Priority is an explainable operational ordering signal only. It is not AIIE confidence, maliciousness, an Investigation severity, a Finding, or a MITRE decision.

## Version and bounded ledger

`triage-v1` produces an append-only 0–100 point ledger. Every entry contains factor, points, human-readable reason, supporting references where available, and scoring version. The maximum contributions total exactly 100:

| Factor | Maximum | `triage-v1` rule |
| --- | ---: | --- |
| Highest distinct canonical source severity | 25 | CRITICAL 25, HIGH 18, MEDIUM 10, LOW 4, INFO 0 |
| Trusted asset criticality | 20 | normalized hostname matches existing org Asset: critical 20, high 12, medium/low 0 |
| Distinct non-duplicate member count | 10 | 1: 0; 2–3: 4; 4–7: 7; 8+: 10 |
| Independent connector/source diversity | 10 | 1: 0; 2: 5; 3+: 10 |
| Deterministic correlation strength | 10 | max membership score: 45:4, 60:6, 80:8, 100:10 |
| Deterministic behavioral sequence | 10 | auth failure → success → execution/activity: 10; execution → outbound connection: 8 |
| Trusted IOC context | 10 | matching watched IOC: 10; matching internal malicious IOC: 8 |
| Recency | 5 | ≤1h: 5; ≤24h: 3; ≤7d: 1; older: 0 |

Priority bands are explicit: **LOW 0–24**, **MEDIUM 25–49**, **HIGH 50–74**, **CRITICAL 75–100**. No LLM or analyst-free override can alter the computed score/band.

## Trusted and unavailable inputs

Canonical alert severity is normalized bounded metadata and contributes only once through the highest distinct member severity; replay occurrences and semantic duplicates are absent from cluster membership. Asset points use only the existing org-scoped Asset registry matched by normalized hostname. Missing matches are ledgered as unavailable and score zero; default medium/low classifications are neutral.

IOC points require an existing org-scoped matching IP/domain/URL IOC that is watched, or marked `malicious` with `internal` provenance. Arbitrary source alert text, source metadata claims, untrusted source MITRE, IOC confidence, external malicious claims, AIIE output, and `ai_risk_summary` never contribute.

Behavior is limited to exact normalized category sequences ordered by CanonicalAlert `observed_at`; it does not interpret descriptions or invoke AI. Source diversity counts distinct `(connector_id, source)` pairs only.

## Recency and rescoring

Assessment callers supply an explicit timezone-aware `reference_at`; this timestamp is part of the immutable scoring input. Recency is calculated from `reference_at - cluster.last_seen`; a reference before `last_seen` is rejected. This avoids silently changing historical scores as wall time passes.

Rescore after membership addition, cluster merge, trusted Asset/IOC change, scoring-version change, or an intentionally different reference timestamp. The complete scoring input is SHA-256 fingerprinted. Repeating the same cluster state, `triage-v1`, trusted context, and reference timestamp returns the existing assessment; changed inputs append a new assessment and never overwrite history.

## Persistence and read boundary

Alembic `0017` adds immutable `alert_cluster_assessments`, with org scope, `RESTRICT` cluster provenance, score/priority check constraints, scoring version, input hash, full ledger, reference/evaluation timestamps, and a unique `(cluster_id, scoring_version, input_hash)` idempotency constraint.

`AlertClusterTriageService` provides internal `assess`, `get_latest`, and `list_history` read methods. It does not alter cluster membership/lifecycle, CanonicalAlert, RawEvent, FACT, AIIE, Findings, MITRE, or Investigations. No HTTP endpoint or UI is added in this phase.
