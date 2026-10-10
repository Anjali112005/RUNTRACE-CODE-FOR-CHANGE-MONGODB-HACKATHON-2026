import json
import logging

import httpx
import pytest

from fake_server import VALID_KEY, FakeRunTrace
from runtrace_sdk import ConfigurationError, RunTraceClient, RunTraceConfig, TelemetryError


@pytest.fixture
def server():
    return FakeRunTrace()


def make_client(server, **overrides):
    options = {"api_url": "http://127.0.0.1:8000", "api_key": VALID_KEY, "max_retries": 2, **overrides}
    config = RunTraceConfig(**options)
    return RunTraceClient(config, transport=server.transport())


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("runtrace_sdk.client.time.sleep", lambda _s: None)


# -- configuration ---------------------------------------------------------------

def test_config_from_env(monkeypatch):
    monkeypatch.setenv("RUNTRACE_API_URL", "http://localhost:9000/")
    monkeypatch.setenv("RUNTRACE_API_KEY", VALID_KEY)
    monkeypatch.setenv("RUNTRACE_STRICT", "true")
    monkeypatch.setenv("RUNTRACE_VERSION", "2.1")
    cfg = RunTraceConfig.from_env()
    assert cfg.api_url == "http://localhost:9000" and cfg.strict and cfg.version == "2.1"
    assert VALID_KEY not in repr(cfg)


def test_config_errors_are_clear(monkeypatch):
    monkeypatch.delenv("RUNTRACE_API_KEY", raising=False)
    with pytest.raises(ConfigurationError, match="RUNTRACE_API_KEY is not set"):
        RunTraceConfig.from_env()
    with pytest.raises(ConfigurationError, match="invalid format"):
        RunTraceConfig(api_key="rt_live_short")
    with pytest.raises(ConfigurationError, match="http"):
        RunTraceConfig(api_url="ftp://x", api_key=VALID_KEY)
    monkeypatch.setenv("RUNTRACE_STRICT", "maybe")
    with pytest.raises(ConfigurationError, match="RUNTRACE_STRICT"):
        RunTraceConfig.from_env(api_key=VALID_KEY)


def test_disabled_mode_needs_no_key(monkeypatch):
    monkeypatch.setenv("RUNTRACE_ENABLED", "false")
    monkeypatch.delenv("RUNTRACE_API_KEY", raising=False)
    client = RunTraceClient.from_env()
    with client.run("wf") as run:
        with run.step("a") as step:
            step.set_output(1)
    assert run.run_id is None and run.status == "success"


# -- runs ----------------------------------------------------------------------------

def test_successful_run_records_steps_in_order(server):
    client = make_client(server, environment="test", version="1.0")
    with client.run("Customer Support Workflow", metadata={"model": "m"}) as run:
        with run.step("retrieve_context", event_type="retrieval", input={"q": "hi"}) as step:
            step.set_output(["doc-1", "doc-2"])
        with run.step("generate_answer") as step:
            with run.step("call_llm", event_type="llm") as inner:
                inner.set_output({"text": "hello"})
            step.set_output("hello")
        run.event("cache_miss", metadata={"key": "abc"})
    assert run.status == "success"
    stored = server.runs[run.run_id]
    assert stored["status"] == "success" and stored["version"] == "1.0" and stored["environment"] == "test"
    events = server.ordered_events(run.run_id)
    assert [e["name"] for e in events] == ["retrieve_context", "generate_answer", "call_llm", "cache_miss"]
    assert [e["sequence"] for e in events] == [1, 2, 3, 4]
    assert events[0]["output_summary"] == ["doc-1", "doc-2"] and events[0]["event_type"] == "retrieval"
    assert all(e["event_id"].startswith("evt_") and len(e["event_id"]) == 36 for e in events)
    assert events[1]["duration_ms"] >= events[2]["duration_ms"]
    assert stored["finish"]["duration_ms"] > 0


def test_failed_step_reraises_original_exception(server):
    client = make_client(server)
    with pytest.raises(json.JSONDecodeError):
        with client.run("wf") as run:
            with run.step("call_llm") as s:
                s.set_output("```json {}```")
            with run.step("parse_response", input="```json {}```"):
                json.loads("```json {}```")
    assert server.runs[run.run_id]["status"] == "failed"
    events = server.ordered_events(run.run_id)
    assert [e["status"] for e in events] == ["success", "failed"]
    err = events[1]["error"]
    assert err["type"] == "json.decoder.JSONDecodeError" and "Expecting value" in err["message"]
    assert "Traceback" in err["traceback"]
    assert "JSONDecodeError" in server.runs[run.run_id]["finish"]["error_summary"]


def test_exception_outside_step_is_recorded_once(server):
    client = make_client(server)
    with pytest.raises(KeyError):
        with client.run("wf") as run:
            with run.step("ok"):
                pass
            {}["missing"]  # noqa: B018
    events = server.ordered_events(run.run_id)
    assert [e["name"] for e in events] == ["ok", "unhandled_exception"]
    assert events[1]["error"]["type"] == "KeyError"


