# runtrace-sdk

Python SDK for RunTrace. It records an instrumented run (and its steps) and sends them to the RunTrace API
over HTTP. This package lives in this repository and is **not published to PyPI**.

```powershell
python -m pip install -e .\sdk          # from the RunTraceNew folder; only dependency: httpx
```

## Usage

```python
from runtrace_sdk import RunTraceClient

client = RunTraceClient.from_env()            # reads RUNTRACE_* environment variables

with client.run("Customer Support Workflow", metadata={"model": "my-model"}) as run:
    with run.step("retrieve_context", event_type="retrieval", input={"question": q}) as step:
        context = retrieve_context(q)
        step.set_output([d.id for d in context])

    with run.step("generate_answer", event_type="llm") as step:
        answer = generate_answer(context)
        step.set_output({"text": answer})
        step.add_metadata(prompt_tokens=412)

    run.event("cache_miss", metadata={"key": "faq"})   # point-in-time event (no duration)
```

### API

| Call | Purpose |
|---|---|
| `RunTraceClient.from_env(**overrides)` / `RunTraceClient(RunTraceConfig(...))` | create a client |
| `client.run(name, *, version=None, environment=None, metadata=None)` | context manager → `Run` |
| `run.step(name, *, event_type="step", input=None, metadata=None)` | context manager → `Step` |
| `step.set_output(value)`, `step.set_input(value)`, `step.add_metadata(**kv)` | enrich the step |
| `run.event(name, *, event_type="log", status="info", output=None, metadata=None)` | point event |
| `run.flush()` | send buffered events now |
| `run.run_id`, `run.status`, `run.dropped_events` | results |
| `client.verify()`, `client.health()` | check key / API |

`event_type` is free-form lowercase (e.g. `step`, `llm`, `tool`, `retrieval`, `parse`, `http`). Use `tool` for
tool invocations so failures get the tool-failure diagnosis.

### Guarantees

* **Your exceptions are preserved.** A failing step is recorded (type, message, traceback) and the original
  exception is re-raised unchanged. An exception outside any step is recorded once as `unhandled_exception`.
* **Best-effort by default.** If RunTrace is unreachable, the app keeps running and the SDK logs a single
  warning. `RUNTRACE_STRICT=true` raises `TelemetryError` instead — but never while an application exception is
  propagating.
* **Duplicate-safe retries.** Every event carries a client-generated `event_id` and each run a `client_run_key`;
  the server de-duplicates identical retries (and rejects conflicting reuse with 409). Transient errors (network,
  429, 5xx) are retried with backoff.
* **No secret leakage.** Values are converted to bounded JSON; keys like `password`, `api_key`, `token`,
  `authorization` and patterns like `rt_live_…`, `sk-…`, bearer tokens and credentials in URLs are redacted
  client-side (and again server-side). The API key is never included in `repr()` or logs.

### Configuration

| Variable | Default | |
|---|---|---|
| `RUNTRACE_API_URL` | `http://127.0.0.1:8000` | API base URL |
| `RUNTRACE_API_KEY` | — (required when enabled) | project key `rt_live_…` |
| `RUNTRACE_VERSION` / `RUNTRACE_ENVIRONMENT` | — | default version / environment for runs |
| `RUNTRACE_ENABLED` | `true` | `false` turns telemetry off (no key needed) |
| `RUNTRACE_STRICT` | `false` | raise on telemetry failures |
| `RUNTRACE_TIMEOUT` | `5` | seconds per request |
| `RUNTRACE_MAX_RETRIES` | `2` | retries for transient failures |
| `RUNTRACE_BATCH_SIZE` | `20` | events per request (also flushed at run end) |
| `RUNTRACE_CAPTURE_TRACEBACK` | `true` | include tracebacks in step errors |

Invalid values raise `ConfigurationError` with a clear message (the key is masked).

## CLI

```powershell
runtrace ping            # API health, MongoDB status, key validity
runtrace send-test-run   # records a tiny two-step run
python -m runtrace_sdk ping
```

## Tests

```powershell
python -m pip install -e ".\sdk[dev]"
cd sdk; python -m pytest
```

Tests use `httpx.MockTransport` with an in-memory fake of the API (`tests/fake_server.py`), so no server is needed.
