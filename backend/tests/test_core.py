from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.errors import problem, register_exception_handlers
from app.core.logging import configure_logging


def test_problem_response_omits_absent_details() -> None:
    response = problem(400, "bad_request", "Bad request", "request-1")
    assert response.status_code == 400
    assert b'"request_id":"request-1"' in response.body
    assert b'"details"' not in response.body


def test_validation_errors_use_controlled_contract() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/items/{item_id}")
    async def read_item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    @app.middleware("http")
    async def request_id(request, call_next):  # type: ignore[no-untyped-def]
        request.state.request_id = "validation-request"
        return await call_next(request)

    response = TestClient(app).get("/items/not-an-integer")
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "validation_failed"


def test_http_errors_use_controlled_contract() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/forbidden")
    async def forbidden() -> None:
        raise HTTPException(status_code=403, detail="Forbidden")

    @app.middleware("http")
    async def request_id(request, call_next):  # type: ignore[no-untyped-def]
        request.state.request_id = "http-error-request"
        return await call_next(request)

    response = TestClient(app).get("/forbidden")
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "http_error"


def test_unhandled_errors_do_not_expose_exception_text() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/failure")
    async def failure() -> None:
        raise RuntimeError("sensitive implementation detail")

    @app.middleware("http")
    async def request_id(request, call_next):  # type: ignore[no-untyped-def]
        request.state.request_id = "failure-request"
        return await call_next(request)

    response = TestClient(app, raise_server_exceptions=False).get("/failure")
    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert "sensitive" not in response.text


def test_logging_supports_console_and_json_renderers() -> None:
    configure_logging("INFO", False)
    configure_logging("INFO", True)
