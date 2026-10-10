"""Shared fixtures.

API tests use mongomock (an in-memory MongoDB implementation), so they never touch a
developer's real database. They are skipped - and reported as skipped, not passed - if
fastapi or mongomock is not installed (pip install -r requirements-dev.txt).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterator

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings  # noqa: E402


def make_settings(**overrides: Any) -> Settings:
    base = Settings(mongodb_uri="mongodb://unused", mongodb_db="runtrace_test", log_level="WARNING")
    return base.with_overrides(**overrides)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def mongo_db():
    mongomock = pytest.importorskip("mongomock")
    client = mongomock.MongoClient(tz_aware=True)
    return client["runtrace_test"]


@pytest.fixture
def client_factory(mongo_db):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.main import create_app

    clients: list[Any] = []

    def factory(settings: Settings | None = None, ai_service: Any = None) -> Any:
        app = create_app(settings or make_settings(), db=mongo_db, ai_service=ai_service)
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield factory
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(client_factory) -> Iterator[Any]:
    yield client_factory()


@pytest.fixture
def project(client) -> dict[str, Any]:
    response = client.post("/api/projects", json={"name": "Test Project", "description": "for tests"})
    assert response.status_code == 201, response.text
    return response.json()


def auth(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def evt(seq: int, name: str, status: str = "success", **extra: Any) -> dict[str, Any]:
    return {"sequence": seq, "name": name, "status": status, **extra}


def record_run(client, api_key: str, name: str, events: list[dict[str, Any]], status: str,
               version: str | None = None) -> str:
    start = client.post("/api/runs/start", json={"name": name, **({"version": version} if version else {})},
                        headers=auth(api_key))
    assert start.status_code == 201, start.text
    run_id = start.json()["run_id"]
    if events:
        r = client.post(f"/api/runs/{run_id}/events", json={"events": events}, headers=auth(api_key))
        assert r.status_code == 200, r.text
    r = client.post(f"/api/runs/{run_id}/finish", json={"status": status}, headers=auth(api_key))
    assert r.status_code == 200, r.text
    return run_id
