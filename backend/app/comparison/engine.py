"""Deterministic run comparison.

Alignment strategy (documented in docs/ARCHITECTURE.md):

1. Each event gets a *logical step key* ``"<name>#<n>"`` where ``n`` is the
   occurrence count of that name within its run, in sequence order. So the second
   call of ``call_llm`` is ``call_llm#2``. Events are never paired merely because
   they share a sequence number.
2. Events whose keys exist in both runs are paired. The longest increasing
   subsequence of comparison positions (taken in baseline order) identifies pairs
   that keep their relative order; other pairs are flagged ``reordered``.
3. Baseline-only keys are ``missing``; comparison-only keys are ``added``.
4. Entries are emitted in execution order of the comparison run, with missing
   baseline steps placed right after the step that preceded them in the baseline.
5. The earliest observable divergence is the first entry in that order that is
   added, missing, or has a changed status, output, error or (non-volatile)
   metadata. Timing-only differences are reported but never count as divergence.

Limitations: steps that are renamed look like one missing + one added step; loops
with a different number of iterations align by occurrence index; only recorded
(instrumented) events can be compared.
"""

from __future__ import annotations

import bisect
from typing import Any

from ..utils.timeutil import iso

VOLATILE_METADATA_KEYS = {
    "timestamp", "time", "started_at", "finished_at", "created_at", "request_id", "trace_id",
    "span_id", "duration_ms", "latency_ms", "elapsed_ms", "run_id", "event_id", "pid", "thread",
    "thread_id", "host", "hostname", "sdk_version", "python_version",
}
MAX_CHANGES = 60
NOTABLE_RATIO = 2.0
NOTABLE_DELTA_MS = 250.0


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def diff_values(baseline: Any, comparison: Any, path: str = "$", out: list[dict[str, Any]] | None = None,
                ignore_keys: set[str] | None = None) -> list[dict[str, Any]]:
    """Structural diff. Change kinds: type_changed, key_removed, key_added, length_changed, value_changed."""
    out = [] if out is None else out
    if len(out) >= MAX_CHANGES:
        return out
    bt, ct = _type_name(baseline), _type_name(comparison)
    if bt != ct:
        out.append({"path": path, "kind": "type_changed", "baseline_type": bt, "comparison_type": ct,
                    "baseline": _preview(baseline), "comparison": _preview(comparison)})
        return out
    if isinstance(baseline, dict):
        ignore = ignore_keys or set()
        bkeys = [k for k in baseline if k not in ignore]
        ckeys = [k for k in comparison if k not in ignore]
        for key in bkeys:
            if key not in comparison:
                out.append({"path": f"{path}.{key}", "kind": "key_removed", "baseline": _preview(baseline[key])})
        for key in ckeys:
            if key not in baseline:
                out.append({"path": f"{path}.{key}", "kind": "key_added", "comparison": _preview(comparison[key])})
        for key in bkeys:
            if key in comparison:
                diff_values(baseline[key], comparison[key], f"{path}.{key}", out)
        return out
    if isinstance(baseline, list):
        if len(baseline) != len(comparison):
            out.append({"path": path, "kind": "length_changed", "baseline": len(baseline), "comparison": len(comparison)})
        for i, (b, c) in enumerate(zip(baseline[:25], comparison[:25])):
            diff_values(b, c, f"{path}[{i}]", out)
        return out
    if baseline != comparison:
        out.append({"path": path, "kind": "value_changed", "baseline": _preview(baseline), "comparison": _preview(comparison)})
    return out


def _preview(value: Any, limit: int = 300) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "…"
    if isinstance(value, (dict, list)):
        import json

        text = json.dumps(value, default=str)
        return value if len(text) <= limit else text[:limit] + "…"
    return value


SCHEMA_KINDS = {"type_changed", "key_removed", "key_added"}


def step_keys(events: list[dict[str, Any]]) -> list[str]:
    counts: dict[str, int] = {}
    keys = []
    for event in events:
        name = event["name"]
        counts[name] = counts.get(name, 0) + 1
        keys.append(f"{name}#{counts[name]}")
    return keys


def _lis_indices(values: list[int]) -> set[int]:
    """Indices (into `values`) of one longest strictly increasing subsequence."""
    tails: list[int] = []
    tails_idx: list[int] = []
    parent = [-1] * len(values)
    for i, v in enumerate(values):
        pos = bisect.bisect_left(tails, v)
        if pos == len(tails):
            tails.append(v)
            tails_idx.append(i)
        else:
            tails[pos] = v
            tails_idx[pos] = i
        parent[i] = tails_idx[pos - 1] if pos > 0 else -1
    result: set[int] = set()
    i = tails_idx[-1] if tails_idx else -1
    while i != -1:
        result.add(i)
        i = parent[i]
    return result


