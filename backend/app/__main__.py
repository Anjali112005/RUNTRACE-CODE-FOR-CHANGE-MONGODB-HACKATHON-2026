"""`python -m app` starts the API using RUNTRACE_HOST / RUNTRACE_PORT (defaults 127.0.0.1:8000).

Override the port without editing .env:  python -m app --port 8010
"""

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the RunTrace API server")
    parser.add_argument("--host", help="Bind address (default from RUNTRACE_HOST or 127.0.0.1)")
    parser.add_argument("--port", type=int, help="Port (default from RUNTRACE_PORT or 8000)")
    parser.add_argument("--reload", action="store_true", help="Auto-reload on code changes (development)")
    args = parser.parse_args()
    if args.host:
        os.environ["RUNTRACE_HOST"] = args.host
    if args.port:
        os.environ["RUNTRACE_PORT"] = str(args.port)

    import uvicorn

    from .config import Settings

    settings = Settings.from_env()
    print(f"RunTrace API starting on http://{settings.host}:{settings.port}  (docs: /docs)")
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=args.reload,
                log_level=settings.log_level.lower())


if __name__ == "__main__":
    main()
