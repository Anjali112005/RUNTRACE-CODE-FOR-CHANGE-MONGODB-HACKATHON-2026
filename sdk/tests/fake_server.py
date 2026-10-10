"""In-memory fake of the RunTrace ingestion API, served through httpx.MockTransport.

It mirrors the server's idempotency rules (client_run_key, event_id, idempotent finish) so
SDK retry behaviour can be tested without a network or database.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

import httpx

VALID_KEY = "rt_live_" + "A" * 43


class FakeRunTrace:
    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self.events: dict[str, dict[str, dict[str, Any]]] = {}
        self.requests: list[tuple[str, str, Any]] = []
        self.fail_next: list[Callable[[httpx.Request], Any]] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.requests.append((request.method, request.url.path, body))
        if request.headers.get("authorization") != f"Bearer {VALID_KEY}":
            return httpx.Response(401, json={"error": {"code": "unauthorized", "message": "bad key"}})
        hook = self.fail_next.pop(0) if self.fail_next else None
        if hook is not None:
            result = hook(request)
            if isinstance(result, httpx.Response):
                return result
        path = request.url.path
        if path == "/health":
            return httpx.Response(200, json={"status": "ok", "version": "test", "database": {"connected": True}})
        if path == "/api/keys/verify":
            return httpx.Response(200, json={"project_id": "prj_1", "project_name": "Test", "key_id": "key_1"})
        if path == "/api/runs/start":
            for run in self.runs.values():
                if run["client_run_key"] == body["client_run_key"]:
                    return httpx.Response(200, json=run)
            run_id = f"run_{uuid.uuid4().hex}"
            run = {"run_id": run_id, "status": "running", **body}
            self.runs[run_id] = run
            self.events[run_id] = {}
            return httpx.Response(201, json=run)
        parts = path.strip("/").split("/")
        run_id = parts[2]
        if run_id not in self.runs:
            return httpx.Response(404, json={"error": {"code": "not_found", "message": "no run"}})
        if parts[3] == "events":
            accepted = duplicates = 0
            for ev in body["events"]:
                existing = self.events[run_id].get(ev["event_id"])
                if existing is not None:
                    if existing != ev:
                        return httpx.Response(409, json={"error": {"code": "conflict", "message": "dup"}})
                    duplicates += 1
                    continue
                self.events[run_id][ev["event_id"]] = ev
                accepted += 1
            return httpx.Response(200, json={"run_id": run_id, "accepted": accepted, "duplicates": duplicates, "results": []})
        if parts[3] == "finish":
            run = self.runs[run_id]
            if run["status"] != "running" and run["status"] != body["status"]:
                return httpx.Response(409, json={"error": {"code": "conflict", "message": "finished"}})
            run.update(status=body["status"], finish=body)
            return httpx.Response(200, json=run)
        return httpx.Response(404, json={"error": {"code": "not_found", "message": path}})

    def ordered_events(self, run_id: str) -> list[dict[str, Any]]:
        return sorted(self.events[run_id].values(), key=lambda e: e["sequence"])
