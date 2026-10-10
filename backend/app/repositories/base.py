from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any

from pymongo.collection import Collection
from pymongo.database import Database

from ..utils.timeutil import ensure_utc

HIDDEN_FIELDS = {"_id", "key_hash", "content_hash", "fingerprint"}


def clean(doc: dict[str, Any] | None, hidden: set[str] = HIDDEN_FIELDS) -> dict[str, Any] | None:
    """Strip internal fields and normalise datetimes to UTC-aware values."""
    if doc is None:
        return None
    out: dict[str, Any] = {}
    for key, value in doc.items():
        if key in hidden:
            continue
        out[key] = ensure_utc(value) if isinstance(value, datetime) else value
    return out


def search_regex(term: str) -> dict[str, Any]:
    return {"$regex": re.escape(term.strip()[:100]), "$options": "i"}


def page_meta(total: int, page: int, page_size: int) -> dict[str, int]:
    return {"total": total, "page": page, "page_size": page_size,
            "pages": max(1, math.ceil(total / page_size)) if page_size else 1}


class Repository:
    collection_name: str = ""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.col: Collection = db[self.collection_name]
