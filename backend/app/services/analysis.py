"""Comparison, diagnosis persistence and fix verification."""

from __future__ import annotations

from typing import Any

from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from ..comparison.engine import compare_runs, step_keys
from ..config import Settings
from ..diagnosis.engine import diagnose
from ..errors import bad_request, conflict, not_found
from ..repositories import EventRepository, FindingRepository, RunRepository
from ..repositories.base import page_meta
from ..security import generate_finding_id
from ..utils.timeutil import iso, utcnow

VERIFICATION_NOTE = ("Verification compares observable behaviour of the corrected run with the failure. "
                     "It shows whether the symptom is gone; it does not prove the hypothesis was the root cause.")


class AnalysisService:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.settings = settings
        self.runs = RunRepository(db)
        self.events = EventRepository(db)
        self.findings = FindingRepository(db)

    def _run(self, run_id: str) -> dict[str, Any]:
        run = self.runs.get(run_id)
        if run is None:
            raise not_found("Run", run_id)
        return run

    # -- comparison ------------------------------------------------------------
    def compare(self, baseline_run_id: str, comparison_run_id: str, include_diagnosis: bool = True) -> dict[str, Any]:
        if baseline_run_id == comparison_run_id:
            raise bad_request("Choose two different runs to compare.")
        baseline, comparison = self._run(baseline_run_id), self._run(comparison_run_id)
        b_events = self.events.list_for_run(baseline_run_id)
        c_events = self.events.list_for_run(comparison_run_id)
        result = compare_runs(baseline, b_events, comparison, c_events)
        if include_diagnosis:
            drafts = diagnose(comparison, c_events, baseline, b_events, result)
            result["diagnosis"] = {
                "persisted": False,
                "note": "Hypotheses are generated from recorded evidence and are not proven causes. "
                        "Use 'Save findings' (POST /api/runs/{run_id}/analyze) to store them.",
                "findings": [d.to_dict() for d in drafts],
            }
        return result

    # -- diagnosis ---------------------------------------------------------------
    def analyze(self, run_id: str, baseline_run_id: str | None = None) -> dict[str, Any]:
        run = self._run(run_id)
        events = self.events.list_for_run(run_id)
        baseline = None
        selection = "none"
        if baseline_run_id:
            if baseline_run_id == run_id:
                raise bad_request("A run cannot be its own baseline.")
            baseline = self._run(baseline_run_id)
            if baseline["project_id"] != run["project_id"]:
                raise bad_request("Baseline run must belong to the same project.")
            selection = "explicit"
        else:
            baseline = self.runs.find_baseline(run["project_id"], run["name"], run["started_at"], run_id)
            selection = "latest_successful_same_name" if baseline else "none"
            if baseline is None:
                baseline = self.runs.find_baseline(run["project_id"], None, run["started_at"], run_id)
                selection = "latest_successful_in_project" if baseline else "none"
        comparison = None
        b_events: list[dict[str, Any]] | None = None
        if baseline is not None:
            b_events = self.events.list_for_run(baseline["run_id"])
            comparison = compare_runs(baseline, b_events, run, events)
        drafts = diagnose(run, events, baseline, b_events, comparison)

        now = utcnow()
        stored = []
        for draft in drafts:
            fp = draft.fingerprint(run_id, baseline["run_id"] if baseline else None)
            analysis_fields = {**draft.to_dict(), "baseline_run_id": baseline["run_id"] if baseline else None,
                               "updated_at": now}
            existing = self.findings.get_by_fingerprint(fp)
            if existing:
                stored.append(self.findings.replace_analysis(fp, analysis_fields))
                continue
            doc = {
                "finding_id": generate_finding_id(), "fingerprint": fp, "project_id": run["project_id"],
                "run_id": run_id, "verification_status": "unverified", "verification": None,
                "source": "deterministic", "is_demo": bool(run.get("is_demo")), "created_at": now,
                **analysis_fields,
            }
            try:
                stored.append(self.findings.insert(doc))
            except DuplicateKeyError:  # concurrent analyze of the same run
                stored.append(self.findings.replace_analysis(fp, analysis_fields))
        return {
            "run_id": run_id,
            "baseline_run_id": baseline["run_id"] if baseline else None,
            "baseline_selection": selection,
            "findings": stored,
            "comparison_summary": ({**comparison["summary"], "earliest_divergence": comparison["earliest_divergence"]}
                                   if comparison else None),
        }

    def get_finding(self, finding_id: str) -> dict[str, Any]:
        finding = self.findings.get(finding_id)
        if finding is None:
            raise not_found("Finding", finding_id)
        return finding

    def list_findings(self, *, page: int, page_size: int, **filters: Any) -> dict[str, Any]:
        query = self.findings.build_query(**filters)
        items, total = self.findings.list(query, (page - 1) * page_size, page_size)
        return {"items": items, "meta": page_meta(total, page, page_size)}

    # -- verification --------------------------------------------------------------
    def verify(self, finding_id: str, corrected_run_id: str) -> dict[str, Any]:
        finding = self.get_finding(finding_id)
        if corrected_run_id == finding["run_id"]:
            raise bad_request("Verify against a different (corrected) run, not the run that produced the finding.")
        failed_run = self._run(finding["run_id"])
        corrected = self._run(corrected_run_id)
        if corrected["project_id"] != finding["project_id"]:
            raise bad_request("The corrected run must belong to the same project as the finding.")
        if corrected["status"] == "running":
            raise conflict("The corrected run is still running; verify after it finishes.")

        events = self.events.list_for_run(corrected_run_id)
        by_key = dict(zip(step_keys(events), events))
        failed_events = [e for e in events if e.get("status") == "failed"]
        checks: list[dict[str, Any]] = []

        checks.append({
            "check": "run_succeeded",
            "description": "Corrected run finished successfully",
            "passed": corrected["status"] == "success",
            "observed": corrected["status"],
            "expected": "success",
        })
        step_key = finding.get("step_key")
        step_event = None
        if step_key and finding.get("category") != "config_mismatch":
            step_event = by_key.get(step_key)
            if step_event is None and finding.get("step"):
                step_event = next((e for e in events if e["name"] == finding["step"]), None)
            checks.append({
                "check": "step_present",
                "description": f"Step '{finding.get('step')}' was recorded in the corrected run",
                "passed": step_event is not None,
                "observed": step_event["event_id"] if step_event else None,
                "expected": "recorded",
            })
            if step_event is not None:
                checks.append({
                    "check": "step_succeeded",
                    "description": f"Step '{finding.get('step')}' did not fail",
                    "passed": step_event.get("status") != "failed",
                    "observed": step_event.get("status"),
                    "expected": "not failed",
                    "event_id": step_event["event_id"],
                })
        checks.append({
            "check": "no_failed_events",
            "description": "No step failed in the corrected run",
            "passed": not failed_events,
            "observed": [e["name"] for e in failed_events[:10]],
            "expected": [],
        })
        if corrected["started_at"] < failed_run["started_at"]:
            checks.append({"check": "run_order", "description": "Corrected run started after the failing run",
                           "passed": False, "observed": iso(corrected["started_at"]), "expected": f"after {iso(failed_run['started_at'])}"})

        step_missing = any(c["check"] == "step_present" and not c["passed"] for c in checks)
        if all(c["passed"] for c in checks):
            status = "verified"
        elif step_missing and corrected["status"] == "success":
            status = "inconclusive"
        elif any(c["check"] == "run_order" for c in checks) and corrected["status"] == "success" and not failed_events:
            status = "inconclusive"
        else:
            status = "not_improved"
        verification = {
            "run_id": corrected_run_id,
            "checked_at": iso(utcnow()),
            "result": status,
            "checks": checks,
            "note": VERIFICATION_NOTE,
        }
        return self.findings.update(finding_id, {"verification_status": status, "verification": verification,
                                                  "updated_at": utcnow()})  # type: ignore[return-value]
