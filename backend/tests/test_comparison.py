from app.comparison.engine import align_events, compare_runs, diff_values


def ev(seq, name, status="success", output=None, error=None, metadata=None, duration=None, run="run_b"):
    return {"event_id": f"evt_{run}_{seq}", "run_id": run, "sequence": seq, "name": name, "event_type": "step",
            "status": status, "output_summary": output, "error": error, "metadata": metadata or {},
            "duration_ms": duration, "input_summary": None}


def run(run_id, status="success", version="1"):
    return {"run_id": run_id, "project_id": "prj_x", "name": "wf", "status": status, "version": version,
            "metadata": {}}


def test_diff_values_kinds():
    changes = diff_values({"a": 1, "b": {"c": 2}, "d": "x"}, {"a": 1, "b": {"c": 3}, "e": 1, "d": 5})
    kinds = {(c["path"], c["kind"]) for c in changes}
    assert ("$.b.c", "value_changed") in kinds
    assert ("$.e", "key_added") in kinds
    assert ("$.d", "type_changed") in kinds
    assert diff_values([1, 2], [1, 2, 3])[0]["kind"] == "length_changed"
    assert diff_values(None, None) == []


def test_identical_runs_have_no_divergence():
    a = [ev(1, "load"), ev(2, "call", output={"x": 1})]
    b = [ev(1, "load", run="run_c"), ev(2, "call", output={"x": 1}, run="run_c")]
    result = compare_runs(run("run_b"), a, run("run_c"), b)
    assert result["earliest_divergence"] is None
    assert result["summary"]["unchanged"] == 2


def test_earliest_divergence_is_first_changed_step():
    base = [ev(1, "load"), ev(2, "call_llm", output={"answer": "hi"}), ev(3, "parse", output={"ok": True})]
    cmp_ = [ev(1, "load", run="run_c"), ev(2, "call_llm", output="```json {}```", run="run_c"),
            ev(3, "parse", status="failed", error={"type": "JSONDecodeError", "message": "Expecting value"}, run="run_c")]
    result = compare_runs(run("run_b"), base, run("run_c", "failed"), cmp_)
    div = result["earliest_divergence"]
    assert div["name"] == "call_llm" and div["kind"] == "changed"
    assert div["comparison_event_id"] == "evt_run_c_2"
    assert result["first_failure"]["name"] == "parse"


def test_alignment_does_not_pair_different_steps_at_same_sequence():
    base = [ev(1, "load"), ev(2, "retrieve"), ev(3, "answer")]
    cmp_ = [ev(1, "load", run="run_c"), ev(2, "cache_lookup", run="run_c"), ev(3, "retrieve", run="run_c"),
            ev(4, "answer", run="run_c")]
    result = compare_runs(run("run_b"), base, run("run_c"), cmp_)
    kinds = [(e["name"], e["kind"]) for e in result["entries"]]
    assert kinds == [("load", "unchanged"), ("cache_lookup", "added"), ("retrieve", "unchanged"), ("answer", "unchanged")]
    assert result["earliest_divergence"]["name"] == "cache_lookup"


def test_missing_step_and_repeated_names():
    base = [ev(1, "tool"), ev(2, "tool"), ev(3, "final")]
    cmp_ = [ev(1, "tool", run="run_c"), ev(2, "final", run="run_c")]
    entries = compare_runs(run("run_b"), base, run("run_c"), cmp_)["entries"]
    assert [(e["step_key"], e["kind"]) for e in entries] == [("tool#1", "unchanged"), ("tool#2", "missing"), ("final#1", "unchanged")]


def test_reordered_steps_are_flagged():
    align = align_events([ev(1, "a"), ev(2, "b")], [ev(1, "b", run="c"), ev(2, "a", run="c")])
    assert sum(1 for a in align if a["reordered"]) == 1


def test_timing_only_change_is_not_divergence():
    base = [ev(1, "call", duration=100.0)]
    cmp_ = [ev(1, "call", duration=900.0, run="run_c")]
    result = compare_runs(run("run_b"), base, run("run_c"), cmp_)
    assert result["earliest_divergence"] is None
    assert result["entries"][0]["timing"]["notable"] is True


def test_volatile_metadata_ignored_but_config_metadata_detected():
    base = [ev(1, "call", metadata={"request_id": "a", "model": "m1"})]
    cmp_ = [ev(1, "call", metadata={"request_id": "b", "model": "m2"}, run="run_c")]
    entry = compare_runs(run("run_b"), base, run("run_c"), cmp_)["entries"][0]
    paths = [c["path"] for d in entry["differences"] for c in d.get("changes", [])]
    assert paths == ["$.model"]
