from app.comparison.engine import compare_runs
from app.diagnosis.engine import classify_error, diagnose


def ev(seq, name, status="success", output=None, error=None, run="run_f", event_type="step", inp=None, metadata=None):
    return {"event_id": f"evt_{run}_{seq}", "run_id": run, "sequence": seq, "name": name, "event_type": event_type,
            "status": status, "output_summary": output, "error": error, "metadata": metadata or {},
            "duration_ms": 5.0, "input_summary": inp}


def run(run_id, status):
    return {"run_id": run_id, "project_id": "prj_x", "name": "wf", "status": status, "version": "1", "metadata": {}}


def cats(error):
    return {m["category"] for m in classify_error(error)}


def test_classify_known_errors():
    assert "invalid_json" in cats({"type": "json.decoder.JSONDecodeError", "message": "Expecting value: line 1"})
    assert "missing_module" in cats({"type": "ModuleNotFoundError", "message": "No module named 'pandas'"})
    assert classify_error({"type": "ModuleNotFoundError", "message": "No module named 'pandas'"})[0]["detail"] == "pandas"
    assert "missing_env_var" in cats({"type": "KeyError", "message": "'OPENAI_API_KEY'"})
    assert "missing_env_var" in cats({"type": "RuntimeError", "message": "Environment variable DATABASE_URL is not set"})
    assert "missing_field" in cats({"type": "KeyError", "message": "'answer'"})
    assert "external_timeout" in cats({"type": "httpx.ReadTimeout", "message": "timed out"})
    assert "http_failure" in cats({"type": "HTTPStatusError", "message": "Server error '503 Service Unavailable'"})
    assert "http_failure" in cats({"type": "RuntimeError", "message": "request failed with status code 502"})
    assert "null_output" in cats({"type": "TypeError", "message": "'NoneType' object is not subscriptable"})
    assert cats({"type": "ValueError", "message": "bad value"}) == set()
    assert classify_error(None) == []


def test_unclassified_failure_has_low_confidence():
    drafts = diagnose(run("run_f", "failed"), [ev(1, "step", "failed", error={"type": "ValueError", "message": "bad"})])
    assert drafts[0].category == "step_failure" and drafts[0].confidence == "low"


def test_tool_failure_and_http_status_metadata():
    events = [ev(1, "search_api", "failed", event_type="tool", error={"type": "ValueError", "message": "bad args"},
                 inp={"q": "x"}),
              ev(2, "fetch", "success", metadata={"status_code": 500})]
    categories = {d.category for d in diagnose(run("run_f", "failed"), events)}
    assert {"tool_failure", "http_failure"} <= categories


def test_comparison_based_findings_and_qualified_language():
    base = [ev(1, "config", output={"model": "m1"}, run="run_b", metadata={"model": "m1"}),
            ev(2, "call_llm", output={"answer": "a", "citations": []}, run="run_b"),
            ev(3, "parse", inp='{"answer": "a"}', output={"ok": True}, run="run_b")]
    fail = [ev(1, "config", output={"model": "m2"}, metadata={"model": "m2"}),
            ev(2, "call_llm", output={"text": "```json {}```"}),
            ev(3, "parse", "failed", inp="```json {}```", error={"type": "JSONDecodeError", "message": "Expecting value"})]
    b_run, f_run = run("run_b", "success"), run("run_f", "failed")
    comparison = compare_runs(b_run, base, f_run, fail)
    drafts = diagnose(f_run, fail, b_run, base, comparison)
    by_cat = {d.category: d for d in drafts}
    assert {"invalid_json", "divergence", "schema_change", "missing_field", "config_mismatch"} <= set(by_cat)
    inv = by_cat["invalid_json"]
    assert inv.severity == "high"
    assert any(e["kind"] == "output_difference" and e["step"] == "call_llm" for e in inv.evidence)
    assert "RECORDED_FAILING_INPUT" in inv.regression_test and "your_module" in inv.regression_test
    for d in drafts:
        assert d.observation and d.hypothesis and d.suggested_actions
        assert "root cause is" not in d.hypothesis.lower()
    assert by_cat["divergence"].step == "config"


def test_fingerprint_is_stable():
    d = diagnose(run("run_f", "failed"), [ev(1, "s", "failed", error={"type": "KeyError", "message": "'x'"})])[0]
    assert d.fingerprint("run_f", None) == d.fingerprint("run_f", None)
    assert d.fingerprint("run_f", None) != d.fingerprint("run_f", "run_b")
