# Investigation Promotion Contract

Phase 7.5 implements the sole controlled bridge from a deterministic `AlertCluster` into a normal Aegis investigation. A cluster and its CanonicalAlerts remain alert-triage records; they never directly create FACT rows.

## Implemented flow

`OPEN AlertCluster` → active, same-organization analyst → latest immutable triage assessment → immutable promotion manifest → ordinary Investigation → deterministic `alert-promotion-v1.json` EvidenceItem → existing parser → RawRecord/Event/Indicator/Entity/relationship FACTs → `COMPLETED` promotion + `PROMOTED` cluster + AuditEvent.

The service has no public route in 7.5. This keeps promotion explicitly analyst-controlled at the internal service boundary and does not introduce a connector or automatic workflow.

## Eligibility and idempotency

- The actor must be an active user in the cluster organization.
- The resolved root cluster must be `OPEN`, have one or more unique non-semantic-duplicate members, and have a latest `AlertClusterAssessment`.
- Priority does not promote automatically. There is no AI action in this flow.
- The cluster row is locked during promotion. `alert_cluster_promotions.cluster_id` is unique, so a repeated or concurrent request returns the already-completed promotion and its Investigation.
- Only the final successful transaction sets `AlertCluster.status` to `PROMOTED`.

## Immutable promotion record

`alert_cluster_promotions` stores organization, root cluster, target Investigation, generated EvidenceItem, actor, exact assessment, `alert-promotion-export-v1`, SHA-256 export fingerprint, immutable JSON manifest, completion status, and timestamp. The migration also extends the existing cluster lifecycle constraint with `PROMOTED`; it does not change earlier migrations.

The manifest deterministically sorts members by `(observed_at, canonical_alert_id)` and contains canonical alert/source/connector/raw-event IDs, source alert identity, timestamps, normalized severity/category/rule/observables, payload digest, and membership context/reasons. It contains source references and digests, not a replacement copy of raw connector storage.

## Evidence and FACT boundary

The deterministic export has format `aegis.alert-promotion.export`, version `1.0`, and is parsed only by the dedicated `alert-promotion-json` parser. It is stored and ingested through `EvidenceIngestionService` with acquisition source `alert_cluster_promotion`.

Promotion code imports no canonical FACT ORM model and writes no `RawRecord`, `Event`, `Indicator`, `Entity`, or `EntityRelationship` directly. Those rows are created solely by the existing ingestion service/parser. The original EvidenceItem and raw export records retain the alert IDs, connector/raw provenance, payload digest, and cluster membership context necessary to navigate provenance.

For promotion only, ingestion runs in an atomic mode. If parsing, FACT persistence, promotion-record persistence, or audit persistence fails, the database transaction is rolled back, the generated storage object is deleted, and the cluster is not marked promoted. Ordinary manual evidence-ingestion behavior is unchanged.

## Deliberately deferred

No generic webhook, source adapter, deduplication/correlation/scoring algorithm, public promotion endpoint/UI, automated promotion, AIIE analysis, Finding conversion, MITRE confirmation, response action, or reporting is part of 7.5.