def align_events(baseline: list[dict[str, Any]], comparison: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return ordered alignment entries: {key, b_index, c_index, reordered}."""
    b_keys, c_keys = step_keys(baseline), step_keys(comparison)
    c_pos = {k: i for i, k in enumerate(c_keys)}
    matched_b = [i for i, k in enumerate(b_keys) if k in c_pos]
    matched_c = [c_pos[b_keys[i]] for i in matched_b]
    in_order = _lis_indices(matched_c)
    pair_of_b = {b: (c, idx in in_order) for idx, (b, c) in enumerate(zip(matched_b, matched_c))}

    entries: list[tuple[float, int, dict[str, Any]]] = []
    matched_c_set = set(matched_c)
    for ci, key in enumerate(c_keys):
        if ci not in matched_c_set:
            entries.append((float(ci), 1, {"key": key, "b_index": None, "c_index": ci, "reordered": False}))
    last_pos = -1.0
    offset = 0
    for bi, key in enumerate(b_keys):
        if bi in pair_of_b:
            ci, ordered = pair_of_b[bi]
            entries.append((float(ci), 0, {"key": key, "b_index": bi, "c_index": ci, "reordered": not ordered}))
            if ordered:
                last_pos = float(ci)
                offset = 0
        else:
            offset += 1
            # Place right after the comparison position of the preceding in-order step.
            entries.append((last_pos + 0.5 + offset * 1e-4, 2, {"key": key, "b_index": bi, "c_index": None, "reordered": False}))
    entries.sort(key=lambda item: (item[0], item[1]))
    return [entry for _, _, entry in entries]


def event_ref(event: dict[str, Any] | None) -> dict[str, Any] | None:
    if event is None:
        return None
    return {
        "event_id": event.get("event_id"),
        "run_id": event.get("run_id"),
        "sequence": event.get("sequence"),
        "name": event.get("name"),
        "event_type": event.get("event_type"),
        "status": event.get("status"),
        "duration_ms": event.get("duration_ms"),
        "timestamp": iso(event.get("timestamp")) if event.get("timestamp") else None,
        "input_summary": event.get("input_summary"),
        "output_summary": event.get("output_summary"),
        "error": event.get("error"),
        "metadata": event.get("metadata") or {},
    }


def _error_text(error: dict[str, Any] | None) -> str | None:
    if not error:
        return None
    return f"{error.get('type', 'Error')}: {error.get('message', '')}"


def compare_events(b: dict[str, Any], c: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    differences: list[dict[str, Any]] = []
    if b.get("status") != c.get("status"):
        differences.append({"field": "status", "baseline": b.get("status"), "comparison": c.get("status")})
    if b.get("event_type") != c.get("event_type"):
        differences.append({"field": "event_type", "baseline": b.get("event_type"), "comparison": c.get("event_type")})
    out_changes = diff_values(b.get("output_summary"), c.get("output_summary"))
    if out_changes:
        differences.append({
            "field": "output",
            "changes": out_changes,
            "schema_changed": any(ch["kind"] in SCHEMA_KINDS for ch in out_changes),
        })
    in_changes = diff_values(b.get("input_summary"), c.get("input_summary"))
    if in_changes:
        differences.append({"field": "input", "changes": in_changes})
    be, ce = _error_text(b.get("error")), _error_text(c.get("error"))
    if be != ce:
        differences.append({"field": "error", "baseline": be, "comparison": ce})
    meta_changes = diff_values(b.get("metadata") or {}, c.get("metadata") or {}, ignore_keys=VOLATILE_METADATA_KEYS)
    if meta_changes:
        differences.append({"field": "metadata", "changes": meta_changes})

    timing = None
    bd, cd = b.get("duration_ms"), c.get("duration_ms")
    if bd is not None and cd is not None:
        delta = round(cd - bd, 3)
        ratio = round(cd / bd, 3) if bd > 0 else None
        notable = abs(delta) >= NOTABLE_DELTA_MS and (ratio is None or ratio >= NOTABLE_RATIO or ratio <= 1 / NOTABLE_RATIO)
        timing = {"baseline_ms": bd, "comparison_ms": cd, "delta_ms": delta, "ratio": ratio, "notable": notable}
    return differences, timing


def _run_meta(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run.get("run_id"),
        "project_id": run.get("project_id"),
        "name": run.get("name"),
        "status": run.get("status"),
        "version": run.get("version"),
        "environment": run.get("environment"),
        "started_at": iso(run.get("started_at")),
        "finished_at": iso(run.get("finished_at")),
        "duration_ms": run.get("duration_ms"),
        "error_summary": run.get("error_summary"),
        "event_count": run.get("event_count", 0),
        "is_demo": bool(run.get("is_demo")),
        "metadata": run.get("metadata") or {},
    }


def _describe(entry: dict[str, Any]) -> str:
    name = entry["name"]
    if entry["kind"] == "added":
        return f"Step '{name}' appears only in the comparison run."
    if entry["kind"] == "missing":
        return f"Step '{name}' was recorded in the baseline but not in the comparison run."
    parts = []
    for diff in entry["differences"]:
        field = diff["field"]
        if field == "status":
            parts.append(f"status changed {diff['baseline']} → {diff['comparison']}")
        elif field == "output":
            paths = ", ".join(ch["path"].removeprefix("$.").removeprefix("$") or "value" for ch in diff["changes"][:3])
            label = "output schema changed" if diff.get("schema_changed") else "output value changed"
            parts.append(f"{label} ({paths})" if paths else label)
        elif field == "error":
            parts.append("error changed" if diff["baseline"] else "a new error was recorded")
        elif field == "metadata":
            parts.append("metadata changed: " + ", ".join(ch["path"].removeprefix("$.") for ch in diff["changes"][:4]))
        elif field == "input":
            parts.append("input changed")
        elif field == "event_type":
            parts.append("event type changed")
    return f"Step '{name}': " + "; ".join(parts) + "."


def compare_runs(baseline_run: dict[str, Any], baseline_events: list[dict[str, Any]],
                 comparison_run: dict[str, Any], comparison_events: list[dict[str, Any]]) -> dict[str, Any]:
    baseline_events = sorted(baseline_events, key=lambda e: e["sequence"])
    comparison_events = sorted(comparison_events, key=lambda e: e["sequence"])
    alignment = align_events(baseline_events, comparison_events)

    entries: list[dict[str, Any]] = []
    counts = {"unchanged": 0, "changed": 0, "added": 0, "missing": 0, "reordered": 0,
              "status_changed": 0, "output_changed": 0, "schema_changed": 0, "error_changed": 0,
              "metadata_changed": 0, "input_changed": 0, "notable_timing": 0}
    for position, item in enumerate(alignment):
        b = baseline_events[item["b_index"]] if item["b_index"] is not None else None
        c = comparison_events[item["c_index"]] if item["c_index"] is not None else None
        name = (c or b)["name"]  # type: ignore[index]
        entry: dict[str, Any] = {
            "position": position,
            "step_key": item["key"],
            "name": name,
            "baseline": event_ref(b),
            "comparison": event_ref(c),
            "reordered": item["reordered"],
            "differences": [],
            "timing": None,
        }
        if b is None:
            entry["kind"] = "added"
        elif c is None:
            entry["kind"] = "missing"
        else:
            diffs, timing = compare_events(b, c)
            entry["differences"], entry["timing"] = diffs, timing
            entry["kind"] = "changed" if diffs else "unchanged"
            for diff in diffs:
                key = f"{diff['field']}_changed"
                if key in counts:
                    counts[key] += 1
                if diff["field"] == "output" and diff.get("schema_changed"):
                    counts["schema_changed"] += 1
            if timing and timing["notable"]:
                counts["notable_timing"] += 1
        if entry["reordered"]:
            counts["reordered"] += 1
        counts[entry["kind"]] += 1
        entry["description"] = _describe(entry) if entry["kind"] != "unchanged" else None
        entries.append(entry)

    earliest = next((e for e in entries if e["kind"] != "unchanged"), None)
    earliest_divergence = None
    if earliest is not None:
        earliest_divergence = {
            "position": earliest["position"],
            "step_key": earliest["step_key"],
            "name": earliest["name"],
            "kind": earliest["kind"],
            "description": earliest["description"],
            "baseline_event_id": (earliest["baseline"] or {}).get("event_id"),
            "comparison_event_id": (earliest["comparison"] or {}).get("event_id"),
            "baseline_sequence": (earliest["baseline"] or {}).get("sequence"),
            "comparison_sequence": (earliest["comparison"] or {}).get("sequence"),
            "fields": [d["field"] for d in earliest["differences"]],
        }

    first_failure = next((e for e in comparison_events if e.get("status") == "failed"), None)

    run_differences = []
    for field in ("status", "version", "environment", "name", "error_summary"):
        if baseline_run.get(field) != comparison_run.get(field):
            run_differences.append({"field": field, "baseline": baseline_run.get(field), "comparison": comparison_run.get(field)})
    meta_changes = diff_values(baseline_run.get("metadata") or {}, comparison_run.get("metadata") or {},
                               ignore_keys=VOLATILE_METADATA_KEYS)
    if meta_changes:
        run_differences.append({"field": "metadata", "changes": meta_changes})

    warnings = []
    if baseline_run.get("project_id") != comparison_run.get("project_id"):
        warnings.append("Runs belong to different projects; differences may reflect unrelated workflows.")
    if baseline_run.get("name") != comparison_run.get("name"):
        warnings.append("Runs have different names; confirm they execute the same workflow.")
    if comparison_run.get("status") == "running" or baseline_run.get("status") == "running":
        warnings.append("At least one run is still running; later events may change the result.")
    if not baseline_events or not comparison_events:
        warnings.append("At least one run has no recorded events.")

    return {
        "baseline": _run_meta(baseline_run),
        "comparison": _run_meta(comparison_run),
        "alignment_strategy": "logical-step-key (name + occurrence index) with order-preserving matching",
        "entries": entries,
        "summary": {
            **counts,
            "total_entries": len(entries),
            "baseline_events": len(baseline_events),
            "comparison_events": len(comparison_events),
            "identical": earliest is None and not run_differences,
        },
        "earliest_divergence": earliest_divergence,
        "first_failure": event_ref(first_failure),
        "run_differences": run_differences,
        "warnings": warnings,
    }
