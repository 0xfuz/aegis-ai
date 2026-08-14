"""
Central application configuration.

All configuration is read from environment variables (see .env.example at
the repo root). Nothing here should ever hold a real secret — defaults are
for local development only and are intentionally weak so they are obviously
unsafe to run in production unchanged.
"""
from functools import lru_cache
from pathlib import Path
from typing import List
from urllib.parse import quote

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_JWT_DEFAULT = "CHANGE_ME_dev_only_insecure_secret"
_INSECURE_DATABASE_MARKER = "aegis_dev_password"


def _read_secret_file(path_value: str, *, label: str) -> str:
    """Read one bounded Docker-secret style file without ever logging it."""
    path = Path(path_value)
    try:
        info = path.stat()
        if not path.is_file() or not 0 < info.st_size <= 4096:
            raise ValueError
        value = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"Production requires a valid {label} secret file.") from exc
    value = value[:-1] if value.endswith("\n") else value
    if not value or value.strip() != value:
        raise ValueError(f"Production requires a valid {label} secret file.")
    return value


def _is_strong_secret(value: str, *, minimum_length: int) -> bool:
    """A small deployment boundary, not a replacement password policy."""
    if len(value) < minimum_length or value.strip() != value:
        return False
    classes = sum((
        any(char.islower() for char in value),
        any(char.isupper() for char in value),
        any(char.isdigit() for char in value),
        any(not char.isalnum() for char in value),
    ))
    return classes >= 3


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
    DATABASE_HOST: str = "postgres"
    DATABASE_PORT: int = 5432
    DATABASE_USER: str = "aegis"
    DATABASE_NAME: str = "aegis_ai"
    DATABASE_PASSWORD_FILE: str | None = None
    JWT_SECRET_KEY_FILE: str | None = None

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
    # Phase 8.5 trusted provider boundary.  These settings are intentionally
    # separate from legacy AI_PROVIDER settings and remain opt-in.
    INTELLIGENCE_PROVIDER_ENABLED: bool = False
    INTELLIGENCE_PROVIDER: str = "ollama"
    INTELLIGENCE_OLLAMA_BASE_URL: str = "http://ollama:11434"
    INTELLIGENCE_OLLAMA_MODEL: str = "llama3.2:latest"
    INTELLIGENCE_OLLAMA_ALLOWED_MODELS: str = "llama3.2:latest"
    INTELLIGENCE_PROVIDER_CONNECT_TIMEOUT_SECONDS: int = 5
    # provider-timeout-v2: measured local llama3.2:latest response completes
    # within 55.607s; these fixed bounds leave finite headroom without caller control.
    INTELLIGENCE_PROVIDER_READ_TIMEOUT_SECONDS: int = 90
    INTELLIGENCE_PROVIDER_TOTAL_TIMEOUT_SECONDS: int = 105
    INTELLIGENCE_PROVIDER_MAX_REQUEST_BYTES: int = 262144
    INTELLIGENCE_PROVIDER_MAX_RESPONSE_BYTES: int = 262144
    INTELLIGENCE_PROVIDER_MAX_CONCURRENCY: int = 2

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
        if min(self.INTELLIGENCE_PROVIDER_CONNECT_TIMEOUT_SECONDS, self.INTELLIGENCE_PROVIDER_READ_TIMEOUT_SECONDS, self.INTELLIGENCE_PROVIDER_TOTAL_TIMEOUT_SECONDS, self.INTELLIGENCE_PROVIDER_MAX_REQUEST_BYTES, self.INTELLIGENCE_PROVIDER_MAX_RESPONSE_BYTES, self.INTELLIGENCE_PROVIDER_MAX_CONCURRENCY) <= 0 or self.INTELLIGENCE_PROVIDER_READ_TIMEOUT_SECONDS > self.INTELLIGENCE_PROVIDER_TOTAL_TIMEOUT_SECONDS:
            raise ValueError("Intelligence provider bounds are invalid.")
        if self.ENVIRONMENT.lower() != "production":
            return self
        if not self.JWT_SECRET_KEY_FILE or not self.DATABASE_PASSWORD_FILE:
            raise ValueError("Production requires Docker secret-file inputs for JWT and database credentials.")
        self.JWT_SECRET_KEY = _read_secret_file(self.JWT_SECRET_KEY_FILE, label="JWT")
        database_password = _read_secret_file(self.DATABASE_PASSWORD_FILE, label="database")
        self.DATABASE_URL = (
            "postgresql+psycopg2://"
            f"{quote(self.DATABASE_USER, safe='')}:{quote(database_password, safe='')}"
            f"@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}"
        )
        if self.DEBUG:
            raise ValueError("Production requires DEBUG=false.")
        if self.JWT_SECRET_KEY == _INSECURE_JWT_DEFAULT or not _is_strong_secret(self.JWT_SECRET_KEY, minimum_length=32):
            raise ValueError("Production requires a strong non-default JWT secret.")
        if database_password == _INSECURE_DATABASE_MARKER or not _is_strong_secret(database_password, minimum_length=16):
            raise ValueError("Production requires a strong non-default database password.")
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
