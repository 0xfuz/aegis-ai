#!/usr/bin/env python3
"""Aggregate-only diagnostics through the canonical Wazuh webhook boundary."""
from __future__ import annotations

import argparse
import copy
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.main import app
from app.modules.alert_triage.domain.correlation_v2_service import CORRELATION_V2_VERSION
from app.modules.alert_triage.infrastructure.models import AlertClusterMembership
from app.shared.database import SessionLocal
from tests.support.wazuh_webhook_fixture import (
    create_wazuh_webhook_fixture,
    post_wazuh_webhook_event,
)

SCENARIOS = {
    "single_new_event": 1,
    "exact_replay": 2,
    "bounded_10": 10,
    "bounded_25": 25,
    "correlation_candidate": 2,
}
COUNTERS = (
    "total_statements", "select_count", "insert_count", "update_count",
    "delete_count", "other_statement_count", "flush_count", "commit_count",
    "rollback_count", "transaction_count",
)
_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE = _ROOT / "backend" / "tests" / "fixtures" / "wazuh" / "sparse_valid.json"


def _classify(statement: str) -> str:
    """Classify only the SQL operation in memory; never retain SQL text."""
    word = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else ""
    return {"SELECT": "select_count", "INSERT": "insert_count", "UPDATE": "update_count", "DELETE": "delete_count"}.get(word, "other_statement_count")


class AggregateCounter:
    """Scoped SQLAlchemy listeners for aggregate request-path counts."""

    def __init__(self, engine: Any):
        self.engine = engine
        self.values = {key: 0 for key in COUNTERS}
        self._installed = False

    def _inc(self, key: str) -> None:
        self.values[key] += 1

    def _statement(self, _conn: Any, _cursor: Any, statement: str, _params: Any, _context: Any, _many: Any) -> None:
        self._inc("total_statements")
        self._inc(_classify(statement))

    def _after_flush(self, *_args: Any) -> None: self._inc("flush_count")
    def _after_commit(self, *_args: Any) -> None: self._inc("commit_count")
    def _after_rollback(self, *_args: Any) -> None: self._inc("rollback_count")
    def _after_begin(self, *_args: Any) -> None: self._inc("transaction_count")

    def install(self) -> None:
        if self._installed:
            return
        event.listen(self.engine, "before_cursor_execute", self._statement)
        event.listen(Session, "after_flush", self._after_flush)
        event.listen(Session, "after_commit", self._after_commit)
        event.listen(Session, "after_rollback", self._after_rollback)
        event.listen(Session, "after_begin", self._after_begin)
        self._installed = True

    def remove(self) -> None:
        if not self._installed:
            return
        event.remove(self.engine, "before_cursor_execute", self._statement)
        event.remove(Session, "after_flush", self._after_flush)
        event.remove(Session, "after_commit", self._after_commit)
        event.remove(Session, "after_rollback", self._after_rollback)
        event.remove(Session, "after_begin", self._after_begin)
        self._installed = False


def _template() -> dict[str, Any]:
    return json.loads(_TEMPLATE.read_text(encoding="utf-8"))


def _event(sequence: int, *, correlation: bool = False) -> dict[str, Any]:
    """Build a deterministic synthetic Wazuh-shaped event; never output it."""
    body = copy.deepcopy(_template())
    observed = datetime(2026, 8, 9, 12, tzinfo=timezone.utc) + timedelta(seconds=sequence * 30)
    body["id"] = f"diagnostic-{sequence:03d}"
    body["timestamp"] = observed.isoformat()
    body["agent"] = {"id": f"{sequence:03d}", "name": f"diagnostic-{sequence}.example.com"}
    body["decoder"] = {"name": "syslog"}
    body["data"] = {
        "user": "diagnostic-user", "process": "diagnostic-process",
        "dstip": "192.0.2.10" if correlation else f"192.0.2.{(sequence % 200) + 20}",
    }
    return body


