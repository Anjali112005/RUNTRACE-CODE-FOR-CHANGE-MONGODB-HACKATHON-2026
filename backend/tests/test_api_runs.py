import uuid

import pytest

from conftest import auth, evt, make_settings

pytest.importorskip("fastapi")
pytest.importorskip("mongomock")


def start(client, key, **body):
    return client.post("/api/runs/start", json={"name": "wf", **body}, headers=auth(key))


def test_ingestion_requires_key(client):
    assert client.post("/api/runs/start", json={"name": "wf"}).status_code == 401


def test_run_lifecycle(client, project):
    key = project["key"]["api_key"]
    r = start(client, key, version="1.2", environment="dev", metadata={"model": "m"})
    assert r.status_code == 201
    run = r.json()
    assert run["status"] == "running" and run["finished_at"] is None and run["duration_ms"] is None
    assert run["started_at"].endswith("Z")
    run_id = run["run_id"]

    events = [evt(1, "load"), evt(2, "call", output_summary={"a": 1}, duration_ms=12.5),
              evt(3, "parse", "failed", error={"type": "ValueError", "message": "boom"})]
    ing = client.post(f"/api/runs/{run_id}/events", json={"events": events}, headers=auth(key))
    assert ing.status_code == 200 and ing.json()["accepted"] == 3

    fin = client.post(f"/api/runs/{run_id}/finish", json={"status": "failed"}, headers=auth(key))
    assert fin.status_code == 200
    body = fin.json()
    assert body["status"] == "failed"
    assert body["finished_at"] is not None and body["duration_ms"] is not None
    assert "parse: ValueError: boom" in body["error_summary"]
    assert body["event_count"] == 3 and body["failed_event_count"] == 1

    # Idempotent finish; conflicting finish rejected.
    assert client.post(f"/api/runs/{run_id}/finish", json={"status": "failed"}, headers=auth(key)).status_code == 200
    assert client.post(f"/api/runs/{run_id}/finish", json={"status": "success"}, headers=auth(key)).status_code == 409

    listed = client.get(f"/api/runs/{run_id}/events").json()
    assert [e["sequence"] for e in listed["items"]] == [1, 2, 3]
    assert client.get("/api/runs", params={"status": "failed"}).json()["meta"]["total"] == 1


def test_start_is_idempotent_with_client_run_key(client, project):
    key = project["key"]["api_key"]
    ck = uuid.uuid4().hex
    first = start(client, key, client_run_key=ck)
    second = start(client, key, client_run_key=ck)
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["run_id"] == second.json()["run_id"]


def test_duplicate_events_are_idempotent_and_conflicts_rejected(client, project):
    key = project["key"]["api_key"]
    run_id = start(client, key).json()["run_id"]
    eid = "evt_" + uuid.uuid4().hex
    payload = {"events": [evt(1, "a", event_id=eid, output_summary={"x": 1})]}
    assert client.post(f"/api/runs/{run_id}/events", json=payload, headers=auth(key)).json()["accepted"] == 1
    retry = client.post(f"/api/runs/{run_id}/events", json=payload, headers=auth(key))
    assert retry.status_code == 200 and retry.json()["duplicates"] == 1 and retry.json()["accepted"] == 0

    changed = {"events": [evt(1, "a", event_id=eid, output_summary={"x": 2})]}
    conflict = client.post(f"/api/runs/{run_id}/events", json=changed, headers=auth(key))
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "conflict"

    other_id = {"events": [evt(1, "b", event_id="evt_" + uuid.uuid4().hex)]}
    assert client.post(f"/api/runs/{run_id}/events", json=other_id, headers=auth(key)).status_code == 409
    assert client.get(f"/api/runs/{run_id}").json()["event_count"] == 1


