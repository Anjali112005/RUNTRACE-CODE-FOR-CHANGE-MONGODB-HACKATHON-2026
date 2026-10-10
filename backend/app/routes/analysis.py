from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pymongo.database import Database

from ..auth import Principal, get_db, get_settings, require_reader
from ..config import Settings
from ..schemas.analysis import CompareRequest, FindingList, FindingOut, VerifyRequest
from ..services.analysis import AnalysisService
from ..services.runs import RunService

router = APIRouter(prefix="/api", tags=["comparison", "findings"])


@router.post("/compare", summary="Compare a baseline run with a comparison run")
def compare(payload: CompareRequest, principal: Principal = Depends(require_reader),
            db: Database = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    runs = RunService(db, settings)
    for run_id in (payload.baseline_run_id, payload.comparison_run_id):
        principal.ensure_project(runs.get(run_id)["project_id"])
    return AnalysisService(db, settings).compare(payload.baseline_run_id, payload.comparison_run_id,
                                                 payload.include_diagnosis)


@router.get("/findings", response_model=FindingList, summary="Search findings")
def list_findings(
    project_id: Optional[str] = Query(default=None, max_length=40),
    run_id: Optional[str] = Query(default=None, max_length=40),
    severity: Optional[str] = Query(default=None, pattern="^(high|medium|low)$"),
    category: Optional[str] = Query(default=None, max_length=40),
    verification_status: Optional[str] = Query(default=None, pattern="^(unverified|verified|not_improved|inconclusive)$"),
    q: Optional[str] = Query(default=None, max_length=100),
    include_demo: bool = True,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    principal: Principal = Depends(require_reader),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not principal.is_admin:
        project_id = principal.project_id
    return AnalysisService(db, settings).list_findings(
        page=page, page_size=page_size, project_id=project_id, run_id=run_id, severity=severity,
        category=category, verification_status=verification_status, q=q, include_demo=include_demo)


@router.get("/findings/{finding_id}", response_model=FindingOut, summary="Finding detail")
def get_finding(finding_id: str, principal: Principal = Depends(require_reader),
                db: Database = Depends(get_db), settings: Settings = Depends(get_settings)):
    finding = AnalysisService(db, settings).get_finding(finding_id)
    principal.ensure_project(finding["project_id"])
    return finding


@router.post("/findings/{finding_id}/verify", response_model=FindingOut,
             summary="Check a corrected run against a finding's failure")
def verify_finding(finding_id: str, payload: VerifyRequest, principal: Principal = Depends(require_reader),
                   db: Database = Depends(get_db), settings: Settings = Depends(get_settings)):
    svc = AnalysisService(db, settings)
    principal.ensure_project(svc.get_finding(finding_id)["project_id"])
    return svc.verify(finding_id, payload.run_id)
