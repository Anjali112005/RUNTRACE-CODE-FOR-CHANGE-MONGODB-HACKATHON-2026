from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo import DESCENDING

from .base import Repository, clean, search_regex

FAILED_STATUSES = ["failed", "timed_out"]


class RunRepository(Repository):
    collection_name = "runs"

    def insert(self, doc: dict[str, Any]) -> dict[str, Any]:
        self.col.insert_one(doc)
        return clean(doc)  # type: ignore[return-value]

    def get(self, run_id: str) -> dict[str, Any] | None:
        return clean(self.col.find_one({"run_id": run_id}))

    def get_by_client_key(self, project_id: str, client_run_key: str) -> dict[str, Any] | None:
        return clean(self.col.find_one({"project_id": project_id, "client_run_key": client_run_key}))

    def update(self, run_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        self.col.update_one({"run_id": run_id}, {"$set": fields})
        return self.get(run_id)

    def increment_counts(self, run_id: str, events: int, failed: int) -> None:
        if events or failed:
            self.col.update_one({"run_id": run_id}, {"$inc": {"event_count": events, "failed_event_count": failed}})

    @staticmethod
    def build_query(project_id: str | None = None, status: str | None = None, q: str | None = None,
                    include_demo: bool = True, version: str | None = None,
                    since: datetime | None = None) -> dict[str, Any]:
        query: dict[str, Any] = {}
        if project_id:
            query["project_id"] = project_id
        if status:
            query["status"] = status
        if version:
            query["version"] = version
        if not include_demo:
            query["is_demo"] = {"$ne": True}
        if since:
            query["started_at"] = {"$gte": since}
        if q:
            query["$or"] = [{"name": search_regex(q)}, {"run_id": q.strip()}, {"error_summary": search_regex(q)}]
        return query

    def list(self, query: dict[str, Any], skip: int, limit: int) -> tuple[list[dict[str, Any]], int]:
        total = self.col.count_documents(query)
        docs = self.col.find(query).sort("started_at", DESCENDING).skip(skip).limit(limit)
        return [clean(d) for d in docs], total  # type: ignore[misc]

    def count(self, query: dict[str, Any]) -> int:
        return self.col.count_documents(query)

    def find_baseline(self, project_id: str, name: str | None, before: datetime, exclude_run_id: str) -> dict[str, Any] | None:
        query: dict[str, Any] = {"project_id": project_id, "status": "success", "started_at": {"$lte": before},
                                 "run_id": {"$ne": exclude_run_id}}
        if name:
            query["name"] = name
        doc = self.col.find_one(query, sort=[("started_at", DESCENDING)])
        return clean(doc)

    def mark_stale(self, cutoff: datetime, now: datetime, minutes: int) -> int:
        result = self.col.update_many(
            {"status": "running", "started_at": {"$lt": cutoff}},
            {"$set": {"status": "timed_out", "finished_at": now, "duration_ms": None,
                      "error_summary": f"No finish call received within {minutes} minutes; marked timed_out by the server.",
                      "updated_at": now}},
        )
        return result.modified_count

    def last_run_at(self, project_id: str) -> datetime | None:
        doc = self.col.find_one({"project_id": project_id}, {"started_at": 1}, sort=[("started_at", DESCENDING)])
        return clean(doc)["started_at"] if doc else None  # type: ignore[index]

    def aggregate(self, pipeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return list(self.col.aggregate(pipeline))

    def find_projection(self, query: dict[str, Any], projection: dict[str, int], limit: int = 0) -> list[dict[str, Any]]:
        cursor = self.col.find(query, projection)
        if limit:
            cursor = cursor.limit(limit)
        return [clean(d) for d in cursor]  # type: ignore[misc]

    def demo_run_ids(self) -> list[str]:
        return [d["run_id"] for d in self.col.find({"is_demo": True}, {"run_id": 1})]

    def delete_demo(self) -> int:
        return self.col.delete_many({"is_demo": True}).deleted_count
