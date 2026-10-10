from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from pymongo.database import Database

from ..auth import Principal, get_db, get_settings, require_admin, require_project_key, require_reader
from ..config import Settings
from ..schemas.analysis import AnalyzeRequest, AnalyzeResponse, FindingOut
from ..schemas.runs import EventBatch, EventIngestResponse, EventList, RunFinish, RunList, RunOut, RunStart
from ..services.analysis import AnalysisService
from ..services.runs import RunService

router = APIRouter(prefix="/api", tags=["runs"])


def _owned_run(run_id: str, principal: Principal, svc: RunService) -> dict:
    run = svc.get(run_id)
    principal.ensure_project(run["project_id"])
    return run


# -- ingestion (project API key) -------------------------------------------------

@router.post("/runs/start", response_model=RunOut, status_code=201, tags=["ingestion"],
             summary="Start a run. Retrying with the same client_run_key returns the same run (200).")
def start_run(payload: RunStart, response: Response, principal: Principal = Depends(require_project_key),
              db: Database = Depends(get_db), settings: Settings = Depends(get_settings)):
    run, created = RunService(db, settings).start(principal.project_id or "", payload)
    if not created:
        response.status_code = 200
    return run


@router.post("/runs/{run_id}/events", response_model=EventIngestResponse, tags=["ingestion"],
             summary="Append events. Identical retries are idempotent; conflicting duplicates return 409.")
def ingest_events(run_id: str, payload: EventBatch, principal: Principal = Depends(require_project_key),
                  db: Database = Depends(get_db), settings: Settings = Depends(get_settings)):
    svc = RunService(db, settings)
    run = _owned_run(run_id, principal, svc)
    return svc.ingest(run, payload.events)


@router.post("/runs/{run_id}/finish", response_model=RunOut, tags=["ingestion"],
             summary="Finish a run with status success or failed (idempotent)")
def finish_run(run_id: str, payload: RunFinish, principal: Principal = Depends(require_project_key),
               db: Database = Depends(get_db), settings: Settings = Depends(get_settings)):
    svc = RunService(db, settings)
    run = _owned_run(run_id, principal, svc)
    return svc.finish(run, payload)


# -- reads ----------------------------------------------------------------------

@router.get("/runs", response_model=RunList, summary="List runs across projects (dashboard)")
def list_runs(
    project_id: Optional[str] = Query(default=None, max_length=40),
    status: Optional[str] = Query(default=None, pattern="^(running|success|failed|timed_out)$"),
    q: Optional[str] = Query(default=None, max_length=100),
    version: Optional[str] = Query(default=None, max_length=64),
    include_demo: bool = True,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    _: Principal = Depends(require_admin),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return RunService(db, settings).list(project_id=project_id, status=status, q=q, include_demo=include_demo,
                                         version=version, page=page, page_size=page_size)


@router.get("/runs/{run_id}", response_model=RunOut, summary="Run detail")
def get_run(run_id: str, principal: Principal = Depends(require_reader),
            db: Database = Depends(get_db), settings: Settings = Depends(get_settings)):
    svc = RunService(db, settings)
    svc.sweep_stale()
    run = _owned_run(run_id, principal, svc)
    return svc.with_project_names([run])[0]


@router.get("/runs/{run_id}/events", response_model=EventList, summary="Events of a run in sequence order")
def get_events(run_id: str, principal: Principal = Depends(require_reader),
               db: Database = Depends(get_db), settings: Settings = Depends(get_settings)):
    svc = RunService(db, settings)
    _owned_run(run_id, principal, svc)
    events = svc.events_for(run_id)
    return {"run_id": run_id, "items": events, "total": len(events)}


@router.get("/runs/{run_id}/findings", response_model=list[FindingOut], tags=["findings"],
            summary="Stored findings for a run")
def run_findings(run_id: str, principal: Principal = Depends(require_reader),
                 db: Database = Depends(get_db), settings: Settings = Depends(get_settings)):
    _owned_run(run_id, principal, RunService(db, settings))
    return AnalysisService(db, settings).findings.list_for_run(run_id)


@router.post("/runs/{run_id}/analyze", response_model=AnalyzeResponse, tags=["findings"],
             summary="Run deterministic diagnosis and store findings (idempotent per run+baseline)")
def analyze_run(run_id: str, payload: Optional[AnalyzeRequest] = None, principal: Principal = Depends(require_reader),
                db: Database = Depends(get_db), settings: Settings = Depends(get_settings)):
    _owned_run(run_id, principal, RunService(db, settings))
    baseline_id = payload.baseline_run_id if payload else None
    if baseline_id:
        _owned_run(baseline_id, principal, RunService(db, settings))
    return AnalysisService(db, settings).analyze(run_id, baseline_id)
