# Alert Cluster Contract

Status: **implemented in Phase 7.3**. Clusters are deterministic, organization-scoped candidate-incident containers. They are not FACT, an Investigation, a triage verdict, or an AI conclusion.

## Eligible input

Correlation consumes CanonicalAlerts only. Exact replays have no new CanonicalAlert and therefore cannot add membership. Alerts recorded as semantic duplicates by Phase 7.2 are excluded. All original CanonicalAlerts, RawEvents, occurrences, and deduplication decisions remain preserved. The time window is evaluated against a matching existing member, so a cluster may form a bounded transitive chain; a new alert must still be within 180 seconds of at least one member rather than merely of the cluster's first alert.

## `correlation-v1` rule

Alerts must be in the same organization and within an inclusive **180-second absolute observed-time window**. A correlation must then satisfy one of:

- a strong shared normalized observable—hostname, domain, URL, or file—plus time proximity and score at least 50; or
- both public source and destination IPs match plus time proximity and score at least 50; or
- at least two independent weak observables—username and process—plus time proximity and score at least 45.

Category contributes five supporting points; source-supplied MITRE techniques contribute five supporting points only. Severity, category, title, or MITRE can never correlate alerts by themselves. Every matching decision records score, version, candidate alert, matched values, and time delta.

## False-merge protections and limitations

Private/NAT, loopback, reserved, multicast, unspecified, or link-local IPs are not strong signals. A lone public IP is also insufficient to avoid merging broad scanner/gateway traffic. A common account alone, process alone, category/severity/title alone, or source MITRE alone is insufficient. The current implementation intentionally has no automatic split; a later analyst-managed cluster lifecycle must address false merges without erasing history.

## Cluster identity and membership

Every independently processed alert first receives a singleton OPEN cluster with identity key `correlation-v1:alert:<UUID>`. This stable key makes the initial identity deterministic. Membership is append-only and unique per CanonicalAlert; it stores the cluster, alert, optional correlated candidate, score, reasons, version, and time.

`member_count`, `first_seen`, `last_seen`, and `source_diversity` are refreshed from immutable members. Source diversity counts distinct `(connector_id, source)` pairs, allowing a strong shared observable to corroborate across configured sources while semantic deduplication remains conservative within connector/source scope.

## Merge behavior

When an incoming alert matches multiple OPEN clusters, the lexically smallest stable identity key survives. Each other cluster is marked CLOSED with `merged_into_cluster_id` set to the survivor. Its existing memberships are never moved or deleted; read operations follow merge lineage and return all historical members. `alert_cluster_merges` records survivor, absorbed cluster, trigger alert, rules/version, score/reasons, and time. An absorbed cluster can be merged once, and repeat processing has no effect.

## Read boundary

`AlertCorrelationService` provides internal `process`, `list_clusters`, `get_cluster`, and `list_members` methods. No HTTP endpoint, UI, triage scoring, promotion, connector, AIIE, Finding, or MITRE behavior is introduced in Phase 7.3.
