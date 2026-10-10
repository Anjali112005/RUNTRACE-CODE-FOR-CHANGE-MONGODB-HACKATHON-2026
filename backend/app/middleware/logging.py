"""Access log that never records headers, query strings or bodies (they may contain secrets)."""

from __future__ import annotations

import logging
import time
from typing import Any

log = logging.getLogger("runtrace.access")


class RequestLogMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status = {"code": 500}

        async def capture(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            elapsed = (time.perf_counter() - started) * 1000
            log.info("%s %s -> %s (%.1f ms)", scope.get("method"), scope.get("path"), status["code"], elapsed)
