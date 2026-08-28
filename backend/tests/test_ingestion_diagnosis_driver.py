import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("ingestion_diagnosis_driver", ROOT / "scripts/release/ingestion_diagnosis_driver.py")
diag = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = diag
SPEC.loader.exec_module(diag)


def test_scenarios_have_exact_bounds_and_use_shared_fastapi_fixture_contract():
    assert diag.SCENARIOS == {
        "single_new_event": 1,
        "exact_replay": 2,
        "bounded_10": 10,
        "bounded_25": 25,
        "correlation_candidate": 2,
    }
    source = (ROOT / "scripts/release/ingestion_diagnosis_driver.py").read_text()
    assert "create_wazuh_webhook_fixture" in source
    assert "post_wazuh_webhook_event" in source
    assert "/api/v1/ingest/wazuh/v1/" not in source


def test_replay_is_identical_and_bounded_sequences_are_unique():
    replay = diag._scenario_bodies("exact_replay")
    assert replay[0] == replay[1] and replay[0] is not replay[1]
    for scenario, count in (("bounded_10", 10), ("bounded_25", 25)):
        bodies = diag._scenario_bodies(scenario)
        assert len(bodies) == count
        assert len({body["id"] for body in bodies}) == count


def test_correlation_candidate_is_bounded_and_requires_v2_path():
    bodies = diag._scenario_bodies("correlation_candidate")
    assert len(bodies) == 2
    assert bodies[0]["agent"]["name"] != bodies[1]["agent"]["name"]
    assert bodies[0]["data"]["user"] == bodies[1]["data"]["user"]
    assert bodies[0]["data"]["process"] == bodies[1]["data"]["process"]
    assert "DIAGNOSTIC_CORRELATION_NOT_REACHED" in (ROOT / "scripts/release/ingestion_diagnosis_driver.py").read_text()


def test_statement_classification_retains_only_operation_counts():
    assert diag._classify("SELECT value") == "select_count"
    assert diag._classify("INSERT value") == "insert_count"
    assert diag._classify("UPDATE value") == "update_count"
    assert diag._classify("DELETE value") == "delete_count"
    assert diag._classify("CREATE value") == "other_statement_count"
    assert all("sql" not in key and "payload" not in key for key in diag.COUNTERS)


def test_listener_removal_is_safe_after_failure(monkeypatch):
    removed = []
    counter = diag.AggregateCounter(object())
    counter._installed = True
    monkeypatch.setattr(diag.event, "remove", lambda _target, name, _callback: removed.append(name))
    counter.remove()
    assert set(removed) == {"before_cursor_execute", "after_flush", "after_commit", "after_rollback", "after_begin"}
    assert not counter._installed


def test_safe_exception_output_has_only_category_and_aggregate_fields(monkeypatch):
    class FakeSession:
        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(diag, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(diag, "_run_endpoint_scenario", lambda *_: (_ for _ in ()).throw(RuntimeError("sensitive value")))
    result = diag.run("single_new_event")
    assert not result["success"] and result["safe_failure_category"] == "DIAGNOSTIC_FAILED"
    serialized = json.dumps(result)
    for forbidden in ("sensitive value", "payload", "secret", "token", "header", "database_url", "sql"):
        assert forbidden not in serialized


def test_atomic_private_output_and_rejects_relative_or_symlink_paths(tmp_path):
    target = tmp_path / "safe.json"
    diag._write(str(target), {"schema_version": "v1", "success": False, "safe_failure_category": "SAFE"})
    assert target.stat().st_mode & 0o777 == 0o600
    assert "payload" not in target.read_text()
    with pytest.raises(ValueError):
        diag._write("relative.json", {})
    linked = tmp_path / "linked.json"
    linked.symlink_to(target)
    with pytest.raises(ValueError):
        diag._write(str(linked), {})
