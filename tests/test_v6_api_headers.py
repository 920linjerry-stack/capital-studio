"""V6 -- API route freshness headers + additive payload guarantees."""

from app import app


def test_v6_intelligence_sets_no_store_headers():
    client = app.test_client()
    resp = client.get("/api/modeling/v6/intelligence")
    assert resp.status_code == 200
    cc = resp.headers.get("Cache-Control", "")
    assert "no-store" in cc
    assert "no-cache" in cc
    assert resp.headers.get("Pragma") == "no-cache"


def test_v6_intelligence_payload_is_additive_and_honest():
    client = app.test_client()
    resp = client.get("/api/modeling/v6/intelligence")
    data = resp.get_json()
    # pre-existing keys preserved (API compatibility)
    for key in ("generated_at", "data_mode", "event_count", "sources",
                "source_health", "boundaries", "portfolio", "events"):
        assert key in data
    # new freshness + breaking keys present
    for key in ("generated_at_local", "freshness", "freshness_status",
                "freshness_warning_zh", "source_mode", "alerts", "alert_summary"):
        assert key in data
    # offline default must read as fixture fallback, never "live"
    assert data["source_mode"] in ("fixture_fallback", "offline", "error")
    assert data["data_mode"] != "live"


def test_v6_intelligence_no_raw_exception_leak():
    client = app.test_client()
    resp = client.get("/api/modeling/v6/intelligence")
    body = resp.get_data(as_text=True)
    assert "Traceback" not in body
