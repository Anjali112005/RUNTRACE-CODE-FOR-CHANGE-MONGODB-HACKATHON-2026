"""FastAPI application factory.

Run locally:  python -m app            (uses RUNTRACE_HOST / RUNTRACE_PORT)
         or:  uvicorn app.main:app --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, DuplicateKeyError, PyMongoError
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .config import Settings
from .database import DatabaseState, create_client, safe_error
from .errors import ApiError, db_unavailable
from .middleware import BodySizeLimitMiddleware, RequestLogMiddleware
from .routes import ROUTERS
from .security import SlidingWindowLimiter
from .services.ai import AIService

log = logging.getLogger("runtrace")

DESCRIPTION = """
**RunTrace** — Find the Regression. Trace the Evidence. Verify the Fix.

* Ingestion endpoints authenticate with a project API key: `Authorization: Bearer rt_live_…`.
* Dashboard endpoints use `X-RunTrace-Admin-Token` when `RUNTRACE_ADMIN_TOKEN` is set (otherwise open mode).
* Findings separate observations (recorded facts) from hypotheses (possible explanations).
"""


def _configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level, logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(settings: Settings | None = None, db: Database | None = None, ai_service: AIService | None = None) -> FastAPI:
    """Build the app. Pass `db` (e.g. a mongomock database) to skip the real MongoDB connection."""
    settings = settings or Settings.from_env()
    _configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = None
        if db is None:
            client = create_client(settings)
            app.state.db_state = DatabaseState(client[settings.mongodb_db])
        else:
            app.state.db_state = DatabaseState(db, assume_connected=True)
        if not app.state.db_state.check(force=True):
            log.error("Starting WITHOUT a database connection. API calls that need data will return 503 until "
                      "MongoDB is reachable. Reason: %s", app.state.db_state.last_error)
        try:
            yield
        finally:
            if client is not None:
                client.close()

    app = FastAPI(title="RunTrace API", version=__version__, description=DESCRIPTION, lifespan=lifespan)
    app.state.settings = settings
    app.state.ingest_limiter = SlidingWindowLimiter(settings.ingest_rate_per_minute)
    app.state.api_limiter = SlidingWindowLimiter(settings.api_rate_per_minute)
    app.state.ai_service = ai_service or AIService(settings)
    # Set eagerly so the app also works when used without the lifespan (e.g. some test clients).
    if db is not None:
        app.state.db_state = DatabaseState(db, assume_connected=True)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-RunTrace-Key", "X-RunTrace-Admin-Token"],
        max_age=600,
    )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(RequestLogMiddleware)

    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(exc.body(), status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed", 413: "payload_too_large"}.get(exc.status_code, f"http_{exc.status_code}")
        return JSONResponse({"error": {"code": code, "message": str(exc.detail)}}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Do not echo submitted input back: it may contain secrets.
        errors = [{"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()[:50]]
        return JSONResponse({"error": {"code": "validation_error", "message": "Request validation failed.",
                                       "details": errors}}, status_code=422)

    @app.exception_handler(PyMongoError)
    async def mongo_handler(request: Request, exc: PyMongoError) -> JSONResponse:
        if isinstance(exc, DuplicateKeyError):
            return JSONResponse({"error": {"code": "conflict", "message": "A record with this identifier already exists."}},
                                status_code=409)
        if not isinstance(exc, ConnectionFailure):  # ServerSelectionTimeoutError, NetworkTimeout, AutoReconnect...
            log.error("Database operation failed: %s", safe_error(exc))
            return JSONResponse({"error": {"code": "database_error", "message": "A database operation failed."}},
                                status_code=500)
        state = request.app.state.db_state
        state.connected = False
        state.last_error = safe_error(exc)
        log.error("Database error: %s", state.last_error)
        err = db_unavailable(state.last_error)
        return JSONResponse(err.body(), status_code=err.status_code)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled error: %s", type(exc).__name__)
        return JSONResponse({"error": {"code": "internal_error", "message": "An unexpected error occurred."}},
                            status_code=500)

    for router in ROUTERS:
        app.include_router(router)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, Any]:
        return {"service": "RunTrace API", "docs": "/docs", "health": "/health"}

    return app


def _lazy_app() -> FastAPI:
    return create_app()


app = _lazy_app()


def run() -> None:
    import uvicorn

    settings = app.state.settings
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, log_level=settings.log_level.lower())
