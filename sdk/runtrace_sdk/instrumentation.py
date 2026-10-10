"""Run and Step context managers.

Behaviour guarantees:
* Application exceptions are always re-raised unchanged (``__exit__`` returns False).
* In best-effort mode (default) telemetry failures are logged once and never break the app.
* In strict mode (RUNTRACE_STRICT=true) telemetry failures raise TelemetryError - except while an
  application exception is already propagating, which is never masked.
* Every event has a client-generated ``event_id`` and the run has a ``client_run_key``, so
  retried requests are de-duplicated by the server.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import TYPE_CHECKING, Any

from .exceptions import TelemetryError
from .models import capture_error, new_event_id, to_json_safe, utc_iso

if TYPE_CHECKING:
    from .client import RunTraceClient

log = logging.getLogger("runtrace_sdk")

_UNSET = object()


class Step:
    """One instrumented step. Use via ``run.step(name)``."""

    def __init__(self, run: "Run", name: str, event_type: str, input: Any, metadata: dict[str, Any]) -> None:
        self.run = run
        self.name = name
        self.event_type = event_type
        self.input = input
        self.metadata = dict(metadata)
        self.output: Any = _UNSET
        self.sequence: int | None = None
        self.event_id = new_event_id()
        self.status: str | None = None
        self._started = 0.0
        self._timestamp = ""

    def set_output(self, value: Any) -> None:
        """Record the step's output (summarised, redacted and truncated before sending)."""
        self.output = value

    def set_input(self, value: Any) -> None:
        self.input = value

    def add_metadata(self, **values: Any) -> None:
        self.metadata.update(values)

    def __enter__(self) -> "Step":
        self.sequence = self.run._next_sequence()
        self._timestamp = utc_iso()
        self._started = time.perf_counter()
        return self

    def __exit__(self, exc_type: Any, exc: BaseException | None, tb: Any) -> bool:
        duration = round((time.perf_counter() - self._started) * 1000, 3)
        self.status = "failed" if exc is not None else "success"
        error = None
        if exc is not None:
            error = capture_error(exc, self.run.client.config.capture_traceback)
            self.run._last_step_exception = exc
        self.run._record({
            "event_id": self.event_id,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "name": self.name,
            "status": self.status,
            "timestamp": self._timestamp,
            "duration_ms": duration,
            "input_summary": self.input,
            "output_summary": None if self.output is _UNSET else self.output,
            "error": error,
            "metadata": self.metadata,
        }, app_error=exc is not None)
        return False  # never swallow application exceptions


