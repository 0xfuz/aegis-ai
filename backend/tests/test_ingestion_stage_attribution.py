from types import SimpleNamespace

from tests.support.ingestion_stage_attribution import COUNTERS, STAGES, StageAttribution, classify_frames


def _frame(module: str): return SimpleNamespace(frame=SimpleNamespace(f_globals={"__name__": module}))


def test_nested_precedence_is_fixed_and_never_emits_stack_data():
    assert classify_frames([_frame("app.modules.alert_triage.domain.webhook_service"), _frame("app.modules.alert_triage.domain.correlation_v2_service")]) == "correlation_v2"
    assert classify_frames([_frame("app.modules.alert_triage.domain.webhook_service"), _frame("app.modules.alert_triage.domain.triage_service")]) == "triage"
    assert classify_frames([_frame("app.modules.connectors.api.router")]) == "response_or_framework"
    assert classify_frames([_frame("unknown")]) == "unattributed"
    assert set(STAGES) == {"authentication", "raw_event", "canonical_alert", "deduplication", "correlation_v2", "triage", "response_or_framework", "unattributed"}


def test_aggregate_reconciliation_and_sensitive_exclusion_without_database_events():
    counter = StageAttribution(object())
    counter.counts["raw_event"]["flush"] = 1
    counter.counts["correlation_v2"]["flush"] = 2
    counter.counts["triage"]["commit"] = 1
    whole = {key: 0 for key in COUNTERS}; whole.update({"flush": 3, "commit": 1})
    assert counter.reconcile(whole)
    rendered = repr(counter.counts)
    for forbidden in ("payload", "secret", "token", "sql", "path", "parameter"):
        assert forbidden not in rendered.lower()
