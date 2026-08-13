from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.modules.identity.api.router import auth_router, users_router
from app.modules.investigations.api.router import router as investigations_router
from app.modules.connectors.api.router import router as connectors_router, ingest_router
from app.modules.ai_reasoning.api.intelligence_router import router as intelligence_router
from app.modules.attack_graph.api.router import router as attack_graph_router
from app.modules.assets.api.router import router as assets_router
from app.modules.evidence.api.router import router as evidence_router
from app.modules.reporting.api.router import router as reporting_router
from app.modules.demos.api.router import router as demos_router
from app.shared.exceptions import register_exception_handlers

settings = get_settings()
configure_logging()

app = FastAPI(
    title=f"{settings.APP_NAME} API",
    description=(
        "AI-Powered Security Decision Engine — REST API. "
        "v1 ships authentication/RBAC and the investigations module (mock "
        "data). v2 adds the connector framework, AI reasoning (Gemini/"
        "Anthropic/Ollama), and the Attack Graph — a real derived view "
        "over existing investigation data, never a fabricated diagram."
    ),
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)


@app.get("/api/v1/health", tags=["System"])
def health_check() -> dict[str, str]:
    """Liveness/readiness probe target for Docker/Kubernetes."""
    return {"status": "ok", "service": settings.APP_NAME}


app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(users_router, prefix=settings.API_V1_PREFIX)
app.include_router(investigations_router, prefix=settings.API_V1_PREFIX)
app.include_router(reporting_router, prefix=settings.API_V1_PREFIX)
app.include_router(connectors_router, prefix=settings.API_V1_PREFIX)
app.include_router(ingest_router, prefix=settings.API_V1_PREFIX)
app.include_router(intelligence_router, prefix=settings.API_V1_PREFIX)
app.include_router(attack_graph_router, prefix=settings.API_V1_PREFIX)
app.include_router(assets_router, prefix=settings.API_V1_PREFIX)
app.include_router(evidence_router, prefix=settings.API_V1_PREFIX)
app.include_router(demos_router, prefix=settings.API_V1_PREFIX)
