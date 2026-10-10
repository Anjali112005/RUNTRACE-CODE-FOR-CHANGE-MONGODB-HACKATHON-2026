"""SDK exception hierarchy."""

from __future__ import annotations

from typing import Any


class RunTraceError(Exception):
    """Base class for all RunTrace SDK errors."""


class ConfigurationError(RunTraceError):
    """Invalid or missing configuration (e.g. RUNTRACE_API_KEY)."""


class TelemetryError(RunTraceError):
    """Telemetry could not be delivered. Raised only in strict mode."""


class TransportError(TelemetryError):
    """Network-level failure talking to the RunTrace API."""


class APIError(TelemetryError):
    """The RunTrace API returned an error response."""

    def __init__(self, status_code: int, code: str, message: str, details: Any = None) -> None:
        super().__init__(f"RunTrace API error {status_code} ({code}): {message}")
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
