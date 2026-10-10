"""Deterministic, evidence-backed diagnosis.

Every finding separates:
  * observation  - what the stored events / comparison show (fact)
  * evidence     - references to the exact recorded events, errors and differences
  * hypothesis   - a plausible, explicitly qualified explanation (not a proven cause)
  * suggested_actions - practical next investigation steps
Verification happens later, against a separate corrected run (see services/findings.py).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from ..comparison.engine import VOLATILE_METADATA_KEYS, event_ref, step_keys
from . import regression

CONFIG_KEY_PATTERN = re.compile(
    r"(^|_)(model|temperature|top_p|top_k|max_tokens|prompt|prompt_version|template|config|settings|"
    r"endpoint|base_url|url|region|provider|schema|format|response_format|seed|tool_choice|version)($|_)",
    re.IGNORECASE,
)

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class FindingDraft:
    category: str
    severity: str
    confidence: str
    title: str
    observation: str
    hypothesis: str
    suggested_actions: list[str]
    evidence: list[dict[str, Any]] = field(default_factory=list)
    regression_test: str | None = None
    step: str | None = None
    step_key: str | None = None

    def fingerprint(self, run_id: str, baseline_run_id: str | None) -> str:
        raw = "|".join([run_id, baseline_run_id or "-", self.category, self.step_key or self.step or "-"])
        return hashlib.sha256(raw.encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category, "severity": self.severity, "confidence": self.confidence,
            "title": self.title, "summary": self.observation, "observation": self.observation,
            "hypothesis": self.hypothesis, "suggested_actions": self.suggested_actions,
            "evidence": self.evidence, "regression_test": self.regression_test,
            "step": self.step, "step_key": self.step_key,
        }


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

_JSON_TYPES = {"JSONDecodeError", "json.decoder.JSONDecodeError", "simplejson.errors.JSONDecodeError"}
_JSON_MSG = re.compile(
    r"Expecting value|Expecting property name|Unterminated string|Extra data|Invalid control character|"
    r"Invalid \\escape|invalid json|not valid json|json decode|could not parse json|Unexpected token",
    re.IGNORECASE,
)
_MODULE_MSG = re.compile(r"No module named ['\"]?([A-Za-z0-9_.\-]+)")
_ENV_MSG = re.compile(
    r"(environment variable|env var|env\.? variable)[^A-Za-z0-9]*['\"]?([A-Z][A-Z0-9_]{2,})?|"
    r"['\"]?([A-Z][A-Z0-9_]{2,})['\"]? (is not set|not set|is missing|missing)",
    re.IGNORECASE,
)
_UPPER_KEY = re.compile(r"^['\"]?([A-Z][A-Z0-9_]{2,})['\"]?$")
_FIELD_KEY = re.compile(r"^['\"]?([A-Za-z_][A-Za-z0-9_\-]*)['\"]?$")
_FIELD_MSG = re.compile(r"field required|missing required|missing key|missing field|required property|KeyError", re.IGNORECASE)
_TIMEOUT_TYPES = {"TimeoutError", "ReadTimeout", "ConnectTimeout", "WriteTimeout", "PoolTimeout", "Timeout",
                  "TimeoutException", "asyncio.TimeoutError", "socket.timeout", "DeadlineExceeded", "APITimeoutError"}
_TIMEOUT_MSG = re.compile(r"timed out|timeout|deadline exceeded", re.IGNORECASE)
_HTTP_TYPES = {"HTTPError", "HTTPStatusError", "APIStatusError", "RateLimitError", "InternalServerError",
               "ServiceUnavailableError", "BadRequestError", "AuthenticationError"}
_HTTP_MSG = re.compile(r"(status(?: code)?|HTTP)\s*[:=]?\s*([45]\d\d)\b|\b([45]\d\d)\s+(Client|Server) Error", re.IGNORECASE)
_NULL_MSG = re.compile(r"'NoneType' object|NoneType|unexpected null|got None|returned None", re.IGNORECASE)


def _short_type(error_type: str) -> str:
    return error_type.rsplit(".", 1)[-1] if error_type else ""


def classify_error(error: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return matched categories: [{category, confidence, detail}]. Pure function."""
    if not error:
        return []
    etype = str(error.get("type") or "")
    short = _short_type(etype)
    msg = str(error.get("message") or "")
    matches: list[dict[str, Any]] = []

    if etype in _JSON_TYPES or short == "JSONDecodeError":
        matches.append({"category": "invalid_json", "confidence": "high", "detail": f"{short} raised"})
    elif _JSON_MSG.search(msg):
        matches.append({"category": "invalid_json", "confidence": "medium", "detail": "message matches a JSON parse error"})

    module_match = _MODULE_MSG.search(msg)
    if short in {"ModuleNotFoundError", "ImportError"} or module_match:
        module = module_match.group(1) if module_match else None
        matches.append({"category": "missing_module", "confidence": "high" if module_match else "medium",
                        "detail": module})

    env_name = None
    env_match = _ENV_MSG.search(msg)
    if short == "KeyError" and _UPPER_KEY.match(msg.strip()):
        env_name = _UPPER_KEY.match(msg.strip()).group(1)  # type: ignore[union-attr]
        matches.append({"category": "missing_env_var", "confidence": "medium", "detail": env_name})
    elif env_match:
        env_name = env_match.group(2) or env_match.group(3)
        matches.append({"category": "missing_env_var", "confidence": "medium" if env_name else "low", "detail": env_name})

    if short == "KeyError" and not env_name:
        key = _FIELD_KEY.match(msg.strip())
        matches.append({"category": "missing_field", "confidence": "high", "detail": key.group(1) if key else msg[:80]})
    elif short in {"ValidationError"} or (_FIELD_MSG.search(msg) and short != "KeyError"):
        matches.append({"category": "missing_field", "confidence": "medium", "detail": msg[:120]})

    if short in _TIMEOUT_TYPES or etype in _TIMEOUT_TYPES:
        matches.append({"category": "external_timeout", "confidence": "high", "detail": short})
    elif _TIMEOUT_MSG.search(msg):
        matches.append({"category": "external_timeout", "confidence": "medium", "detail": "message mentions a timeout"})

    http_match = _HTTP_MSG.search(msg)
    if short in _HTTP_TYPES or http_match:
        code = None
        if http_match:
            code = http_match.group(2) or http_match.group(3)
        matches.append({"category": "http_failure", "confidence": "high" if code else "medium", "detail": code})

    if (short in {"TypeError", "AttributeError"} and _NULL_MSG.search(msg)) or "unexpected null" in msg.lower():
        matches.append({"category": "null_output", "confidence": "medium", "detail": "operation on None"})
    return matches


