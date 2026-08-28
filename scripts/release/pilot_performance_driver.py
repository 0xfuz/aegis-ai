#!/usr/bin/env python3
"""Aggregate-only HTTP driver for the bounded V1-B2 local pilot harness."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import socket
import threading
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class DriverFailure(RuntimeError):
    def __init__(self, category: str, operation: str):
        super().__init__(category)
        self.category, self.operation = category, operation


@dataclass
class State:
    started: float
    current_scenario: str = "authentication"
    last_completed_scenario: str = ""
    requested_requests: int = 0
    completed_requests: int = 0
    current_counts: dict | None = None
    completed_scenarios: list[dict] | None = None

    def begin(self, scenario: str) -> None:
        self.current_scenario = scenario
        self.current_counts = {"requested": 0, "submitted": 0, "completed": 0, "accepted": 0, "failed": 0, "pending_at_deadline": 0}
        if self.completed_scenarios is None:
            self.completed_scenarios = []

    def complete(self) -> None:
        self.last_completed_scenario = self.current_scenario

    def requested(self) -> None:
        self.requested_requests += 1
        if self.current_counts is not None:
            self.current_counts["requested"] += 1

    def completed(self, status: int | None = None) -> None:
        self.completed_requests += 1
        if self.current_counts is not None:
            self.current_counts["completed"] += 1
            if status is not None and 200 <= status < 300:
                self.current_counts["accepted"] += 1
            elif status is not None:
                self.current_counts["failed"] += 1


def _read_secret(path: str) -> str:
    return Path(path).read_text(encoding="utf-8").strip()


def _request(url: str, *, category: str, operation: str, method: str = "GET", payload: dict | None = None, token: str | None = None, secret: str | None = None) -> tuple[int, bytes]:
    headers, data = {"Accept": "application/json"}, None
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if secret:
        headers["X-Ingest-Secret"] = secret
    try:
        with urlopen(Request(url, data=data, headers=headers, method=method), timeout=15) as response:  # nosec B310: shell verifies loopback
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read(1024)
    except (TimeoutError, socket.timeout) as exc:
        raise DriverFailure(category, operation) from exc
    except URLError as error:
        if isinstance(error.reason, (TimeoutError, socket.timeout)):
            raise DriverFailure(category, operation) from error
        return 599, b""


def _call(state: State, url: str, *, category: str, operation: str, **kwargs) -> tuple[int, bytes]:
    state.requested()
    result = _request(url, category=category, operation=operation, **kwargs)
    state.completed(result[0])
    return result


def _json(status: int, body: bytes, operation: str) -> dict:
    if not 200 <= status < 300:
        raise DriverFailure("API_RESPONSE_REJECTED", operation)
    try:
        value = json.loads(body)
    except (TypeError, ValueError) as exc:
        raise DriverFailure("API_RESPONSE_INVALID", operation) from exc
    if not isinstance(value, dict):
        raise DriverFailure("API_RESPONSE_INVALID", operation)
    return value


def _login_and_rotate(api: str, email: str, initial: str, rotated: str, state: State) -> str:
    status, body = _call(state, f"{api}/auth/login", category="AUTH_REQUEST_TIMEOUT", operation="initial_login", method="POST", payload={"email": email, "password": initial})
    response = _json(status, body, "initial_login")
    token = response.get("access_token")
    if not isinstance(token, str) or not response.get("password_rotation_required"):
        raise DriverFailure("AUTH_CONTRACT_REJECTED", "initial_login")
    status, _ = _call(state, f"{api}/auth/password/rotate", category="AUTH_REQUEST_TIMEOUT", operation="password_rotation", method="POST", token=token, payload={"current_password": initial, "new_password": rotated})
    if status != 204:
        raise DriverFailure("AUTH_CONTRACT_REJECTED", "password_rotation")
    status, body = _call(state, f"{api}/auth/login", category="AUTH_REQUEST_TIMEOUT", operation="rotated_login", method="POST", payload={"email": email, "password": rotated})
    response = _json(status, body, "rotated_login")
    token = response.get("access_token")
    if not isinstance(token, str) or response.get("password_rotation_required"):
        raise DriverFailure("AUTH_CONTRACT_REJECTED", "rotated_login")
    return token


def _connector(api: str, token: str, name: str, state: State) -> tuple[str, str]:
    status, body = _call(state, f"{api}/connectors/webhook", category="INGEST_REQUEST_TIMEOUT", operation="connector_creation", method="POST", token=token, payload={"name": name})
    response = _json(status, body, "connector_creation")
    connector = response.get("connector")
    if not isinstance(connector, dict) or not isinstance(connector.get("id"), str) or not isinstance(response.get("ingest_secret"), str):
        raise DriverFailure("INGEST_CONTRACT_REJECTED", "connector_creation")
    return connector["id"], response["ingest_secret"]


def _payload(prefix: str, index: int) -> dict:
    observed = datetime(2026, 8, 22, tzinfo=timezone.utc) + timedelta(seconds=index)
    return {"id": f"v1b2-{prefix}-{index:04d}", "timestamp": observed.isoformat().replace("+00:00", "Z"), "rule": {"id": "100500", "level": 3, "description": "Synthetic bounded pilot event", "groups": ["syslog"]}, "manager": {"name": "v1b2-manager"}, "agent": {"id": f"{index:03d}", "name": f"pilot-host-{index:03d}", "ip": f"198.51.100.{(index % 200) + 1}"}, "decoder": {"name": "syslog"}, "data": {"process": "pilot-syslog"}}


def _percentile(samples: list[float], fraction: float) -> float:
    return 0.0 if not samples else round(sorted(samples)[max(0, int(len(samples) * fraction) - 1)], 2)


def _remaining(deadline: float, operation: str) -> float:
    left = deadline - time.monotonic()
    if left <= 0:
        raise DriverFailure("SCENARIO_DEADLINE_TIMEOUT", operation)
    return left


def _result(future: concurrent.futures.Future, deadline: float, operation: str):
    try:
        return future.result(timeout=_remaining(deadline, operation))
    except DriverFailure:
        raise
    except concurrent.futures.TimeoutError as exc:
        raise DriverFailure("FUTURE_COMPLETION_TIMEOUT", operation) from exc


def _send_scenario(api: str, token: str, *, name: str, events: int, rate: int, concurrency: int, timeout: int, state: State) -> dict:
    connectors = [_connector(api, token, f"{name}-{i}", state) for i in range(max(1, (events + 59) // 60))]
    # Connector/auth traffic is run-global setup, never event accounting.
    state.begin(name)
    started, statuses, latencies = time.monotonic(), Counter(), []
    # The bounded drain deadline starts at the final scheduled submission:
    # emission window + existing 15s request timeout + 2s orchestration slack,
    # never beyond the certified scenario bound.
    emission_window = max(0, events - 1) / rate
    deadline = min(started + timeout, started + emission_window + 15 + 2)
    counts = {"target_events": events, "futures_scheduled": 0, "http_started": 0, "http_returned": 0, "accepted": 0, "rejected_or_failed": 0, "cancelled_before_start": 0, "running_at_deadline": 0, "queued_at_deadline": 0, "late_completed_after_deadline": 0}
    counts_lock = threading.Lock()
    frozen = threading.Event()
    def send(index: int) -> tuple[int, float]:
        connector_id, secret = connectors[index % len(connectors)]
        tick = time.monotonic()
        with counts_lock: counts["http_started"] += 1
        status, _ = _call(state, f"{api}/ingest/wazuh/v1/{connector_id}", category="INGEST_REQUEST_TIMEOUT", operation="wazuh_ingestion", method="POST", payload=_payload(name, index), secret=secret)
        with counts_lock:
            if frozen.is_set(): counts["late_completed_after_deadline"] += 1
            else:
                counts["http_returned"] += 1
                counts["accepted" if 200 <= status < 300 else "rejected_or_failed"] += 1
        return status, (time.monotonic() - tick) * 1000
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=concurrency)
    try:
        futures = []
        for index in range(events):
            due = started + index / rate
            while time.monotonic() < due:
                time.sleep(min(.01, due - time.monotonic(), _remaining(deadline, "rate_scheduling")))
            futures.append(pool.submit(send, index)); counts["futures_scheduled"] += 1
        done, pending = concurrent.futures.wait(futures, timeout=_remaining(deadline, "ingestion_future"))
        for future in done:
            status, latency = future.result()
            statuses[status] += 1; latencies.append(latency)
        frozen.set()
        if pending:
            # Reconcile every Future that crossed the deadline before deciding
            # it is genuinely pending; never label a completed Future timed out.
            reconciled = [future for future in pending if future.done()]
            for future in reconciled:
                pending.remove(future)
                status, latency = future.result()
                statuses[status] += 1; latencies.append(latency)
            if pending:
                counts["running_at_deadline"] = sum(item.running() for item in pending)
                counts["queued_at_deadline"] = len(pending) - counts["running_at_deadline"]
                counts["cancelled_before_start"] = sum(item.cancel() for item in pending if not item.running())
                state.current_counts = dict(counts)
                raise DriverFailure("FUTURE_COMPLETION_TIMEOUT", "ingestion_future")
    finally:
        # Never let context-manager shutdown turn a bounded deadline into an
        # unbounded hidden wait. In-flight HTTP calls retain their own 15s cap.
        pool.shutdown(wait=False, cancel_futures=True)
    elapsed = time.monotonic() - started; state.complete()
    state.current_counts = dict(counts)
    return {"scenario": name, **counts, "p50_ms": _percentile(latencies, .5), "p95_ms": _percentile(latencies, .95), "p99_ms": _percentile(latencies, .99), "duration_seconds": round(elapsed, 2), "achieved_accepted_rate": round(counts["accepted"] / elapsed, 2), "target_met": counts["accepted"] == events and counts["futures_scheduled"] == events, "invariants_valid": counts["accepted"] + counts["rejected_or_failed"] <= counts["http_returned"] <= counts["http_started"] <= counts["futures_scheduled"]}


def _read_scenario(api: str, token: str, concurrency: int, timeout: int, state: State) -> dict:
    state.begin("bounded_reads")
    connector_id, secret = _connector(api, token, "read-seed", state)
    status, body = _call(state, f"{api}/ingest/webhook/{connector_id}", category="READ_REQUEST_TIMEOUT", operation="read_seed_ingestion", method="POST", payload={"title": "Synthetic bounded pilot investigation", "severity": "low", "description": "Synthetic benign test record.", "indicators": []}, secret=secret)
    investigation = _json(status, body, "read_seed_ingestion").get("investigation_id")
    if not isinstance(investigation, str):
        raise DriverFailure("READ_CONTRACT_REJECTED", "read_seed_ingestion")
    endpoints = ["/investigations/dashboard-summary?window=7d", "/investigations?limit=20&offset=0", "/alert-triage/clusters?limit=20&offset=0", f"/investigations/{investigation}/overview", f"/investigations/{investigation}/evidence/inventory?limit=20&offset=0", f"/investigations/{investigation}/timeline?limit=20&offset=0", f"/investigations/{investigation}/entities?limit=20&offset=0", f"/investigations/{investigation}/indicators?limit=20&offset=0", f"/investigations/{investigation}/relationships", f"/investigations/{investigation}/intelligence/runs?limit=20&offset=0", f"/investigations/{investigation}/findings?limit=20&offset=0", f"/investigations/{investigation}/mitre?limit=20&offset=0", f"/investigations/{investigation}/notes?limit=20&offset=0", f"/investigations/{investigation}/audit?limit=20&offset=0"]
    started, deadline, statuses, latencies = time.monotonic(), time.monotonic() + timeout, Counter(), []
    def read(endpoint: str) -> tuple[int, float]:
        tick = time.monotonic(); status, _ = _call(state, f"{api}{endpoint}", category="READ_REQUEST_TIMEOUT", operation="bounded_read", token=token); return status, (time.monotonic() - tick) * 1000
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        for future in [pool.submit(read, endpoint) for endpoint in endpoints]:
            status, latency = _result(future, deadline, "read_future")
            statuses[status] += 1; latencies.append(latency)
    elapsed = time.monotonic() - started; state.complete()
    return {"scenario": "bounded_reads", "requests": len(endpoints), "server_errors": sum(v for k, v in statuses.items() if k >= 500), "client_errors": sum(v for k, v in statuses.items() if 400 <= k < 500), "p50_ms": _percentile(latencies, .5), "p95_ms": _percentile(latencies, .95), "p99_ms": _percentile(latencies, .99), "duration_seconds": round(elapsed, 2)}


def _smoke(api: str, token: str, state: State) -> dict:
    """One ingestion and one authenticated bounded read; never a benchmark."""
    state.begin("measurement_smoke")
    connector_id, secret = _connector(api, token, "measurement-smoke", state)
    status, _ = _call(state, f"{api}/ingest/wazuh/v1/{connector_id}", category="INGEST_REQUEST_TIMEOUT", operation="wazuh_ingestion", method="POST", payload=_payload("smoke", 0), secret=secret)
    if not 200 <= status < 300:
        raise DriverFailure("INGEST_CONTRACT_REJECTED", "wazuh_ingestion")
    status, _ = _call(state, f"{api}/investigations/dashboard-summary?window=7d", category="READ_REQUEST_TIMEOUT", operation="bounded_read", token=token)
    if not 200 <= status < 300:
        raise DriverFailure("READ_CONTRACT_REJECTED", "bounded_read")
    state.complete()
    return {"scenario": "measurement_smoke", "requests": 2, "status": "completed"}


def _write_status(path: str, state: State, category: str = "", operation: str = "") -> None:
    target = Path(path)
    if target.is_symlink():
        raise DriverFailure("DRIVER_STATUS_PATH_INVALID", "status_persistence")
    value = {"aggregate_only": True, "current_scenario": state.current_scenario, "last_completed_scenario": state.last_completed_scenario, "failed_scenario": state.current_scenario if category else "", "safe_failure_category": category, "service_or_operation": operation, "completed_requests": state.completed_requests, "requested_requests": state.requested_requests, "scenario_counts": state.current_counts or {}, "completed_scenarios": state.completed_scenarios or [], "elapsed_seconds": round(time.monotonic() - state.started, 2), "measurement_started": True}
    temporary = target.with_name(f".{target.name}.{os.getpid()}")
    temporary.write_text(json.dumps(value, separators=(",", ":")) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600); os.replace(temporary, target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    for option in ("api", "email-file", "initial-password-file", "rotated-password-file", "status-file"):
        parser.add_argument(f"--{option}", required=True)
    parser.add_argument("--smoke-only", action="store_true")
    parser.add_argument("--baseline-only", action="store_true")
    for name, default in (("baseline-events", 300), ("baseline-rate", 5), ("baseline-concurrency", 5), ("baseline-timeout", 180), ("burst-events", 150), ("burst-rate", 10), ("burst-concurrency", 10), ("burst-timeout", 90), ("read-concurrency", 10), ("read-timeout", 180), ("forwarder-events", 25), ("forwarder-timeout", 180)):
        parser.add_argument(f"--{name}", type=int, default=default)
    args = parser.parse_args(argv)
    if not args.api.startswith("http://127.0.0.1:"):
        raise SystemExit("local loopback API endpoint required")
    state = State(time.monotonic())
    try:
        token = _login_and_rotate(args.api, _read_secret(args.email_file), _read_secret(args.initial_password_file), _read_secret(args.rotated_password_file), state); state.complete()
        if args.smoke_only:
            results = [_smoke(args.api, token, state)]
        elif args.baseline_only:
            result = _send_scenario(args.api, token, name="ingestion_baseline", events=args.baseline_events, rate=args.baseline_rate, concurrency=args.baseline_concurrency, timeout=args.baseline_timeout, state=state)
            results = [result]; state.completed_scenarios.append(result)
        else:
            results = []
            for scenario in (("ingestion_baseline", args.baseline_events, args.baseline_rate, args.baseline_concurrency, args.baseline_timeout), ("controlled_burst", args.burst_events, args.burst_rate, args.burst_concurrency, args.burst_timeout)):
                result = _send_scenario(args.api, token, name=scenario[0], events=scenario[1], rate=scenario[2], concurrency=scenario[3], timeout=scenario[4], state=state)
                results.append(result); state.completed_scenarios.append(result)
            result = _read_scenario(args.api, token, args.read_concurrency, args.read_timeout, state=state)
            results.append(result); state.completed_scenarios.append(result)
    except DriverFailure as failure:
        _write_status(args.status_file, state, failure.category, failure.operation); return 2
    except TimeoutError:
        _write_status(args.status_file, state, "DRIVER_UNCLASSIFIED_TIMEOUT", "driver_boundary"); return 2
    except Exception:
        _write_status(args.status_file, state, "DRIVER_CONTRACT_FAILED", "driver_boundary"); return 2
    _write_status(args.status_file, state)
    print(json.dumps({"aggregate_only": True, "scenarios": results}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
