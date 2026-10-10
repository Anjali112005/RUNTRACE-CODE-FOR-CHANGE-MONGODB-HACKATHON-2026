"""Metrics computed from the full set of matching records (never from a paginated subset)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from pymongo.database import Database

from ..config import Settings
from ..repositories import FindingRepository, ProjectRepository, RunRepository
from ..utils.timeutil import ensure_utc, iso, utcnow

MAX_DAYS = 365


class MetricsService:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.settings = settings
        self.runs = RunRepository(db)
        self.projects = ProjectRepository(db)
        self.findings = FindingRepository(db)

    def compute(self, project_id: str | None, days: int, include_demo: bool) -> dict[str, Any]:
        days = max(1, min(days, MAX_DAYS))
        now = utcnow()
        since = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
        base = self.runs.build_query(project_id=project_id, include_demo=include_demo)
        window = {**base, "started_at": {"$gte": since}}

        def count(extra: dict[str, Any]) -> int:
            return self.runs.count({**window, **extra})

        total = count({})
        success = count({"status": "success"})
        failed = count({"status": "failed"})
        timed_out = count({"status": "timed_out"})
        running = count({"status": "running"})
        finished = success + failed + timed_out

        avg_rows = self.runs.aggregate([
            {"$match": {**window, "duration_ms": {"$ne": None}, "status": {"$in": ["success", "failed"]}}},
            {"$group": {"_id": None, "avg": {"$avg": "$duration_ms"}, "n": {"$sum": 1}}},
        ])
        avg = avg_rows[0]["avg"] if avg_rows else None
        n_dur = avg_rows[0]["n"] if avg_rows else 0

        version_rows = self.runs.aggregate([
            {"$match": window},
            {"$group": {
                "_id": "$version",
                "total": {"$sum": 1},
                "success": {"$sum": {"$cond": [{"$eq": ["$status", "success"]}, 1, 0]}},
                "failed": {"$sum": {"$cond": [{"$or": [{"$eq": ["$status", "failed"]},
                                                       {"$eq": ["$status", "timed_out"]}]}, 1, 0]}},
            }},
        ])
        by_version = sorted(
            ({"version": r["_id"] or "unversioned", "total": r["total"], "success": r["success"], "failed": r["failed"],
              "failure_rate": round(r["failed"] / (r["success"] + r["failed"]), 4) if (r["success"] + r["failed"]) else None}
             for r in version_rows),
            key=lambda r: r["version"],
        )

        # Daily activity: bucket every run in the window (projection only; bounded by MAX_DAYS).
        buckets: dict[str, dict[str, Any]] = {}
        for i in range(days):
            day = (since + timedelta(days=i)).date().isoformat()
            buckets[day] = {"date": day, "total": 0, "success": 0, "failed": 0, "running": 0}
        for row in self.runs.find_projection(window, {"started_at": 1, "status": 1}):
            day = ensure_utc(row["started_at"]).date().isoformat()  # type: ignore[union-attr]
            bucket = buckets.get(day)
            if bucket is None:
                continue
            bucket["total"] += 1
            status = row.get("status")
            if status == "success":
                bucket["success"] += 1
            elif status in ("failed", "timed_out"):
                bucket["failed"] += 1
            else:
                bucket["running"] += 1

        fq = self.findings.build_query(project_id=project_id, include_demo=include_demo)
        findings = {
            "total": self.findings.count(fq),
            "high": self.findings.count({**fq, "severity": "high"}),
            "verified": self.findings.count({**fq, "verification_status": "verified"}),
            "unverified": self.findings.count({**fq, "verification_status": "unverified"}),
        }
        total_projects = 1 if project_id else self.projects.count(include_demo)
        return {
            "scope": {"project_id": project_id, "days": days, "since": iso(since), "include_demo": include_demo},
            "totals": {"projects": total_projects, "runs": total, "success": success, "failed": failed,
                       "timed_out": timed_out, "running": running, "finished": finished,
                       "all_time_runs": self.runs.count(base)},
            "success_rate": round(success / finished, 4) if finished else None,
            "average_duration_ms": round(avg, 2) if avg is not None else None,
            "duration_sample_size": n_dur,
            "by_version": by_version,
            "activity": list(buckets.values()),
            "findings": findings,
            "notes": [
                "Success rate = successful / finished runs (running runs excluded) within the window.",
                "Average duration only includes finished runs with a recorded duration.",
                "Failures by version show correlation, not causation.",
            ],
            "generated_at": iso(now),
        }
