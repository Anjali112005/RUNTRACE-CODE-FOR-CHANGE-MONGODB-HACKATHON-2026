"""UTC time helpers. All timestamps in RunTrace are stored and returned as UTC."""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    # MongoDB stores millisecond precision; truncate so round-trips compare equal.
    now = datetime.now(timezone.utc)
    return now.replace(microsecond=(now.microsecond // 1000) * 1000)


def ensure_utc(value: datetime | None) -> datetime | None:
    """Return a timezone-aware UTC datetime. Naive datetimes are interpreted as UTC
    (PyMongo returns naive datetimes unless tz_aware=True; mongomock may do the same)."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def iso(value: datetime | None) -> str | None:
    value = ensure_utc(value)
    return value.isoformat().replace("+00:00", "Z") if value else None


def duration_ms(start: datetime | None, end: datetime | None) -> float | None:
    start, end = ensure_utc(start), ensure_utc(end)
    if start is None or end is None:
        return None
    return max(0.0, round((end - start).total_seconds() * 1000, 3))
