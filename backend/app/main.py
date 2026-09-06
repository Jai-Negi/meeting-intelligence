import logging

from fastapi import FastAPI

from app.config import get_settings
from app.logging_config import setup_logging

settings = get_settings()
setup_logging(level="DEBUG" if settings.debug else "INFO")

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    description="Multi agent meeting intelligence engine",
    version="0.1.0",
)


@app.on_event("startup")
async def on_startup() -> None:
    logger.info(
        "application starting",
        extra={"environment": settings.environment, "llm_provider": settings.llm_provider},
    )


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
    }
