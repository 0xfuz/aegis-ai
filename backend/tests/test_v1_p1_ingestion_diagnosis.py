"""Static guard for the aggregate-only V1-P1 ingestion diagnosis record."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_ingestion_diagnosis_records_measured_formula_and_scope_limits():
    text = (ROOT / "docs/release/V1_P1_INGESTION_DIAGNOSIS.md").read_text(encoding="utf-8")
    assert "5da563b330349d4e804c58630dfd3e1f789534d8" in text
    assert "sole Alembic head `0024`" in text
    assert "SELECT(n) = n² + 29n" in text
    assert "Total SQL(n) = n² + 37n" in text
    assert "AlertCorrelationV2Service.process" in text
    assert "no throughput" in text.lower()
    assert "No V1-B2 performance benchmark rerun" in text


def test_diagnosis_preserves_authoritative_optimization_constraints():
    text = (ROOT / "docs/release/V1_P1_INGESTION_DIAGNOSIS.md").read_text(encoding="utf-8")
    for requirement in (
        "deduplication", "membership reasons/scores", "organization predicates",
        "triage", "transaction", "promotion", "response schema",
        "full backend certification",
    ):
        assert requirement in text
