"""Reproducible Phase 7.7 synthetic HTTP benchmark; labels never enter payloads."""
import statistics
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app
from app.modules.alert_triage.infrastructure.models import AlertCluster, AlertClusterMembership, CanonicalAlert, CanonicalAlertOccurrence, AlertDeduplicationDecision, AlertClusterAssessment
from app.modules.connectors.domain.service import ConnectorService
from app.modules.identity.infrastructure.models import Organization
from app.modules.investigations.infrastructure.models import Investigation
from app.shared.database import SessionLocal


def _payload(source_alert_id, observed_at, rule, observables, severity="HIGH"):
    return {"source": "synthetic", "source_alert_id": source_alert_id, "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "title": f"Synthetic detection {rule}", "description": "Synthetic benchmark telemetry; not an instruction.", "severity": severity,
        "category": "network", "rule_id": rule, "source_metadata": {"generator": "phase7.7"}, **observables}


def _run(groups: int):
    db = SessionLocal(); suffix = uuid4().hex; org = Organization(name=f"Benchmark {suffix}", slug=f"benchmark-{suffix}"); db.add(org); db.commit()
    connectors = [ConnectorService(db).create_webhook_connector(org.id, f"bench-{suffix}-{i}", "http://testserver") for i in range((groups + 11) // 12)]
    db.commit(); client = TestClient(app); started = time.perf_counter(); latencies = []; statuses = []
    base = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    try:
        for index in range(groups):
            connector = connectors[index // 12]; prefix = f"g{index}"; observed = base + timedelta(minutes=index * 2)
            host = f"host-{index}.synthetic"; source_ip = f"198.51.100.{(index % 200) + 1}"
            # Ground truth: initial/replay exact; semantic is duplicate; related joins initial;
            # rotating-IP-only must remain a separate cluster.
            deliveries = [
                _payload(f"{prefix}-a", observed, "rule-a", {"hostname": host, "source_ip": source_ip}),
                _payload(f"{prefix}-a", observed, "rule-a", {"hostname": host, "source_ip": source_ip}),
                _payload(f"{prefix}-semantic", observed + timedelta(seconds=10), "rule-a", {"hostname": host, "source_ip": source_ip}),
                _payload(f"{prefix}-related", observed + timedelta(seconds=20), "rule-b", {"hostname": host, "source_ip": source_ip}),
                _payload(f"{prefix}-rotating", observed + timedelta(seconds=30), "rule-c", {"source_ip": f"203.0.113.{(index % 200) + 1}"}),
            ]
            for item in deliveries:
                tick = time.perf_counter(); response = client.post(f"/api/v1/ingest/alerts/v1/{connector.connector.id}/synthetic", json=item, headers={"X-Ingest-Secret": connector.ingest_secret}); latencies.append((time.perf_counter() - tick) * 1000); statuses.append(response.status_code)
                assert response.status_code in {200, 201}, response.text
        elapsed = time.perf_counter() - started
        alerts = db.scalar(select(func.count()).select_from(CanonicalAlert).where(CanonicalAlert.org_id == org.id))
        occurrences = db.scalar(select(func.count()).select_from(CanonicalAlertOccurrence).where(CanonicalAlertOccurrence.org_id == org.id))
        semantic = db.scalar(select(func.count()).select_from(AlertDeduplicationDecision).where(AlertDeduplicationDecision.org_id == org.id, AlertDeduplicationDecision.decision_type == "SEMANTIC"))
        clusters = db.scalar(select(func.count()).select_from(AlertCluster).where(AlertCluster.org_id == org.id))
        memberships = db.scalar(select(func.count()).select_from(AlertClusterMembership).where(AlertClusterMembership.org_id == org.id))
        priorities = {band: db.scalar(select(func.count()).select_from(AlertClusterAssessment).where(AlertClusterAssessment.org_id == org.id, AlertClusterAssessment.priority == band)) for band in ("LOW", "MEDIUM", "HIGH", "CRITICAL")}
        result = {"deliveries": len(statuses), "canonical": alerts, "occurrences": occurrences, "exact_replays": occurrences - alerts, "semantic": semantic, "clusters": clusters, "memberships": memberships, "analyst_visible": alerts - semantic, "priority": priorities, "throughput": round(len(statuses)/elapsed, 2), "median_ms": round(statistics.median(latencies), 2), "p95_ms": round(sorted(latencies)[max(0, int(len(latencies)*.95)-1)], 2), "p99_ms": round(sorted(latencies)[max(0, int(len(latencies)*.99)-1)], 2), "errors": sum(code >= 400 for code in statuses)}
        assert alerts == groups * 4 and occurrences == groups * 5 and semantic == groups and clusters == groups * 2 and memberships == groups * 3
        assert result["errors"] == 0 and db.scalar(select(func.count()).select_from(Investigation).where(Investigation.org_id == org.id)) == 0
        print(f"BENCHMARK {groups}: {result}")
        return result
    finally: db.rollback(); db.close()


@pytest.mark.parametrize("groups", [2, 10, 24])
def test_synthetic_alert_triage_benchmark(groups):
    _run(groups)