def test_events_after_finish_rejected_but_retries_ok(client, project):
    key = project["key"]["api_key"]
    run_id = start(client, key).json()["run_id"]
    payload = {"events": [evt(1, "a", event_id="evt_" + uuid.uuid4().hex)]}
    client.post(f"/api/runs/{run_id}/events", json=payload, headers=auth(key))
    client.post(f"/api/runs/{run_id}/finish", json={"status": "success"}, headers=auth(key))
    assert client.post(f"/api/runs/{run_id}/events", json=payload, headers=auth(key)).status_code == 200
    late = {"events": [evt(2, "b")]}
    assert client.post(f"/api/runs/{run_id}/events", json=late, headers=auth(key)).status_code == 409


def test_secrets_are_redacted_on_ingest(client, project, mongo_db):
    key = project["key"]["api_key"]
    run_id = start(client, key, metadata={"api_key": "sk-abcdefghijklmnopqrstuvwxyz"}).json()["run_id"]
    events = [evt(1, "call", metadata={"authorization": "Bearer abcdefghijklmnop", "max_tokens": 100},
                  input_summary={"prompt": f"use key {key}"})]
    client.post(f"/api/runs/{run_id}/events", json={"events": events}, headers=auth(key))
    raw = str(list(mongo_db["events"].find({}))) + str(list(mongo_db["runs"].find({})))
    assert key not in raw and "abcdefghijklmnop" not in raw and "sk-abcdefghij" not in raw
    stored = client.get(f"/api/runs/{run_id}/events").json()["items"][0]
    assert stored["metadata"]["max_tokens"] == 100


def test_invalid_requests(client, project):
    key = project["key"]["api_key"]
    run_id = start(client, key).json()["run_id"]
    bad = [
        {"events": []},
        {"events": [{"sequence": -1, "name": "a"}]},
        {"events": [{"sequence": 1, "name": "a", "status": "weird"}]},
        {"events": [{"sequence": 1, "name": "a", "event_id": "not-an-id"}]},
    ]
    for body in bad:
        r = client.post(f"/api/runs/{run_id}/events", json=body, headers=auth(key))
        assert r.status_code == 422, body
        assert "input" not in r.json()["error"]["details"][0]  # submitted values are never echoed
    assert client.post("/api/runs/run_" + "0" * 32 + "/events", json={"events": [evt(1, "a")]},
                       headers=auth(key)).status_code == 404
    assert client.post(f"/api/runs/{run_id}/finish", json={"status": "running"}, headers=auth(key)).status_code == 422


def test_payload_limits(client_factory, project):
    c = client_factory(make_settings(max_request_bytes=2048, max_events_per_batch=2))
    created = c.post("/api/projects", json={"name": "Limits"}).json()
    key = created["key"]["api_key"]
    run_id = c.post("/api/runs/start", json={"name": "wf"}, headers=auth(key)).json()["run_id"]
    big = {"events": [evt(1, "a", output_summary="x" * 5000)]}
    r = c.post(f"/api/runs/{run_id}/events", json=big, headers=auth(key))
    assert r.status_code == 413
    many = {"events": [evt(i, f"s{i}") for i in range(1, 4)]}
    assert c.post(f"/api/runs/{run_id}/events", json=many, headers=auth(key)).status_code == 413


def test_stale_runs_are_marked_timed_out(client, project, mongo_db):
    from datetime import datetime, timedelta, timezone

    from app.services.runs import RunService

    key = project["key"]["api_key"]
    run_id = start(client, key).json()["run_id"]
    mongo_db["runs"].update_one({"run_id": run_id},
                                {"$set": {"started_at": datetime.now(timezone.utc) - timedelta(hours=5)}})
    RunService(mongo_db, make_settings()).sweep_stale(force=True)
    run = client.get(f"/api/runs/{run_id}").json()
    assert run["status"] == "timed_out" and run["duration_ms"] is None
    # A late finish still records the real outcome.
    assert client.post(f"/api/runs/{run_id}/finish", json={"status": "success"}, headers=auth(key)).json()["status"] == "success"
