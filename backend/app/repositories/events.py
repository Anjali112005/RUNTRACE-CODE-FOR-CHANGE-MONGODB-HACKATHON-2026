from __future__ import annotations

from typing import Any

from pymongo import ASCENDING

from .base import Repository, clean


class EventRepository(Repository):
    collection_name = "events"

    def insert(self, doc: dict[str, Any]) -> None:
        self.col.insert_one(doc)

    def find_existing(self, run_id: str, event_id: str | None, sequence: int) -> dict[str, Any] | None:
        """Return the stored event that collides by event_id (preferred) or sequence, with its content hash."""
        doc = None
        if event_id:
            doc = self.col.find_one({"run_id": run_id, "event_id": event_id})
        if doc is None:
            doc = self.col.find_one({"run_id": run_id, "sequence": sequence})
        if doc is not None:
            doc.pop("_id", None)
        return doc

    def list_for_run(self, run_id: str, limit: int = 5000) -> list[dict[str, Any]]:
        docs = self.col.find({"run_id": run_id}).sort("sequence", ASCENDING).limit(limit)
        return [clean(d) for d in docs]  # type: ignore[misc]

    def count_for_run(self, run_id: str) -> int:
        return self.col.count_documents({"run_id": run_id})

    def first_failure(self, run_id: str) -> dict[str, Any] | None:
        return clean(self.col.find_one({"run_id": run_id, "status": "failed"}, sort=[("sequence", ASCENDING)]))

    def delete_for_runs(self, run_ids: list[str]) -> int:
        return self.col.delete_many({"run_id": {"$in": run_ids}}).deleted_count