# ---------------------------------------------------------------------------
# Finding templates
# ---------------------------------------------------------------------------


def _err_text(error: dict[str, Any] | None) -> str:
    if not error:
        return "unknown error"
    return f"{error.get('type', 'Error')}: {str(error.get('message', ''))[:300]}"


def _event_evidence(event: dict[str, Any], description: str, value: Any = None, field_name: str | None = None) -> dict[str, Any]:
    item = {
        "kind": "event",
        "description": description,
        "run_id": event.get("run_id"),
        "event_id": event.get("event_id"),
        "sequence": event.get("sequence"),
        "step": event.get("name"),
    }
    if field_name:
        item["field"] = field_name
    if value is not None:
        item["value"] = value
    return item


def _find_entry(comparison: dict[str, Any] | None, event_id: str | None) -> dict[str, Any] | None:
    if not comparison or not event_id:
        return None
    for entry in comparison["entries"]:
        if (entry.get("comparison") or {}).get("event_id") == event_id:
            return entry
    return None


def _nearest_output_change_before(comparison: dict[str, Any] | None, position: int | None) -> dict[str, Any] | None:
    """Closest upstream step (before `position`) whose output differs from the baseline."""
    if not comparison or position is None:
        return None
    found = None
    for entry in comparison["entries"]:
        if entry["position"] >= position:
            break
        if entry.get("comparison") and any(d["field"] == "output" for d in entry["differences"]):
            found = entry
    return found


