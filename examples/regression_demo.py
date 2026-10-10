"""End-to-end regression loop driven through the real API:

1. record a good baseline run, a regressed run and a fixed run with the SDK,
2. compare baseline vs regressed and print the earliest observable divergence,
3. store findings for the regressed run,
4. verify the invalid-JSON finding against the fixed run.

Requires RUNTRACE_API_URL and RUNTRACE_API_KEY (a project key). The compare / analyze / verify
calls are authorised with the same project key, scoped to that project.

    python examples/regression_demo.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sdk"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from runtrace_sdk import RunTraceClient  # noqa: E402
from sample_ai_workflow import run_workflow  # noqa: E402


def api(client: httpx.Client, method: str, path: str, json: Any = None) -> Any:
    response = client.request(method, path, json=json)
    if response.status_code >= 400:
        raise SystemExit(f"{method} {path} failed: HTTP {response.status_code} {response.text}")
    return response.json()


def main(transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    sdk = RunTraceClient.from_env(transport=transport)
    run_ids: dict[str, str] = {}
    for variant in ("good", "regressed", "fixed"):
        recorder: list = []
        try:
            run_workflow(sdk, variant, recorder=recorder)
        except Exception as exc:  # expected for the regressed variant; the SDK recorded it
            print(f"  ({variant} raised {type(exc).__name__}, as expected for this variant)")
        if not recorder or not recorder[0].run_id:
            raise SystemExit("The run was not recorded. Check RUNTRACE_API_URL / RUNTRACE_API_KEY (try: runtrace ping).")
        run_ids[variant] = recorder[0].run_id
        time.sleep(0.01)

    headers = {"Authorization": f"Bearer {sdk.config.api_key}"}
    with httpx.Client(base_url=sdk.config.api_url, headers=headers, timeout=10, transport=transport) as http:
        comparison = api(http, "POST", "/api/compare", {"baseline_run_id": run_ids["good"],
                                                        "comparison_run_id": run_ids["regressed"]})
        div = comparison["earliest_divergence"]
        print("\nEarliest observable divergence:", div["description"] if div else "none")
        print("First failure:", (comparison.get("first_failure") or {}).get("name"))

        analysis = api(http, "POST", f"/api/runs/{run_ids['regressed']}/analyze", {"baseline_run_id": run_ids["good"]})
        print("\nFindings (observations + qualified hypotheses):")
        for f in analysis["findings"]:
            print(f"  [{f['severity']:>6}] {f['category']:<16} {f['title']}")

        target = next((f for f in analysis["findings"] if f["category"] == "invalid_json"), None)
        verified = None
        if target:
            verified = api(http, "POST", f"/api/findings/{target['finding_id']}/verify", {"run_id": run_ids["fixed"]})
            print(f"\nVerification of '{target['title']}' against fixed run: {verified['verification_status']}")
            for check in verified["verification"]["checks"]:
                print(f"  {'PASS' if check['passed'] else 'FAIL'}  {check['description']}")
    sdk.close()
    return {"runs": run_ids, "earliest_divergence": div, "findings": analysis["findings"],
            "verification": verified["verification_status"] if verified else None}


if __name__ == "__main__":
    main()
