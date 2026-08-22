#!/usr/bin/env python3
"""Aggregate-only HTTP driver for the bounded V1-B2 local pilot harness.

This process intentionally retains credentials and response bodies only in
memory long enough to make the authenticated request.  Its stdout contains
only scenario aggregates, never identifiers, headers, bodies, or secrets.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import statistics
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _read_secret(path: str) -> str:
    return Path(path).read_text(encoding="utf-8").strip()


def _request(url: str, *, method: str = "GET", payload: dict | None = None, token: str | None = None, secret: str | None = None) -> tuple[int, bytes]:
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if secret:
        headers["X-Ingest-Secret"] = secret
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=15) as response:  # nosec B310: loopback enforced by the shell harness
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read(1024)
    except URLError:
        return 599, b""


def _json(status: int, body: bytes) -> dict:
    if not 200 <= status < 300:
        raise RuntimeError(f"safe HTTP category {status}")
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise RuntimeError("unexpected bounded API response")
    return parsed


def _login_and_rotate(api: str, email: str, initial: str, rotated: str) -> str:
    status, body = _request(f"{api}/auth/login", method="POST", payload={"email": email, "password": initial})
    response = _json(status, body)
    token = response.get("access_token")
    if not isinstance(token, str) or not response.get("password_rotation_required"):
        raise RuntimeError("bootstrap authentication contract failed")
    status, _ = _request(f"{api}/auth/password/rotate", method="POST", token=token, payload={"current_password": initial, "new_password": rotated})
    if status != 204:
        raise RuntimeError(f"safe password-rotation category {status}")
    status, body = _request(f"{api}/auth/login", method="POST", payload={"email": email, "password": rotated})
    response = _json(status, body)
    token = response.get("access_token")
    if not isinstance(token, str) or response.get("password_rotation_required"):
        raise RuntimeError("rotated authentication contract failed")
    return token


def _connector(api: str, token: str, name: str) -> tuple[str, str]:
    status, body = _request(f"{api}/connectors/webhook", method="POST", token=token, payload={"name": name})
    response = _json(status, body)
    connector = response.get("connector")
    if not isinstance(connector, dict) or not isinstance(connector.get("id"), str) or not isinstance(response.get("ingest_secret"), str):
        raise RuntimeError("connector contract failed")
    return connector["id"], response["ingest_secret"]


def _payload(prefix: str, index: int) -> dict:
    # Synthetic RFC-5737 documentation addresses and test-only identities.
    observed = datetime(2026, 8, 22, tzinfo=timezone.utc) + timedelta(seconds=index)
    return {
        "id": f"v1b2-{prefix}-{index:04d}", "timestamp": observed.isoformat().replace("+00:00", "Z"),
        "rule": {"id": "100500", "level": 3, "description": "Synthetic bounded pilot event", "groups": ["syslog"]},
        "manager": {"name": "v1b2-manager"},
        "agent": {"id": f"{index:03d}", "name": f"pilot-host-{index:03d}", "ip": f"198.51.100.{(index % 200) + 1}"},
        "decoder": {"name": "syslog"},
        "data": {"process": "pilot-syslog"},
    }


def _percentile(samples: list[float], percent: float) -> float:
    if not samples:
        return 0.0
    return round(sorted(samples)[max(0, int(len(samples) * percent) - 1)], 2)


def _send_scenario(api: str, token: str, *, name: str, events: int, rate: int, concurrency: int, timeout: int) -> dict:
    # Connector rate limiting is 60/minute. The fixed connector count keeps
    # every synthetic delivery within the certified public boundary.
    connector_count = max(1, (events + 59) // 60)
    connectors = [_connector(api, token, f"{name}-{i}") for i in range(connector_count)]
    started = time.monotonic()
    latencies: list[float] = []
    statuses: Counter[int] = Counter()

    def send(index: int) -> tuple[int, float]:
        connector_id, secret = connectors[index % connector_count]
        tick = time.monotonic()
        status, _ = _request(f"{api}/ingest/wazuh/v1/{connector_id}", method="POST", payload=_payload(name, index), secret=secret)
        return status, (time.monotonic() - tick) * 1000

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = []
        for index in range(events):
            due = started + (index / rate)
            while time.monotonic() < due:
                time.sleep(min(0.01, due - time.monotonic()))
            futures.append(pool.submit(send, index))
        for future in futures:
            status, latency = future.result(timeout=max(1, timeout - int(time.monotonic() - started)))
            statuses[status] += 1
            latencies.append(latency)
    elapsed = time.monotonic() - started
    if elapsed > timeout:
        raise RuntimeError(f"{name} exceeded its fixed duration bound")
    return {
        "scenario": name, "events": events, "accepted": sum(count for status, count in statuses.items() if 200 <= status < 300),
        "rejected": sum(count for status, count in statuses.items() if 400 <= status < 500), "server_errors": sum(count for status, count in statuses.items() if status >= 500),
        "p50_ms": _percentile(latencies, .50), "p95_ms": _percentile(latencies, .95), "p99_ms": _percentile(latencies, .99),
        "duration_seconds": round(elapsed, 2), "throughput_events_per_second": round(events / elapsed, 2),
    }


def _seed_read_investigation(api: str, token: str) -> str:
    connector_id, secret = _connector(api, token, "read-seed")
    payload = {"title": "Synthetic bounded pilot investigation", "severity": "low", "description": "Synthetic benign test record.", "indicators": []}
    status, body = _request(f"{api}/ingest/webhook/{connector_id}", method="POST", payload=payload, secret=secret)
    response = _json(status, body)
    investigation_id = response.get("investigation_id")
    if not isinstance(investigation_id, str):
        raise RuntimeError("read seed contract failed")
    return investigation_id


def _read_scenario(api: str, token: str, concurrency: int, timeout: int) -> dict:
    investigation_id = _seed_read_investigation(api, token)
    endpoints = [
        "/investigations/dashboard-summary?window=7d", "/investigations?limit=20&offset=0", "/alert-triage/clusters?limit=20&offset=0",
        f"/investigations/{investigation_id}/overview", f"/investigations/{investigation_id}/evidence/inventory?limit=20&offset=0",
        f"/investigations/{investigation_id}/timeline?limit=20&offset=0", f"/investigations/{investigation_id}/entities?limit=20&offset=0",
        f"/investigations/{investigation_id}/indicators?limit=20&offset=0", f"/investigations/{investigation_id}/relationships",
        f"/investigations/{investigation_id}/intelligence/runs?limit=20&offset=0", f"/investigations/{investigation_id}/findings?limit=20&offset=0",
        f"/investigations/{investigation_id}/mitre?limit=20&offset=0", f"/investigations/{investigation_id}/notes?limit=20&offset=0",
        f"/investigations/{investigation_id}/audit?limit=20&offset=0",
    ]
    started = time.monotonic(); statuses: Counter[int] = Counter(); latencies: list[float] = []
    def read(endpoint: str) -> tuple[int, float]:
        tick = time.monotonic(); status, _ = _request(f"{api}{endpoint}", token=token); return status, (time.monotonic() - tick) * 1000
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        for status, latency in pool.map(read, endpoints):
            statuses[status] += 1; latencies.append(latency)
    elapsed = time.monotonic() - started
    if elapsed > timeout: raise RuntimeError("read scenario exceeded its fixed duration bound")
    return {"scenario": "bounded_reads", "requests": len(endpoints), "server_errors": sum(count for status, count in statuses.items() if status >= 500),
            "client_errors": sum(count for status, count in statuses.items() if 400 <= status < 500), "p50_ms": _percentile(latencies, .50),
            "p95_ms": _percentile(latencies, .95), "p99_ms": _percentile(latencies, .99), "duration_seconds": round(elapsed, 2)}


def main() -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--api", required=True); parser.add_argument("--email-file", required=True); parser.add_argument("--initial-password-file", required=True); parser.add_argument("--rotated-password-file", required=True)
    for name, default in (("baseline-events", 300), ("baseline-rate", 5), ("baseline-concurrency", 5), ("baseline-timeout", 180), ("burst-events", 150), ("burst-rate", 10), ("burst-concurrency", 10), ("burst-timeout", 90), ("read-concurrency", 10), ("read-timeout", 180), ("forwarder-events", 25), ("forwarder-timeout", 180)):
        parser.add_argument(f"--{name}", type=int, default=default)
    args = parser.parse_args()
    if not args.api.startswith("http://127.0.0.1:"):
        raise SystemExit("local loopback API endpoint required")
    token = _login_and_rotate(args.api, _read_secret(args.email_file), _read_secret(args.initial_password_file), _read_secret(args.rotated_password_file))
    results = [
        _send_scenario(args.api, token, name="ingestion_baseline", events=args.baseline_events, rate=args.baseline_rate, concurrency=args.baseline_concurrency, timeout=args.baseline_timeout),
        _send_scenario(args.api, token, name="controlled_burst", events=args.burst_events, rate=args.burst_rate, concurrency=args.burst_concurrency, timeout=args.burst_timeout),
        _read_scenario(args.api, token, args.read_concurrency, args.read_timeout),
    ]
    # Forwarder outage/recovery requires a loopback TLS proxy/CA fixture. It
    # is intentionally run by the shell harness only after its TLS contract is
    # available; never downgrade the durable forwarder to plaintext for a load test.
    print(json.dumps({"aggregate_only": True, "scenarios": results}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"aggregate_only": True, "safe_failure_category": type(exc).__name__}), file=sys.stderr)
        raise SystemExit(2)
