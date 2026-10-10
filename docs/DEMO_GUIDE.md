# Demo guide

Two ways to see the full loop: **seeded demo data** (fastest) or **real SDK runs** (shows ingestion).

## Scenario

A support assistant answers "How do I reset my password?" in six steps:
`load_config → retrieve_context → build_prompt → call_llm → parse_response → format_answer`.

| Version | Change | Result |
|---|---|---|
| 1.0 | prompt `support-v1`; the model returns raw JSON | success (baseline) |
| 1.1 | prompt `support-v2-markdown`; the model wraps JSON in ```` ```json ```` fences | `parse_response` raises `JSONDecodeError` → failed |
| 1.2 | same prompt; the parser strips code fences | success (fix) |

## Option A — seeded demo data

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m app.seed_demo
```

It creates the project **Demo · Support Assistant** (badge "Demo"), three runs, analyzes the failed run against
the baseline and verifies the invalid-JSON finding against the fixed run. Running it again changes nothing;
`--reset` deletes only `is_demo` records and recreates them.

## Option B — real SDK runs

1. Dashboard → **Projects → New project** → copy the key.
2. In a terminal:
   ```powershell
   cd RunTraceNew
   python -m pip install -e .\sdk
   $env:RUNTRACE_API_URL = "http://127.0.0.1:8000"
   $env:RUNTRACE_API_KEY = "rt_live_..."
   python examples\sample_ai_workflow.py --variant good
   python examples\sample_ai_workflow.py --variant regressed   # exits with JSONDecodeError on purpose
   python examples\sample_ai_workflow.py --variant fixed
   ```
   Or run `python examples\regression_demo.py`, which records all three and performs steps 4–8 through the API,
   printing the divergence, findings and verification checks.

## Walkthrough in the dashboard

1. **Overview** — the stat strip and activity chart show 3 runs, 1 failed.
2. **Runs → the failed 1.1 run** — the timeline auto-expands `parse_response` with
   `json.decoder.JSONDecodeError: Expecting value…` and its recorded input (the fenced JSON).
3. **Compare Runs** — baseline = 1.0 run, comparison = 1.1 run → **Compare**.
4. **Earliest observable divergence**: `load_config` — the `prompt_version` output changed (`support-v1` →
   `support-v2-markdown`). The table then shows `build_prompt` and `call_llm` changed, `parse_response` failed,
   and `format_answer` missing. Click rows to see baseline vs comparison values in the evidence panel.
5. **Diagnostic hypotheses** —
   * *Invalid JSON while running 'parse_response'* (high): observation = the recorded error; evidence = the
     failing input, the changed output of the preceding `call_llm` step and the baseline step; hypothesis = the
     parser likely received JSON wrapped in Markdown fences (qualified, not proven); a pytest regression test
     built from the recorded failing input.
   * *Configuration differs from the baseline*: e.g. version 1.0 → 1.1 and the recorded run metadata changed (correlation).
   * *Earliest observable divergence at 'load_config'*.
6. **Save findings** — stores them (idempotent).
7. **Findings → Invalid JSON…** → **Verify the fix** → choose the 1.2 run → **Verify**: all checks pass
   (run succeeded, `parse_response` present and not failed, no failed steps) → status **verified**, with the note
   that this shows the symptom is gone, not that the hypothesis was proven.
8. **Compare** the failed 1.1 run (baseline) against the fixed 1.2 run. With the seeded data the divergence is at
   `parse_response` (`failed → success`, `strip_code_fences` metadata changed); with the SDK example it is already at
   `load_config`, because that script records the `strip_code_fences` flag in the config step's output. A banner
   suggests verifying the failed run's findings against this run.
9. **Metrics** — by-version chart shows the failure only in 1.1 (presented as correlation).

Toggle **Include demo data** on Runs/Metrics to separate seeded data from SDK-ingested runs.
