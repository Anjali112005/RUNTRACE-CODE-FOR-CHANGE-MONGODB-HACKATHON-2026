from __future__ import annotations

from typing import Any

from pymongo import DESCENDING

from .base import Repository, clean, search_regex


class FindingRepository(Repository):
    collection_name = "findings"

    def get(self, finding_id: str) -> dict[str, Any] | None:
        return clean(self.col.find_one({"finding_id": finding_id}))

    def get_by_fingerprint(self, fingerprint: str) -> dict[str, Any] | None:
        return clean(self.col.find_one({"fingerprint": fingerprint}))

    def insert(self, doc: dict[str, Any]) -> dict[str, Any]:
        self.col.insert_one(doc)
        return clean(doc)  # type: ignore[return-value]

    def replace_analysis(self, fingerprint: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        """Refresh analysis fields of an existing finding without touching its verification state."""
        self.col.update_one({"fingerprint": fingerprint}, {"$set": fields})
        return self.get_by_fingerprint(fingerprint)

    def update(self, finding_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        self.col.update_one({"finding_id": finding_id}, {"$set": fields})
        return self.get(finding_id)

    def list_for_run(self, run_id: str) -> list[dict[str, Any]]:
        docs = self.col.find({"run_id": run_id}).sort("created_at", DESCENDING)
        return [clean(d) for d in docs]  # type: ignore[misc]

    @staticmethod
    def build_query(project_id: str | None = None, run_id: str | None = None, severity: str | None = None,
                    category: str | None = None, verification_status: str | None = None, q: str | None = None,
                    include_demo: bool = True) -> dict[str, Any]:
        query: dict[str, Any] = {}
        for field, value in (("project_id", project_id), ("run_id", run_id), ("severity", severity),
                             ("category", category), ("verification_status", verification_status)):
            if value:
                query[field] = value
        if not include_demo:
            query["is_demo"] = {"$ne": True}
        if q:
            query["$or"] = [{"title": search_regex(q)}, {"summary": search_regex(q)}, {"step": search_regex(q)}]
        return query

    def list(self, query: dict[str, Any], skip: int, limit: int) -> tuple[list[dict[str, Any]], int]:
        total = self.col.count_documents(query)
        docs = self.col.find(query).sort("created_at", DESCENDING).skip(skip).limit(limit)
        return [clean(d) for d in docs], total  # type: ignore[misc]

    def count(self, query: dict[str, Any]) -> int:
        return self.col.count_documents(query)

    def delete_for_runs(self, run_ids: list[str]) -> int:
        return self.col.delete_many({"run_id": {"$in": run_ids}}).deleted_count