def test_secrets_are_redacted_client_side(server):
    client = make_client(server)
    with client.run("wf", metadata={"api_key": "sk-123456789012345678901"}) as run:
        with run.step("call", metadata={"authorization": "Bearer abcdefghijklmnop", "max_tokens": 5}) as s:
            s.set_output({"note": f"key is {VALID_KEY}", "big": "x" * 10000})
    body = json.dumps(server.requests)
    assert VALID_KEY not in body.replace(f'"Bearer {VALID_KEY}"', "")
    assert "abcdefghijklmnop" not in body and "sk-1234567890" not in body
    ev = server.ordered_events(run.run_id)[0]
    assert ev["metadata"]["max_tokens"] == 5 and len(ev["output_summary"]["big"]) < 4200


def test_batching_flushes_during_run(server):
    client = make_client(server, batch_size=2)
    with client.run("wf") as run:
        for i in range(5):
            with run.step(f"s{i}"):
                pass
    posts = [r for r in server.requests if r[1].endswith("/events")]
    assert len(posts) == 3
    assert [e["sequence"] for e in server.ordered_events(run.run_id)] == [1, 2, 3, 4, 5]


# -- network failures & retries --------------------------------------------------------

def test_best_effort_when_api_unreachable(caplog):
    def down(request):
        raise httpx.ConnectError("refused", request=request)

    client = RunTraceClient(RunTraceConfig(api_key=VALID_KEY, max_retries=1), transport=httpx.MockTransport(down))
    caplog.set_level(logging.WARNING, logger="runtrace_sdk")
    result = []
    with client.run("wf") as run:
        with run.step("work"):
            result.append(42)
    assert result == [42] and run.run_id is None
    assert run.dropped_events == 1
    assert sum("telemetry unavailable" in r.getMessage() for r in caplog.records) == 1


def test_best_effort_still_reraises_app_errors():
    def down(request):
        raise httpx.ConnectError("refused", request=request)

    client = RunTraceClient(RunTraceConfig(api_key=VALID_KEY, max_retries=0), transport=httpx.MockTransport(down))
    with pytest.raises(ZeroDivisionError):
        with client.run("wf") as run:
            with run.step("divide"):
                1 / 0  # noqa: B018


def test_strict_mode_raises_on_telemetry_failure():
    def down(request):
        raise httpx.ConnectError("refused", request=request)

    client = RunTraceClient(RunTraceConfig(api_key=VALID_KEY, strict=True, max_retries=0),
                            transport=httpx.MockTransport(down))
    with pytest.raises(TelemetryError):
        with client.run("wf"):
            pass


def test_strict_mode_never_masks_app_exception(server):
    client = make_client(server, strict=True, max_retries=0)
    with pytest.raises(ValueError, match="app failure"):
        with client.run("wf") as run:
            server.fail_next.append(lambda req: httpx.Response(503, json={"error": {"code": "x", "message": "down"}}))
            with run.step("s"):
                raise ValueError("app failure")


def test_retries_are_duplicate_safe(server):
    calls = {"dropped": 0}

    def flaky(request):
        if request.url.path.endswith("/events") and not calls["dropped"]:
            # The server stores the batch, but the connection drops before the response arrives.
            calls["dropped"] += 1
            server.handle(request)
            raise httpx.ReadError("connection reset", request=request)
        return server.handle(request)

    client = RunTraceClient(RunTraceConfig(api_key=VALID_KEY, max_retries=2), transport=httpx.MockTransport(flaky))
    with client.run("wf") as run:
        with run.step("a"):
            pass
        with run.step("b"):
            pass
    events_posts = [r for r in server.requests if r[1].endswith("/events")]
    assert len(events_posts) == 2
    assert [e["event_id"] for e in events_posts[0][2]["events"]] == [e["event_id"] for e in events_posts[1][2]["events"]]
    assert len(server.events[run.run_id]) == 2
    assert server.runs[run.run_id]["status"] == "success"
    assert run.dropped_events == 0


def test_start_retry_uses_same_client_run_key(server):
    client = make_client(server)
    server.fail_next.append(lambda req: httpx.Response(503, json={"error": {"code": "down", "message": "x"}}))
    with client.run("wf") as run:
        pass
    starts = [r for r in server.requests if r[1] == "/api/runs/start"]
    assert len(starts) == 2 and starts[0][2]["client_run_key"] == starts[1][2]["client_run_key"]
    assert len(server.runs) == 1 and run.run_id in server.runs


def test_invalid_key_rejected_by_api():
    server = FakeRunTrace()
    other_key = "rt_live_" + "B" * 43
    client = RunTraceClient(RunTraceConfig(api_key=other_key, strict=True), transport=server.transport())
    with pytest.raises(TelemetryError, match="401"):
        client.verify()
