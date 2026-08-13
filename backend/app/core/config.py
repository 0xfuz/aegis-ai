"""
Central application configuration.

All configuration is read from environment variables (see .env.example at
the repo root). Nothing here should ever hold a real secret — defaults are
for local development only and are intentionally weak so they are obviously
unsafe to run in production unchanged.
"""
from functools import lru_cache
from typing import List

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_JWT_DEFAULT = "CHANGE_ME_dev_only_insecure_secret"
_INSECURE_DATABASE_MARKER = "aegis_dev_password"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    APP_NAME: str = "Aegis AI"
    ENVIRONMENT: str = "development"  # development | staging | production
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = True
    SEED_DEMO_DATA: bool = False

    # --- Security / Auth ---
    JWT_SECRET_KEY: str = "CHANGE_ME_dev_only_insecure_secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- Database ---
    DATABASE_URL: str = (
        "postgresql+psycopg2://aegis:aegis_dev_password@postgres:5432/aegis_ai"
    )

    # Used only to build the ingest URL displayed to admins when they
    # create a connector — purely cosmetic/informational, the actual
    # routing works regardless of what's configured here.
    PUBLIC_API_BASE_URL: str = "http://localhost:8000"

    # --- AI reasoning ---
    # 'gemini' is the default: genuinely free within Gemini's rate limits,
    # no credit card required. Switch to 'anthropic' if you have an
    # Anthropic key and prefer Claude's reasoning quality.
    AI_PROVIDER: str = "gemini"

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # Fully local via Ollama — no key, no billing account, no regional
    # eligibility restrictions. Set AI_PROVIDER=ollama to use this.
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "llama3.2"

    # Empty by default on purpose: the ai_reasoning module checks this and
    # returns a clear, honest error ("AI reasoning isn't configured") when
    # unset, rather than the app crashing at import time or silently
    # returning fake analysis. Set this in your .env to enable it.
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-5"

    # --- Redis / Celery (wired for later phases, used sparingly in MVP) ---
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    # Phase 8.4 dispatch is opt-in. PostgreSQL runs remain usable while no
    # worker/Redis deployment is configured; no development default executes.
    INTELLIGENCE_EXECUTION_ENABLED: bool = False
    INTELLIGENCE_DISPATCH_ENABLED: bool = False
    INTELLIGENCE_EXECUTION_QUEUE: str = "intelligence-execution"
    INTELLIGENCE_TASK_PROTOCOL_VERSION: str = "intelligence-run-v1"
    INTELLIGENCE_RECONCILIATION_SECONDS: int = 15
    INTELLIGENCE_QUEUE_MIN_AGE_SECONDS: int = 15

    # --- Canonical evidence ingestion (Phase 2) ---
    # Deliberately outside any frontend/public tree. Files are served only by
    # authenticated controlled-download endpoints introduced with ingestion.
    EVIDENCE_STORAGE_DIR: str = "/app/storage/evidence"
    MAX_EVIDENCE_BYTES: int = 5 * 1024 * 1024
    MAX_RAW_RECORD_LENGTH: int = 64 * 1024
    MAX_RAW_RECORDS: int = 10_000
    MAX_EVENTS: int = 10_000
    MAX_EXTRACTED_INDICATORS: int = 50_000
    MAX_EXTRACTED_ENTITIES: int = 50_000
    MAX_JSON_DEPTH: int = 32

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.INTELLIGENCE_RECONCILIATION_SECONDS <= 0 or self.INTELLIGENCE_QUEUE_MIN_AGE_SECONDS < 0:
            raise ValueError("Intelligence reconciliation timing must be bounded.")
        if self.ENVIRONMENT.lower() != "production":
            return self
        if self.DEBUG:
            raise ValueError("Production requires DEBUG=false.")
        if not self.JWT_SECRET_KEY or self.JWT_SECRET_KEY == _INSECURE_JWT_DEFAULT:
            raise ValueError("Production requires an explicitly supplied non-default JWT secret.")
        if _INSECURE_DATABASE_MARKER in self.DATABASE_URL:
            raise ValueError("Production requires non-default database credentials.")
        if self.SEED_DEMO_DATA:
            raise ValueError("Production must not enable demo-data seeding.")
        return self

    # --- CORS ---
    # Stored as a plain string, deliberately NOT List[str] — pydantic-settings
    # tries to json.loads() any list-typed field's raw env value before any
    # validator runs, which breaks on an ordinary comma-separated value like
    # "http://localhost:3000,http://foo.com" (this bit us twice already: once
    # via a bare List[str] field, once via a version of pydantic-settings too
    # old for the NoDecode escape hatch). A plain str field sidesteps that
    # machinery entirely — split it via the property below instead.
    CORS_ORIGINS_RAW: str = "http://localhost:3000"

    @property
    def CORS_ORIGINS(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS_RAW.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Settings are cached — env vars are read once per process."""
    return Settings()
