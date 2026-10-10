from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any

from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from ..config import Settings
from ..errors import ApiError, conflict, not_found
from ..repositories import EventRepository, ProjectRepository, RunRepository, VersionRepository
from ..repositories.base import page_meta
from ..schemas.runs import EventIn, RunFinish, RunStart
from ..security import canonical_hash, generate_event_id, generate_run_id, sanitize
from ..utils.timeutil import duration_ms, ensure_utc, iso, utcnow

FINAL_STATUSES = {"success", "failed"}

_sweep_lock = threading.Lock()
_last_sweep = 0.0


class RunService:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.settings = settings
        self.runs = RunRepository(db)
        self.events = EventRepository(db)
        self.projects = ProjectRepository(db)
        self.versions = VersionRepository(db)

    def _sanitize(self, value: Any) -> Any:
        return sanitize(value, self.settings.max_field_chars, self.settings.redact_keys)

    # -- lifecycle ------------------------------------------------------------
    def start(self, project_id: str, payload: RunStart, *, source: str = "sdk", is_demo: bool = False,
              started_at: datetime | None = None) -> tuple[dict[str, Any], bool]:
        client_key = payload.client_run_key or uuid.uuid4().hex
        existing = self.runs.get_by_client_key(project_id, client_key)
        if existing:
            if existing["name"] != payload.name:
                raise conflict("client_run_key was already used for a run with a different name.")
            return existing, False
        version_id = None
        if payload.version:
            version_id = self.versions.ensure(project_id, payload.version)["version_id"]
        now = utcnow()
        doc = {
            "run_id": generate_run_id(),
            "project_id": project_id,
            "client_run_key": client_key,
            "version_id": version_id,
            "version": payload.version,
            "name": payload.name,
            "status": "running",
            "environment": payload.environment,
            "started_at": ensure_utc(started_at) or now,
            "finished_at": None,
            "duration_ms": None,
            "error_summary": None,
            "summary": {},
            "metadata": self._sanitize(payload.metadata),
            "event_count": 0,
            "failed_event_count": 0,
            "is_demo": is_demo,
            "source": source,
            "created_at": now,
            "updated_at": now,
        }
        try:
            run = self.runs.insert(doc)
        except DuplicateKeyError:
            existing = self.runs.get_by_client_key(project_id, client_key)
            if existing is None:
                raise
            return existing, False
        run.pop("client_run_key", None)
        return run, True

    def ingest(self, run: dict[str, Any], events: list[EventIn]) -> dict[str, Any]:
        if len(events) > self.settings.max_events_per_batch:
            raise ApiError(413, "batch_too_large",
                           f"At most {self.settings.max_events_per_batch} events per request.")
        finished = run["status"] in FINAL_STATUSES
        results: list[dict[str, Any]] = []
        created = failed_created = 0
        for event in sorted(events, key=lambda e: e.sequence):
            doc, content_hash = self._event_doc(run, event)
            existing = self.events.find_existing(run["run_id"], event.event_id, event.sequence) if finished else None
            if finished and existing is None:
                raise conflict(f"Run {run['run_id']} is already finished; new events are rejected.",
                               {"sequence": event.sequence, "accepted_before_conflict": results})
            if existing is None:
                try:
                    self.events.insert(doc)
                    results.append({"event_id": doc["event_id"], "sequence": event.sequence, "result": "created"})
                    created += 1
                    failed_created += 1 if event.status == "failed" else 0
                    continue
                except DuplicateKeyError:
                    existing = self.events.find_existing(run["run_id"], event.event_id, event.sequence)
                    if existing is None:
                        raise
            if existing.get("content_hash") == content_hash:
                results.append({"event_id": existing["event_id"], "sequence": existing["sequence"], "result": "duplicate"})
                continue
            reason = ("event_id was already used with different content" if event.event_id and existing["event_id"] == event.event_id
                      else f"sequence {event.sequence} is already used by another event")
            self.runs.increment_counts(run["run_id"], created, failed_created)
            raise conflict(f"Conflicting duplicate event: {reason}.",
                           {"event_id": event.event_id, "sequence": event.sequence,
                            "existing_event_id": existing["event_id"], "accepted_before_conflict": results})
        self.runs.increment_counts(run["run_id"], created, failed_created)
        if created:
            self.runs.update(run["run_id"], {"updated_at": utcnow()})
        return {"run_id": run["run_id"], "accepted": created, "duplicates": len(results) - created, "results": results}

    def _event_doc(self, run: dict[str, Any], event: EventIn) -> tuple[dict[str, Any], str]:
        input_summary = self._sanitize(event.input_summary)
        output_summary = self._sanitize(event.output_summary)
        metadata = self._sanitize(event.metadata)
        error = self._sanitize(event.error.model_dump()) if event.error else None
        hashed = {
            "event_id": event.event_id, "sequence": event.sequence, "event_type": event.event_type,
            "name": event.name, "status": event.status, "timestamp": iso(event.timestamp),
            "duration_ms": event.duration_ms, "input_summary": input_summary, "output_summary": output_summary,
            "error": error, "metadata": metadata,
        }
        content_hash = canonical_hash(hashed)
        doc = {
            "event_id": event.event_id or generate_event_id(),
            "run_id": run["run_id"],
            "project_id": run["project_id"],
            "sequence": event.sequence,
            "event_type": event.event_type,
            "name": event.name,
            "status": event.status,
            "timestamp": event.timestamp or utcnow(),
            "duration_ms": event.duration_ms,
            "input_summary": input_summary,
            "output_summary": output_summary,
            "error": error,
            "metadata": metadata,
            "content_hash": content_hash,
            "received_at": utcnow(),
        }
        return doc, content_hash

    def finish(self, run: dict[str, Any], payload: RunFinish, *, finished_at: datetime | None = None) -> dict[str, Any]:
        if run["status"] in FINAL_STATUSES:
            if run["status"] == payload.status:
                return run  # idempotent retry
            raise conflict(f"Run is already finished with status '{run['status']}'.")
        now = ensure_utc(finished_at) or utcnow()
        first_failure = self.events.first_failure(run["run_id"])
        error_summary = payload.error_summary
        if payload.status == "failed" and not error_summary and first_failure and first_failure.get("error"):
            err = first_failure["error"]
            error_summary = f"{first_failure['name']}: {err.get('type', 'Error')}: {err.get('message', '')}"[:1000]
        summary = dict(self._sanitize(payload.summary))
        summary.update({
            "event_count": self.events.count_for_run(run["run_id"]),
            "first_failed_step": first_failure["name"] if first_failure else None,
        })
        fields = {
            "status": payload.status,
            "finished_at": now,
            "duration_ms": payload.duration_ms if payload.duration_ms is not None else duration_ms(run["started_at"], now),
            "error_summary": self._sanitize(error_summary) if error_summary else None,
            "summary": summary,
            "updated_at": utcnow(),
        }
        return self.runs.update(run["run_id"], fields)  # type: ignore[return-value]

    # -- reads ----------------------------------------------------------------
    def get(self, run_id: str) -> dict[str, Any]:
        run = self.runs.get(run_id)
        if run is None:
            raise not_found("Run", run_id)
        run.pop("client_run_key", None)
        return run

    def with_project_names(self, runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        names = self.projects.names([r["project_id"] for r in runs])
        for run in runs:
            run.pop("client_run_key", None)
            run["project_name"] = names.get(run["project_id"])
        return runs

    def list(self, *, project_id: str | None, status: str | None, q: str | None, include_demo: bool,
             version: str | None, page: int, page_size: int) -> dict[str, Any]:
        self.sweep_stale()
        query = self.runs.build_query(project_id, status, q, include_demo, version)
        items, total = self.runs.list(query, (page - 1) * page_size, page_size)
        return {"items": self.with_project_names(items), "meta": page_meta(total, page, page_size)}

    def events_for(self, run_id: str) -> list[dict[str, Any]]:
        events = self.events.list_for_run(run_id)
        for e in events:
            e.pop("received_at", None)
        return events

    # -- maintenance ------------------------------------------------------------
    def sweep_stale(self, force: bool = False) -> int:
        """Mark runs that never called finish as timed_out (throttled to every 30 s per process)."""
        global _last_sweep
        now_mono = time.monotonic()
        if not force and now_mono - _last_sweep < 30:
            return 0
        with _sweep_lock:
            _last_sweep = now_mono
            now = utcnow()
            minutes = self.settings.stale_run_minutes
            return self.runs.mark_stale(now - timedelta(minutes=minutes), now, minutes)
