"""Static guardrails for the V1-B2 local-only pilot harness."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_pilot_harness_is_bounded_disposable_and_cleans_up():
    text = (ROOT / "scripts/release/run-pilot-performance.sh").read_text(encoding="utf-8")
    assert "set -euo pipefail" in text
    assert "aegis-v1b2-" in text and "project must use the aegis-v1b2-* namespace" in text
    assert "preserved R4 resources are never a harness target" in text
    assert "trap 'cleanup $?' EXIT" in text
    assert "trap 'on_err $?' ERR" in text
    assert "trap 'on_signal INT 130' INT" in text
    assert "trap 'on_signal TERM 143' TERM" in text
    assert "down --volumes --remove-orphans" in text
    assert "docker system prune" not in text and "docker volume prune" not in text
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


def test_readiness_retries_transient_startup_failures_and_requires_both_http_contracts():
    text = (ROOT / "scripts/release/run-pilot-performance.sh").read_text(encoding="utf-8")
    assert 'while (( SECONDS < deadline )); do' in text
    assert '--connect-timeout 2 --max-time 5' in text
    assert 'sleep 2' in text
    assert 'set_safe_failure "SERVICE_READINESS_TIMEOUT" "$CURRENT_STAGE" "$1"' in text
    assert 'wait_http "api" "$API_ORIGIN/api/v1/health" "Aegis AI"' in text
    assert 'wait_http "frontend" "$FRONTEND_ORIGIN/healthz" "frontend"' in text
    assert text.index('wait_http "frontend"') < text.rindex('\n  measure\n}')
    assert '2>/dev/null' in text and 'never printed or written to an artifact' in text


def test_readiness_failure_evidence_and_summary_are_aggregate_only_with_real_newlines():
    text = (ROOT / "scripts/release/run-pilot-performance.sh").read_text(encoding="utf-8")
    for key in ('current_stage', 'last_completed_stage', 'failed_stage', 'safe_failure_category', 'service_or_operation', 'elapsed_seconds', 'measurement_started', 'cleanup'):
        assert key in text
    assert "write_operator_summary" in text
    assert "printf 'V1-B2 STATUS: NOT MEASURED\\nHarness exit category" in text
    assert "curl output" not in text.lower()


def test_pilot_harness_persists_safe_stage_state_before_measurement_and_on_failures():
    text = (ROOT / "scripts/release/run-pilot-performance.sh").read_text(encoding="utf-8")
    assert 'CURRENT_STAGE="initializing"' in text
    assert 'LAST_COMPLETED_STAGE=""' in text
    assert 'MEASUREMENT_STARTED="false"' in text
    assert 'mark_stage "preflight" "repository_and_host_safety"' in text
    assert 'mark_stage_completed "preflight"' in text
    assert 'mark_stage "api_readiness" "api"' in text
    assert 'mark_stage_completed "frontend_readiness"' in text
    assert 'mark_stage "measurement" "pilot_performance_driver"' in text
    assert 'MEASUREMENT_STARTED="true"' in text
    assert text.index('MEASUREMENT_STARTED="true"') < text.index('pilot_performance_driver.py')


def test_pilot_harness_classifies_command_and_signal_failures_without_retaining_output():
    text = (ROOT / "scripts/release/run-pilot-performance.sh").read_text(encoding="utf-8")
    assert 'set_safe_failure "HARNESS_COMMAND_FAILED" "$CURRENT_STAGE" "$CURRENT_OPERATION"' in text
    assert 'set_safe_failure "HARNESS_INTERRUPTED_${signal}" "$CURRENT_STAGE" "$CURRENT_OPERATION"' in text
    assert 'set_safe_failure "HARNESS_PRECONDITION_FAILED" "$CURRENT_STAGE" "$CURRENT_OPERATION"' in text
    assert 'CLEANUP_STATUS="completed"' in text
    assert 'CLEANUP_STATUS="failed"' in text
    assert 'write_result exit-code "$status"' in text
    assert 'response bodies, logs, or environment values are retained' in text


def test_pilot_harness_runs_each_measurement_driver_once_after_both_readiness_checks():
    text = (ROOT / "scripts/release/run-pilot-performance.sh").read_text(encoding="utf-8")
    assert text.count("pilot_performance_driver.py") == 1
    frontend_ready = text.index('mark_stage_completed "frontend_readiness"')
    driver = text.index('pilot_performance_driver.py')
    assert frontend_ready < driver


def test_pilot_harness_uses_a_valid_synthetic_bootstrap_identity_and_classifies_exit_two():
    text = (ROOT / "scripts/release/run-pilot-performance.sh").read_text(encoding="utf-8")
    assert "BOOTSTRAP_ADMIN_EMAIL_REQUIRED=pilot-admin@example.com" in text
    assert "example.invalid" not in text
    assert 'mark_stage "bootstrap" "administrator_bootstrap"' in text
    assert '--profile bootstrap run --rm admin-bootstrap' in text
    assert 'local bootstrap_status=$?' in text
    assert 'set_safe_failure "BOOTSTRAP_FAILED" "bootstrap" "administrator_bootstrap"' in text
    assert 'return "$bootstrap_status"' in text
    assert 'mark_stage_completed "bootstrap"' in text
    assert text.index('mark_stage_completed "bootstrap"') < text.index('pilot_performance_driver.py')


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
    assert "V1-B2 STATUS: BLOCKED" in text


def test_v1_b3_campaign_is_isolated_and_inherits_the_exact_v1_b2_workload():
    text = (ROOT / "scripts/release/run-pilot-performance.sh").read_text(encoding="utf-8")
    assert '--campaign) (($# >= 2)) || fail "--campaign requires v1-b3"' in text
    assert 'v1-b3)' in text
    assert 'PROJECT="${AEGIS_V1B3_PROJECT:-$V1B3_PROJECT_DEFAULT}"' in text
    assert 'aegis-v1b3-pilot-* namespace' in text
    assert 'V1-B3 requires the complete unchanged V1-B2 workload' in text
    for bound in ("BASELINE_EVENTS=300", "BASELINE_RATE=5", "BASELINE_CONCURRENCY=5", "BURST_EVENTS=150", "BURST_RATE=10", "BURST_CONCURRENCY=10", "FORWARDER_EVENTS=25"):
        assert bound in text
    assert 'WORKLOAD_PROFILE="V1-B2-UNCHANGED"' in text
    assert 'correlation-v2 bulk candidate/member reads' in text
    assert '/home/omar/.local/state/aegis-v1b3-performance' in text


def test_v1_b3_rejects_v1_b2_results_and_labels_only_its_own_safe_artifacts():
    text = (ROOT / "scripts/release/run-pilot-performance.sh").read_text(encoding="utf-8")
    assert 'V1-B3 result directory must not resolve to preserved V1-B2 results' in text
    assert '*aegis-v1b2-* || "$resolved" == *v1b2-performance*' in text
    assert '\\"campaign_id\\":\\"$CAMPAIGN_ID\\"' in text
    assert '\\"campaign_status\\":\\"$CAMPAIGN_STATUS\\"' in text
    assert '\\"source_commit\\"' in text and '\\"migration_head\\":\\"0024\\"' in text
    assert 'V1-B3 STATUS: %s' in text
    assert 'decorate_v1b3_aggregate' in text
    assert 'No credentials, payloads, response bodies, logs, or environment values are retained.' in text
