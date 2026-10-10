import time

import pytest

from conftest import auth, evt, make_settings, record_run

pytest.importorskip("fastapi")
pytest.importorskip("mongomock")
httpx = pytest.importorskip("httpx")

GOOD = '{"answer": "hi", "citations": ["kb-1"]}'
BAD = '```json\n{"answer": "hi"}\n```'


def scenario(client, key):
    baseline = record_run(client, key, "support", [
        evt(1, "load_config", output_summary={"prompt_version": "v1"}),
        evt(2, "call_llm", event_type="llm", output_summary={"text": GOOD}),
        evt(3, "parse_response", input_summary=GOOD, output_summary={"answer": "hi"}),
    ], "success", version="1.0")
    time.sleep(0.01)  # distinct start timestamps (millisecond precision) for baseline auto-selection
    failed = record_run(client, key, "support", [
        evt(1, "load_config", output_summary={"prompt_version": "v1"}),
        evt(2, "call_llm", event_type="llm", output_summary={"text": BAD}),
        evt(3, "parse_response", "failed", input_summary=BAD,
            error={"type": "json.decoder.JSONDecodeError", "message": "Expecting value: line 1 column 1 (char 0)"}),
    ], "failed", version="1.1")
    time.sleep(0.01)
    fixed = record_run(client, key, "support", [
        evt(1, "load_config", output_summary={"prompt_version": "v1"}),
        evt(2, "call_llm", event_type="llm", output_summary={"text": BAD}),
        evt(3, "parse_response", input_summary=BAD, output_summary={"answer": "hi"}),
    ], "success", version="1.2")
    return baseline, failed, fixed


def test_compare_reports_earliest_divergence(client, project):
    baseline, failed, _ = scenario(client, project["key"]["api_key"])
    r = client.post("/api/compare", json={"baseline_run_id": baseline, "comparison_run_id": failed})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["earliest_divergence"]["name"] == "call_llm"
    assert body["summary"]["unchanged"] == 1
    assert body["first_failure"]["name"] == "parse_response"
    cats = {f["category"] for f in body["diagnosis"]["findings"]}
    assert "invalid_json" in cats and body["diagnosis"]["persisted"] is False
    assert client.post("/api/compare", json={"baseline_run_id": baseline, "comparison_run_id": baseline}).status_code == 400
    missing = "run_" + "f" * 32
    assert client.post("/api/compare", json={"baseline_run_id": baseline, "comparison_run_id": missing}).status_code == 404


def test_analyze_is_idempotent_and_verify_loop(client, project):
    baseline, failed, fixed = scenario(client, project["key"]["api_key"])
    first = client.post(f"/api/runs/{failed}/analyze", json={}).json()
    assert first["baseline_run_id"] == baseline
    assert first["baseline_selection"] == "latest_successful_same_name"
    second = client.post(f"/api/runs/{failed}/analyze", json={}).json()
    assert {f["finding_id"] for f in first["findings"]} == {f["finding_id"] for f in second["findings"]}

    invalid = next(f for f in first["findings"] if f["category"] == "invalid_json")
    assert invalid["severity"] == "high"
    assert invalid["verification_status"] == "unverified"
    assert invalid["observation"] and invalid["hypothesis"] and invalid["evidence"]
    assert "your_module" in invalid["regression_test"]

    # Verifying with the failing run itself is rejected; with another failing run is not_improved.
    assert client.post(f"/api/findings/{invalid['finding_id']}/verify", json={"run_id": failed}).status_code == 400
    still_bad = record_run(client, project["key"]["api_key"], "support", [
        evt(1, "parse_response", "failed", error={"type": "JSONDecodeError", "message": "Expecting value"})], "failed")
    nr = client.post(f"/api/findings/{invalid['finding_id']}/verify", json={"run_id": still_bad}).json()
    assert nr["verification_status"] == "not_improved"

    ok = client.post(f"/api/findings/{invalid['finding_id']}/verify", json={"run_id": fixed}).json()
    assert ok["verification_status"] == "verified"
    assert all(c["passed"] for c in ok["verification"]["checks"])
    assert "does not prove" in ok["verification"]["note"]

    listed = client.get("/api/findings", params={"verification_status": "verified"}).json()
    assert [f["finding_id"] for f in listed["items"]] == [invalid["finding_id"]]
    assert client.get(f"/api/runs/{failed}/findings").status_code == 200


def test_metrics_reflect_records(client, project):
    pid = project["project"]["project_id"]
    scenario(client, project["key"]["api_key"])
    m = client.get(f"/api/projects/{pid}/metrics").json()
    assert m["totals"]["runs"] == 3 and m["totals"]["success"] == 2 and m["totals"]["failed"] == 1
    assert m["success_rate"] == pytest.approx(2 / 3, abs=1e-3)
    assert {v["version"]: v["failed"] for v in m["by_version"]} == {"1.0": 0, "1.1": 1, "1.2": 0}
    assert sum(day["total"] for day in m["activity"]) == 3
    assert client.get("/api/metrics").json()["totals"]["projects"] == 1


def test_project_key_metrics_are_scoped(client, project):
    other = client.post("/api/projects", json={"name": "Other"}).json()
    record_run(client, other["key"]["api_key"], "x", [], "success")
    scenario(client, project["key"]["api_key"])
    m = client.get("/api/metrics", headers=auth(project["key"]["api_key"])).json()
    assert m["scope"]["project_id"] == project["project"]["project_id"] and m["totals"]["runs"] == 3


def test_ai_disabled_by_default(client, project):
    assert client.get("/api/ai/status").json()["enabled"] is False
    baseline, _, _ = scenario(client, project["key"]["api_key"])
    r = client.post("/api/ai/chat", json={"question": "why?", "run_id": baseline})
    assert r.status_code == 503 and r.json()["error"]["code"] == "ai_disabled"


def test_ai_enabled_with_mock_transport(client_factory):
    from app.services.ai import AIService

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["key"] = request.headers.get("x-goog-api-key")
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "Hypothesis: fences."}]}}]})

    settings = make_settings(gemini_api_key="test-gemini-key")
    c = client_factory(settings, ai_service=AIService(settings, transport=httpx.MockTransport(handler)))
    created = c.post("/api/projects", json={"name": "AI"}).json()
    run_id = record_run(c, created["key"]["api_key"], "wf", [evt(1, "a")], "success")
    r = c.post("/api/ai/chat", json={"question": "summarise", "run_id": run_id})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "ai_generated" and body["answer"] == "Hypothesis: fences."
    assert seen["key"] == "test-gemini-key"
    assert "test-gemini-key" not in r.text
    events = c.get(f"/api/runs/{run_id}/events").json()["items"]
    assert len(events) == 1  # raw events untouched


def test_demo_seed_is_idempotent(mongo_db):
    from app.seed_demo import reset_demo, seed_demo

    settings = make_settings()
    first = seed_demo(mongo_db, settings)
    assert first["created"] is True and first["verified"]
    assert first["earliest_divergence"]["name"] == "load_config"
    assert seed_demo(mongo_db, settings)["created"] is False
    assert mongo_db["runs"].count_documents({"is_demo": True}) == 3
    assert mongo_db["runs"].count_documents({"is_demo": {"$ne": True}}) == 0
    reset_demo(mongo_db)
    assert mongo_db["runs"].count_documents({}) == 0
