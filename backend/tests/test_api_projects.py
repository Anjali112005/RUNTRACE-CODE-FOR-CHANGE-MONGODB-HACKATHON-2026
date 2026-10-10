import pytest

from conftest import auth, make_settings, record_run

pytest.importorskip("fastapi")
pytest.importorskip("mongomock")


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["database"]["connected"] is True
    assert body["auth_mode"] == "open"
    assert body["ai"]["enabled"] is False


def test_create_project_returns_key_once_and_stores_only_hash(client, mongo_db):
    r = client.post("/api/projects", json={"name": "  Support Bot ", "description": "x",
                                           "settings": {"environment": "dev"}})
    assert r.status_code == 201, r.text
    body = r.json()
    key = body["key"]["api_key"]
    assert key.startswith("rt_live_")
    assert body["project"]["name"] == "Support Bot"
    assert body["project"]["project_id"].startswith("prj_")
    stored = list(mongo_db["project_keys"].find({}))
    assert len(stored) == 1
    assert key not in str(stored)
    assert stored[0]["key_hash"] != key
    detail = client.get(f"/api/projects/{body['project']['project_id']}").json()
    assert "api_key" not in str(detail)
    assert detail["keys"][0]["active"] is True


def test_project_validation(client):
    assert client.post("/api/projects", json={"name": ""}).status_code == 422
    assert client.post("/api/projects", json={"name": "   "}).status_code == 422
    assert client.post("/api/projects", json={"name": "ok", "unknown": 1}).status_code == 422


def test_list_search_and_update(client, project):
    pid = project["project"]["project_id"]
    client.post("/api/projects", json={"name": "Other"})
    found = client.get("/api/projects", params={"q": "test proj"}).json()
    assert [p["project_id"] for p in found["items"]] == [pid]
    assert found["meta"]["total"] == 1
    r = client.patch(f"/api/projects/{pid}", json={"description": "updated"})
    assert r.status_code == 200 and r.json()["description"] == "updated"
    assert client.patch(f"/api/projects/{pid}", json={}).status_code == 400
    assert client.get("/api/projects/prj_missing").status_code == 404


def test_key_validation_rotation_and_revocation(client, project):
    pid = project["project"]["project_id"]
    old_key = project["key"]["api_key"]
    assert client.get("/api/keys/verify", headers=auth(old_key)).json()["project_id"] == pid
    assert client.get("/api/keys/verify").status_code == 401
    assert client.get("/api/keys/verify", headers=auth("rt_live_" + "x" * 43)).status_code == 401
    assert client.get("/api/keys/verify", headers=auth("not-a-key")).status_code == 401

    rotated = client.post(f"/api/projects/{pid}/keys/rotate", json={"revoke_existing": True})
    assert rotated.status_code == 201
    new_key = rotated.json()["api_key"]
    assert client.get("/api/keys/verify", headers=auth(old_key)).status_code == 401
    assert client.get("/api/keys/verify", headers={"X-RunTrace-Key": new_key}).status_code == 200

    revoked = client.post(f"/api/projects/{pid}/keys/revoke", json={}).json()["revoked"]
    assert rotated.json()["key_id"] in revoked
    assert client.get("/api/keys/verify", headers=auth(new_key)).status_code == 401
    assert client.post(f"/api/projects/{pid}/keys/revoke", json={"key_id": rotated.json()["key_id"]}).status_code == 409


def test_project_key_cannot_read_other_projects(client, project):
    other = client.post("/api/projects", json={"name": "Other"}).json()
    other_run = record_run(client, other["key"]["api_key"], "wf", [{"sequence": 1, "name": "a"}], "success")
    key = project["key"]["api_key"]
    assert client.get(f"/api/runs/{other_run}", headers=auth(key)).status_code == 403
    assert client.get(f"/api/projects/{other['project']['project_id']}", headers=auth(key)).status_code == 403
    assert client.post(f"/api/runs/{other_run}/events", json={"events": [{"sequence": 2, "name": "b"}]},
                       headers=auth(key)).status_code == 403
    # Admin-only listing is not reachable by changing nothing but the key in admin-token mode (see below).


def test_admin_token_mode(client_factory):
    c = client_factory(make_settings(admin_token="s3cret-admin-token"))
    assert c.get("/health").json()["auth_mode"] == "admin_token"
    assert c.get("/api/projects").status_code == 401
    assert c.get("/api/projects", headers={"X-RunTrace-Admin-Token": "wrong"}).status_code == 401
    ok = c.post("/api/projects", json={"name": "P"}, headers={"X-RunTrace-Admin-Token": "s3cret-admin-token"})
    assert ok.status_code == 201
    key = ok.json()["key"]["api_key"]
    # A project key is not an admin credential.
    assert c.get("/api/projects", headers=auth(key)).status_code == 401


def test_versions(client, project):
    pid = project["project"]["project_id"]
    r = client.post(f"/api/projects/{pid}/versions", json={"version": "1.0.0", "metadata": {"commit": "abc"}})
    assert r.status_code == 201
    again = client.post(f"/api/projects/{pid}/versions", json={"version": "1.0.0"})
    assert again.status_code == 200 and again.json()["version_id"] == r.json()["version_id"]
    assert client.post(f"/api/projects/{pid}/versions", json={"version": "bad version!"}).status_code == 422
    record_run(client, project["key"]["api_key"], "wf", [], "success", version="1.0.0")
    versions = client.get(f"/api/projects/{pid}/versions").json()
    assert versions[0]["run_count"] == 1


def test_database_unavailable_reports_503(client_factory):
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(make_settings(mongodb_uri="mongodb://127.0.0.1:1/?directConnection=true", mongodb_timeout_ms=200))
    with TestClient(app) as c:
        health = c.get("/health").json()
        assert health["status"] == "degraded" and health["database"]["connected"] is False
        r = c.get("/api/projects")
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "database_unavailable"
