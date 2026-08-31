"""The production Celery app must register its fenced internal task surface."""
from app.workers.intelligence_celery import celery_app


def test_intelligence_tasks_are_registered_on_the_production_celery_app():
    names = set(celery_app.tasks)
    assert "app.workers.intelligence_tasks.execute_intelligence_run" in names
    assert "app.workers.intelligence_tasks.reconcile_intelligence_runs" in names
    assert "app.workers.intelligence_tasks.recover_intelligence_leases" in names
