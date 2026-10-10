"""SDK configuration, read from environment variables by default."""

from __future__ import annotations

import os
import re
import warnings
from dataclasses import dataclass, replace
from urllib.parse import urlparse

from .exceptions import ConfigurationError

KEY_PATTERN = re.compile(r"^rt_live_[A-Za-z0-9_\-]{43}$")
TRUE = {"1", "true", "yes", "on"}
FALSE = {"0", "false", "no", "off"}


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in TRUE:
        return True
    if value in FALSE:
        return False
    raise ConfigurationError(f"{name} must be true/false, got {raw!r}")


def _number(name: str, default: float, cast: type = float, minimum: float = 0) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = cast(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number, got {raw!r}") from exc
    if value < minimum:
        raise ConfigurationError(f"{name} must be >= {minimum}")
    return value


def mask_key(key: str | None) -> str:
    if not key:
        return "<unset>"
    return key[:12] + "…" if len(key) > 12 else "<invalid>"


@dataclass(frozen=True)
class RunTraceConfig:
    api_url: str = "http://127.0.0.1:8000"
    api_key: str | None = None
    environment: str | None = None
    version: str | None = None
    enabled: bool = True
    strict: bool = False
    timeout: float = 5.0
    max_retries: int = 2
    batch_size: int = 20
    capture_traceback: bool = True
    max_value_chars: int = 4000

    def __post_init__(self) -> None:
        if not self.enabled:
            return
        parsed = urlparse(self.api_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConfigurationError(f"RUNTRACE_API_URL must be an http(s) URL, got {self.api_url!r}")
        if not self.api_key:
            raise ConfigurationError(
                "RUNTRACE_API_KEY is not set. Create a project in the RunTrace dashboard and export its key, "
                "or set RUNTRACE_ENABLED=false to disable telemetry.")
        if not KEY_PATTERN.match(self.api_key):
            raise ConfigurationError(f"RUNTRACE_API_KEY has an invalid format ({mask_key(self.api_key)}). "
                                     "Expected rt_live_ followed by 43 URL-safe characters.")
        if self.timeout <= 0:
            raise ConfigurationError("timeout must be > 0")
        if self.batch_size < 1:
            raise ConfigurationError("batch_size must be >= 1")
        host = parsed.hostname or ""
        if parsed.scheme == "http" and host not in {"127.0.0.1", "localhost", "::1"}:
            warnings.warn("RUNTRACE_API_URL uses plain http to a non-local host; the API key is sent unencrypted.",
                          RuntimeWarning, stacklevel=3)

    def __repr__(self) -> str:  # never print the key
        return (f"RunTraceConfig(api_url={self.api_url!r}, api_key={mask_key(self.api_key)!r}, "
                f"environment={self.environment!r}, version={self.version!r}, enabled={self.enabled}, "
                f"strict={self.strict})")

    def with_overrides(self, **kwargs: object) -> "RunTraceConfig":
        return replace(self, **kwargs)  # type: ignore[arg-type]

    @classmethod
    def from_env(cls, **overrides: object) -> "RunTraceConfig":
        values: dict[str, object] = {
            "api_url": (os.environ.get("RUNTRACE_API_URL") or cls.api_url).rstrip("/"),
            "api_key": (os.environ.get("RUNTRACE_API_KEY") or "").strip() or None,
            "environment": os.environ.get("RUNTRACE_ENVIRONMENT") or None,
            "version": os.environ.get("RUNTRACE_VERSION") or None,
            "enabled": _bool("RUNTRACE_ENABLED", True),
            "strict": _bool("RUNTRACE_STRICT", False),
            "timeout": _number("RUNTRACE_TIMEOUT", 5.0),
            "max_retries": int(_number("RUNTRACE_MAX_RETRIES", 2, int)),
            "batch_size": int(_number("RUNTRACE_BATCH_SIZE", 20, int, 1)),
            "capture_traceback": _bool("RUNTRACE_CAPTURE_TRACEBACK", True),
        }
        values.update(overrides)
        return cls(**values)  # type: ignore[arg-type]
