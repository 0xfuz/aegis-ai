"""Deterministic aggregate-only coverage for the V1-B2 driver."""
from __future__ import annotations

import concurrent.futures
import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("pilot_performance_driver", ROOT / "scripts/release/pilot_performance_driver.py")
assert SPEC and SPEC.loader
driver = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = driver
SPEC.loader.exec_module(driver)


def test_individual_auth_timeout_is_classified_without_request_content(monkeypatch):
    monkeypatch.setattr(driver, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError()))
    with pytest.raises(driver.DriverFailure, match="AUTH_REQUEST_TIMEOUT") as failure:
        driver._request("http://127.0.0.1:18100/api/v1/auth/login", category="AUTH_REQUEST_TIMEOUT", operation="initial_login")
    assert failure.value.operation == "initial_login"


def test_future_timeout_and_partial_counts_remain_safe(tmp_path):
    state = driver.State(time.monotonic(), current_scenario="ingestion_baseline", requested_requests=4, completed_requests=2)
    future = concurrent.futures.Future()
    with pytest.raises(driver.DriverFailure, match="FUTURE_COMPLETION_TIMEOUT"):
        driver._result(future, time.monotonic() + 0.001, "ingestion_future")
    status = tmp_path / "driver-status.json"
    driver._write_status(str(status), state, "FUTURE_COMPLETION_TIMEOUT", "ingestion_future")
    recorded = json.loads(status.read_text(encoding="utf-8"))
    assert recorded["current_scenario"] == recorded["failed_scenario"] == "ingestion_baseline"
    assert recorded["requested_requests"] == 4 and recorded["completed_requests"] == 2
    assert {"token", "password", "body", "url", "header"}.isdisjoint(recorded)


def test_driver_stops_before_later_scenarios_when_authentication_times_out(monkeypatch, tmp_path):
    status = tmp_path / "driver-status.json"
    for name in ("email", "initial", "rotated"):
        (tmp_path / name).write_text("bounded-test-value\n", encoding="utf-8")
    monkeypatch.setattr(driver, "_login_and_rotate", lambda *_args: (_ for _ in ()).throw(driver.DriverFailure("AUTH_REQUEST_TIMEOUT", "initial_login")))
    monkeypatch.setattr(driver, "_send_scenario", lambda *_args, **_kwargs: pytest.fail("later scenario must not start"))
    exit_code = driver.main(["--api", "http://127.0.0.1:18100/api/v1", "--email-file", str(tmp_path / "email"), "--initial-password-file", str(tmp_path / "initial"), "--rotated-password-file", str(tmp_path / "rotated"), "--status-file", str(status)])
    recorded = json.loads(status.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert recorded["safe_failure_category"] == "AUTH_REQUEST_TIMEOUT"
    assert recorded["last_completed_scenario"] == "" and recorded["measurement_started"] is True


def test_smoke_mode_is_one_ingestion_and_one_bounded_read_only():
    source = (ROOT / "scripts/release/pilot_performance_driver.py").read_text(encoding="utf-8")
    harness = (ROOT / "scripts/release/run-pilot-performance.sh").read_text(encoding="utf-8")
    assert 'parser.add_argument("--smoke-only", action="store_true")' in source
    assert 'results = [_smoke(args.api, token, state)] if args.smoke_only' in source
    assert '"scenario": "measurement_smoke", "requests": 2' in source
    assert '--smoke-only) SMOKE_ONLY=true' in harness
    assert 'PROJECT="aegis-v1b2-smoke-pilot"' in harness
    smoke = harness[harness.index("start_smoke_core() {"):harness.index("measure() {")]
    assert 'up -d postgres migrate api' in smoke
    assert all(forbidden not in smoke for forbidden in ("frontend", "redis", "intelligence-worker", "intelligence-beat", "ollama", "wazuh"))
    assert 'mode=(--smoke-only)' in harness and 'SMOKE_STATUS="SMOKE_PASS"' in harness and 'SMOKE_FAIL' in harness