def _scenario_bodies(scenario: str) -> list[dict[str, Any]]:
    if scenario == "single_new_event": return [_event(1)]
    if scenario == "exact_replay":
        body = _event(1)
        return [body, copy.deepcopy(body)]
    if scenario == "bounded_10": return [_event(index) for index in range(1, 11)]
    if scenario == "bounded_25": return [_event(index) for index in range(1, 26)]
    if scenario == "correlation_candidate":
        # Different hosts avoid semantic dedupe; common user/process/destination
        # and a bounded timestamp gap exercise the actual v2 candidate path.
        return [_event(1, correlation=True), _event(2, correlation=True)]
    raise ValueError("Unsupported diagnostic scenario.")


def _submit(client: TestClient, fixture: Any, body: dict[str, Any]) -> dict[str, Any]:
    """Use the shared fixture's actual endpoint helper; do not retain output."""
    response = post_wazuh_webhook_event(client, fixture, body)
    if response.status_code not in {200, 201}:
        raise RuntimeError("DIAGNOSTIC_HTTP_REJECTED")
    return response.json()  # inspected only in memory for correlation-v2 below


def _run_endpoint_scenario(scenario: str, session: Session) -> tuple[dict[str, int], float]:
    """Setup precedes listener installation, excluding bootstrap SQL counters."""
    fixture = create_wazuh_webhook_fixture(session)
    counter = AggregateCounter(session.get_bind())
    bodies = _scenario_bodies(scenario)
    started = time.monotonic()
    try:
        counter.install()
        with TestClient(app) as client:
            responses = [_submit(client, fixture, body) for body in bodies]
        if scenario == "correlation_candidate":
            if any(response.get("correlation_version") != CORRELATION_V2_VERSION for response in responses):
                raise RuntimeError("DIAGNOSTIC_CORRELATION_NOT_REACHED")
            membership = session.scalar(select(AlertClusterMembership.id).where(
                AlertClusterMembership.org_id == fixture.organization.id,
                AlertClusterMembership.correlation_version == CORRELATION_V2_VERSION,
            ))
            if membership is None:
                raise RuntimeError("DIAGNOSTIC_CORRELATION_NOT_REACHED")
    finally:
        elapsed = round((time.monotonic() - started) * 1000, 2)
        counter.remove()
    return counter.values, elapsed


def _safe_category(exc: Exception) -> str:
    return str(exc) if str(exc) in {"DIAGNOSTIC_HTTP_REJECTED", "DIAGNOSTIC_CORRELATION_NOT_REACHED"} else "DIAGNOSTIC_FAILED"


def run(scenario: str) -> dict[str, Any]:
    if scenario not in SCENARIOS:
        raise ValueError("Unsupported diagnostic scenario.")
    session = SessionLocal()
    result: dict[str, Any] = {
        "schema_version": "v1p1a-ingestion-diagnosis-v1", "scenario": scenario,
        "bounded_event_count": SCENARIOS[scenario], "success": False,
        "safe_failure_category": "", **{key: 0 for key in COUNTERS},
        "elapsed_milliseconds": 0.0,
    }
    try:
        counters, elapsed = _run_endpoint_scenario(scenario, session)
        result.update(counters)
        result["elapsed_milliseconds"] = elapsed
        result["success"] = True
    except Exception as exc:
        result["safe_failure_category"] = _safe_category(exc)
        session.rollback()
    finally:
        session.close()
    return result


def _write(path: str, value: dict[str, Any]) -> None:
    target = Path(path)
    if not target.is_absolute() or target.is_symlink():
        raise ValueError("invalid output path")
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if target.parent.is_symlink():
        raise ValueError("invalid output path")
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as handle:
            json.dump(value, handle, separators=(",", ":"))
            handle.write("\n")
        os.replace(temporary, target)
        os.chmod(target, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one aggregate-only synthetic ingestion diagnostic scenario.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--scenario", required=True, choices=sorted(SCENARIOS))
    args = parser.parse_args(argv)
    _write(args.output, run(args.scenario))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
