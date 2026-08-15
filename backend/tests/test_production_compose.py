"""R2 static and settings guardrails for the production Compose boundary."""
from pathlib import Path
import re

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.config import Settings


ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_COMPOSE = ROOT / "docker-compose.production.yml"


def _production_settings(tmp_path: Path, **overrides) -> Settings:
    jwt = tmp_path / "jwt-secret"
    database = tmp_path / "database-password"
    jwt.write_text("R2-Test-JWT-Secret-1234567890-AbCd!", encoding="utf-8")
    database.write_text("R2-Test-Database-Password-123456!", encoding="utf-8")
    values = {
        "ENVIRONMENT": "production", "DEBUG": False, "SEED_DEMO_DATA": False,
        "JWT_SECRET_KEY_FILE": str(jwt), "DATABASE_PASSWORD_FILE": str(database),
        "DATABASE_USER": "aegis", "DATABASE_NAME": "aegis", "DATABASE_HOST": "postgres",
    }
    values.update(overrides)
    return Settings(**values)


def test_production_uses_file_backed_secrets_and_never_default_values(tmp_path):
    settings = _production_settings(tmp_path)
    assert settings.JWT_SECRET_KEY != "CHANGE_ME_dev_only_insecure_secret"
    assert settings.DATABASE_URL.startswith("postgresql+psycopg2://aegis:")
    with pytest.raises(PydanticValidationError):
        Settings(ENVIRONMENT="production", DEBUG=False, SEED_DEMO_DATA=False)
    weak = tmp_path / "weak"; weak.write_text("short", encoding="utf-8")
    with pytest.raises(PydanticValidationError):
        _production_settings(tmp_path, JWT_SECRET_KEY_FILE=str(weak))
    with pytest.raises(PydanticValidationError):
        _production_settings(tmp_path, DATABASE_PASSWORD_FILE=str(weak))


def test_production_compose_has_one_migration_writer_and_private_internal_services():
    text = PRODUCTION_COMPOSE.read_text(encoding="utf-8")
    assert text.count('command: ["alembic", "upgrade", "head"]') == 1
    assert "admin-bootstrap:" in text and 'profiles: ["bootstrap"]' in text
    assert "migrate: {condition: service_completed_successfully}" in text
    for service in ("postgres", "redis", "migrate", "intelligence-worker", "intelligence-beat", "ollama"):
        block = re.search(rf"^  {service}:\n(.*?)(?=^  [a-z][a-z-]*:|^networks:)", text, re.MULTILINE | re.DOTALL).group(1)
        assert "ports:" not in block
    api_block = re.search(r"^  api:\n(.*?)(?=^  frontend:)", text, re.MULTILINE | re.DOTALL).group(1)
    frontend_block = re.search(r"^  frontend:\n(.*?)(?=^  intelligence-worker:)", text, re.MULTILINE | re.DOTALL).group(1)
    assert '"127.0.0.1:${API_PORT:-8000}:8000"' in api_block
    assert '"127.0.0.1:${FRONTEND_PORT:-3000}:3000"' in frontend_block
    assert "aegis_postgres_data" in text and "aegis_evidence_data" in text and "aegis_ollama_data" in text


def test_production_compose_pins_ollama_and_fixed_trusted_model_without_legacy_secrets():
    text = PRODUCTION_COMPOSE.read_text(encoding="utf-8")
    assert "ollama/ollama@sha256:4dea9fb511947e24a84237bb636b0203abcb2ff0d3fbc7b4ff865deb91362131" in text
    assert "INTELLIGENCE_OLLAMA_MODEL: llama3.2:latest" in text
    assert "INTELLIGENCE_OLLAMA_ALLOWED_MODELS: llama3.2:latest" in text
    assert "POSTGRES_PASSWORD:" not in text and "JWT_SECRET_KEY:" not in text
    assert "POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password" in text
    assert "JWT_SECRET_KEY_FILE: /run/secrets/jwt_signing_secret" in text
    assert "INTELLIGENCE_PROVIDER_ENABLED: ${INTELLIGENCE_PROVIDER_ENABLED:-false}" in text
    assert "ollama/ollama:latest" not in text


def test_api_has_no_redis_or_ollama_startup_dependency_and_worker_uses_certified_queue():
    text = PRODUCTION_COMPOSE.read_text(encoding="utf-8")
    api_block = re.search(r"^  api:\n(.*?)(?=^  frontend:)", text, re.MULTILINE | re.DOTALL).group(1)
    worker_block = re.search(r"^  intelligence-worker:\n(.*?)(?=^  intelligence-beat:)", text, re.MULTILINE | re.DOTALL).group(1)
    assert "redis:" not in api_block and "ollama:" not in api_block
    assert "--queues=intelligence-execution" in worker_block


def test_production_worker_and_beat_healthchecks_are_process_aware_not_http():
    text = PRODUCTION_COMPOSE.read_text(encoding="utf-8")
    worker_block = re.search(r"^  intelligence-worker:\n(.*?)(?=^  intelligence-beat:)", text, re.MULTILINE | re.DOTALL).group(1)
    beat_block = re.search(r"^  intelligence-beat:\n(.*?)(?=^  ollama:)", text, re.MULTILINE | re.DOTALL).group(1)
    assert "inspect ping --destination=celery@$$HOSTNAME" in worker_block
    assert "grep -q pong" in worker_block
    assert "localhost:8000" not in worker_block
    assert "grep -aq celery /proc/1/cmdline" in beat_block
    assert "grep -aq beat /proc/1/cmdline" in beat_block
    assert "localhost:8000" not in beat_block
