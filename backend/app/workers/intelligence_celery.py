"""Internal Celery wiring for fenced Intelligence Run delivery only."""
from celery import Celery
from app.core.config import get_settings

settings=get_settings()
celery_app=Celery("aegis_intelligence",broker=settings.CELERY_BROKER_URL,backend=settings.CELERY_RESULT_BACKEND,
                 include=["app.workers.intelligence_tasks"])
celery_app.conf.update(
    task_default_queue=settings.INTELLIGENCE_EXECUTION_QUEUE,
    task_ignore_result=True,
    task_acks_late=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    beat_schedule={
        "reconcile-intelligence-runs": {"task":"app.workers.intelligence_tasks.reconcile_intelligence_runs","schedule":settings.INTELLIGENCE_RECONCILIATION_SECONDS},
        "recover-intelligence-leases": {"task":"app.workers.intelligence_tasks.recover_intelligence_leases","schedule":settings.INTELLIGENCE_RECONCILIATION_SECONDS},
    },
)
