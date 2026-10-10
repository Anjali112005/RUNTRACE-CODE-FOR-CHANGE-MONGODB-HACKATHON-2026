# Configuration reference

## Backend (`backend/.env` or environment)

| Variable | Default | Description |
|---|---|---|
| `RUNTRACE_MONGODB_URI` | `mongodb://127.0.0.1:27017` | MongoDB connection string (local or `mongodb+srv://…` Atlas). Secret if it contains credentials. |
| `RUNTRACE_MONGODB_DB` | `runtrace` | Database name |
| `RUNTRACE_MONGODB_TIMEOUT_MS` | `3000` | Server-selection / connect timeout |
| `RUNTRACE_HOST` | `127.0.0.1` | Bind address for `python -m app` |
| `RUNTRACE_PORT` | `8000` | Port for `python -m app` (or pass `--port`) |
| `RUNTRACE_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `RUNTRACE_CORS_ORIGINS` | `http://127.0.0.1:5173,http://localhost:5173` | Comma-separated allowed browser origins |
| `RUNTRACE_ADMIN_TOKEN` | *(empty = open mode)* | Required in `X-RunTrace-Admin-Token` for dashboard/management endpoints |
| `RUNTRACE_MAX_REQUEST_BYTES` | `1048576` | Max request body size |
| `RUNTRACE_MAX_EVENTS_PER_BATCH` | `500` | Max events per ingestion request |
| `RUNTRACE_MAX_FIELD_CHARS` | `8000` | Strings longer than this are truncated on ingest |
| `RUNTRACE_INGEST_RATE_PER_MINUTE` | `1200` | Requests/min per API key |
| `RUNTRACE_API_RATE_PER_MINUTE` | `600` | Requests/min per client IP for admin endpoints |
| `RUNTRACE_STALE_RUN_MINUTES` | `60` | Runs still `running` after this are marked `timed_out` |
| `RUNTRACE_REDACT_KEYS` | *(empty)* | Extra field names to redact (comma-separated, case-insensitive) |
| `GEMINI_API_KEY` | *(empty = AI off)* | Enables `/api/ai/chat`. Server-side only. |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model ID for `generateContent`; change it if Google retires this model |
| `GEMINI_TIMEOUT_SECONDS` | `20` | AI request timeout |

Invalid numbers fail fast at startup with a message naming the variable.

## Frontend (`frontend/.env`)

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | Backend URL (public; compiled into the bundle — never put secrets in `VITE_*`) |
| `VITE_PORT` | `5173` | Dev server port; the next free port is used if it is taken |

## SDK (environment of the instrumented app)

| Variable | Default | Description |
|---|---|---|
| `RUNTRACE_API_URL` | `http://127.0.0.1:8000` | Backend URL |
| `RUNTRACE_API_KEY` | — | Project key (`rt_live_…`), required unless disabled |
| `RUNTRACE_VERSION` | — | Default run version |
| `RUNTRACE_ENVIRONMENT` | — | Default run environment |
| `RUNTRACE_ENABLED` | `true` | `false` disables telemetry entirely |
| `RUNTRACE_STRICT` | `false` | Raise `TelemetryError` on delivery failures |
| `RUNTRACE_TIMEOUT` | `5` | Seconds per HTTP request |
| `RUNTRACE_MAX_RETRIES` | `2` | Retries for network errors, 429 and 5xx |
| `RUNTRACE_BATCH_SIZE` | `20` | Events per request |
| `RUNTRACE_CAPTURE_TRACEBACK` | `true` | Include tracebacks in recorded errors |

## Example: running on different ports

```powershell
# backend on 8010
python -m app --port 8010
# frontend/.env
VITE_API_BASE_URL=http://127.0.0.1:8010
VITE_PORT=5180
# backend/.env
RUNTRACE_CORS_ORIGINS=http://127.0.0.1:5180,http://localhost:5180
# SDK
$env:RUNTRACE_API_URL = "http://127.0.0.1:8010"
```
