"""Static safety contract for the operator-only V1-P1A diagnostic harness."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "scripts/release/run-ingestion-diagnosis.sh"


def source() -> str:
    return HARNESS.read_text(encoding="utf-8")


def test_harness_uses_only_the_exact_sequential_diagnostic_contract():
    text = source()
    assert 'SCENARIOS=(single_new_event exact_replay bounded_10 bounded_25 correlation_candidate)' in text
    assert 'for scenario in "${SCENARIOS[@]}"; do' in text
    assert "ingestion_diagnosis_driver.py --scenario $scenario" in text
    assert "DIAGNOSTIC_FIXTURE_REQUIRED" not in text
    assert "rate test, burst, benchmark" in text
    assert "frontend, worker, beat, Ollama" in text


def test_exact_namespace_and_cleanup_are_bounded_to_disposable_resources():
    text = source()
    assert 'PROJECT="aegis-v1p1a-diagnosis-run"' in text
    assert '"$PROJECT" =~ ^aegis-v1p1a-diagnosis-' in text
    assert 'docker network create "$NETWORK"' in text
    assert 'docker volume create "$VOLUME"' in text
    assert 'docker rm -f "$RUNNER" "$MIGRATE" "$POSTGRES"' in text
    assert 'docker network rm "$NETWORK"' in text and 'docker volume rm "$VOLUME"' in text
    assert "docker system prune" not in text and "docker volume prune" not in text
    assert "aegis-r4-" in text and "aegis-v1b2-" in text


def test_preflight_has_no_container_creation_and_result_paths_are_protected():
    text = source()
    preflight = text.split('if "$PREFLIGHT_ONLY"; then', 1)[1].split('CURRENT_STAGE="resource_preflight"', 1)[0]
    assert "docker run" not in preflight and "docker build" not in preflight
    assert "--preflight-only" in text and "--result-dir" in text
    assert "realpath -m" in text and "unsafe result directory" in text
    assert "mkdir -p -m 700" in text and "chmod 700" in text and "chmod 600" in text
    assert "os.O_EXCL" in text and "os.replace" in text


def test_status_and_aggregate_preserve_completed_work_without_sensitive_content():
    text = source()
    for field in ("current_stage", "last_completed_stage", "current_scenario", "last_completed_scenario", "safe_failure_category", "elapsed_seconds", "cleanup_state"):
        assert field in text
    assert "write_aggregate" in text and "scenario-${scenario}.json" in text
    assert "LAST_COMPLETED_SCENARIO=\"$scenario\"" in text
    assert "SCENARIO_TIMEOUT_OR_DRIVER_FAILURE" in text and "SCENARIO_RESULT_INVALID" in text
    for forbidden in ("docker inspect", "docker logs", "pg_dump", "printenv", "curl", "request_body"):
        assert forbidden not in text


def test_harness_keeps_debug_false_and_uses_no_benchmark_controls():
    text = source()
    assert "DEBUG=false" in text
    assert "INTELLIGENCE_EXECUTION_ENABLED" not in text
    assert "OLLAMA" not in text
    assert "concurrency" not in text and "events/second" not in text
    assert "timeout 600 docker build" in text and "timeout 180 docker run" in text and "timeout 120 docker run" in text
