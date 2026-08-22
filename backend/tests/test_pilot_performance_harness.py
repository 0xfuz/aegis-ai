"""Static guardrails for the V1-B2 local-only pilot harness."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_pilot_harness_is_bounded_disposable_and_cleans_up():
    text = (ROOT / "scripts/release/run-pilot-performance.sh").read_text(encoding="utf-8")
    assert "set -euo pipefail" in text
    assert "aegis-v1b2-" in text and "project must use the aegis-v1b2-* namespace" in text
    assert "preserved R4 resources are never a harness target" in text
    assert "trap cleanup EXIT INT TERM" in text
    assert "down --volumes --remove-orphans" in text
    assert "--result-dir" in text and "--preflight-only" in text
    assert "result directory must not be a symlink" in text
    assert "unsafe result directory" in text
    assert "status.json" in text and "aggregate.json" in text and "operator-summary.txt" in text and "exit-code" in text
    assert "chmod 700 \"$RESULT_DIR\"" in text and "chmod 600 \"$temporary\"" in text
    for bound in ("BASELINE_EVENTS=300", "BASELINE_RATE=5", "BASELINE_CONCURRENCY=5", "BASELINE_TIMEOUT=180", "BURST_EVENTS=150", "BURST_RATE=10", "BURST_CONCURRENCY=10", "BURST_TIMEOUT=90", "FORWARDER_EVENTS=25"):
        assert bound in text


def test_pilot_harness_uses_loopback_http_contracts_and_disabled_ai_only():
    text = (ROOT / "scripts/release/run-pilot-performance.sh").read_text(encoding="utf-8")
    assert "http://127.0.0.1" in text
    assert "API target must be loopback" in text
    for gate in ("INTELLIGENCE_EXECUTION_ENABLED=false", "INTELLIGENCE_DISPATCH_ENABLED=false", "INTELLIGENCE_PROVIDER_ENABLED=false"):
        assert gate in text
    assert 'up -d postgres redis migrate api frontend' in text
    assert "intelligence-worker" not in text and "intelligence-beat" not in text
    assert '--profile ollama' not in text
    assert "psql" not in text and "INSERT INTO" not in text
    assert "ingest/wazuh/v1" not in text  # the bounded driver owns HTTP request details


def test_pilot_driver_is_required_and_uses_no_database_path():
    text = (ROOT / "scripts/release/run-pilot-performance.sh").read_text(encoding="utf-8")
    assert "scripts/release/pilot_performance_driver.py" in text
    assert "X-Ingest-Secret" not in text
    driver = (ROOT / "scripts/release/pilot_performance_driver.py").read_text(encoding="utf-8")
    assert "INSERT INTO" not in driver and "psql" not in driver
    assert "aggregate_only" in driver


def test_pilot_report_declares_the_fixed_limits_and_non_production_boundary():
    text = (ROOT / "docs/release/V1_0_PILOT_PERFORMANCE.md").read_text(encoding="utf-8")
    for phrase in ("300 distinct events at 5 events/s", "150 distinct events at 10 events/s", "25 synthetic local deliveries", "not a\nproduction, Enterprise", "15 GiB", "2 GiB"):
        assert phrase in text
    assert "not populated until the harness has run exactly\nonce" in text
    assert "V1-B2 STATUS: NOT MEASURED" in text
