"""A small, self-contained "AI support assistant" instrumented with the RunTrace SDK.

No external LLM is called: the model is simulated so the regression is reproducible.

    variant   version  behaviour
    good      1.0      prompt v1, model returns raw JSON, parser succeeds
    regressed 1.1      prompt v2 asks for Markdown, model wraps JSON in ``` fences -> JSONDecodeError
    fixed     1.2      prompt v2, parser strips code fences -> succeeds

Usage (after exporting RUNTRACE_API_URL and RUNTRACE_API_KEY):
    python examples/sample_ai_workflow.py --variant good
    python examples/sample_ai_workflow.py --variant regressed
    python examples/sample_ai_workflow.py --variant fixed
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sdk"))  # allow running without pip install

from runtrace_sdk import RunTraceClient  # noqa: E402

VERSIONS = {"good": "1.0", "regressed": "1.1", "fixed": "1.2"}
KNOWLEDGE_BASE = [
    {"doc_id": "kb-12", "title": "Account security", "text": "Passwords are reset from Settings > Security."},
    {"doc_id": "kb-31", "title": "Password reset emails", "text": "Reset links expire after 30 minutes."},
    {"doc_id": "kb-77", "title": "Billing", "text": "Invoices are emailed monthly."},
]


# --- business logic (unchanged by instrumentation) ------------------------------------

def load_config(variant: str) -> dict[str, Any]:
    return {
        "model": "simulated-llm",
        "temperature": 0.2,
        "prompt_version": "support-v1" if variant == "good" else "support-v2-markdown",
        "strip_code_fences": variant == "fixed",
    }


def retrieve_context(question: str, top_k: int = 2) -> list[dict[str, Any]]:
    words = set(re.findall(r"\w+", question.lower()))
    scored = [(len(words & set(re.findall(r"\w+", (d["title"] + " " + d["text"]).lower()))), d) for d in KNOWLEDGE_BASE]
    return [d for score, d in sorted(scored, key=lambda x: -x[0])[:top_k] if score > 0]


def build_prompt(config: dict[str, Any], question: str, docs: list[dict[str, Any]]) -> str:
    context = "\n".join(f"[{d['doc_id']}] {d['text']}" for d in docs)
    style = ('Respond ONLY with JSON: {"answer": str, "citations": [doc_id]}' if config["prompt_version"] == "support-v1"
             else "Respond in friendly Markdown. Include a JSON block with answer and citations.")
    return f"{style}\n\nContext:\n{context}\n\nQuestion: {question}"


def call_llm(prompt: str, config: dict[str, Any]) -> str:
    time.sleep(0.05)  # simulated latency
    payload = {"answer": "Open Settings > Security and choose 'Reset password'. The emailed link expires after 30 minutes.",
               "citations": re.findall(r"\[(kb-\d+)\]", prompt)}
    if "Markdown" in prompt:
        return "```json\n" + json.dumps(payload, indent=2) + "\n```"
    return json.dumps(payload)


def parse_response(text: str, strip_code_fences: bool) -> dict[str, Any]:
    if strip_code_fences:
        match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1)
    return json.loads(text)


def format_answer(parsed: dict[str, Any]) -> str:
    return f"{parsed['answer']} (sources: {', '.join(parsed['citations'])})"


# --- instrumented workflow ------------------------------------------------------------

def run_workflow(client: RunTraceClient, variant: str, question: str = "How do I reset my password?",
                 recorder: list | None = None) -> str:
    """Run the workflow. If `recorder` is given, the SDK Run object is appended to it (to read run_id)."""
    with client.run("Customer Support Workflow", version=VERSIONS[variant],
                    metadata={"variant": variant, "question": question}) as run:
        if recorder is not None:
            recorder.append(run)
        with run.step("load_config") as step:
            config = load_config(variant)
            step.set_output(config)
        with run.step("retrieve_context", event_type="retrieval", input={"question": question}) as step:
            docs = retrieve_context(question)
            step.set_output([{"doc_id": d["doc_id"], "title": d["title"]} for d in docs])
        with run.step("build_prompt", input={"documents": len(docs)}) as step:
            prompt = build_prompt(config, question, docs)
            step.set_output({"prompt_version": config["prompt_version"], "characters": len(prompt)})
        with run.step("call_llm", event_type="llm", metadata={"model": config["model"],
                                                              "temperature": config["temperature"]}) as step:
            raw = call_llm(prompt, config)
            step.set_output({"text": raw})
        with run.step("parse_response", event_type="parse", input=raw,
                      metadata={"strip_code_fences": config["strip_code_fences"]}) as step:
            parsed = parse_response(raw, config["strip_code_fences"])
            step.set_output({"keys": sorted(parsed)})
        with run.step("format_answer") as step:
            answer = format_answer(parsed)
            step.set_output(answer)
    print(f"[{variant}] run {run.run_id}: {run.status}")
    return answer


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--variant", choices=list(VERSIONS), default="good")
    args = parser.parse_args()
    client = RunTraceClient.from_env()
    try:
        print(run_workflow(client, args.variant))
        return 0
    except Exception as exc:  # the SDK already recorded it; show it like the real app would
        print(f"[{args.variant}] workflow failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
