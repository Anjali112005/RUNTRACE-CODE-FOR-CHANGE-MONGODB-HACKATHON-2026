"""Payload helpers: safe JSON serialisation, client-side redaction and error capture."""

from __future__ import annotations

import dataclasses
import re
import traceback
import uuid
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

REDACTED = "[REDACTED]"
_SENSITIVE_KEY = re.compile(
    r"(^|[_\-.])(password|passwd|pwd|secret|client[_-]?secret|token|access[_-]?token|refresh[_-]?token|"
    r"api[_-]?key|apikey|access[_-]?key|authorization|cookie|credentials?|private[_-]?key|session[_-]?id)($|[_\-.])"
)
_SECRET_VALUES = [
    (re.compile(r"rt_live_[A-Za-z0-9_\-]{16,}"), "rt_live_" + REDACTED),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"), "sk-" + REDACTED),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"), REDACTED),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/\-]{8,}=*"), "Bearer " + REDACTED),
    (re.compile(r"(mongodb(?:\+srv)?://|https?://)[^:/\s@]+:[^@\s]+@"), r"\1" + REDACTED + "@"),
]


def new_event_id() -> str:
    return f"evt_{uuid.uuid4().hex}"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _redact_str(text: str) -> str:
    for pattern, repl in _SECRET_VALUES:
        text = pattern.sub(repl, text)
    return text


def to_json_safe(value: Any, max_chars: int = 4000, _depth: int = 0, _sensitive: bool = False) -> Any:
    """Convert arbitrary Python values into bounded, redacted JSON-compatible data."""
    if _depth > 8:
        return "[MAX_DEPTH]"
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"), float("-inf")) else str(value)
    if isinstance(value, str):
        if _sensitive:
            return REDACTED
        text = _redact_str(value)
        return text if len(text) <= max_chars else text[:max_chars] + f"…[truncated {len(text) - max_chars} chars]"
    if isinstance(value, bytes):
        return f"<bytes len={len(value)}>"
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return to_json_safe(value.value, max_chars, _depth + 1, _sensitive)
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for i, (k, v) in enumerate(value.items()):
            if i >= 100:
                out["__truncated_keys__"] = len(value) - 100
                break
            key = str(k)
            out[key] = to_json_safe(v, max_chars, _depth + 1, _sensitive or bool(_SENSITIVE_KEY.search(key.lower())))
        return out
    if isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)
        out_list = [to_json_safe(v, max_chars, _depth + 1, _sensitive) for v in items[:100]]
        if len(items) > 100:
            out_list.append(f"…[truncated {len(items) - 100} items]")
        return out_list
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return to_json_safe(dataclasses.asdict(value), max_chars, _depth + 1, _sensitive)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):  # pydantic v2 models
        try:
            return to_json_safe(model_dump(mode="json"), max_chars, _depth + 1, _sensitive)
        except Exception:  # noqa: BLE001 - fall through to repr
            pass
    text = repr(value)
    return to_json_safe(text, max_chars, _depth + 1, _sensitive)


def error_type_name(exc: BaseException) -> str:
    cls = type(exc)
    module = cls.__module__
    return cls.__qualname__ if module in {"builtins", "__main__"} else f"{module}.{cls.__qualname__}"


def capture_error(exc: BaseException, with_traceback: bool, max_chars: int = 4000) -> dict[str, Any]:
    error: dict[str, Any] = {"type": error_type_name(exc), "message": _redact_str(str(exc))[:max_chars]}
    if with_traceback:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__, limit=12))
        error["traceback"] = _redact_str(tb)[-8000:]
    return error
