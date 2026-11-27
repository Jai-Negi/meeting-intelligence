import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_email import router as email_router
from app.api.routes_history import router as history_router
from app.api.routes_meetings import router as meetings_router
from app.config import get_settings
from app.database.maintenance import fail_interrupted_jobs
from app.database.session import init_db
from app.logging_config import setup_logging

settings = get_settings()
setup_logging(level="DEBUG" if settings.debug else "INFO")

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    fail_interrupted_jobs()
    logger.info(
        "application starting",
        extra={"environment": settings.environment, "llm_providers": settings.llm_provider_chain},
    )
    yield


app = FastAPI(
    title=settings.app_name,
    description="Multi agent meeting intelligence engine",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meetings_router)
app.include_router(history_router)
app.include_router(email_router)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
        "transcription_provider": settings.transcription_provider,
    }
