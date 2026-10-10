from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pymongo.database import Database

from ..auth import Principal, get_db, get_settings, require_reader
from ..config import Settings
from ..schemas.analysis import MetricsOut
from ..services.metrics import MetricsService
from ..services.projects import ProjectService
from ..services.runs import RunService

router = APIRouter(prefix="/api", tags=["metrics"])


@router.get("/metrics", response_model=MetricsOut, summary="Metrics across all projects, or one project")
def metrics(
    project_id: Optional[str] = Query(default=None, max_length=40),
    days: int = Query(default=30, ge=1, le=365),
    include_demo: bool = True,
    principal: Principal = Depends(require_reader),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not principal.is_admin:
        project_id = principal.project_id
    if project_id:
        ProjectService(db, settings).get(project_id)
    RunService(db, settings).sweep_stale()
    return MetricsService(db, settings).compute(project_id, days, include_demo)


@router.get("/projects/{project_id}/metrics", response_model=MetricsOut, summary="Metrics for one project")
def project_metrics(
    project_id: str,
    days: int = Query(default=30, ge=1, le=365),
    principal: Principal = Depends(require_reader),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    principal.ensure_project(project_id)
    ProjectService(db, settings).get(project_id)
    RunService(db, settings).sweep_stale()
    return MetricsService(db, settings).compute(project_id, days, True)
