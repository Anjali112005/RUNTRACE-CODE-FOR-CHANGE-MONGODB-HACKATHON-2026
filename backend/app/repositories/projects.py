from __future__ import annotations

from typing import Any

from pymongo import DESCENDING

from .base import Repository, clean, search_regex


class ProjectRepository(Repository):
    collection_name = "projects"

    def insert(self, doc: dict[str, Any]) -> dict[str, Any]:
        self.col.insert_one(doc)
        return clean(doc)  # type: ignore[return-value]

    def get(self, project_id: str) -> dict[str, Any] | None:
        return clean(self.col.find_one({"project_id": project_id}))

    def get_by_demo_key(self, demo_key: str) -> dict[str, Any] | None:
        return clean(self.col.find_one({"demo_key": demo_key}))

    def list(self, q: str | None, include_demo: bool, skip: int, limit: int) -> tuple[list[dict[str, Any]], int]:
        query: dict[str, Any] = {}
        if q:
            query["$or"] = [{"name": search_regex(q)}, {"description": search_regex(q)}, {"project_id": q.strip()}]
        if not include_demo:
            query["is_demo"] = {"$ne": True}
        total = self.col.count_documents(query)
        docs = self.col.find(query).sort("created_at", DESCENDING).skip(skip).limit(limit)
        return [clean(d) for d in docs], total  # type: ignore[misc]

    def update(self, project_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        self.col.update_one({"project_id": project_id}, {"$set": fields})
        return self.get(project_id)

    def names(self, project_ids: list[str]) -> dict[str, str]:
        if not project_ids:
            return {}
        docs = self.col.find({"project_id": {"$in": list(set(project_ids))}}, {"project_id": 1, "name": 1})
        return {d["project_id"]: d["name"] for d in docs}

    def count(self, include_demo: bool = True) -> int:
        return self.col.count_documents({} if include_demo else {"is_demo": {"$ne": True}})

    def delete_demo(self) -> int:
        return self.col.delete_many({"is_demo": True}).deleted_count
