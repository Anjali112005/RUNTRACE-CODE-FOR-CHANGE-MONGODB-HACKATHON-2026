from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from pymongo import DESCENDING

from ..utils.timeutil import ensure_utc
from .base import Repository, clean


class KeyRepository(Repository):
    collection_name = "project_keys"

    def insert(self, doc: dict[str, Any]) -> None:
        self.col.insert_one(doc)

    def find_by_hash(self, key_hash: str) -> dict[str, Any] | None:
        doc = self.col.find_one({"key_hash": key_hash})
        if doc is None:
            return None
        doc.pop("_id", None)
        return doc  # includes key_hash for constant-time verification by the caller

    def list_for_project(self, project_id: str) -> list[dict[str, Any]]:
        docs = self.col.find({"project_id": project_id}).sort("created_at", DESCENDING)
        return [clean(d) for d in docs]  # type: ignore[misc]

    def active_ids(self, project_id: str) -> list[str]:
        return [d["key_id"] for d in self.col.find({"project_id": project_id, "revoked_at": None}, {"key_id": 1})]

    def revoke(self, project_id: str, key_ids: list[str], when: datetime) -> list[str]:
        revoked = []
        for key_id in key_ids:
            result = self.col.update_one({"project_id": project_id, "key_id": key_id, "revoked_at": None},
                                         {"$set": {"revoked_at": when}})
            if result.modified_count:
                revoked.append(key_id)
        return revoked

    def touch(self, key_id: str, last_used_at: datetime | None, now: datetime) -> None:
        """Update last_used_at at most once a minute to avoid a write per request."""
        last = ensure_utc(last_used_at)
        if last is None or now - last > timedelta(seconds=60):
            self.col.update_one({"key_id": key_id}, {"$set": {"last_used_at": now}})

    def delete_for_projects(self, project_ids: list[str]) -> int:
        return self.col.delete_many({"project_id": {"$in": project_ids}}).deleted_count