def _error_finding(category: str, confidence: str, detail: Any, event: dict[str, Any], key: str,
                   is_first_failure: bool, run_failed: bool, producer_entry: dict[str, Any] | None,
                   baseline_event: dict[str, Any] | None) -> FindingDraft:
    step = event["name"]
    err = _err_text(event.get("error"))
    severity = "high" if is_first_failure and run_failed else "medium"
    evidence = [_event_evidence(event, f"Step '{step}' failed with {err}", event.get("error"), "error")]
    if event.get("input_summary") is not None:
        evidence.append(_event_evidence(event, f"Recorded input of '{step}'", event.get("input_summary"), "input_summary"))
    producer_note = ""
    if producer_entry is not None:
        out_diff = next((d for d in producer_entry["differences"] if d["field"] == "output"), None)
        if out_diff:
            what = "changed structure" if out_diff.get("schema_changed") else "changed"
            producer_note = (f" The output of the preceding step '{producer_entry['name']}' {what} compared with "
                             "the baseline, which is consistent with this failure.")
            evidence.append({
                "kind": "output_difference",
                "description": f"Output of '{producer_entry['name']}' differs from the baseline",
                "run_id": (producer_entry.get("comparison") or {}).get("run_id"),
                "event_id": (producer_entry.get("comparison") or {}).get("event_id"),
                "sequence": (producer_entry.get("comparison") or {}).get("sequence"),
                "step": producer_entry["name"],
                "value": out_diff["changes"][:10],
            })
    baseline_input = baseline_event.get("input_summary") if baseline_event else None
    if baseline_event is not None:
        evidence.append(_event_evidence(baseline_event, f"Same step in the baseline run finished with status "
                                        f"'{baseline_event.get('status')}'", baseline_input, "input_summary"))

    producer_name = producer_entry["name"] if producer_entry else None
    failing_input = event.get("input_summary")
    if failing_input is None and producer_entry and producer_entry.get("comparison"):
        failing_input = producer_entry["comparison"].get("output_summary")

    if category == "invalid_json":
        return FindingDraft(
            category, severity, confidence,
            f"Invalid JSON while running '{step}'",
            f"Step '{step}' raised {err}.",
            "The step likely received text that is not valid JSON (for example JSON wrapped in Markdown code "
            "fences, prose around the JSON, or a truncated response)." + producer_note,
            [f"Inspect the recorded input of '{step}' in the evidence panel and compare it with the baseline input.",
             "Check whether a prompt, model or response-format change altered the raw output format.",
             "Make the parser tolerant of the observed format, or constrain the producer to strict JSON.",
             "Add the suggested regression test using the recorded failing input."],
            evidence,
            regression.consumer_test(event["run_id"], producer_name, step, failing_input, baseline_input,
                                     (event.get("error") or {}).get("type")) if failing_input is not None else None,
            step, key,
        )
    if category == "missing_module":
        module = detail or "the reported module"
        return FindingDraft(
            category, severity, confidence, f"Missing Python module: {module}",
            f"Step '{step}' raised {err}.",
            f"The runtime environment may not have '{module}' installed, or a dependency/virtual-environment "
            "change made it unavailable.",
            [f"Run `python -c \"import {module}\"` in the same environment as the workflow.",
             "Compare installed packages (pip freeze) between the baseline and failing environments.",
             "Pin the dependency in requirements and rebuild the environment."],
            evidence, regression.module_test(event["run_id"], module) if detail else None, step, key,
        )
    if category == "missing_env_var":
        var = detail or "a required variable"
        return FindingDraft(
            category, severity, confidence, f"Possibly missing environment variable: {var}",
            f"Step '{step}' raised {err}.",
            f"The error is consistent with {var} not being set in the environment where the run executed.",
            [f"Check that {var} is defined in the failing environment (without printing its value).",
             "Compare deployment/environment configuration between the baseline and failing runs."],
            evidence, regression.env_test(event["run_id"], detail) if detail else None, step, key,
        )
    if category == "missing_field":
        field_name = detail or "an expected field"
        return FindingDraft(
            category, severity, confidence, f"Expected field missing in '{step}'",
            f"Step '{step}' raised {err}.",
            f"The data handled by '{step}' may no longer contain '{field_name}', for example after an upstream "
            "schema or prompt change." + producer_note,
            ["Compare the recorded input/output structure with the baseline run.",
             f"Decide whether '{field_name}' should be optional or whether the producer must always include it.",
             "Add a contract test for the expected fields."],
            evidence,
            regression.consumer_test(event["run_id"], producer_name, step, failing_input, baseline_input,
                                     (event.get("error") or {}).get("type")) if failing_input is not None else None,
            step, key,
        )
    if category == "external_timeout":
        return FindingDraft(
            category, severity, confidence, f"External call timed out in '{step}'",
            f"Step '{step}' raised {err}" + (f" after {event['duration_ms']:.0f} ms." if event.get("duration_ms") else "."),
            "An external dependency may have been slow or unreachable, or the configured timeout may be too low "
            "for the current workload.",
            ["Check the dependency's status and latency around the run's timestamp.",
             "Compare this step's duration with the baseline in the comparison view.",
             "Review timeout and retry settings; consider bounded retries with backoff."],
            evidence, None, step, key,
        )
    if category == "http_failure":
        code = f" (HTTP {detail})" if detail else ""
        return FindingDraft(
            category, severity, confidence, f"Failed HTTP response in '{step}'{code}",
            f"Step '{step}' recorded {err}.",
            "A remote service returned an error response. 4xx codes often indicate request, authentication or quota "
            "problems; 5xx codes usually indicate a server-side or availability problem.",
            ["Inspect the recorded request metadata (endpoint, status code) for this step.",
             "Check credentials, quotas and request payload changes since the baseline.",
             "Retry only idempotent requests, with backoff."],
            evidence, None, step, key,
        )
    if category == "null_output":
        return FindingDraft(
            category, severity, confidence, f"Unexpected null value in '{step}'",
            f"Step '{step}' raised {err}.",
            "A value the step expected was None, possibly because an earlier step returned nothing." + producer_note,
            ["Find which earlier step should have produced the value and inspect its recorded output.",
             "Add explicit handling or validation for empty results."],
            evidence,
            regression.consumer_test(event["run_id"], producer_name, step, failing_input, baseline_input,
                                     (event.get("error") or {}).get("type")) if failing_input is not None else None,
            step, key,
        )
    if category == "tool_failure":
        return FindingDraft(
            category, severity, confidence, f"Tool invocation failed: '{step}'",
            f"Tool step '{step}' failed with {err}.",
            "The tool call itself failed; the arguments, the tool's availability, or its contract may have changed.",
            ["Inspect the recorded tool input and compare it with the baseline invocation.",
             "Call the tool directly with the recorded input to reproduce.",
             "Validate tool arguments before invocation."],
            evidence,
            regression.consumer_test(event["run_id"], None, step, event.get("input_summary"), baseline_input,
                                     (event.get("error") or {}).get("type")) if event.get("input_summary") is not None else None,
            step, key,
        )
    # Unclassified failure.
    return FindingDraft(
        "step_failure", severity, "low", f"Step '{step}' failed",
        f"Step '{step}' failed with {err}. No known error pattern matched.",
        "The recorded data is not sufficient for a specific hypothesis; the error message and preceding steps are "
        "the best starting point." + producer_note,
        ["Read the full error and traceback in the evidence panel.",
         "Compare with a successful baseline run to find the earliest divergence."],
        evidence, None, step, key,
    )


