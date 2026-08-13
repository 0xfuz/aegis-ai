"""Static operational guardrails for the Phase 8.4 Compose boundary."""
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_only_the_one_shot_migration_service_owns_migration_and_bootstrap():
    entrypoint = (BACKEND_ROOT / "docker-entrypoint.sh").read_text()
    assert "alembic upgrade head" not in entrypoint
    assert "python -m app.seed.bootstrap" not in entrypoint
