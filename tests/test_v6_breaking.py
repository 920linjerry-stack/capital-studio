"""V6 -- breaking-news / sudden-sentiment detector tests (deterministic)."""

from datetime import datetime, timedelta, timezone

from modeling.v6.schemas import MarketEvent
from modeling.v6.breaking import detect_breaking
from modeling.v6.templates import contains_banned_phrase

NOW = datetime(2026, 6, 23, 12, 0, 0, tzinfo=timezone.utc)


def _ev(eid, *, hours_ago, ticker=None, direction=1, etype="uncategorized",
        magnitude=3.0, source="Public News", tags=None):
    ts = (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return MarketEvent(
        event_id=eid, title=f"{ticker or 'mkt'} {etype} headline", source=source,
        timestamp=ts, effective_at=ts, event_type=etype, direction=direction,
        magnitude=magnitude, data_mode="live",
        related_tickers=[ticker] if ticker else [], affected_tags=tags or [],
    )


def test_clustered_fresh_headlines_raise_urgency():
    evs = [
        _ev("a", hours_ago=0.2, ticker="NVDA", etype="guidance_raise", source="Yahoo"),
        _ev("b", hours_ago=0.5, ticker="NVDA", etype="ai_capex_semis", source="Google News"),
        _ev("c", hours_ago=1.0, ticker="NVDA", etype="analyst_upgrade", source="Analyst"),
    ]
    out = detect_breaking(evs, now=NOW)
    assert out["alerts"], "expected at least one alert for a fresh cluster"
    top = out["alerts"][0]
    assert top["urgency"] in ("breaking", "elevated")
    assert "NVDA" in top["affected_tickers"]
    assert out["summary"]["max_urgency"] in ("breaking", "elevated")


def test_old_clustered_headlines_do_not_raise_urgency():
    evs = [
        _ev("a", hours_ago=30, ticker="NVDA", etype="guidance_raise"),
        _ev("b", hours_ago=31, ticker="NVDA", etype="ai_capex_semis"),
        _ev("c", hours_ago=32, ticker="NVDA", etype="analyst_upgrade"),
    ]
    out = detect_breaking(evs, now=NOW)
    assert out["alerts"] == []
    assert out["summary"]["max_urgency"] == "normal"


def test_conflicting_directions_mark_mixed():
    evs = [
        _ev("a", hours_ago=0.5, ticker="AAPL", direction=1, etype="guidance_raise", source="Yahoo"),
        _ev("b", hours_ago=1.0, ticker="AAPL", direction=-1, etype="price_target_cut", source="Analyst"),
    ]
    out = detect_breaking(evs, now=NOW)
    aapl = [a for a in out["alerts"] if "AAPL" in a["affected_tickers"]]
    assert aapl, "expected an AAPL alert"
    assert aapl[0]["dominant_direction"] == "mixed"


def test_source_failure_creates_honest_alert():
    statuses = [
        {"source_id": "yahoo", "source_name": "Yahoo Finance RSS", "mode": "error", "error": "timeout"},
        {"source_id": "google", "source_name": "Google News RSS", "mode": "unavailable"},
    ]
    out = detect_breaking([], now=NOW, source_statuses=statuses)
    assert any(a["alert_type"] == "source_failure" for a in out["alerts"])
    assert out["summary"]["has_source_failure"] is True


def test_urgent_single_event_surfaces():
    evs = [_ev("s", hours_ago=0.3, ticker="XOM", etype="sanctions", magnitude=4.5)]
    out = detect_breaking(evs, now=NOW)
    assert out["alerts"], "a fresh sanctions headline should surface"


def test_macro_cluster_classifies_as_macro_shock():
    evs = [
        _ev("a", hours_ago=0.3, etype="cpi_hot", magnitude=4.0, tags=["inflation"], source="Yahoo"),
        _ev("b", hours_ago=0.6, etype="yields_up", magnitude=3.5, tags=["yields"], source="Google News"),
        _ev("c", hours_ago=1.2, etype="rate_hike", magnitude=4.0, tags=["rates"], source="Macro"),
    ]
    out = detect_breaking(evs, now=NOW)
    types = {a["alert_type"] for a in out["alerts"]}
    assert types & {"macro_shock", "sentiment_shock", "headline_velocity", "sector_shock"}


def test_alerts_carry_required_fields_and_no_advice():
    evs = [
        _ev("a", hours_ago=0.2, ticker="NVDA", etype="guidance_raise", source="Yahoo"),
        _ev("b", hours_ago=0.5, ticker="NVDA", etype="ai_capex_semis", source="Google News"),
        _ev("c", hours_ago=1.0, ticker="NVDA", direction=-1, etype="price_target_cut", source="Analyst"),
    ]
    out = detect_breaking(evs, now=NOW)
    required = {
        "urgency", "urgency_score", "alert_type", "title_zh", "summary_zh",
        "affected_tickers", "affected_tags", "dominant_direction", "confidence",
        "evidence_count", "source_count", "first_seen_at", "last_seen_at",
        "freshness_status",
    }
    for a in out["alerts"]:
        assert required <= set(a)
        # generated Chinese must never contain trade instructions
        assert contains_banned_phrase(a["title_zh"]) is None
        assert contains_banned_phrase(a["summary_zh"], ignore_quoted=True) is None


def test_empty_input_is_quiet():
    out = detect_breaking([], now=NOW)
    assert out["alerts"] == []
    assert out["summary"]["total"] == 0
