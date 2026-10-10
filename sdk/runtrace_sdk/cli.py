"""Small CLI:  runtrace ping   |   runtrace send-test-run

Reads the same environment variables as the SDK (RUNTRACE_API_URL, RUNTRACE_API_KEY).
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from . import __version__
from .client import RunTraceClient
from .exceptions import RunTraceError


def _ping(client: RunTraceClient) -> int:
    health = client.health()
    db = health.get("database", {})
    print(f"API      {client.config.api_url}  status={health.get('status')}  version={health.get('version')}")
    print(f"MongoDB  connected={db.get('connected')}" + (f"  error={db.get('error')}" if db.get("error") else ""))
    who = client.verify()
    print(f"API key  valid for project '{who['project_name']}' ({who['project_id']})")
    return 0 if health.get("status") == "ok" else 1


def _send_test_run(client: RunTraceClient) -> int:
    with client.run("RunTrace CLI test run", metadata={"source": "runtrace-cli"}) as run:
        with run.step("prepare") as step:
            step.set_output({"ok": True})
        with run.step("wait", metadata={"sleep_ms": 50}):
            time.sleep(0.05)
    print(json.dumps({"run_id": run.run_id, "status": run.status, "dropped_events": run.dropped_events}))
    return 0 if run.run_id else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="runtrace", description=f"RunTrace SDK CLI {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ping", help="Check API health and validate RUNTRACE_API_KEY")
    sub.add_parser("send-test-run", help="Record a tiny two-step run")
    args = parser.parse_args(argv)
    try:
        with RunTraceClient.from_env(strict=True) as client:
            return _ping(client) if args.command == "ping" else _send_test_run(client)
    except RunTraceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
