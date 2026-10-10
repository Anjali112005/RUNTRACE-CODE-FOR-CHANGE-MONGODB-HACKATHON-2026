# RunTrace backend

FastAPI + PyMongo service that ingests runs/events, compares runs, produces deterministic findings,
verifies fixes and serves metrics. Optional Gemini assistance runs server-side only.

## Run (Windows PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt     # runtime deps + pytest + mongomock
Copy-Item .env.example .env                       # edit RUNTRACE_MONGODB_URI if needed
python -m app                                     # or: python -m app --port 8010 --reload
```

macOS/Linux: `python3 -m venv .venv && source .venv/bin/activate`, then the same commands.

* Docs: `http://127.0.0.1:8000/docs` · Health: `http://127.0.0.1:8000/health`
* Equivalent: `uvicorn app.main:app --host 127.0.0.1 --port 8000`
* Demo data: `python -m app.seed_demo` (idempotent) / `python -m app.seed_demo --reset` (removes only `is_demo` data)

## Layout

```
app/
  main.py            app factory, middleware, error handlers, lifespan (connects to MongoDB)
  __main__.py        `python -m app` launcher with --host/--port
  config.py          Settings from environment / backend/.env
  database.py        MongoClient, health state, idempotent index creation
  security.py        IDs, API-key generation/hashing, redaction, truncation, rate limiter
  auth.py            Principal model + FastAPI dependencies (project key / admin token)
  errors.py          ApiError → {"error": {code, message, details}}
  schemas/           Pydantic request/response models
  repositories/      one class per collection (projects, project_keys, project_versions, runs, events, findings)
  services/          business logic (projects, runs, analysis, metrics, ai)
  comparison/        deterministic run comparison (pure functions)
  diagnosis/         deterministic diagnosis + regression-test generation (pure functions)
  routes/            thin HTTP layer
  middleware/        body-size limit, secret-free access log
  seed_demo.py       explicit demo seeding
tests/               pytest suite (mongomock; never touches a real database)
```

## Tests

```powershell
python -m pytest -q
```

* `test_security.py`, `test_comparison.py`, `test_diagnosis.py` — pure unit tests.
* `test_api_*.py` — full HTTP tests through FastAPI's `TestClient` against an in-memory **mongomock** database.
  They are skipped (and reported as skipped) if `fastapi`/`mongomock` are not installed.
* `test_database_unavailable_reports_503` uses a real PyMongo client pointed at a closed port to prove the API
  reports a clear 503 instead of pretending to work.

See [../docs/API.md](../docs/API.md) for the endpoint reference and [../docs/CONFIGURATION.md](../docs/CONFIGURATION.md)
for all environment variables.
