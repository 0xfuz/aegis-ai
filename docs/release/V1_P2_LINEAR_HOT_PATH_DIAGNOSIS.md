# V1-P2 Linear Ingestion Hot-Path Diagnosis

Status: diagnostic evidence only — not a throughput certification.

## Scope and method

This document records a small, sequential, disposable PostgreSQL diagnostic
at commit `5e8b9fa1d9a3e283a288c44029ad9a1046cad8c8`, with Alembic sole head
`0024`.  It follows the already-certified Wazuh FastAPI webhook boundary and
uses the shared synthetic webhook fixture.  SQLAlchemy test-only event
listeners were installed after fixture setup and removed before cleanup.

The result retains only fixed stage labels and aggregate SQL/session counters.
It contains no SQL text or parameters, payloads, identities, credentials,
headers, response bodies, logs, database URLs, or database contents.  This
was not a rate test, burst test, pilot benchmark, or production measurement.

The three bounded scenarios were:

| Scenario | Bounded submissions | Purpose |
| --- | ---: | --- |
| `single_new_event` | 1 | One unique Wazuh-shaped event |
| `exact_replay` | 2 | The same source identity twice |
| `correlation_candidate` | 2 | A minimal pair that reaches correlation-v2 candidate processing |

## Synchronous call path

The authenticated request enters `ingest_wazuh_alert` in the connector router,
authenticates the connector, and calls
`WazuhAlertWebhookService.ingest`.  Before the response returns, that method:

1. flushes the raw event;
2. maps and persists the CanonicalAlert/occurrence;
3. executes deterministic deduplication;
4. runs correlation-v2 candidate selection and membership persistence;
5. runs deterministic triage; and
6. serializes the bounded ingest result.

The relevant implementation boundaries are
`alert_triage/domain/webhook_service.py`,
`alert_triage/domain/service.py`,
`alert_triage/domain/deduplication_service.py`,
`alert_triage/domain/correlation_v2_service.py`, and
`alert_triage/domain/triage_service.py`.  No authoritative stage is moved
asynchronously by this diagnosis.

## Reconciled aggregate counts

The per-stage SQL counts reconcile internally to the direct-request aggregate
counter.  The earlier P1 whole-scenario `correlation_candidate` total includes
its post-response verification boundary, so it is not a like-for-like request
total. `transaction_begin` is the reported transaction count;
transaction-end callbacks are shown only to check session lifecycle balance.

| Scenario | Statements (SELECT / INSERT / UPDATE) | Flush / commit / transaction begin | Elapsed ms |
| --- | --- | --- | ---: |
| `single_new_event` | 38 (30 / 6 / 2) | 7 / 3 / 4 | 605.54 |
| `exact_replay` | 53 (41 / 9 / 3) | 11 / 5 / 7 | 1076.36 |
| `correlation_candidate` | 81 (66 / 11 / 4) | 13 / 6 / 8 | 919.82 |

Stage attribution for the unique-event and controlled-candidate cases:

| Stage | Single-event SELECTs | Candidate SELECTs | Principal observed work |
| --- | ---: | ---: | --- |
| raw event | 8 | 16 | authentication/persistence boundary |
| canonical alert | 1 | 2 | alert plus occurrence persistence |
| deduplication | 6 | 12 | deterministic decision reads |
| correlation-v2 | 6 | 15 | candidate/membership and cluster work |
| triage | 9 | 19 | persisted lineage, alert, asset/IOC and assessment reads |

The remaining counted SQL is zero for DELETE/other operations in these runs.
The stage callback also observed 11/18/21 transaction-end notifications for
the three scenarios, respectively; those are not additional transaction
begins.

## Localization and interpretation

V1-P1B1 already removed the proven quadratic candidate-read boundary:
`AlertCorrelationV2Service._candidate_read_maps` now bulk loads selected
open-cluster memberships and their distinct alerts.  This diagnostic did not
find that former quadratic shape again.  In the two-event candidate scenario,
correlation-v2 contributed 15 of 66 SELECTs while preserving the actual
candidate path.

The largest observed linear read share is triage: 9 of 30 SELECTs for a unique
event and 19 of 66 for the candidate pair.  Static inspection localizes its
current shape to `AlertClusterTriageService.assess`: it reads the versioned
cluster lineage in `_members_for_cluster_version`, resolves each member with
`_alert`, and separately evaluates bounded asset/IOC and assessment context.
This is a localization result, not proof that any individual triage query is
redundant.

The seven flushes, three commits, and four transaction begins per unique event
remain high but linear.  They are caused by independent existing persistence
boundaries across raw-event, canonical-alert, deduplication, correlation, and
triage services.  They are deliberately not changed in V1-P2A1.

Exact replay has distinct, expected behavior: it records occurrence/replay
state and reads current state rather than executing the full new-event
correlation/triage sequence.  It is not evidence of a new-event linear
hot-path defect.

## One bounded follow-up optimization

The smallest candidate batch is a separately reviewed **triage read-shape**
change: bulk-read the already selected version-scoped memberships' canonical
alerts in `AlertClusterTriageService.assess`, then retain the existing
membership order when forming the ledger.  It must not change scoring rules,
correlation selection, time windows, flush/commit boundaries, or response
schemas.

Required acceptance gates before such a change are:

- same persisted memberships, scores, ordered reasons, and triage outputs;
- no cross-organization or cross-version read expansion;
- same deterministic replay behavior and promotion boundary;
- a focused PostgreSQL query-boundary regression showing the removed repeated
  alert reads without a new unbounded scan;
- Wazuh ingestion, deduplication, correlation-v2 adversarial, triage, and
  promotion regressions; and
- current-source full backend regression.

## Constraints and limitations

This evidence makes no production-scale, latency, capacity, or throughput
claim.  V1-B3 remains FAILED at 280/300 accepted requests at five events per
second, and no V1-B2/V1-B3 workload was rerun here.  No production application
behavior, schema, migration, authority policy, correlation threshold, triage
rule, AI/provider behavior, R4 resource, or certification tag changed.

## V1-P2B1 appendix — bounded triage materialization result

V1-P2B1 replaces only the assessment path's one CanonicalAlert lookup per
version-scoped membership with one same-organization bulk alert read.  It does
not consolidate flushes, commits, or transactions.  The direct PostgreSQL
query-boundary test remains fixed at three SELECTs (lineage, membership, and
alert materialization) for 1, 5, and 10 members.

The same three bounded stage-attribution scenarios were run after semantic
regressions.  The counters below contain request work only and aggregate-safe
operation counts:

| Scenario | Before direct request | After direct request | Interpretation |
| --- | --- | --- | --- |
| `single_new_event` | 38 SQL; 30 SELECT; triage 9 SELECT | 38 SQL; 30 SELECT; triage 9 SELECT | A singleton has one alert, so the bulk read has no count reduction. |
| `exact_replay` | 53 SQL; 41 SELECT; triage 12 SELECT | 53 SQL; 41 SELECT; triage 12 SELECT | Replay reads existing state and does not run a new assessment. |
| `correlation_candidate` | 79 SQL; 64 SELECT; triage 19 SELECT | 78 SQL; 63 SELECT; triage 18 SELECT | The two-member assessment removes the repeated alert materialization read. |

The post-change candidate preserves 11 INSERTs, 4 UPDATEs, 13 flushes,
6 commits, and 8 transaction begins.  Those unchanged linear persistence
boundaries remain intentionally deferred.  The direct-request candidate total
is distinct from the P1 whole-scenario value of 81 because that earlier driver
also counted post-response validation work; neither value is a throughput or
latency claim.