def diagnose(run: dict[str, Any], events: list[dict[str, Any]],
             baseline_run: dict[str, Any] | None = None, baseline_events: list[dict[str, Any]] | None = None,
             comparison: dict[str, Any] | None = None) -> list[FindingDraft]:
    """Produce findings for `run`. `comparison` is compare_runs(baseline, run) when a baseline exists."""
    events = sorted(events, key=lambda e: e["sequence"])
    keys = dict(zip((e["event_id"] for e in events), step_keys(events)))
    baseline_by_key: dict[str, dict[str, Any]] = {}
    if baseline_events:
        ordered = sorted(baseline_events, key=lambda e: e["sequence"])
        baseline_by_key = dict(zip(step_keys(ordered), ordered))
    run_failed = run.get("status") in {"failed", "timed_out"}
    drafts: list[FindingDraft] = []
    seen: set[tuple[str, str]] = set()

    def add(draft: FindingDraft) -> None:
        ident = (draft.category, draft.step_key or draft.step or "")
        if ident not in seen:
            seen.add(ident)
            drafts.append(draft)

    failed = [e for e in events if e.get("status") == "failed"]
    first_failure_id = failed[0]["event_id"] if failed else None

    # 1. Failed events: classify recorded errors.
    for event in failed[:10]:
        key = keys[event["event_id"]]
        entry = _find_entry(comparison, event["event_id"])
        position = entry["position"] if entry else None
        producer = _nearest_output_change_before(comparison, position)
        baseline_event = baseline_by_key.get(key)
        matches = classify_error(event.get("error"))
        is_first = event["event_id"] == first_failure_id
        for match in matches:
            add(_error_finding(match["category"], match["confidence"], match["detail"], event, key,
                               is_first, run_failed, producer, baseline_event))
        if event.get("event_type") == "tool":
            add(_error_finding("tool_failure", "high", None, event, key, is_first, run_failed, producer, baseline_event))
        if not matches and event.get("event_type") != "tool":
            add(_error_finding("step_failure", "low", None, event, key, is_first, run_failed, producer, baseline_event))

    # 2. HTTP status codes recorded in metadata (even on non-failed events).
    for event in events:
        meta = event.get("metadata") or {}
        code = meta.get("status_code", meta.get("http_status"))
        if isinstance(code, int) and code >= 400 and ("http_failure", keys[event["event_id"]]) not in seen:
            add(_error_finding("http_failure", "high", str(code), event, keys[event["event_id"]],
                               event["event_id"] == first_failure_id, run_failed, None, baseline_by_key.get(keys[event["event_id"]])))

    # 3. Comparison-based findings.
    if comparison is not None:
        drafts.extend(_comparison_findings(run, comparison, run_failed, first_failure_id, seen))

    drafts.sort(key=lambda d: (SEVERITY_ORDER.get(d.severity, 3), d.category))
    return drafts


