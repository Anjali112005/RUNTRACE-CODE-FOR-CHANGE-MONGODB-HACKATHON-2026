from app.security import (SlidingWindowLimiter, canonical_hash, generate_event_id, generate_project_api_key,
                          generate_project_id, generate_run_id, hash_api_key, key_display_prefix, looks_like_api_key,
                          redact, truncate, ID_PATTERNS)


def test_ids_are_prefixed_and_unique():
    ids = {generate_run_id() for _ in range(2000)}
    assert len(ids) == 2000
    assert all(ID_PATTERNS["run"].match(i) for i in ids)
    assert ID_PATTERNS["project"].match(generate_project_id())
    assert ID_PATTERNS["event"].match(generate_event_id())


def test_api_key_format_and_hash():
    key = generate_project_api_key()
    assert key.startswith("rt_live_") and looks_like_api_key(key)
    assert hash_api_key(key) == hash_api_key(key)
    assert hash_api_key(key) != hash_api_key(generate_project_api_key())
    assert key not in hash_api_key(key)
    assert len(key_display_prefix(key)) == len("rt_live_") + 4
    assert not looks_like_api_key("rt_live_short")


def test_redaction_by_key_and_pattern():
    data = {
        "api_key": "abc123", "Authorization": "Bearer abcdefghijkl", "nested": {"password": "hunter2"},
        "max_tokens": 512, "prompt_tokens": 40, "tokenizer": "cl100k",
        "note": "used key rt_live_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA ok",
        "dsn": "mongodb+srv://user:pa55@cluster.example.net/db",
        "credentials": {"user": "x", "token": "y"},
    }
    out = redact(data)
    assert out["api_key"] == "[REDACTED]"
    assert out["Authorization"] == "[REDACTED]"
    assert out["nested"]["password"] == "[REDACTED]"
    assert out["max_tokens"] == 512 and out["prompt_tokens"] == 40 and out["tokenizer"] == "cl100k"
    assert "AAAAAAAA" not in out["note"]
    assert "pa55" not in out["dsn"]
    assert out["credentials"] == {"user": "[REDACTED]", "token": "[REDACTED]"}


def test_extra_redact_keys():
    assert redact({"customer_ssn": "123"}, extra_keys=["customer_ssn"]) == {"customer_ssn": "[REDACTED]"}


def test_truncate_bounds_size():
    out = truncate({"text": "x" * 500, "items": list(range(300))}, 100)
    assert len(out["text"]) < 150 and "truncated" in out["text"]
    assert len(out["items"]) == 201


def test_canonical_hash_is_order_independent():
    assert canonical_hash({"a": 1, "b": [1, 2]}) == canonical_hash({"b": [1, 2], "a": 1})
    assert canonical_hash({"a": 1}) != canonical_hash({"a": 2})


def test_rate_limiter():
    limiter = SlidingWindowLimiter(2, 60)
    assert limiter.check("k")[0] and limiter.check("k")[0]
    allowed, retry = limiter.check("k")
    assert not allowed and retry >= 1
    assert limiter.check("other")[0]
