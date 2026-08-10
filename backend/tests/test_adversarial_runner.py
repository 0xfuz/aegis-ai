from sqlalchemy import func, select

from app.modules.alert_triage.domain.correlation_service import AlertCorrelationService, CORRELATION_VERSION
from app.modules.alert_triage.domain.correlation_v2_service import AlertCorrelationV2Service, CORRELATION_V2_VERSION
from app.modules.alert_triage.infrastructure.models import AlertClusterMembership, CanonicalAlert
from app.shared.database import SessionLocal
from support_adversarial_runner import (
    GROUND_TRUTH_KEYS, PRODUCTION_ALERT_FIELDS, SCENARIOS, V1DatabaseCorrelationAdapter,
    V2DatabaseCorrelationAdapter, metrics, run,
)

def test_pairwise_metrics_are_exact():
 result=metrics((("a","b"),("c",)),(("a","b","c"),))
 assert result=={"precision":1/3,"recall":1.0,"f1":.5,"false_merges":2,"missed_correlations":0}

def test_shared_runner_emits_each_scenario_and_per_scenario_result():
 rows,total=run(lambda s:s.expected_groups)
 assert len(rows)==len(SCENARIOS) and all(row["passed"] for row in rows)
 assert total["precision"]==total["recall"]==total["f1"]==1.0


def test_all_scenarios_have_complete_materializable_telemetry_and_no_ground_truth_fields():
    assert len(SCENARIOS) == 12
    for scenario in SCENARIOS:
        assert {row["id"] for row in scenario.telemetry} == set(scenario.alerts)
        for row in scenario.telemetry:
            assert GROUND_TRUTH_KEYS.isdisjoint(row)
            assert GROUND_TRUTH_KEYS.isdisjoint(row["source_metadata"])
            assert {"source", "source_alert_id", "observed_at", "title", "severity", "category", "rule_id", "observables"} <= set(row)


def test_v1_adapter_materializes_every_scenario_and_uses_only_v1_persisted_memberships(monkeypatch):
    db = SessionLocal()
    try:
        monkeypatch.setattr(AlertCorrelationV2Service, "process", lambda *_: (_ for _ in ()).throw(AssertionError("v2 invoked by v1 adapter")))
        adapter = V1DatabaseCorrelationAdapter(db)
        for scenario in SCENARIOS:
            actual = adapter(scenario)
            assert actual
        for alert in db.scalars(select(CanonicalAlert)):
            assert GROUND_TRUTH_KEYS.isdisjoint(alert.source_metadata)
            assert not (GROUND_TRUTH_KEYS & PRODUCTION_ALERT_FIELDS)
    finally:
        db.rollback(); db.close()


def test_v2_adapter_materializes_every_scenario_and_uses_only_v2_persisted_memberships(monkeypatch):
    db = SessionLocal()
    try:
        monkeypatch.setattr(AlertCorrelationService, "process", lambda *_: (_ for _ in ()).throw(AssertionError("v1 invoked by v2 adapter")))
        adapter = V2DatabaseCorrelationAdapter(db)
        for scenario in SCENARIOS:
            actual = adapter(scenario)
            assert actual
    finally:
        db.rollback(); db.close()


def test_adapters_read_persisted_memberships_and_repeated_runs_are_deterministic():
    db = SessionLocal()
    try:
        first = V2DatabaseCorrelationAdapter(db)(SCENARIOS[3])
        second = V2DatabaseCorrelationAdapter(db)(SCENARIOS[3])
        assert first == second == (("a", "b"),)
        assert db.scalar(select(func.count()).select_from(AlertClusterMembership).where(
            AlertClusterMembership.correlation_version == CORRELATION_V2_VERSION,
        )) >= 4
    finally:
        db.rollback(); db.close()


def test_adapters_keep_v1_v2_memberships_isolated_for_the_same_canonical_alerts():
    db = SessionLocal()
    try:
        v1, v2 = V1DatabaseCorrelationAdapter(db), V2DatabaseCorrelationAdapter(db)
        alerts = v1.materialize(SCENARIOS[3])
        v1.invoke(alerts)
        v1_groups = v1.persisted_groups(alerts)
        v2.invoke(alerts)
        assert v1.persisted_groups(alerts) == v1_groups
        assert v2.persisted_groups(alerts) == (("a", "b"),)
        for alert in alerts.values():
            versions = set(db.scalars(select(AlertClusterMembership.correlation_version).where(
                AlertClusterMembership.alert_id == alert.id,
            )))
            assert versions == {CORRELATION_VERSION, CORRELATION_V2_VERSION}
    finally:
        db.rollback(); db.close()
