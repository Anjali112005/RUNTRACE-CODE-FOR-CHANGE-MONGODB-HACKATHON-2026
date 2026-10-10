"""Identifiers, API-key handling, secret redaction, payload limits and rate limiting."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
import uuid
from collections import deque
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Identifiers (server-generated, collision-resistant; uniqueness is also
# enforced by unique MongoDB indexes).
# ---------------------------------------------------------------------------

ID_PATTERNS = {
    "project": re.compile(r"^prj_[a-f0-9]{32}$"),
    "run": re.compile(r"^run_[a-f0-9]{32}$"),
    "event": re.compile(r"^evt_[a-f0-9]{32}$"),
    "finding": re.compile(r"^fnd_[a-f0-9]{32}$"),
    "key": re.compile(r"^key_[a-f0-9]{32}$"),
    "version": re.compile(r"^ver_[a-f0-9]{32}$"),
}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def generate_project_id() -> str:
    return _new_id("prj")


def generate_run_id() -> str:
    return _new_id("run")


def generate_event_id() -> str:
    return _new_id("evt")


def generate_finding_id() -> str:
    return _new_id("fnd")


def generate_key_id() -> str:
    return _new_id("key")


def generate_version_id() -> str:
    return _new_id("ver")


# ---------------------------------------------------------------------------
# Project API keys. Only a SHA-256 hash is stored. Keys carry 256 bits of
# randomness, so an unsalted fast hash is appropriate (as with other bearer
# tokens); slow password hashing is unnecessary for high-entropy secrets.
# ---------------------------------------------------------------------------

API_KEY_PREFIX = "rt_live_"
API_KEY_PATTERN = re.compile(r"^rt_live_[A-Za-z0-9_\-]{43}$")


def generate_project_api_key() -> str:
    return f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def key_display_prefix(api_key: str) -> str:
    """Short, non-secret hint shown in the UI (e.g. 'rt_live_Ab3d…')."""
    return api_key[: len(API_KEY_PREFIX) + 4]


def looks_like_api_key(value: str) -> bool:
    return bool(API_KEY_PATTERN.match(value))


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    return value[:12] + "…" if len(value) > 12 else "…"


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

REDACTED = "[REDACTED]"

_SENSITIVE_KEY = re.compile(
    r"(^|[_\-.])(password|passwd|pwd|secret|client[_-]?secret|token|access[_-]?token|"
    r"refresh[_-]?token|api[_-]?key|apikey|access[_-]?key|authorization|auth[_-]?header|"
    r"cookie|set[_-]?cookie|credentials?|private[_-]?key|session[_-]?id|connection[_-]?string)($|[_\-.])"
)

_SECRET_VALUE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"rt_live_[A-Za-z0-9_\-]{16,}"), "rt_live_" + REDACTED),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"), "sk-" + REDACTED),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"), REDACTED),
    (re.compile(r"\b(ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{20,}"), REDACTED),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), REDACTED),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/\-]{8,}=*"), "Bearer " + REDACTED),
    (re.compile(r"(mongodb(?:\+srv)?://)[^:/\s@]+:[^@\s]+@"), r"\1" + REDACTED + "@"),
    (re.compile(r"(https?://)[^:/\s@]+:[^@\s]+@"), r"\1" + REDACTED + "@"),
]


def is_sensitive_key(key: str, extra_keys: Iterable[str] = ()) -> bool:
    lowered = key.lower()
    if lowered in extra_keys:
        return True
    return bool(_SENSITIVE_KEY.search(lowered))


def redact_string(value: str) -> str:
    for pattern, replacement in _SECRET_VALUE_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def redact(value: Any, extra_keys: Iterable[str] = (), _depth: int = 0, _sensitive: bool = False) -> Any:
    """Recursively redact secrets.

    * String values under sensitive keys (password, api_key, authorization, ...) are replaced.
      Numbers are kept so that e.g. ``max_tokens: 512`` survives.
    * Well-known secret formats (RunTrace keys, bearer tokens, credentials in URLs, ...)
      are redacted wherever they appear.
    """
    extra = tuple(extra_keys)
    if _depth > 25:
        return "[MAX_DEPTH]"
    if isinstance(value, str):
        return REDACTED if _sensitive else redact_string(value)
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            key = str(k)
            out[key] = redact(v, extra, _depth + 1, _sensitive or is_sensitive_key(key, extra))
        return out
    if isinstance(value, (list, tuple)):
        return [redact(v, extra, _depth + 1, _sensitive) for v in value]
    return value


def truncate(value: Any, max_chars: int, _depth: int = 0) -> Any:
    """Bound the size of stored strings and collections."""
    if _depth > 20:
        return "[MAX_DEPTH]"
    if isinstance(value, str):
        if len(value) > max_chars:
            return value[:max_chars] + f"…[truncated {len(value) - max_chars} chars]"
        return value
    if isinstance(value, dict):
        items = list(value.items())
        out = {str(k): truncate(v, max_chars, _depth + 1) for k, v in items[:200]}
        if len(items) > 200:
            out["__truncated_keys__"] = len(items) - 200
        return out
    if isinstance(value, list):
        out_list = [truncate(v, max_chars, _depth + 1) for v in value[:200]]
        if len(value) > 200:
            out_list.append(f"…[truncated {len(value) - 200} items]")
        return out_list
    return value


def sanitize(value: Any, max_chars: int, extra_keys: Iterable[str] = ()) -> Any:
    return truncate(redact(value, extra_keys), max_chars)


def canonical_hash(payload: Any) -> str:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Rate limiting (in-process sliding window; for multi-instance deployments put
# a shared limiter such as a reverse proxy in front).
# ---------------------------------------------------------------------------


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """Record a hit. Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                retry = int(self.window - (now - hits[0])) + 1
                return False, max(retry, 1)
            hits.append(now)
            if len(self._hits) > 10_000:  # bound memory
                for k in list(self._hits)[:1000]:
                    if not self._hits[k]:
                        del self._hits[k]
            return True, 0
