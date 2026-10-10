"""MongoDB connection, health checks and idempotent index creation."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError

from .config import Settings
from .security import redact_string

log = logging.getLogger("runtrace.database")

# (keys, options) per collection. create_index is idempotent for identical specs.
INDEXES: dict[str, list[tuple[list[tuple[str, int]], dict[str, Any]]]] = {
    "projects": [
        ([("project_id", ASCENDING)], {"unique": True, "name": "uniq_project_id"}),
        ([("created_at", DESCENDING)], {"name": "created_at_desc"}),
    ],
    "project_keys": [
        ([("key_id", ASCENDING)], {"unique": True, "name": "uniq_key_id"}),
        ([("key_hash", ASCENDING)], {"unique": True, "name": "uniq_key_hash"}),
        ([("project_id", ASCENDING), ("created_at", DESCENDING)], {"name": "project_created"}),
    ],
    "project_versions": [
        ([("version_id", ASCENDING)], {"unique": True, "name": "uniq_version_id"}),
        ([("project_id", ASCENDING), ("version", ASCENDING)], {"unique": True, "name": "uniq_project_version"}),
    ],
    "runs": [
        ([("run_id", ASCENDING)], {"unique": True, "name": "uniq_run_id"}),
        ([("project_id", ASCENDING), ("client_run_key", ASCENDING)], {"unique": True, "name": "uniq_client_run_key"}),
        ([("project_id", ASCENDING), ("started_at", DESCENDING)], {"name": "project_started"}),
        ([("project_id", ASCENDING), ("status", ASCENDING), ("started_at", DESCENDING)], {"name": "project_status_started"}),
        ([("status", ASCENDING), ("started_at", ASCENDING)], {"name": "status_started"}),
        ([("started_at", DESCENDING)], {"name": "started_desc"}),
    ],
    "events": [
        ([("run_id", ASCENDING), ("event_id", ASCENDING)], {"unique": True, "name": "uniq_run_event_id"}),
        ([("run_id", ASCENDING), ("sequence", ASCENDING)], {"unique": True, "name": "uniq_run_sequence"}),
        ([("project_id", ASCENDING), ("timestamp", DESCENDING)], {"name": "project_timestamp"}),
    ],
    "findings": [
        ([("finding_id", ASCENDING)], {"unique": True, "name": "uniq_finding_id"}),
        ([("fingerprint", ASCENDING)], {"unique": True, "name": "uniq_fingerprint"}),
        ([("run_id", ASCENDING), ("created_at", DESCENDING)], {"name": "run_created"}),
        ([("project_id", ASCENDING), ("severity", ASCENDING), ("created_at", DESCENDING)], {"name": "project_severity_created"}),
        ([("project_id", ASCENDING), ("verification_status", ASCENDING)], {"name": "project_verification"}),
        ([("created_at", DESCENDING)], {"name": "created_desc"}),
    ],
}


def ensure_indexes(db: Database) -> None:
    for collection, specs in INDEXES.items():
        for keys, options in specs:
            db[collection].create_index(keys, **options)


def create_client(settings: Settings) -> MongoClient:
    return MongoClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=settings.mongodb_timeout_ms,
        connectTimeoutMS=settings.mongodb_timeout_ms,
        tz_aware=True,
        appname="runtrace-backend",
    )


def safe_error(exc: BaseException) -> str:
    """Error text with any credentials stripped (connection strings can appear in messages)."""
    text = f"{type(exc).__name__}: {exc}"
    return redact_string(text)[:500]


@dataclass
class DatabaseState:
    """Tracks connectivity so the API can report a clear 503 instead of failing obscurely."""

    db: Database | None
    connected: bool = False
    indexes_ready: bool = False
    last_error: str | None = None
    last_check: float = 0.0
    latency_ms: float | None = None
    # Set for an injected in-memory database (tests): skip the network ping.
    assume_connected: bool = False

    def __post_init__(self) -> None:
        self._lock = threading.Lock()

    def check(self, force: bool = False, min_interval: float = 5.0) -> bool:
        if self.assume_connected and self.db is not None:
            if not self.indexes_ready:
                ensure_indexes(self.db)
                self.indexes_ready = True
            self.connected = True
            self.latency_ms = 0.0
            return True
        if self.db is None:
            self.connected = False
            self.last_error = "Database client not initialised."
            return False
        now = time.monotonic()
        if not force and self.connected and now - self.last_check < min_interval:
            return True
        if not force and not self.connected and now - self.last_check < 1.0:
            return False
        with self._lock:
            self.last_check = time.monotonic()
            started = time.perf_counter()
            try:
                self.db.command("ping")
                self.latency_ms = round((time.perf_counter() - started) * 1000, 2)
                if not self.indexes_ready:
                    ensure_indexes(self.db)
                    self.indexes_ready = True
                if not self.connected:
                    log.info("Connected to MongoDB database '%s'", self.db.name)
                self.connected = True
                self.last_error = None
            except PyMongoError as exc:
                self.connected = False
                self.latency_ms = None
                self.last_error = safe_error(exc)
                log.error("MongoDB unavailable: %s", self.last_error)
            return self.connected
