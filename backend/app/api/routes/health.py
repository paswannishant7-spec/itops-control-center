from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.core.config import get_settings
from app.db.session import database_is_ready

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok", "ready", "not_ready"]
    service: str
    version: str


@router.get("/health/live", response_model=HealthResponse, summary="Process liveness")
async def liveness() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", service=settings.app_name, version=settings.app_version)


@router.get("/health/ready", response_model=HealthResponse, summary="Service readiness")
async def readiness(response: Response) -> HealthResponse:
    settings = get_settings()
    if not await database_is_ready():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            status="not_ready", service=settings.app_name, version=settings.app_version
        )
    return HealthResponse(status="ready", service=settings.app_name, version=settings.app_version)
