# Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `/health` shows `"status": "degraded"`, API returns **503 `database_unavailable`** | MongoDB is not reachable. Start MongoDB (`mongod`, the Windows "MongoDB" service, or `docker run -d -p 27017:27017 mongo:7`) or fix `RUNTRACE_MONGODB_URI`. For Atlas, allow your IP in *Network Access* and URL-encode special characters in the password. The API reconnects automatically. |
| `[Errno 10048]` / "address already in use" on 8000 | Another process uses the port. Don't kill unknown processes — run `python -m app --port 8010` and point `VITE_API_BASE_URL` / `RUNTRACE_API_URL` at it. |
| Dashboard says **"Cannot reach the RunTrace API"** | Backend not running, wrong `VITE_API_BASE_URL`, or CORS: add the exact origin Vite prints (e.g. `http://127.0.0.1:5174`) to `RUNTRACE_CORS_ORIGINS` and restart the backend. Restart Vite after editing `frontend/.env`. |
| Dashboard shows **401** on every page | The server has `RUNTRACE_ADMIN_TOKEN` set. Enter it under **Settings → Access & keys** (kept in memory; re-enter after reload). |
| `Activate.ps1 cannot be loaded because running scripts is disabled` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then reopen PowerShell. Or use `.\.venv\Scripts\python.exe` directly. |
| SDK: `ConfigurationError: RUNTRACE_API_KEY is not set` | Export the key in the **same** terminal that runs your app (`$env:RUNTRACE_API_KEY = "…"`), or set `RUNTRACE_ENABLED=false`. |
| SDK: `invalid format` | Keys are `rt_live_` + 43 characters; check for missing characters or quotes. |
| SDK logs "telemetry unavailable" and runs don't appear | API unreachable or key revoked. Run `runtrace ping`. Use `RUNTRACE_STRICT=true` while setting up to get exceptions instead of warnings. |
| 401 `Invalid or revoked API key` | The key was rotated/revoked. Rotate on the project page and update the environment. |
| 409 `Conflicting duplicate event` | Two different events used the same `event_id` or `sequence` within a run (custom clients). The SDK generates unique IDs automatically. |
| 413 `payload_too_large` | Reduce what you record per step, or raise `RUNTRACE_MAX_REQUEST_BYTES`. Lower `RUNTRACE_BATCH_SIZE` in the SDK. |
| Runs stuck as `running` | The process ended before `finish` (e.g. killed). They become `timed_out` after `RUNTRACE_STALE_RUN_MINUTES`; a late `finish` still records the outcome. |
| Compare shows "Runs have different names" | You compared different workflows; results may be meaningless. |
| AI panel says "AI assistance is off" | Set `GEMINI_API_KEY` in `backend/.env` and restart. If you get 502 `ai_error`, check the key and `GEMINI_MODEL`. |
| `npm install` fails behind a proxy | Configure `npm config set proxy …` / `https-proxy …`, or use a mirror registry. |
| Backend tests skipped | Install dev dependencies: `python -m pip install -r requirements-dev.txt` (needs `fastapi` and `mongomock`). |