def _comparison_findings(run: dict[str, Any], comparison: dict[str, Any], run_failed: bool,
                         first_failure_id: str | None, seen: set[tuple[str, str]]) -> list[FindingDraft]:
    out: list[FindingDraft] = []
    baseline_id = comparison["baseline"]["run_id"]
    failure_entry = _find_entry(comparison, first_failure_id)
    failure_pos = failure_entry["position"] if failure_entry else None

    def upstream(entry: dict[str, Any]) -> bool:
        return failure_pos is None or entry["position"] <= failure_pos

    divergence = comparison.get("earliest_divergence")
    if divergence:
        entry = comparison["entries"][divergence["position"]]
        ev = []
        for side in ("baseline", "comparison"):
            ref = entry.get(side)
            if ref:
                ev.append({"kind": "event", "description": f"{side.title()} event for step '{entry['name']}'",
                           "run_id": ref["run_id"], "event_id": ref["event_id"], "sequence": ref["sequence"],
                           "step": entry["name"], "value": {"status": ref["status"], "output_summary": ref["output_summary"],
                                                            "error": ref["error"]}})
        if entry["differences"]:
            ev.append({"kind": "differences", "description": "Recorded differences at this step",
                       "step": entry["name"], "value": entry["differences"]})
        out.append(FindingDraft(
            "divergence", "high" if run_failed else "medium", "high",
            f"Earliest observable divergence at '{entry['name']}'",
            divergence["description"] + f" (compared with baseline run {baseline_id}).",
            "Behaviour first differs from the baseline at this step. If the failure is related to the change, its "
            "origin is likely at or before this point. This is an ordering observation, not proof of cause.",
            ["Inspect the baseline and comparison values for this step side by side.",
             "Check what changed between the two runs' versions, prompts and configuration before this step."],
            ev, None, entry["name"], entry["step_key"],
        ))
        seen.add(("divergence", entry["step_key"]))

    for entry in comparison["entries"]:
        if entry["kind"] != "changed" or not upstream(entry):
            continue
        out_diff = next((d for d in entry["differences"] if d["field"] == "output"), None)
        if not out_diff:
            continue
        if (entry.get("comparison") or {}).get("status") == "failed":
            continue  # a failed step has no meaningful output; its error is diagnosed separately
        changes = out_diff["changes"]
        b_out = (entry.get("baseline") or {}).get("output_summary")
        c_out = (entry.get("comparison") or {}).get("output_summary")
        ref = entry["comparison"] or {}
        base_ev = {"kind": "output_difference", "description": f"Output of '{entry['name']}' vs baseline",
                   "run_id": ref.get("run_id"), "event_id": ref.get("event_id"), "sequence": ref.get("sequence"),
                   "step": entry["name"], "value": changes[:15]}
        sev = "high" if run_failed else "medium"
        if b_out is not None and c_out is None and ("null_output", entry["step_key"]) not in seen:
            seen.add(("null_output", entry["step_key"]))
            out.append(FindingDraft(
                "null_output", sev, "high", f"'{entry['name']}' returned null",
                f"Step '{entry['name']}' recorded a null output, while the baseline recorded a value.",
                "The step may have returned early, swallowed an error, or received an empty upstream response.",
                ["Inspect the step's input and any logged warnings for the comparison run.",
                 "Add validation that fails loudly when this step returns nothing."],
                [base_ev], regression.schema_test(run["run_id"], entry["name"], b_out, c_out), entry["name"], entry["step_key"]))
            continue
        removed = [c["path"] for c in changes if c["kind"] == "key_removed"]
        if removed and ("missing_field", entry["step_key"]) not in seen:
            seen.add(("missing_field", entry["step_key"]))
            out.append(FindingDraft(
                "missing_field", sev, "high", f"Fields missing from '{entry['name']}' output",
                f"Output of '{entry['name']}' no longer contains: {', '.join(removed[:6])}.",
                "Downstream steps that rely on these fields may fail or behave differently.",
                ["Confirm whether the removal was intentional.", "Add a contract test on the step's output fields."],
                [base_ev], regression.schema_test(run["run_id"], entry["name"], b_out, c_out), entry["name"], entry["step_key"]))
        schema = [c for c in changes if c["kind"] in {"type_changed", "key_added"}]
        if schema and ("schema_change", entry["step_key"]) not in seen:
            seen.add(("schema_change", entry["step_key"]))
            kinds = ", ".join(sorted({f"{c['path']} ({c['kind'].replace('_', ' ')})" for c in schema[:5]}))
            out.append(FindingDraft(
                "schema_change", sev, "high", f"Output format of '{entry['name']}' changed",
                f"Output of '{entry['name']}' changed structure compared with the baseline: {kinds}.",
                "A prompt, model, dependency or code change may have altered the output format that later steps "
                "depend on." + (" The failure occurs after this change." if failure_pos is not None else ""),
                ["Compare the baseline and comparison outputs in the evidence panel.",
                 "Identify which change between the runs could alter this output format.",
                 "Either restore the expected format or make consumers handle both."],
                [base_ev], regression.schema_test(run["run_id"], entry["name"], b_out, c_out), entry["name"], entry["step_key"]))

    # Configuration differences (run-level and event-level).
    config_changes = []
    for diff in comparison.get("run_differences", []):
        if diff["field"] in {"version", "environment"}:
            config_changes.append({"scope": "run", "path": diff["field"], "baseline": diff["baseline"], "comparison": diff["comparison"]})
        if diff["field"] == "metadata":
            config_changes.extend({"scope": "run", **c} for c in diff["changes"])
    for entry in comparison["entries"]:
        if not upstream(entry):
            continue
        for diff in entry["differences"]:
            if diff["field"] == "metadata":
                for change in diff["changes"]:
                    leaf = change["path"].rsplit(".", 1)[-1]
                    if CONFIG_KEY_PATTERN.search(leaf) and leaf not in VOLATILE_METADATA_KEYS:
                        config_changes.append({"scope": f"step:{entry['name']}", **change})
    if config_changes:
        listing = "; ".join(f"{c['scope']} {c['path']}: {c.get('baseline')!r} → {c.get('comparison')!r}" for c in config_changes[:6])
        out.append(FindingDraft(
            "config_mismatch", "medium", "medium" if len(config_changes) <= 3 else "low",
            "Configuration differs from the baseline",
            f"Recorded configuration differs between the runs: {listing}.",
            "One of these configuration changes may explain the behaviour change. Differences are correlations; "
            "verify by changing one setting at a time.",
            ["Re-run the workflow with the baseline value of each changed setting, one at a time.",
             "Record configuration in run metadata so future comparisons are precise."],
            [{"kind": "config_difference", "description": "Configuration differences", "value": config_changes[:20]}],
            None, None, "config",
        ))

    notable = [e for e in comparison["entries"] if e.get("timing") and e["timing"]["notable"]]
    if notable:
        worst = max(notable, key=lambda e: abs(e["timing"]["delta_ms"]))
        t = worst["timing"]
        out.append(FindingDraft(
            "timing_change", "low", "high", f"Duration of '{worst['name']}' changed notably",
            f"'{worst['name']}' took {t['comparison_ms']:.0f} ms vs {t['baseline_ms']:.0f} ms in the baseline.",
            "Latency changes can come from load, model changes, or network conditions; a single sample is weak evidence.",
            ["Compare durations across several runs before drawing conclusions."],
            [{"kind": "timing", "description": "Duration comparison", "step": worst["name"],
              "event_id": (worst.get("comparison") or {}).get("event_id"), "value": t}],
            None, worst["name"], worst["step_key"],
        ))
    return out
