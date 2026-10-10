from __future__ import annotations

from typing import Any

from pymongo import DESCENDING
from pymongo.errors import DuplicateKeyError

from ..security import generate_version_id
from ..utils.timeutil import utcnow
from .base import Repository, clean


class VersionRepository(Repository):
    collection_name = "project_versions"

    def get_by_label(self, project_id: str, version: str) -> dict[str, Any] | None:
        return clean(self.col.find_one({"project_id": project_id, "version": version}))

    def create(self, project_id: str, version: str, metadata: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Create a version; returns (doc, created). Existing labels are returned unchanged."""
        existing = self.get_by_label(project_id, version)
        if existing:
            return existing, False
        doc = {"version_id": generate_version_id(), "project_id": project_id, "version": version,
               "metadata": metadata, "created_at": utcnow()}
        try:
            self.col.insert_one(doc)
        except DuplicateKeyError:  # concurrent creation of the same label
            return self.get_by_label(project_id, version), False  # type: ignore[return-value]
        return clean(doc), True  # type: ignore[return-value]

    def ensure(self, project_id: str, version: str) -> dict[str, Any]:
        doc, _ = self.create(project_id, version, {})
        return doc

    def list_for_project(self, project_id: str) -> list[dict[str, Any]]:
        docs = self.col.find({"project_id": project_id}).sort("created_at", DESCENDING)
        return [clean(d) for d in docs]  # type: ignore[misc]

    def delete_for_projects(self, project_ids: list[str]) -> int:
        return self.col.delete_many({"project_id": {"$in": project_ids}}).deleted_count
