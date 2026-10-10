"""Request authentication and authorization (FastAPI dependencies).

Two kinds of callers exist:

* **Project callers** present a project API key (``Authorization: Bearer rt_live_…`` or
  ``X-RunTrace-Key``). They can ingest data and read data for their own project only.
* **Admin (dashboard) callers**. If ``RUNTRACE_ADMIN_TOKEN`` is set they must send it in
  ``X-RunTrace-Admin-Token``; if it is not set the server runs in *open* mode, intended
  for a single developer on localhost, and management endpoints need no token.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import Depends, Request
from pymongo.database import Database

from .config import Settings
from .errors import db_unavailable, forbidden, too_many_requests, unauthorized
from .security import SlidingWindowLimiter, constant_time_equals, looks_like_api_key
from .services.projects import ProjectService


@dataclass(frozen=True)
class Principal:
    kind: Literal["admin", "project"]
    project_id: str | None = None
    key_id: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.kind == "admin"

    def ensure_project(self, project_id: str) -> None:
        if self.kind == "project" and project_id != self.project_id:
            raise forbidden("This API key does not have access to that project.")


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Database:
    state = request.app.state.db_state
    if not state.check():
        raise db_unavailable(state.last_error)
    return state.db


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _limit(request: Request, limiter_name: str, key: str) -> None:
    limiter: SlidingWindowLimiter = getattr(request.app.state, limiter_name)
    allowed, retry = limiter.check(key)
    if not allowed:
        raise too_many_requests(retry)


def _extract_api_key(request: Request) -> str | None:
    header = request.headers.get("x-runtrace-key")
    if header:
        return header.strip()
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def _project_principal(request: Request, db: Database, api_key: str) -> Principal:
    if not looks_like_api_key(api_key):
        raise unauthorized("Invalid API key format.")
    record = ProjectService(db, request.app.state.settings).authenticate_key(api_key)
    if record is None:
        raise unauthorized("Invalid or revoked API key.")
    return Principal("project", record["project_id"], record["key_id"])


def _admin_principal(request: Request) -> Principal:
    settings: Settings = request.app.state.settings
    if settings.admin_token:
        supplied = request.headers.get("x-runtrace-admin-token", "")
        if not supplied or not constant_time_equals(supplied, settings.admin_token):
            raise unauthorized("This endpoint requires the X-RunTrace-Admin-Token header.")
    return Principal("admin")


def require_project_key(request: Request, db: Database = Depends(get_db)) -> Principal:
    api_key = _extract_api_key(request)
    if not api_key:
        raise unauthorized("A project API key is required (Authorization: Bearer rt_live_…).")
    principal = _project_principal(request, db, api_key)
    _limit(request, "ingest_limiter", principal.key_id or "key")
    return principal


def require_admin(request: Request) -> Principal:
    _limit(request, "api_limiter", _client_ip(request))
    return _admin_principal(request)


def require_reader(request: Request, db: Database = Depends(get_db)) -> Principal:
    """Admin, or a project key scoped to its own project."""
    api_key = _extract_api_key(request)
    if api_key:
        principal = _project_principal(request, db, api_key)
        _limit(request, "ingest_limiter", principal.key_id or "key")
        return principal
    return require_admin(request)
