# RunTrace

**Find the Regression. Trace the Evidence. Verify the Fix.**

RunTrace is a developer tool for debugging AI applications and Python workflows. An instrumented app sends
its runs and steps to RunTrace; RunTrace stores them in MongoDB, compares a failing run with a known-good
baseline, reports the **earliest observable divergence**, generates **evidence-backed hypotheses** and
**regression-test suggestions**, and lets you **verify** a fix against a later run.

RunTrace never claims to find a guaranteed root cause. Every finding separates:

| | |
|---|---|
| **Observation** | what the recorded events show (fact) |
| **Evidence** | the exact events, outputs, errors and differences behind it |
| **Hypothesis** | a plausible, qualified explanation — *not a proven cause* |
| **Suggested investigation** | practical next steps |
| **Verification** | whether a later run shows the symptom is gone |

```
 your Python app ──(runtrace_sdk, HTTP + project API key)──▶ FastAPI backend ──▶ MongoDB
                                                                  ▲
 React dashboard (Vite) ──────────(REST, CORS-restricted)─────────┘
```

| Folder | What it is |
|---|---|
| `backend/` | FastAPI + PyMongo API: ingestion, comparison engine, diagnosis engine, metrics, optional Gemini |
| `frontend/` | React + TypeScript + Vite + Tailwind dashboard (8 sections, light/dark themes) |
| `sdk/` | `runtrace-sdk` Python package (local; **not published to PyPI**) + `runtrace` CLI |
| `examples/` | A simulated AI support workflow with a reproducible regression, and an end-to-end demo script |
| `docs/` | Architecture, API, security, demo guide, configuration, troubleshooting, test results |

---

## Quick start (Windows PowerShell)

**Prerequisites:** Python 3.10+, Node.js 18+ (20/22 recommended), and MongoDB — either a local server
(`mongodb://127.0.0.1:27017`, e.g. MongoDB Community Server or `docker run -d -p 27017:27017 mongo:7`)
or a MongoDB Atlas connection string.

### 1. Backend (terminal 1)

```powershell
cd RunTraceNew\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env          # then edit .env: RUNTRACE_MONGODB_URI etc.
python -m app                        # http://127.0.0.1:8000  (use --port 8010 if 8000 is busy)
```

Open <http://127.0.0.1:8000/docs> for the interactive API docs and <http://127.0.0.1:8000/health> for status.
If PowerShell blocks `Activate.ps1`, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.
If MongoDB is unreachable the API still starts, `/health` reports `"degraded"` with the reason, and data
endpoints return **503 `database_unavailable`** — it never pretends to persist data.

Optional demo data (idempotent, flagged `is_demo`):

```powershell
python -m app.seed_demo            # creates "Demo · Support Assistant" once
python -m app.seed_demo --reset    # deletes only demo records, then recreates them
```

### 2. Frontend (terminal 2)

```powershell
cd RunTraceNew\frontend
npm install
Copy-Item .env.example .env        # VITE_API_BASE_URL=http://127.0.0.1:8000
npm run dev                        # opens http://127.0.0.1:5173 (next free port if busy)
```

If Vite picks a port other than 5173, add that origin to `RUNTRACE_CORS_ORIGINS` in `backend\.env`
and restart the backend.

### 3. Instrument an app with the SDK (terminal 3)

Create a project in the dashboard (**Projects → New project**) and copy the API key (shown once).

```powershell
cd RunTraceNew
python -m pip install -e .\sdk
$env:RUNTRACE_API_URL = "http://127.0.0.1:8000"
$env:RUNTRACE_API_KEY = "rt_live_..."
runtrace ping                                         # checks API health + key
python examples\sample_ai_workflow.py --variant good       # baseline (success)
python examples\sample_ai_workflow.py --variant regressed  # fails on purpose: JSONDecodeError
python examples\sample_ai_workflow.py --variant fixed      # the fix (success)
# or the whole compare → analyze → verify loop in one go:
python examples\regression_demo.py
```

```python
from runtrace_sdk import RunTraceClient

client = RunTraceClient.from_env()

with client.run("Customer Support Workflow") as run:
    with run.step("retrieve_context"):
        context = retrieve_context()

    with run.step("generate_answer") as step:
        answer = generate_answer(context)
        step.set_output(answer)          # optional
```

Then use **Compare Runs** (baseline = good, comparison = regressed), **Save findings**, and on **Findings**
verify the invalid-JSON finding against the fixed run. Step-by-step: [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md).

---

## Tests

```powershell
cd backend;  python -m pytest              # API tests use mongomock — your real database is never touched
cd ..\sdk;   python -m pip install -e ".[dev]"; python -m pytest
cd ..\frontend; npm test
```

What was actually executed while building this project, and what was not, is recorded honestly in
[docs/TESTING.md](docs/TESTING.md). In short: the comparison/diagnosis/security unit tests (20) and the SDK
tests (15) were run and pass; the service layer and an SDK→backend end-to-end loop were exercised against an
in-memory MongoDB stand-in; the FastAPI route tests, the frontend build and the Vitest suite were written but
could **not** be run in the build sandbox (no PyPI/npm access) and must be run on your machine.

## Documentation

* [Architecture](docs/ARCHITECTURE.md) — data flow, data model, indexes, alignment strategy, diagnosis rules
* [API reference](docs/API.md) — every endpoint, auth, request/response schemas, errors
* [Security](docs/SECURITY.md) — key handling, redaction, limits, threat model
* [Configuration](docs/CONFIGURATION.md) — every environment variable
* [Demo guide](docs/DEMO_GUIDE.md) · [Troubleshooting](docs/TROUBLESHOOTING.md) · [Testing](docs/TESTING.md)
* Component READMEs: [backend](backend/README.md) · [frontend](frontend/README.md) · [SDK](sdk/README.md)

## Limitations

* Only instrumented steps are visible; RunTrace cannot see code you did not wrap, and never invents file names
  or line numbers.
* Divergence is the earliest *recorded* difference. The real cause may be earlier and unrecorded.
* Step alignment is by name + occurrence; renamed steps appear as one missing and one added step.
* Rate limiting is in-process (per server instance). There are no user accounts; the dashboard is protected by
  an optional admin token and is intended to run on localhost or behind your own access control.
* Gemini is optional and off by default; its output is clearly labelled and never stored over raw data.
