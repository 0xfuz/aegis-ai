"""Celery task payload is deliberately restricted to run ID and protocol."""
from __future__ import annotations
from uuid import UUID, uuid4
from app.core.config import get_settings
from app.modules.ai_reasoning.domain.run_dispatch import IntelligenceRunMaintenance
from app.modules.ai_reasoning.domain.run_executor import FakeExecutionAdapter, FakeExecutionOutcome, IntelligenceRunExecutor
from app.modules.ai_reasoning.domain.grounded_execution import GroundedIntelligenceExecutionPipeline
from app.modules.ai_reasoning.domain.trusted_provider import OllamaCandidateProvider, OllamaReadiness, ProviderPolicy
from app.workers.intelligence_celery import celery_app

class _UnavailableAdapter(FakeExecutionAdapter):
    def execute(self, checkpoint): return FakeExecutionOutcome.SAFE_FAILURE

_test_adapter: FakeExecutionAdapter | None = None
def install_test_adapter(adapter: FakeExecutionAdapter | None) -> None:  # test-only injection; never a client setting
    global _test_adapter; _test_adapter=adapter

def _worker_attempt_id() -> str: return f"intelligence-worker-{uuid4().hex}"

def _safe_result_category(result) -> str:
    """Return only a bounded lifecycle category from an internal executor result.

    Grounded execution deliberately has no fake-executor ``outcome`` field.  The
    task acknowledgement path must therefore never inspect provider output or
    assume a test-only result shape after candidate persistence has committed.
    """
    category = getattr(result, "category", None)
    if isinstance(category, str) and category:
        return category
    outcome = getattr(result, "outcome", None)
    value = getattr(outcome, "value", outcome)
    if isinstance(value, str) and value:
        return value
    return "COMPLETED" if getattr(result, "authoritative", False) else "EXECUTION_FAILED"

def _executor():
    """Production chooses only trusted, configured Ollama; fakes are test-only."""
    if _test_adapter is not None: return IntelligenceRunExecutor(_test_adapter)
    settings=get_settings()
    if not settings.INTELLIGENCE_PROVIDER_ENABLED: return IntelligenceRunExecutor(_UnavailableAdapter())
    try:
        policy=ProviderPolicy.from_settings(settings)
        if OllamaReadiness(True,policy).check()["state"].value != "READY": return IntelligenceRunExecutor(_UnavailableAdapter())
        return GroundedIntelligenceExecutionPipeline(OllamaCandidateProvider(policy))
    except Exception: return IntelligenceRunExecutor(_UnavailableAdapter())

@celery_app.task(name="app.workers.intelligence_tasks.execute_intelligence_run",bind=True,ignore_result=True,acks_late=True)
def execute_intelligence_run(_task, run_id: str, protocol_version: str) -> dict[str,str]:
    settings=get_settings()
    if protocol_version != settings.INTELLIGENCE_TASK_PROTOCOL_VERSION: return {"category":"TASK_PROTOCOL_REJECTED"}
    try: parsed=UUID(run_id)
    except (TypeError,ValueError): return {"category":"TASK_PAYLOAD_REJECTED"}
    if not settings.INTELLIGENCE_EXECUTION_ENABLED: return {"category":"EXECUTION_DISABLED"}
    result=_executor().execute(parsed,_worker_attempt_id())
    return {"category":_safe_result_category(result)}

@celery_app.task(name="app.workers.intelligence_tasks.reconcile_intelligence_runs",ignore_result=True)
def reconcile_intelligence_runs() -> dict[str,int]: return {"count":len(IntelligenceRunMaintenance().reconcile_queued_runs())}

@celery_app.task(name="app.workers.intelligence_tasks.recover_intelligence_leases",ignore_result=True)
def recover_intelligence_leases() -> dict[str,int]: return {"count":len(IntelligenceRunMaintenance().recover_expired_leases())}
