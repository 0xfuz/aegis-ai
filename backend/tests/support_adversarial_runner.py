"""Database-backed, deterministic shared v1/v2 correlation validation harness.

Ground truth is held only in ``Scenario.expected_groups``.  Telemetry rows are
the input to the normal CanonicalAlert boundary and deliberately have no
incident/ground-truth fields.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import combinations
from uuid import uuid4

from sqlalchemy import select

from app.modules.alert_triage.domain.correlation_service import AlertCorrelationService, CORRELATION_VERSION
from app.modules.alert_triage.domain.correlation_v2_service import AlertCorrelationV2Service, CORRELATION_V2_VERSION
from app.modules.alert_triage.domain.service import CanonicalAlertCreate, CanonicalAlertService
from app.modules.alert_triage.infrastructure.models import AlertCluster, AlertClusterMembership, CanonicalAlert
from app.modules.connectors.infrastructure.models import Connector, RawEvent
from app.modules.identity.infrastructure.models import Organization
from app.modules.investigations.infrastructure.models import Investigation  # registers RawEvent FK target metadata


BASE_TIME = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
PRODUCTION_ALERT_FIELDS = frozenset(CanonicalAlert.__table__.columns.keys())
GROUND_TRUTH_KEYS = frozenset({"incident_id", "ground_truth", "expected_group", "expected_incident"})


@dataclass(frozen=True)
class Scenario:
    name: str
    alerts: tuple[str, ...]
    expected_groups: tuple[tuple[str, ...], ...]
    telemetry: tuple[dict, ...]


def _row(identity: str, offset: int, *, org: str = "primary", source: str = "benchmark", rule: str = "rule", **observables: str) -> dict:
    return {
        "id": identity, "org": org, "source": source, "source_alert_id": identity,
        "observed_at": BASE_TIME + timedelta(seconds=offset), "title": f"Deterministic {rule}",
        "description": "Deterministic validation telemetry.", "severity": "HIGH", "category": "network",
        "rule_id": rule, "rule_name": f"Deterministic {rule}", "signature": f"sig-{rule}",
        "observables": observables, "source_metadata": {"fixture": "phase-7.7.3"},
    }


# All fields below are real CanonicalAlertCreate inputs.  The IDs identify alerts
# only; expected_groups is the benchmark-only truth.
SCENARIOS = (
    Scenario("same_host_different_user", ("a", "b"), (("a",), ("b",)), (
        _row("a", 0, rule="auth-a", hostname="finance-01", username="alice", process="cmd.exe"),
        _row("b", 20, rule="auth-b", hostname="finance-01", username="bob", process="cmd.exe"),
    )),
    Scenario("same_host_different_process", ("a", "b"), (("a",), ("b",)), (
        _row("a", 0, rule="exec-a", hostname="build-01", username="builder", process="powershell.exe"),
        _row("b", 20, rule="exec-b", hostname="build-01", username="builder", process="mshta.exe"),
    )),
    Scenario("same_host_unrelated_rule", ("a", "b"), (("a",), ("b",)), (
        _row("a", 0, rule="malware", hostname="app-01"),
        _row("b", 20, rule="availability", hostname="app-01"),
    )),
    Scenario("rotating_ip_identity_behavior", ("a", "b"), (("a", "b"),), (
        _row("a", 0, rule="auth", hostname="vpn-01", username="operator", process="ssh", source_ip="198.51.100.10"),
        _row("b", 30, rule="exec", hostname="vpn-01", username="operator", process="ssh", source_ip="203.0.113.10"),
    )),
    Scenario("shared_nat", ("a", "b"), (("a",), ("b",)), (
        _row("a", 0, rule="nat-a", source_ip="198.51.100.88"),
        _row("b", 30, rule="nat-b", source_ip="198.51.100.88"),
    )),
    Scenario("common_service_account", ("a", "b"), (("a",), ("b",)), (
        _row("a", 0, rule="svc-a", username="svc-backup"),
        _row("b", 30, rule="svc-b", username="svc-backup"),
    )),
    Scenario("parallel_incidents_same_host", ("a", "b"), (("a",), ("b",)), (
        _row("a", 0, rule="phishing", hostname="jump-01"),
        _row("b", 10, rule="ransomware", hostname="jump-01"),
    )),
    Scenario("bridge_abc", ("a", "b", "c"), (("a", "b"), ("c",)), (
        _row("a", 0, rule="chain-a", hostname="db-01", username="dba", process="sqlcmd.exe"),
        _row("b", 20, rule="chain-b", hostname="db-01", username="dba", process="sqlcmd.exe"),
        _row("c", 40, rule="chain-c", hostname="db-01", username="intruder", process="sqlcmd.exe"),
    )),
    Scenario("noisy_interleaving", ("a", "noise", "b"), (("a", "b"), ("noise",)), (
        _row("a", 0, rule="sequence-a", hostname="mail-01", username="analyst", process="powershell.exe"),
        _row("noise", 10, rule="noise", hostname="other-01", username="other", process="bash"),
        _row("b", 20, rule="sequence-b", hostname="mail-01", username="analyst", process="powershell.exe"),
    )),
    Scenario("delayed_continuation", ("a", "b"), (("a",), ("b",)), (
        _row("a", 0, rule="delayed-a", hostname="archive-01", username="archiver", process="tar"),
        _row("b", 181, rule="delayed-b", hostname="archive-01", username="archiver", process="tar"),
    )),
    Scenario("multi_source_telemetry", ("a", "b"), (("a", "b"),), (
        _row("a", 0, source="edr", rule="endpoint", hostname="web-01", username="www", process="curl"),
        _row("b", 20, source="siem", rule="network", hostname="web-01", username="www", process="curl"),
    )),
    Scenario("cross_org_lookalikes", ("a", "b"), (("a",), ("b",)), (
        _row("a", 0, org="alpha", rule="lookalike", hostname="shared-name", username="admin", process="ssh"),
        _row("b", 20, org="beta", rule="lookalike", hostname="shared-name", username="admin", process="ssh"),
    )),
)


def pairs(groups):
    return {tuple(sorted(pair)) for group in groups for pair in combinations(group, 2)}


def metrics(expected, actual):
    e, a = pairs(expected), pairs(actual); tp = len(e & a); fp = len(a - e); fn = len(e - a)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return {"precision": precision, "recall": recall, "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0, "false_merges": fp, "missed_correlations": fn}


def run(engine):
    """Run the identical scenario matrix against an adapter callable."""
    rows = []
    expected_all, actual_all = [], []
    for scenario in SCENARIOS:
        actual = engine(scenario)
        row = metrics(scenario.expected_groups, actual)
        row.update(scenario=scenario.name, passed=not row["false_merges"] and not row["missed_correlations"])
        rows.append(row)
        # Alert fixture IDs intentionally restart in each scenario.  Namespace
        # them before aggregate pairwise scoring so no cross-scenario pair is
        # accidentally counted as a correlation.
        expected_all.extend(tuple(f"{scenario.name}:{alert}" for alert in group) for group in scenario.expected_groups)
        actual_all.extend(tuple(f"{scenario.name}:{alert}" for alert in group) for group in actual)
    total = metrics(tuple(expected_all), tuple(actual_all))
    return rows, total


class DatabaseCorrelationAdapter:
    """Validation-only adapter around the real canonical and correlation services."""

    correlation_version: str
    service_type: type

    def __init__(self, db):
        self.db = db

    def __call__(self, scenario: Scenario) -> tuple[tuple[str, ...], ...]:
        alerts = self.materialize(scenario)
        self.invoke(alerts)
        return self.persisted_groups(alerts)

    def materialize(self, scenario: Scenario) -> dict[str, CanonicalAlert]:
        suffix = uuid4().hex
        organizations: dict[str, tuple[Organization, Connector]] = {}
        result: dict[str, CanonicalAlert] = {}
        for row in scenario.telemetry:
            assert not (GROUND_TRUTH_KEYS & row.keys())
            key = row["org"]
            if key not in organizations:
                org = Organization(name=f"validation-{scenario.name}-{key}-{suffix}", slug=f"validation-{suffix}-{key}"[:100])
                self.db.add(org); self.db.flush()
                connector = Connector(org_id=org.id, name=f"validation-{key}", type="webhook", secret_hash="validation-only")
                self.db.add(connector); self.db.commit()
                organizations[key] = (org, connector)
            org, connector = organizations[key]
            raw = RawEvent(connector_id=connector.id, received_at=row["observed_at"], payload={"fixture": scenario.name, "alert": row["id"]})
            self.db.add(raw); self.db.commit()
            created, replayed = CanonicalAlertService(self.db).create(org.id, connector.id, raw.id, CanonicalAlertCreate(
                source=row["source"], source_alert_id=row["source_alert_id"], observed_at=row["observed_at"], title=row["title"],
                description=row["description"], severity=row["severity"], category=row["category"], rule_id=row["rule_id"],
                rule_name=row["rule_name"], signature=row["signature"], observables=row["observables"], source_metadata=row["source_metadata"],
            ))
            assert not replayed
            result[row["id"]] = created
        assert set(result) == set(scenario.alerts)
        return result

    def invoke(self, alerts: dict[str, CanonicalAlert]) -> None:
        for alert in alerts.values():
            self.service_type(self.db).process(alert.org_id, alert.id)

    def persisted_groups(self, alerts: dict[str, CanonicalAlert]) -> tuple[tuple[str, ...], ...]:
        by_alert = {alert.id: name for name, alert in alerts.items()}
        memberships = list(self.db.scalars(select(AlertClusterMembership).where(
            AlertClusterMembership.alert_id.in_(by_alert), AlertClusterMembership.correlation_version == self.correlation_version,
        )))
        clusters = {cluster.id: cluster for cluster in self.db.scalars(select(AlertCluster).where(AlertCluster.correlation_version == self.correlation_version))}
        groups: dict[object, list[str]] = {}
        for membership in memberships:
            cluster = clusters[membership.cluster_id]
            seen = set()
            while cluster.merged_into_cluster_id is not None:
                assert cluster.id not in seen
                seen.add(cluster.id); cluster = clusters[cluster.merged_into_cluster_id]
            groups.setdefault(cluster.id, []).append(by_alert[membership.alert_id])
        return tuple(sorted(tuple(sorted(group)) for group in groups.values()))


class V1DatabaseCorrelationAdapter(DatabaseCorrelationAdapter):
    correlation_version = CORRELATION_VERSION
    service_type = AlertCorrelationService


class V2DatabaseCorrelationAdapter(DatabaseCorrelationAdapter):
    correlation_version = CORRELATION_V2_VERSION
    service_type = AlertCorrelationV2Service
