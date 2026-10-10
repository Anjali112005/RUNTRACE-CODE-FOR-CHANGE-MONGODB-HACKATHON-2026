# Testing and verification record

This file states exactly what was executed while building RunTrace and what was not. A skipped test is not a
passing test.

## Build-environment constraints

The project was generated in a sandbox with **no access to PyPI, npm or a MongoDB server**. FastAPI, PyMongo,
mongomock and the frontend npm packages could not be installed there. Everything below marked "not run here"
must be run on your machine with the commands at the end of this file.

## Executed in the build environment

| Check | Result |
|---|---|
| Backend pure unit tests — `test_security.py`, `test_comparison.py`, `test_diagnosis.py` (pytest) | **20 passed** |
| Backend API test modules (`test_api_*.py`) | **3 modules skipped** — fastapi not installable here (reported as skipped, not passed) |
| SDK tests — `sdk/tests/test_sdk.py` (pytest + httpx `MockTransport` fake API) | **15 passed** |
| `py_compile` of every backend, SDK and example Python file | passed |
| Pyright static analysis of `backend/app`, `sdk/runtrace_sdk`, `examples` | no errors in project code (remaining reports were false positives from the scratch PyMongo stand-in) |
| Service-layer harness: demo seeding, idempotent re-seed, compare, analyze, verify, metrics, project detail, demo reset, response-schema validation — run against a minimal in-memory PyMongo stand-in (scratch only, not shipped) | passed |
| End-to-end bridge: the real SDK running `examples/regression_demo.py`, with HTTP routed into the real backend schemas + services (same stand-in DB) | passed — earliest divergence at `load_config` (`prompt_version`), `invalid_json` finding with producer evidence, verification **verified** against the fixed run |
| esbuild syntax transform of every frontend `.ts`/`.tsx` file | passed |
| TypeScript check of the frontend with loose shims for third-party packages (checks own modules, props and API types) | passed apart from two shim artefacts (zod type namespace) |

## Not run here (run on your machine)

| Suite | Command | Notes |
|---|---|---|
| Backend API tests: health, project creation, key validation/rotation/revocation, admin-token mode, run lifecycle, idempotent start, duplicate & conflicting events, events after finish, redaction, invalid requests (422), payload limits (413), stale-run sweep, compare/earliest divergence, analyze idempotency, verify loop, metrics, scoped access (403), AI disabled/enabled (mocked), demo seeding, DB-unavailable 503 | `cd backend; python -m pytest` | uses mongomock (in-memory) — never touches your database |
| Frontend tests: navigation, theme switching/persistence, empty/loading/error states, DB-outage message, run list → timeline, project creation + one-time key reveal, comparison view, API client errors, admin-token handling | `cd frontend; npm install; npm test` | `fetch` is mocked |
| Frontend production build / full type-check | `cd frontend; npm run build` | |
| Real MongoDB persistence across restarts | start backend → seed demo → restart backend → data still listed | requires a running MongoDB |

Because the FastAPI route layer, mongomock integration and the React build could not be executed in the build
environment, a first local run may surface small issues there; the business logic beneath them was exercised as
described above.

## Full local test run

```powershell
cd backend;  .\.venv\Scripts\Activate.ps1; python -m pytest
cd ..\sdk;   python -m pip install -e ".[dev]"; python -m pytest
cd ..\frontend; npm install; npm test; npm run build
```
