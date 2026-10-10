"""HTTP client for the RunTrace API."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from . import __version__
from .config import RunTraceConfig
from .exceptions import APIError, TransportError

log = logging.getLogger("runtrace_sdk")

RETRY_STATUSES = {429, 500, 502, 503, 504}


class RunTraceClient:
    """Entry point of the SDK.

    >>> client = RunTraceClient.from_env()
    >>> with client.run("Customer Support Workflow") as run:
    ...     with run.step("retrieve_context"):
    ...         ...
    """

    def __init__(self, config: RunTraceConfig, transport: httpx.BaseTransport | None = None) -> None:
        self.config = config
        self._http: httpx.Client | None = None
        if config.enabled:
            self._http = httpx.Client(
                base_url=config.api_url,
                timeout=config.timeout,
                transport=transport,
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "User-Agent": f"runtrace-sdk/{__version__}",
                },
            )

    @classmethod
    def from_env(cls, transport: httpx.BaseTransport | None = None, **overrides: Any) -> "RunTraceClient":
        return cls(RunTraceConfig.from_env(**overrides), transport=transport)

    def __repr__(self) -> str:
        return f"RunTraceClient({self.config!r})"

    def __enter__(self) -> "RunTraceClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        if self._http is not None:
            self._http.close()

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    # -- public API ---------------------------------------------------------
    def run(self, name: str, *, version: str | None = None, environment: str | None = None,
            metadata: dict[str, Any] | None = None) -> "Run":
        from .instrumentation import Run

        return Run(self, name, version=version or self.config.version,
                   environment=environment or self.config.environment, metadata=metadata or {})

    def verify(self) -> dict[str, Any]:
        """Check the API key; returns {project_id, project_name, key_id}."""
        return self.request("GET", "/api/keys/verify")

    def health(self) -> dict[str, Any]:
        return self.request("GET", "/health")

    # -- low level ------------------------------------------------------------
    def request(self, method: str, path: str, json: Any = None) -> dict[str, Any]:
        if self._http is None:
            raise TransportError("RunTrace telemetry is disabled (RUNTRACE_ENABLED=false).")
        attempts = self.config.max_retries + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                response = self._http.request(method, path, json=json)
            except httpx.HTTPError as exc:
                last_error = exc
                log.debug("RunTrace %s %s failed (attempt %d): %s", method, path, attempt + 1, type(exc).__name__)
                self._sleep(attempt, None)
                continue
            if response.status_code in RETRY_STATUSES and attempt < attempts - 1:
                self._sleep(attempt, response.headers.get("Retry-After"))
                continue
            if response.status_code >= 400:
                raise self._api_error(response)
            try:
                return response.json()
            except ValueError as exc:
                raise APIError(response.status_code, "bad_response", "Response was not JSON.") from exc
        raise TransportError(f"Could not reach RunTrace at {self.config.api_url} "
                             f"({type(last_error).__name__ if last_error else 'error'}).") from last_error

    @staticmethod
    def _api_error(response: httpx.Response) -> APIError:
        try:
            err = response.json().get("error", {})
        except ValueError:
            err = {}
        return APIError(response.status_code, err.get("code", f"http_{response.status_code}"),
                        err.get("message", response.reason_phrase), err.get("details"))

    def _sleep(self, attempt: int, retry_after: str | None) -> None:
        if attempt >= self.config.max_retries:
            return
        delay = 0.2 * (2 ** attempt)
        if retry_after:
            try:
                delay = min(float(retry_after), 5.0)
            except ValueError:
                pass
        time.sleep(delay)


from .instrumentation import Run  # noqa: E402  (re-export for type checkers)
