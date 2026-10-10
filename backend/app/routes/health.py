from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from .. import __version__
from ..utils.timeutil import iso, utcnow

router = APIRouter(tags=["health"])


@router.get("/health", summary="Service and database health")
def health(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    state = request.app.state.db_state
    connected = state.check(force=True)
    return {
        "status": "ok" if connected else "degraded",
        "service": "runtrace-api",
        "version": __version__,
        "time": iso(utcnow()),
        "database": {
            "connected": connected,
            "name": settings.mongodb_db,
            "latency_ms": state.latency_ms,
            "error": None if connected else state.last_error,
            "indexes_ready": state.indexes_ready,
        },
        "auth_mode": settings.auth_mode,
        "ai": {"enabled": settings.ai_enabled, "model": settings.gemini_model if settings.ai_enabled else None},
        "limits": {"max_request_bytes": settings.max_request_bytes,
                   "max_events_per_batch": settings.max_events_per_batch},
    }
