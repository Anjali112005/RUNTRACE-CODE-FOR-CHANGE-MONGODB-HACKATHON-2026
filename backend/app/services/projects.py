from __future__ import annotations

from typing import Any

from pymongo.database import Database

from ..config import Settings
from ..errors import bad_request, conflict, not_found
from ..repositories import KeyRepository, ProjectRepository, RunRepository, VersionRepository
from ..repositories.base import page_meta
from ..security import (constant_time_equals, generate_key_id, generate_project_api_key, generate_project_id,
                        hash_api_key, key_display_prefix, sanitize)
from ..utils.timeutil import utcnow


class ProjectService:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.settings = settings
        self.projects = ProjectRepository(db)
        self.keys = KeyRepository(db)
        self.versions = VersionRepository(db)
        self.runs = RunRepository(db)

    # -- projects ---------------------------------------------------------
    def create(self, name: str, description: str, settings: dict[str, Any], *, is_demo: bool = False,
               demo_key: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        now = utcnow()
        doc: dict[str, Any] = {
            "project_id": generate_project_id(),
            "name": name,
            "description": description,
            "settings": sanitize(settings, self.settings.max_field_chars, self.settings.redact_keys),
            "is_demo": is_demo,
            "created_at": now,
            "updated_at": now,
        }
        if demo_key:
            doc["demo_key"] = demo_key
        project = self.projects.insert(doc)
        key = self.issue_key(project["project_id"])
        return project, key

    def get(self, project_id: str) -> dict[str, Any]:
        project = self.projects.get(project_id)
        if project is None:
            raise not_found("Project", project_id)
        return project

    def with_stats(self, projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ids = [p["project_id"] for p in projects]
        if not ids:
            return projects
        rows = self.runs.aggregate([
            {"$match": {"project_id": {"$in": ids}}},
            {"$group": {
                "_id": "$project_id",
                "total_runs": {"$sum": 1},
                "success_runs": {"$sum": {"$cond": [{"$eq": ["$status", "success"]}, 1, 0]}},
                "failed_runs": {"$sum": {"$cond": [{"$or": [{"$eq": ["$status", "failed"]},
                                                            {"$eq": ["$status", "timed_out"]}]}, 1, 0]}},
                "last_run_at": {"$max": "$started_at"},
            }},
        ])
        stats = {r["_id"]: r for r in rows}
        for project in projects:
            row = stats.get(project["project_id"], {})
            project["stats"] = {
                "total_runs": row.get("total_runs", 0),
                "success_runs": row.get("success_runs", 0),
                "failed_runs": row.get("failed_runs", 0),
                "last_run_at": row.get("last_run_at"),
            }
        return projects

    def list(self, q: str | None, include_demo: bool, page: int, page_size: int) -> dict[str, Any]:
        items, total = self.projects.list(q, include_demo, (page - 1) * page_size, page_size)
        return {"items": self.with_stats(items), "meta": page_meta(total, page, page_size)}

    def detail(self, project_id: str) -> dict[str, Any]:
        project = self.with_stats([self.get(project_id)])[0]
        keys = [self._key_public(k) for k in self.keys.list_for_project(project_id)]
        versions = self.versions.list_for_project(project_id)
        if versions:
            counts = {r["_id"]: r["n"] for r in self.runs.aggregate([
                {"$match": {"project_id": project_id}}, {"$group": {"_id": "$version", "n": {"$sum": 1}}}])}
            for v in versions:
                v["run_count"] = counts.get(v["version"], 0)
        return {"project": project, "keys": keys, "versions": versions}

    def update(self, project_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        self.get(project_id)
        fields = {k: v for k, v in changes.items() if v is not None}
        if "settings" in fields:
            fields["settings"] = sanitize(fields["settings"], self.settings.max_field_chars, self.settings.redact_keys)
        if not fields:
            raise bad_request("No fields to update.")
        fields["updated_at"] = utcnow()
        return self.with_stats([self.projects.update(project_id, fields)])[0]  # type: ignore[list-item]

    # -- keys ---------------------------------------------------------------
    @staticmethod
    def _key_public(doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "key_id": doc["key_id"], "project_id": doc["project_id"], "prefix": doc["prefix"],
            "created_at": doc["created_at"], "revoked_at": doc.get("revoked_at"),
            "last_used_at": doc.get("last_used_at"), "active": doc.get("revoked_at") is None,
        }

    def issue_key(self, project_id: str) -> dict[str, Any]:
        api_key = generate_project_api_key()
        now = utcnow()
        doc = {
            "key_id": generate_key_id(),
            "project_id": project_id,
            "key_hash": hash_api_key(api_key),
            "prefix": key_display_prefix(api_key),
            "created_at": now,
            "revoked_at": None,
            "last_used_at": None,
        }
        self.keys.insert(doc)
        # The plaintext key is returned to the caller exactly once and never persisted.
        return {"key_id": doc["key_id"], "project_id": project_id, "api_key": api_key,
                "prefix": doc["prefix"], "created_at": now}

    def rotate_key(self, project_id: str, revoke_existing: bool) -> dict[str, Any]:
        self.get(project_id)
        previous = self.keys.active_ids(project_id)
        issued = self.issue_key(project_id)
        if revoke_existing and previous:
            self.keys.revoke(project_id, previous, utcnow())
        return issued

    def revoke_keys(self, project_id: str, key_id: str | None) -> list[str]:
        self.get(project_id)
        active = self.keys.active_ids(project_id)
        if key_id:
            if key_id not in active:
                if any(k["key_id"] == key_id for k in self.keys.list_for_project(project_id)):
                    raise conflict("This key is already revoked.")
                raise not_found("Key", key_id)
            targets = [key_id]
        else:
            targets = active
        return self.keys.revoke(project_id, targets, utcnow())

    def authenticate_key(self, api_key: str) -> dict[str, Any] | None:
        """Return the key record for a valid, active key, else None."""
        digest = hash_api_key(api_key)
        record = self.keys.find_by_hash(digest)
        if record is None or not constant_time_equals(record["key_hash"], digest):
            return None
        if record.get("revoked_at") is not None:
            return None
        self.keys.touch(record["key_id"], record.get("last_used_at"), utcnow())
        return record

    # -- versions -----------------------------------------------------------
    def create_version(self, project_id: str, version: str, metadata: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        self.get(project_id)
        return self.versions.create(project_id, version,
                                    sanitize(metadata, self.settings.max_field_chars, self.settings.redact_keys))
