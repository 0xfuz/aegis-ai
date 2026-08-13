"""Celery task payload is deliberately restricted to run ID and protocol."""
from __future__ import annotations
from uuid import UUID, uuid4
from app.core.config import get_settings
from app.modules.ai_reasoning.domain.run_dispatch import IntelligenceRunMaintenance
from app.modules.ai_reasoning.domain.run_executor import FakeExecutionAdapter, FakeExecutionOutcome, IntelligenceRunExecutor
from app.workers.intelligence_celery import celery_app

class _UnavailableAdapter(FakeExecutionAdapter):
    def execute(self, checkpoint): return FakeExecutionOutcome.SAFE_FAILURE

_test_adapter: FakeExecutionAdapter | None = None
def install_test_adapter(adapter: FakeExecutionAdapter | None) -> None:  # test-only injection; never a client setting
    global _test_adapter; _test_adapter=adapter

def _worker_attempt_id() -> str: return f"intelligence-worker-{uuid4().hex}"
def _executor() -> IntelligenceRunExecutor: return IntelligenceRunExecutor(_test_adapter or _UnavailableAdapter())

@celery_app.task(name="app.workers.intelligence_tasks.execute_intelligence_run",bind=True,ignore_result=True,acks_late=True)
def execute_intelligence_run(_task, run_id: str, protocol_version: str) -> dict[str,str]:
    settings=get_settings()
    if protocol_version != settings.INTELLIGENCE_TASK_PROTOCOL_VERSION: return {"category":"TASK_PROTOCOL_REJECTED"}
    try: parsed=UUID(run_id)
    except (TypeError,ValueError): return {"category":"TASK_PAYLOAD_REJECTED"}
    if not settings.INTELLIGENCE_EXECUTION_ENABLED: return {"category":"EXECUTION_DISABLED"}
    result=_executor().execute(parsed,_worker_attempt_id())
    return {"category":result.category or result.outcome.value}

@celery_app.task(name="app.workers.intelligence_tasks.reconcile_intelligence_runs",ignore_result=True)
def reconcile_intelligence_runs() -> dict[str,int]: return {"count":len(IntelligenceRunMaintenance().reconcile_queued_runs())}

@celery_app.task(name="app.workers.intelligence_tasks.recover_intelligence_leases",ignore_result=True)
def recover_intelligence_leases() -> dict[str,int]: return {"count":len(IntelligenceRunMaintenance().recover_expired_leases())}