class Run:
    """A recorded execution. Use via ``client.run(name)`` as a context manager."""

    def __init__(self, client: "RunTraceClient", name: str, *, version: str | None, environment: str | None,
                 metadata: dict[str, Any]) -> None:
        self.client = client
        self.name = name
        self.version = version
        self.environment = environment
        self.metadata = metadata
        self.run_id: str | None = None
        self.status: str | None = None
        self.client_run_key = uuid.uuid4().hex
        self._sequence = 0
        self._buffer: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._telemetry_ok = client.enabled
        self._warned = False
        self._started = 0.0
        self._last_step_exception: BaseException | None = None
        self.dropped_events = 0

    # -- context manager --------------------------------------------------------
    def __enter__(self) -> "Run":
        self._started = time.perf_counter()
        if self._telemetry_ok:
            body: dict[str, Any] = {"name": self.name, "client_run_key": self.client_run_key,
                                    "metadata": self._safe(self.metadata)}
            if self.version:
                body["version"] = self.version
            if self.environment:
                body["environment"] = self.environment
            try:
                self.run_id = self.client.request("POST", "/api/runs/start", body)["run_id"]
            except TelemetryError as exc:
                self._fail(exc, app_error=False)
        return self

    def __exit__(self, exc_type: Any, exc: BaseException | None, tb: Any) -> bool:
        app_error = exc is not None
        if exc is not None and exc is not self._last_step_exception:
            # Exception raised outside any step: record it as its own event so it can be diagnosed.
            self._record({
                "event_id": new_event_id(), "sequence": self._next_sequence(), "event_type": "error",
                "name": "unhandled_exception", "status": "failed", "timestamp": utc_iso(), "duration_ms": None,
                "input_summary": None, "output_summary": None,
                "error": capture_error(exc, self.client.config.capture_traceback), "metadata": {},
            }, app_error=True)
        self.status = "failed" if app_error else "success"
        duration = round((time.perf_counter() - self._started) * 1000, 3)
        error_summary = None
        if isinstance(exc, KeyboardInterrupt):
            error_summary = "Interrupted (KeyboardInterrupt)"
        elif exc is not None:
            error_summary = f"{type(exc).__name__}: {str(capture_error(exc, False)['message'])[:500]}"
        if self._telemetry_ok and self.run_id:
            try:
                self.flush(raise_errors=True)
                self.client.request("POST", f"/api/runs/{self.run_id}/finish", {
                    "status": self.status, "duration_ms": duration,
                    **({"error_summary": error_summary} if error_summary else {}),
                    "summary": {"dropped_events": self.dropped_events} if self.dropped_events else {},
                })
            except TelemetryError as err:
                self._fail(err, app_error=app_error)
        else:
            self.flush()  # telemetry unavailable: counts buffered events as dropped
        return False  # re-raise application exceptions unchanged

    # -- instrumentation API -------------------------------------------------------
    def step(self, name: str, *, event_type: str = "step", input: Any = None,
             metadata: dict[str, Any] | None = None) -> Step:
        """Context manager that records one step (timing, status, errors, optional input/output)."""
        return Step(self, name, event_type, input, metadata or {})

    def event(self, name: str, *, event_type: str = "log", status: str = "info", output: Any = None,
              metadata: dict[str, Any] | None = None) -> None:
        """Record a point-in-time event (no duration), e.g. a decision or a cache hit."""
        self._record({"event_id": new_event_id(), "sequence": self._next_sequence(), "event_type": event_type,
                      "name": name, "status": status, "timestamp": utc_iso(), "duration_ms": None,
                      "input_summary": None, "output_summary": output, "error": None, "metadata": metadata or {}})

    def flush(self, raise_errors: bool = False, app_error: bool = False) -> None:
        """Send buffered events now. Safe to call repeatedly."""
        with self._lock:
            batch, self._buffer = self._buffer, []
        if not batch:
            return
        if not (self._telemetry_ok and self.run_id):
            self.dropped_events += len(batch)
            return
        batch.sort(key=lambda e: e["sequence"])
        try:
            self.client.request("POST", f"/api/runs/{self.run_id}/events", {"events": batch})
        except TelemetryError as exc:
            self.dropped_events += len(batch)
            if raise_errors:
                raise
            self._fail(exc, app_error=app_error)

    # -- internals -------------------------------------------------------------
    def _next_sequence(self) -> int:
        with self._lock:
            self._sequence += 1
            return self._sequence

    def _safe(self, value: Any) -> Any:
        return to_json_safe(value, self.client.config.max_value_chars)

    def _record(self, event: dict[str, Any], app_error: bool = False) -> None:
        if not self.client.enabled:
            return
        for field in ("input_summary", "output_summary", "metadata"):
            event[field] = self._safe(event[field])
        if not isinstance(event["metadata"], dict):
            event["metadata"] = {"value": event["metadata"]}
        event = {k: v for k, v in event.items() if v is not None or k in ("input_summary", "output_summary")}
        with self._lock:
            self._buffer.append(event)
            should_flush = len(self._buffer) >= self.client.config.batch_size
        if should_flush:
            self.flush(app_error=app_error)

    def _fail(self, exc: Exception, app_error: bool) -> None:
        """Handle a telemetry failure according to strict / best-effort mode."""
        self._telemetry_ok = False
        if self.client.config.strict and not app_error:
            raise exc if isinstance(exc, TelemetryError) else TelemetryError(str(exc))
        if not self._warned:
            self._warned = True
            log.warning("RunTrace telemetry unavailable for run %r; continuing without it: %s", self.name, exc)
