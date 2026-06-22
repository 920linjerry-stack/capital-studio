"""V6 -- source adapter errors must never leak raw exception text to clients.

Fault-injects exceptions whose message embeds private Windows paths, URL query
secrets, bearer tokens, and passwords, then asserts none of that reaches the API
response -- only fixed, public-safe fields do.
"""

import json

import pytest

from modeling.v6.sources import registry
from modeling.v6.sources.base import (
    public_error_status, sanitize_source_status, FetchResult,
    _GENERIC_ERROR_EN, _GENERIC_ERROR_ZH,
)
from modeling.v6.api import build_intelligence_response

# A single blob packing every category the sanitizer must strip.
SECRET_BLOB = (
    r"D:\Users\Jerry\secret_token=abc123 "
    r"https://example.com/feed?api_key=secret123&token=abc "
    r"Bearer sk-test-123 password=hunter2 "
    r"Traceback (most recent call last): File C:\Users\Jerry\app.py"
)
FORBIDDEN = [
    r"D:\Users", r"C:\Users", "Jerry", "secret_token", "abc123",
    "api_key", "secret123", "token=abc", "Bearer sk-test-123",
    "password=hunter2", "hunter2", "Traceback", "example.com",
]


def _payload_with_injected_error(monkeypatch, exc):
    """Force the first source adapter to raise ``exc`` and return the payload."""
    registry._CACHE.clear()
    adapter = registry.SOURCE_REGISTRY[0]

    def boom(*args, **kwargs):
        raise exc

    monkeypatch.setattr(adapter, "fetch", boom)
    payload = build_intelligence_response(portfolio_is_demo=True)
    registry._CACHE.clear()
    return payload


def _dump(payload) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


# --- unit: the sanitizer primitives ---------------------------------------

def test_public_error_status_never_includes_raw_text():
    status = public_error_status(RuntimeError(SECRET_BLOB))
    blob = _dump(status)
    for bad in FORBIDDEN:
        assert bad not in blob
    assert status["is_sanitized"] is True
    assert status["error"] == _GENERIC_ERROR_EN
    assert status["error_zh"] == _GENERIC_ERROR_ZH
    assert status["error_code"] in {
        "source_fetch_failed", "source_timeout", "source_parse_failed",
        "source_unavailable", "unknown_source_error",
    }


def test_classification_by_exception_class():
    assert public_error_status(TimeoutError("boom"))["error_code"] == "source_timeout"
    assert public_error_status(ValueError("bad json"))["error_code"] == "source_parse_failed"
    assert public_error_status(ConnectionError("net"))["error_code"] == "source_fetch_failed"
    assert public_error_status(RuntimeError("x"))["error_code"] == "unknown_source_error"


def test_sanitize_status_replaces_raw_error_field():
    raw = {"source_id": "x", "source_name": "X", "mode": "error", "error": SECRET_BLOB}
    clean = sanitize_source_status(raw)
    assert clean["error"] == _GENERIC_ERROR_EN
    assert clean["is_sanitized"] is True
    blob = _dump(clean)
    for bad in FORBIDDEN:
        assert bad not in blob


def test_fetchresult_to_status_is_sanitized():
    fr = FetchResult("x", "X", "error", [], error=SECRET_BLOB)
    status = fr.to_status()
    assert status["error"] == _GENERIC_ERROR_EN
    blob = _dump(status)
    for bad in FORBIDDEN:
        assert bad not in blob


def test_ok_status_has_empty_error_and_no_sanitized_noise():
    fr = FetchResult("x", "X", "fixture", [])
    status = fr.to_status()
    assert status["error"] == ""
    assert "error_zh" not in status
    assert "is_sanitized" not in status


# --- integration: full API payload after fault injection ------------------

def test_api_payload_has_no_raw_exception_after_injection(monkeypatch):
    payload = _payload_with_injected_error(monkeypatch, RuntimeError(SECRET_BLOB))
    blob = _dump(payload)
    for bad in FORBIDDEN:
        assert bad not in blob, f"leaked: {bad}"


def test_api_payload_keeps_public_safe_error_fields(monkeypatch):
    payload = _payload_with_injected_error(monkeypatch, RuntimeError(SECRET_BLOB))
    errored = [s for s in payload["sources"] if s.get("mode") == "error"]
    assert errored, "expected at least one errored source row"
    for s in errored:
        assert s["error"] == _GENERIC_ERROR_EN
        assert s.get("error_zh") == _GENERIC_ERROR_ZH
        assert s.get("is_sanitized") is True
        assert s.get("error_code") in {
            "source_fetch_failed", "source_timeout", "source_parse_failed",
            "source_unavailable", "unknown_source_error",
        }


def test_injected_error_still_drives_source_failure_and_freshness(monkeypatch):
    payload = _payload_with_injected_error(monkeypatch, RuntimeError(SECRET_BLOB))
    # source-mode honest degradation + freshness warning still works
    assert payload["source_mode"] in ("error", "offline", "partial_live", "fixture_fallback")
    # breaking layer still surfaces an honest source-failure alert
    assert payload["alert_summary"]["has_source_failure"] is True
    assert any(a["alert_type"] == "source_failure" for a in payload["alerts"])


def test_timeout_injection_classified_without_leak(monkeypatch):
    payload = _payload_with_injected_error(monkeypatch, TimeoutError(SECRET_BLOB))
    blob = _dump(payload)
    for bad in FORBIDDEN:
        assert bad not in blob
    errored = [s for s in payload["sources"] if s.get("mode") == "error"]
    assert any(s.get("error_code") == "source_timeout" for s in errored)
