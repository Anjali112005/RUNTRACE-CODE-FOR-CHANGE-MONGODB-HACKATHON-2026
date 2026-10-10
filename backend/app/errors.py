"""Typed API errors rendered as {"error": {"code", "message", "details"}}."""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: Any = None,
                 headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers

    def body(self) -> dict[str, Any]:
        err: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details is not None:
            err["details"] = self.details
        return {"error": err}


def bad_request(message: str, details: Any = None) -> ApiError:
    return ApiError(400, "bad_request", message, details)


def unauthorized(message: str = "Missing or invalid credentials.") -> ApiError:
    return ApiError(401, "unauthorized", message, headers={"WWW-Authenticate": "Bearer"})


def forbidden(message: str = "You do not have access to this resource.") -> ApiError:
    return ApiError(403, "forbidden", message)


def not_found(resource: str, identifier: str) -> ApiError:
    return ApiError(404, "not_found", f"{resource} '{identifier}' was not found.")


def conflict(message: str, details: Any = None) -> ApiError:
    return ApiError(409, "conflict", message, details)


def too_many_requests(retry_after: int) -> ApiError:
    return ApiError(429, "rate_limited", "Too many requests. Retry later.",
                    {"retry_after_seconds": retry_after}, headers={"Retry-After": str(retry_after)})


def db_unavailable(detail: str | None = None) -> ApiError:
    return ApiError(
        503,
        "database_unavailable",
        "MongoDB is not reachable, so RunTrace cannot read or persist data. "
        "Check RUNTRACE_MONGODB_URI and that MongoDB is running, then retry.",
        {"reason": detail} if detail else None,
    )
