import json
from pathlib import Path

import pytest

from integrations.wazuh.forwarder import DurableSpool, ForwarderConfig, SpoolFullError, WazuhForwarder


def config(tmp_path, **changes):
    value = dict(base_url="https://aegis.test", connector_id="connector", ingest_secret="secret-never-log", spool_dir=tmp_path, initial_delay_seconds=10, maximum_delay_seconds=60, maximum_attempts=2, maximum_retry_age_seconds=1000, maximum_spool_bytes=100000)
    value.update(changes); return ForwarderConfig(**value)

def payload(): return {"id": "1", "timestamp": "2026-08-10T12:00:00Z", "rule": {"id": "1", "level": 3}, "manager": {"name": "m"}}

def test_environment_configuration_reads_only_a_bounded_secret_file(tmp_path):
    secret = tmp_path / "ingest-secret"; secret.write_text("test-secret-not-logged\n")
    config = ForwarderConfig.from_env({"AEGIS_WAZUH_BASE_URL": "https://aegis.test", "AEGIS_WAZUH_CONNECTOR_ID": "connector", "AEGIS_WAZUH_INGEST_SECRET_FILE": str(secret), "AEGIS_WAZUH_SPOOL_DIR": str(tmp_path / "spool")})
    assert config.ingest_secret == "test-secret-not-logged"
    with pytest.raises(ValueError):
        ForwarderConfig.from_env({"AEGIS_WAZUH_BASE_URL": "https://aegis.test", "AEGIS_WAZUH_CONNECTOR_ID": "connector", "AEGIS_WAZUH_INGEST_SECRET": "not-supported", "AEGIS_WAZUH_SPOOL_DIR": str(tmp_path / "spool")})

def test_success_and_replay_remove_original_payload_unchanged(tmp_path):
    seen = []
    f = WazuhForwarder(config(tmp_path), post=lambda *args: seen.append(json.loads(args[1])) or 201, clock=lambda: 100)
    first = f.submit(payload()); assert f.submit(payload()) == first; f.drain()
    assert seen == [payload()] and not list((tmp_path / "pending").glob("*.json"))
    f = WazuhForwarder(config(tmp_path), post=lambda *args: 200, clock=lambda: 101); f.submit({**payload(), "id": "2"}); f.drain(); assert not list((tmp_path / "pending").glob("*.json"))

@pytest.mark.parametrize("outcome", [TimeoutError(), OSError(), 500, 503, 429])
def test_retryable_failures_persist_attempt_and_backoff(tmp_path, outcome):
    f = WazuhForwarder(config(tmp_path), post=lambda *args: (_ for _ in ()).throw(outcome) if isinstance(outcome, Exception) else outcome, clock=lambda: 100, jitter=lambda *_: 0)
    f.submit(payload()); f.drain(); record = json.loads(next((tmp_path / "pending").glob("*.json")).read_text())
    assert record["attempt_count"] == 1 and record["next_attempt_at"] == 110

@pytest.mark.parametrize("status", [400, 401, 403, 422])
def test_permanent_failures_quarantine_without_secret(tmp_path, status):
    f = WazuhForwarder(config(tmp_path), post=lambda *args: status, clock=lambda: 100); f.submit(payload()); f.drain()
    item = json.loads(next((tmp_path / "quarantine").glob("*.json")).read_text())
    assert item["reason"] == f"HTTP_{status}" and "secret-never-log" not in json.dumps(item)

def test_restart_exhaustion_corruption_atomic_and_bound(tmp_path):
    f = WazuhForwarder(config(tmp_path, maximum_spool_bytes=1000), post=lambda *args: 500, clock=lambda: 100, jitter=lambda *_: 0); f.submit(payload()); f.drain()
    restarted = WazuhForwarder(config(tmp_path, maximum_spool_bytes=1000), post=lambda *args: 500, clock=lambda: 111, jitter=lambda *_: 0); restarted.drain()
    assert list((tmp_path / "quarantine").glob("*.json"))
    spool = DurableSpool(tmp_path / "corrupt", 1000); path = spool.pending / "bad.json"; path.write_text("{"); spool.ready(100); assert list(spool.quarantine.glob("*.json"))
    tiny = DurableSpool(tmp_path / "tiny", 1)
    with pytest.raises(SpoolFullError): tiny.enqueue(payload(), 0)
    assert not list(tiny.pending.glob("*.tmp"))
