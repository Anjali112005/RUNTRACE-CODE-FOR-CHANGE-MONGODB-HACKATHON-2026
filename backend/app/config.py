"""Application settings loaded from environment variables (and an optional backend/.env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

try:  # python-dotenv is a runtime dependency, but keep config importable without it.
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None  # type: ignore[assignment]

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _str(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _int(name: str, default: int, minimum: int = 0) -> int:
    raw = _str(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer, got {raw!r}") from exc
    if value < minimum:
        raise ValueError(f"Environment variable {name} must be >= {minimum}")
    return value


def _float(name: str, default: float) -> float:
    raw = _str(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be a number, got {raw!r}") from exc


def _list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = _str(name)
    if raw is None:
        return default
    return tuple(item.strip() for item in raw.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    mongodb_uri: str = "mongodb://127.0.0.1:27017"
    mongodb_db: str = "runtrace"
    mongodb_timeout_ms: int = 3000
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    cors_origins: tuple[str, ...] = ("http://127.0.0.1:5173", "http://localhost:5173")
    admin_token: str | None = None
    max_request_bytes: int = 1_048_576
    max_events_per_batch: int = 500
    max_field_chars: int = 8000
    ingest_rate_per_minute: int = 1200
    api_rate_per_minute: int = 600
    stale_run_minutes: int = 60
    redact_keys: tuple[str, ...] = field(default_factory=tuple)
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-flash-latest"
    gemini_timeout_seconds: float = 45.0
    gemini_fallback_models: tuple[str, ...] = ("gemini-flash-lite-latest", "gemini-3-flash-preview")

    @property
    def auth_mode(self) -> str:
        return "admin_token" if self.admin_token else "open"

    @property
    def ai_enabled(self) -> bool:
        return bool(self.gemini_api_key)

    def with_overrides(self, **kwargs: object) -> "Settings":
        return replace(self, **kwargs)  # type: ignore[arg-type]

    @classmethod
    def from_env(cls, load_env_file: bool = True) -> "Settings":
        if load_env_file and load_dotenv is not None:
            load_dotenv(BACKEND_DIR / ".env", override=False)
        d = cls()
        return cls(
            mongodb_uri=_str("RUNTRACE_MONGODB_URI", d.mongodb_uri) or d.mongodb_uri,
            mongodb_db=_str("RUNTRACE_MONGODB_DB", d.mongodb_db) or d.mongodb_db,
            mongodb_timeout_ms=_int("RUNTRACE_MONGODB_TIMEOUT_MS", d.mongodb_timeout_ms, 100),
            host=_str("RUNTRACE_HOST", d.host) or d.host,
            port=_int("RUNTRACE_PORT", d.port, 1),
            log_level=(_str("RUNTRACE_LOG_LEVEL", d.log_level) or d.log_level).upper(),
            cors_origins=_list("RUNTRACE_CORS_ORIGINS", d.cors_origins),
            admin_token=_str("RUNTRACE_ADMIN_TOKEN"),
            max_request_bytes=_int("RUNTRACE_MAX_REQUEST_BYTES", d.max_request_bytes, 1024),
            max_events_per_batch=_int("RUNTRACE_MAX_EVENTS_PER_BATCH", d.max_events_per_batch, 1),
            max_field_chars=_int("RUNTRACE_MAX_FIELD_CHARS", d.max_field_chars, 100),
            ingest_rate_per_minute=_int("RUNTRACE_INGEST_RATE_PER_MINUTE", d.ingest_rate_per_minute, 1),
            api_rate_per_minute=_int("RUNTRACE_API_RATE_PER_MINUTE", d.api_rate_per_minute, 1),
            stale_run_minutes=_int("RUNTRACE_STALE_RUN_MINUTES", d.stale_run_minutes, 1),
            redact_keys=tuple(k.lower() for k in _list("RUNTRACE_REDACT_KEYS", ())),
            gemini_api_key=_str("GEMINI_API_KEY"),
            gemini_model=_str("GEMINI_MODEL", d.gemini_model) or d.gemini_model,
            gemini_timeout_seconds=_float("GEMINI_TIMEOUT_SECONDS", d.gemini_timeout_seconds),
            gemini_fallback_models=_list("GEMINI_FALLBACK_MODELS", d.gemini_fallback_models),
        )