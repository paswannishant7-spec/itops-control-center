from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.db.session import dispose_engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    logger = structlog.get_logger()
    await logger.ainfo("application_started", environment=settings.environment)
    yield
    await dispose_engine()
    await logger.ainfo("application_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin).rstrip("/") for origin in settings.cors_origins],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
    )
    # Registered last so even CORS preflight and rejection responses receive hardening headers.
    app.add_middleware(
        SecurityHeadersMiddleware, production=settings.environment.lower() == "production"
    )
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
