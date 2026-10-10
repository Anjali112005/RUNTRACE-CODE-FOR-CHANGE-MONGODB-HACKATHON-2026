from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from pymongo.database import Database

from ..auth import Principal, get_db, get_settings, require_admin, require_project_key, require_reader
from ..config import Settings
from ..schemas.projects import (KeyIssued, KeyOut, KeyRevokeRequest, KeyRevokeResult, KeyRotateRequest,
                                KeyVerifyOut, ProjectCreate, ProjectCreated, ProjectDetail, ProjectList, ProjectOut,
                                ProjectUpdate, VersionCreate, VersionOut)
from ..schemas.runs import RunList
from ..services.projects import ProjectService
from ..services.runs import RunService

router = APIRouter(prefix="/api", tags=["projects"])


def _svc(db: Database, settings: Settings) -> ProjectService:
    return ProjectService(db, settings)


@router.get("/projects", response_model=ProjectList, summary="List projects")
def list_projects(
    q: Optional[str] = Query(default=None, max_length=100),
    include_demo: bool = True,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    _: Principal = Depends(require_admin),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return _svc(db, settings).list(q, include_demo, page, page_size)


@router.post("/projects", response_model=ProjectCreated, status_code=201,
             summary="Create a project and its first API key (shown once)")
def create_project(payload: ProjectCreate, _: Principal = Depends(require_admin),
                   db: Database = Depends(get_db), settings: Settings = Depends(get_settings)):
    project, key = _svc(db, settings).create(payload.name, payload.description,
                                             payload.settings.model_dump(exclude_none=True))
    project["stats"] = {"total_runs": 0, "success_runs": 0, "failed_runs": 0, "last_run_at": None}
    return {"project": project, "key": key}


@router.get("/projects/{project_id}", response_model=ProjectDetail, summary="Project detail with keys and versions")
def get_project(project_id: str, principal: Principal = Depends(require_reader),
                db: Database = Depends(get_db), settings: Settings = Depends(get_settings)):
    principal.ensure_project(project_id)
    return _svc(db, settings).detail(project_id)


@router.patch("/projects/{project_id}", response_model=ProjectOut, summary="Update a project")
def update_project(project_id: str, payload: ProjectUpdate, _: Principal = Depends(require_admin),
                   db: Database = Depends(get_db), settings: Settings = Depends(get_settings)):
    changes = payload.model_dump(exclude_unset=True)
    if payload.settings is not None:
        changes["settings"] = payload.settings.model_dump(exclude_none=True)
    return _svc(db, settings).update(project_id, changes)


@router.get("/projects/{project_id}/keys", response_model=list[KeyOut], summary="List key metadata (never the keys)")
def list_keys(project_id: str, _: Principal = Depends(require_admin),
              db: Database = Depends(get_db), settings: Settings = Depends(get_settings)):
    return _svc(db, settings).detail(project_id)["keys"]


@router.post("/projects/{project_id}/keys/rotate", response_model=KeyIssued, status_code=201,
             summary="Issue a new key (optionally revoking existing ones)")
def rotate_key(project_id: str, payload: Optional[KeyRotateRequest] = None, _: Principal = Depends(require_admin),
               db: Database = Depends(get_db), settings: Settings = Depends(get_settings)):
    revoke_existing = payload.revoke_existing if payload else True
    return _svc(db, settings).rotate_key(project_id, revoke_existing)


@router.post("/projects/{project_id}/keys/revoke", response_model=KeyRevokeResult,
             summary="Revoke one key, or all active keys")
def revoke_keys(project_id: str, payload: Optional[KeyRevokeRequest] = None, _: Principal = Depends(require_admin),
                db: Database = Depends(get_db), settings: Settings = Depends(get_settings)):
    return {"revoked": _svc(db, settings).revoke_keys(project_id, payload.key_id if payload else None)}


@router.post("/projects/{project_id}/versions", response_model=VersionOut, status_code=201,
             summary="Register a version label (returns the existing one if it already exists)")
def create_version(project_id: str, payload: VersionCreate, response: Response,
                   principal: Principal = Depends(require_reader),
                   db: Database = Depends(get_db), settings: Settings = Depends(get_settings)):
    principal.ensure_project(project_id)
    version, created = _svc(db, settings).create_version(project_id, payload.version, payload.metadata)
    if not created:
        response.status_code = 200
    return version


@router.get("/projects/{project_id}/versions", response_model=list[VersionOut], summary="Version history")
def list_versions(project_id: str, principal: Principal = Depends(require_reader),
                  db: Database = Depends(get_db), settings: Settings = Depends(get_settings)):
    principal.ensure_project(project_id)
    return _svc(db, settings).detail(project_id)["versions"]


@router.get("/projects/{project_id}/runs", response_model=RunList, summary="Runs of one project")
def project_runs(
    project_id: str,
    status: Optional[str] = Query(default=None, pattern="^(running|success|failed|timed_out)$"),
    q: Optional[str] = Query(default=None, max_length=100),
    version: Optional[str] = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    principal: Principal = Depends(require_reader),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    principal.ensure_project(project_id)
    _svc(db, settings).get(project_id)
    return RunService(db, settings).list(project_id=project_id, status=status, q=q, include_demo=True,
                                         version=version, page=page, page_size=page_size)


@router.get("/keys/verify", response_model=KeyVerifyOut, tags=["keys"],
            summary="Check that a project API key is valid (used by the SDK CLI)")
def verify_key(principal: Principal = Depends(require_project_key),
               db: Database = Depends(get_db), settings: Settings = Depends(get_settings)):
    project = _svc(db, settings).get(principal.project_id or "")
    return {"project_id": project["project_id"], "project_name": project["name"], "key_id": principal.key_id}
