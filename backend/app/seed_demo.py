"""Explicit, idempotent demo seeding.

    python -m app.seed_demo           # create the demo project once (skips if it exists)
    python -m app.seed_demo --reset   # delete ONLY demo records, then recreate them

Scenario ("Support Assistant"):
  v1.0  baseline   - the LLM returns raw JSON, the parser succeeds.            -> success
  v1.1  regression - a new prompt makes the LLM wrap JSON in Markdown fences,
                     parse_response raises JSONDecodeError.                    -> failed
  v1.2  fix        - the parser strips code fences.                            -> success

All records carry is_demo=true and source="demo_seed" so they are distinguishable from SDK data.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from typing import Any, Literal

from pymongo.database import Database

from .config import Settings
from .database import DatabaseState, create_client
from .repositories import EventRepository, FindingRepository, KeyRepository, ProjectRepository, RunRepository, VersionRepository
from .schemas.runs import EventIn, RunFinish, RunStart
from .services.analysis import AnalysisService
from .services.projects import ProjectService
from .services.runs import RunService
from .utils.timeutil import utcnow

DEMO_KEY = "runtrace-demo-support-assistant-v1"
QUESTION = "How do I reset my password?"
ANSWER = {"answer": "Open Settings > Security and choose 'Reset password'. A reset link is emailed to you.",
          "citations": ["kb-12", "kb-31"]}
CONTEXT = [{"doc_id": "kb-12", "title": "Account security", "score": 0.91},
           {"doc_id": "kb-31", "title": "Password reset emails", "score": 0.84}]


def _workflow(version: str) -> tuple[list[dict[str, Any]], Literal["success", "failed"], str | None]:
    """Return (events, final_status, error_summary) for a scripted run."""
    prompt_version = "support-v1" if version == "1.0" else "support-v2-markdown"
    raw_json = json.dumps(ANSWER)
    llm_text = raw_json if version == "1.0" else f"```json\n{json.dumps(ANSWER, indent=2)}\n```"
    events: list[dict[str, Any]] = [
        {"name": "load_config", "event_type": "step", "duration_ms": 4,
         "output_summary": {"model": "demo-llm-small", "temperature": 0.2, "prompt_version": prompt_version}},
        {"name": "retrieve_context", "event_type": "retrieval", "duration_ms": 142,
         "input_summary": {"query": QUESTION, "top_k": 2}, "output_summary": {"documents": CONTEXT}},
        {"name": "build_prompt", "event_type": "step", "duration_ms": 2,
         "input_summary": {"documents": 2},
         "output_summary": {"template": prompt_version, "characters": 1184 if version == "1.0" else 1342}},
        {"name": "call_llm", "event_type": "llm", "duration_ms": 820 if version == "1.0" else 905,
         "input_summary": {"model": "demo-llm-small", "prompt_template": prompt_version},
         "output_summary": {"text": llm_text, "finish_reason": "stop"},
         "metadata": {"model": "demo-llm-small", "prompt_tokens": 412, "completion_tokens": 61}},
    ]
    if version == "1.1":
        events.append({
            "name": "parse_response", "event_type": "parse", "status": "failed", "duration_ms": 1,
            "input_summary": llm_text,
            "error": {"type": "json.decoder.JSONDecodeError", "message": "Expecting value: line 1 column 1 (char 0)",
                      "traceback": "Traceback (most recent call last):\n  ...\njson.decoder.JSONDecodeError: "
                                   "Expecting value: line 1 column 1 (char 0)"},
        })
        return events, "failed", None
    parse_input = llm_text
    events.append({"name": "parse_response", "event_type": "parse", "duration_ms": 1, "input_summary": parse_input,
                   "output_summary": {"keys": ["answer", "citations"], "citations": 2},
                   "metadata": {"strip_code_fences": version == "1.2"}})
    events.append({"name": "format_answer", "event_type": "step", "duration_ms": 3,
                   "output_summary": {"answer": ANSWER["answer"], "citations": ANSWER["citations"]}})
    return events, "success", None


def _record(runs: RunService, project_id: str, version: str, started: datetime) -> dict[str, Any]:
    events, status, error_summary = _workflow(version)
    run, _ = runs.start(project_id, RunStart(
        name="Customer Support Workflow", version=version, environment="demo",
        metadata={"prompt_version": events[0]["output_summary"]["prompt_version"], "model": "demo-llm-small",
                  "seeded": True},
        client_run_key=f"demo-{DEMO_KEY}-{version.replace('.', '-')}",
    ), source="demo_seed", is_demo=True, started_at=started)
    clock = started
    payload = []
    for seq, ev in enumerate(events, start=1):
        clock = clock + timedelta(milliseconds=ev.get("duration_ms") or 1)
        payload.append(EventIn(sequence=seq, timestamp=clock, status=ev.get("status", "success"),
                               **{k: v for k, v in ev.items() if k != "status"}))
    runs.ingest(run, payload)
    total = sum(ev.get("duration_ms") or 0 for ev in events) + 35
    return runs.finish(run, RunFinish(status=status, error_summary=error_summary, duration_ms=total,
                                      summary={"question": QUESTION}),
                       finished_at=started + timedelta(milliseconds=total))


def reset_demo(db: Database) -> dict[str, int]:
    projects = ProjectRepository(db)
    project_ids = [d["project_id"] for d in db["projects"].find({"is_demo": True}, {"project_id": 1})]
    run_ids = RunRepository(db).demo_run_ids()
    return {
        "findings": FindingRepository(db).delete_for_runs(run_ids),
        "events": EventRepository(db).delete_for_runs(run_ids),
        "runs": RunRepository(db).delete_demo(),
        "keys": KeyRepository(db).delete_for_projects(project_ids),
        "versions": VersionRepository(db).delete_for_projects(project_ids),
        "projects": projects.delete_demo(),
    }


def seed_demo(db: Database, settings: Settings, now: datetime | None = None) -> dict[str, Any]:
    existing = ProjectRepository(db).get_by_demo_key(DEMO_KEY)
    if existing:
        return {"created": False, "project_id": existing["project_id"],
                "message": "Demo data already exists; nothing was changed. Use --reset to recreate it."}
    now = now or utcnow()
    project, _key = ProjectService(db, settings).create(
        "Demo · Support Assistant",
        "Seeded demonstration of a prompt regression: JSON output wrapped in Markdown breaks the parser, "
        "then a parser fix restores the workflow.",
        {"environment": "demo"}, is_demo=True, demo_key=DEMO_KEY,
    )
    runs = RunService(db, settings)
    baseline = _record(runs, project["project_id"], "1.0", now - timedelta(days=2, hours=3))
    failed = _record(runs, project["project_id"], "1.1", now - timedelta(days=1, hours=2))
    fixed = _record(runs, project["project_id"], "1.2", now - timedelta(hours=1))
    analysis = AnalysisService(db, settings)
    result = analysis.analyze(failed["run_id"], baseline["run_id"])
    verified = []
    for finding in result["findings"]:
        if finding["category"] == "invalid_json":
            verified.append(analysis.verify(finding["finding_id"], fixed["run_id"]))
    return {
        "created": True,
        "project_id": project["project_id"],
        "runs": {"baseline": baseline["run_id"], "failed": failed["run_id"], "fixed": fixed["run_id"]},
        "findings": len(result["findings"]),
        "verified": [v["finding_id"] for v in verified if v["verification_status"] == "verified"],
        "earliest_divergence": (result["comparison_summary"] or {}).get("earliest_divergence"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed RunTrace demo data (idempotent).")
    parser.add_argument("--reset", action="store_true", help="Delete existing demo records first (only is_demo data).")
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    client = create_client(settings)
    state = DatabaseState(client[settings.mongodb_db])
    if not state.check(force=True):
        print(f"ERROR: cannot reach MongoDB ({state.last_error}). Check RUNTRACE_MONGODB_URI.", file=sys.stderr)
        return 2
    db = client[settings.mongodb_db]
    if args.reset:
        print("Removed demo records:", reset_demo(db))
    result = seed_demo(db, settings)
    print(json.dumps(result, indent=2, default=str))
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
