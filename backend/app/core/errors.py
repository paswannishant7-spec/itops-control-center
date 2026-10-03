from collections.abc import Mapping
from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def problem(
    status_code: int,
    code: str,
    title: str,
    request_id: str,
    details: Any = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    payload: dict[str, Any] = {
        "type": f"urn:itops:error:{code}",
        "title": title,
        "status": status_code,
        "code": code,
        "request_id": request_id,
    }
    if details is not None:
        payload["details"] = details
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(payload),
        media_type="application/problem+json",
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        title = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return problem(
            exc.status_code, "http_error", title, request.state.request_id, headers=exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "validation_failed",
            "Request validation failed",
            request.state.request_id,
            exc.errors(),
        )

    @app.exception_handler(Exception)
    async def unexpected_handler(request: Request, exc: Exception) -> JSONResponse:
        structlog.get_logger().exception("unhandled_exception", error_type=type(exc).__name__)
        return problem(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_error",
            "An unexpected error occurred",
            request.state.request_id,
        )
