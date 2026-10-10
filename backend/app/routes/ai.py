from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pymongo.database import Database

from ..auth import Principal, get_db, get_settings, require_reader
from ..config import Settings
from ..errors import bad_request
from ..schemas.analysis import AIChatRequest, AIChatResponse, AIStatus
from ..services.ai import AIService
from ..services.analysis import AnalysisService
from ..services.runs import RunService

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _ai(request: Request) -> AIService:
    return request.app.state.ai_service


@router.get("/status", response_model=AIStatus, summary="Whether optional AI assistance is enabled")
def ai_status(request: Request):
    return _ai(request).status()


@router.post("/chat", response_model=AIChatResponse,
             summary="Ask Gemini about a run or finding (answers are labelled AI-generated and never stored)")
def ai_chat(payload: AIChatRequest, request: Request, principal: Principal = Depends(require_reader),
            db: Database = Depends(get_db), settings: Settings = Depends(get_settings)):
    if not payload.run_id and not payload.finding_id:
        raise bad_request("Provide run_id or finding_id so the answer is grounded in recorded data.")
    context: dict[str, Any] = {}
    analysis = AnalysisService(db, settings)
    runs = RunService(db, settings)
    run_id = payload.run_id
    if payload.finding_id:
        finding = analysis.get_finding(payload.finding_id)
        principal.ensure_project(finding["project_id"])
        context["finding"] = {k: finding.get(k) for k in ("category", "severity", "title", "observation", "evidence",
                                                         "hypothesis", "suggested_actions", "verification_status")}
        run_id = run_id or finding["run_id"]
    if run_id:
        run = runs.get(run_id)
        principal.ensure_project(run["project_id"])
        context["run"] = {k: run.get(k) for k in ("run_id", "name", "status", "version", "environment",
                                                 "error_summary", "duration_ms", "metadata")}
        context["events"] = [
            {k: e.get(k) for k in ("sequence", "name", "event_type", "status", "duration_ms", "input_summary",
                                   "output_summary", "error", "metadata")}
            for e in runs.events_for(run_id)[:60]
        ]
    return _ai(request).chat(payload.question, context)