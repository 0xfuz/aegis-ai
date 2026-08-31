# V1-P1 ingestion SQL diagnosis

Status: diagnostic evidence only. This document makes no throughput,
production-capacity, latency-SLO, losslessness, or production-readiness claim.

## Scope and methodology

The operator-run V1-P1A diagnostic completed from commit
`5da563b330349d4e804c58630dfd3e1f789534d8` against a fresh disposable
PostgreSQL database at the sole Alembic head `0024`. It used the existing
authenticated Wazuh webhook boundary, synthetic test fixtures, and
test-only SQLAlchemy event counters. The counters retained only statement
types, session lifecycle counts, and aggregate elapsed time. They retained no
SQL text or parameters, request/response bodies, source identities,
credentials, headers, database URL, rows, logs, or dumps.

The bounded scenarios were sequential, not a rate or load test:

- `single_new_event`: one new Wazuh-shaped event.
- `exact_replay`: the same source identity and payload twice.
- `bounded_10`: ten unique sequential events.
- `bounded_25`: twenty-five unique sequential events.
- `correlation_candidate`: two deterministic inputs that reached the actual
  persisted correlation-v2 path through the webhook endpoint.

The harness exit code was zero and cleanup completed. Its operator summary
correctly remains `NOT MEASURED`: this is a query-shape diagnosis, not a
performance certification.

## Aggregate observations

| Scenario | Events | SELECT | INSERT | UPDATE | Total SQL | Flush | Commit | Transactions | Elapsed ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `single_new_event` | 1 | 30 | 6 | 2 | 38 | 7 | 3 | 4 | 355.50 |
| `bounded_10` | 10 | 390 | 60 | 20 | 470 | 70 | 30 | 40 | 2,523.25 |
| `bounded_25` | 25 | 1,350 | 150 | 50 | 1,550 | 175 | 75 | 100 | 6,422.87 |
| `exact_replay` | 2 | 41 | — | — | 53 | 11 | 5 | — | 501.73 |
| `correlation_candidate` | 2 | 66 | 11 | 4 | 81 | 13 | 6 | 9 | 521.07 |

`—` means the retained requested aggregate excerpt did not include that field;
it must not be inferred.

For the isolated new-event scenarios, the measured statement formulas are:

- `SELECT(n) = n² + 29n`
- `Total SQL(n) = n² + 37n`

INSERT, UPDATE, flush, commit, and transaction counts are linear in this
bounded dataset. The replay scenario is a separate read path with 41 SELECTs
for two submissions. The controlled correlation candidate costs 66 SELECTs
and confirms that the version-two path was exercised; it is not evidence of a
throughput envelope.

## Synchronous path and localized hotspot

The HTTP handler in
`backend/app/modules/connectors/api/router.py` authenticates the connector and
calls `WazuhAlertWebhookService.ingest`. That service synchronously persists
the RawEvent, maps the Wazuh record, creates the canonical alert, runs
deduplication, invokes `AlertCorrelationV2Service.process`, invokes triage for
the resulting cluster, and returns only after the request transaction commits.

The proven quadratic read shape is in
`backend/app/modules/alert_triage/domain/correlation_v2_service.py`, in
`AlertCorrelationV2Service.process`:

1. It reads all OPEN `correlation-v2` clusters for the current organization.
2. For every returned cluster, it performs a separate persisted membership
   query.
3. For every returned membership, it calls `_alert`, a separate
   organization-scoped canonical-alert SELECT.
4. It then computes the deterministic compatibility ledger from those loaded
   alerts.

For the isolated sequence, each new unique event leaves another open cluster.
The next event therefore repeats membership and canonical-alert reads across
the growing set. This static loop/query boundary is consistent with the
measured `n²` SELECT coefficient. It is the confirmed hotspot.

The later selected-cluster membership read and the triage path also read
persisted data. In the measured singleton-cluster sequence, those reads,
deduplication, authentication, RawEvent/canonical persistence, response work,
and triage are linear secondary costs. In particular, triage reads its chosen
cluster/version members and alerts, cluster lineage, assets, IOCs, and an
assessment lookup; it does not execute inside the correlation candidate loop.

No ORM relationship lazy-load was used as the demonstrated quadratic boundary:
the repeated reads are explicit `select(...)` calls. No conclusion is drawn
about unmeasured database plan/index behavior, locks, network latency, or
larger cluster-member cardinalities.

## Rejected or unproven hypotheses

- The evidence does not prove that repeated organization authentication lookup
  is quadratic; it occurs per request and is part of the linear remainder.
- The evidence does not prove a full-table scan or missing-index defect;
  statement counts do not retain query plans or SQL text.
- The evidence does not show triage reads inside the correlation-candidate
  loop.
- The evidence does not support asynchronous deferral of persistence,
  deduplication, correlation, or triage. Those operations remain synchronous
  authoritative request-path behavior.
- The evidence does not justify reducing flush/commit boundaries in the first
  batch. Their measured aggregate counts are linear and are a separate later
  investigation.

## Smallest recommended optimization batch

Change only correlation-v2 candidate loading: replace the loop’s per-open-
cluster membership query and per-membership `_alert` query with one bounded,
organization-scoped bulk read of v2 memberships and their canonical alerts for
the already-selected OPEN v2 clusters. Group those in memory by cluster ID,
then apply the existing deterministic representative, compatibility, tie-break,
and ledger code unchanged.

The batch must not alter deduplication, membership rows or their stored
reasons/scores, correlation version selection, triage, flush/commit behavior,
transaction boundaries, promotion, or the response schema. It must retain
strict organization predicates and never load another organization's alerts.

## Required acceptance gates for that batch

- Identical authoritative persisted RawEvent, CanonicalAlert, deduplication,
  correlation-v2 membership, membership reasons/scores, and triage records for
  the existing fixtures.
- Identical deterministic correlation decisions and version-aware behavior,
  including cross-organization isolation and replay behavior.
- Identical triage outputs, transaction atomicity, analyst-controlled
  promotion behavior, and webhook response schema.
- A focused query-count regression showing removal of the measured `n²`
  SELECT component for the same `1`, `10`, and `25` diagnostic shape.
- full backend certification after the production change.
- No V1-B2 performance benchmark rerun until the query-shape change is
  separately validated.

## Limitations

This diagnosis is a small, local, disposable-database observation. It does
not certify a sustainable event rate, production capacity, high availability,
hardware suitability, or a supported throughput envelope. V1-B2 remains
blocked as documented elsewhere.
