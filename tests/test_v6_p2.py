"""V6 P2 -- bands, narrative/themes, weighting modes, EDGAR coverage."""

from datetime import datetime, timezone

from modeling.v6 import templates
from modeling.v6.api import build_intelligence_response
from modeling.v6.exposure import build_portfolio
from modeling.v6.fixtures import load_fixture_events
from modeling.v6.impact_engine import analyze_portfolio
from modeling.v6.narrative import group_events, portfolio_narrative, THEME_CN
from modeling.v6.sources.adapters import _CIK, _FORM_LABELS, SecEdgar

NOW = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)


# --- bands ---------------------------------------------------------------

def test_severity_bands_thresholds():
    assert templates.severity_band(1.0) == "low"
    assert templates.severity_band(2.0) == "medium"
    assert templates.severity_band(3.5) == "high"
    assert templates.severity_band(4.5) == "extreme"
    assert templates.severity_cn(4.6) == "极高"


def test_confidence_and_disagreement_bands():
    assert templates.confidence_band_cn(0.2) == "低"
    assert templates.confidence_band_cn(0.5) == "中"
    assert templates.confidence_band_cn(0.8) == "高"
    assert templates.disagreement_band(0.7) == "high"
    assert templates.disagreement_band(0.1) == "low"


def test_freshness_labels():
    assert templates.freshness_cn("live") == "新鲜"
    assert templates.freshness_cn("fixture") == "示例回退"
    assert "实时" in templates.freshness_cn("live-partial")


def test_payload_exposes_event_and_portfolio_bands():
    p = build_intelligence_response(None, now=NOW)
    assert set(p["bands"]) >= {"disagreement_cn", "confidence_cn", "freshness_cn"}
    e = p["events"][0]
    assert e["severity"] in ("low", "medium", "high", "extreme")
    assert e["confidence_band_cn"] in ("低", "中", "高")


# --- narrative + themes --------------------------------------------------

def _analysis(name=None):
    holdings = None
    res = analyze_portfolio(build_portfolio(holdings), load_fixture_events(now=NOW), now=NOW)
    return res


def test_group_events_buckets_into_known_themes():
    groups = group_events(_analysis())
    assert groups
    for g in groups:
        assert g["theme"] in THEME_CN
        assert g["theme_cn"] == THEME_CN[g["theme"]]
        assert g["event_count"] >= 1


def test_groups_sorted_by_abs_impact():
    groups = group_events(_analysis())
    abs_imp = [g["abs_impact"] for g in groups]
    assert abs_imp == sorted(abs_imp, reverse=True)


def test_narrative_is_chinese_and_advice_free():
    nar = portfolio_narrative(_analysis())
    assert any("一" <= ch <= "鿿" for ch in nar)
    assert templates.contains_banned_phrase(nar, ignore_quoted=True) is None
    assert "非投资建议" in nar


def test_narrative_mentions_future_catalyst():
    nar = portfolio_narrative(_analysis())
    assert "未来" in nar


def test_narrative_has_hedge_conclusion():
    nar = portfolio_narrative(_analysis())
    assert "多空对冲后" in nar
    assert "净" in nar


def test_semis_theme_present_for_ai_capex():
    groups = group_events(_analysis())
    themes = {g["theme"] for g in groups}
    # the bundled AI-capex/semis event routes to the 半导体供应链 theme
    assert "semis" in themes
    assert THEME_CN["semis"] == "半导体供应链"


# --- weighting modes -----------------------------------------------------

def test_market_value_weighting_when_present():
    holdings = [
        {"symbol": "AAPL", "market_value_base": 9000.0},
        {"symbol": "MSFT", "market_value_base": 1000.0},
    ]
    pf = build_portfolio(holdings)
    assert pf["weighting"] == "market-value"
    assert pf["weight_is_fallback"] is False
    w = {p["exposure"].ticker: p["weight"] for p in pf["positions"]}
    assert abs(w["AAPL"] - 0.9) < 1e-6


def test_cost_basis_weighting_fallback():
    holdings = [
        {"symbol": "AAPL", "cost_price": 100, "quantity": 10},
        {"symbol": "MSFT", "cost_price": 100, "quantity": 90},
    ]
    pf = build_portfolio(holdings)
    assert pf["weighting"] == "cost-basis"
    assert pf["weight_is_fallback"] is False


def test_equal_weight_fallback_when_no_data():
    pf = build_portfolio([{"symbol": "AAPL"}, {"symbol": "MSFT"}])
    assert pf["weighting"] == "equal-weight"
    assert pf["weight_is_fallback"] is True


def test_weighting_changes_portfolio_score():
    events = load_fixture_events(now=NOW)
    heavy_aapl = analyze_portfolio(build_portfolio(
        [{"symbol": "AAPL", "market_value_base": 9000}, {"symbol": "JPM", "market_value_base": 1000}]), events, now=NOW)
    heavy_jpm = analyze_portfolio(build_portfolio(
        [{"symbol": "AAPL", "market_value_base": 1000}, {"symbol": "JPM", "market_value_base": 9000}]), events, now=NOW)
    assert heavy_aapl["net_impact_score"] != heavy_jpm["net_impact_score"]


# --- EDGAR coverage ------------------------------------------------------

def test_edgar_cik_coverage_expanded():
    for t in ["AAPL", "MSFT", "NVDA", "AMZN", "AVGO", "ASML", "BAC", "GS", "CVX", "LLY", "TSM"]:
        assert t in _CIK and _CIK[t].isdigit() and len(_CIK[t]) == 10


def test_edgar_form_labels_present():
    assert "8-K" in _FORM_LABELS and "10-Q" in _FORM_LABELS


def test_edgar_fixture_mode_offline():
    res = SecEdgar().fetch(tickers=["AAPL"], allow_network=False)
    assert res.mode == "fixture"
    assert res.items and res.items[0].related_tickers == ["AAPL"]


# --- source health -------------------------------------------------------

def test_source_status_carries_reliability_and_last_seen():
    from modeling.v6.sources.registry import ingest_events
    _, statuses = ingest_events(allow_network=False)
    for s in statuses:
        assert {"reliability", "last_success", "last_error",
                "success_count", "error_count"} <= set(s)
    # fixture mode counts as a success, so reliability is not 异常
    assert all(s["reliability"] != "异常" for s in statuses)
    assert any(s["success_count"] >= 1 for s in statuses)


def test_source_health_summary_shape_and_flags():
    from modeling.v6.sources.registry import source_health
    h = source_health([{"mode": "fixture"}, {"mode": "fixture"}, {"mode": "error"}])
    assert h["any_error"] is True
    assert h["all_fixture"] is False
    assert h["total"] == 3
    h2 = source_health([{"mode": "fixture"}, {"mode": "fixture"}])
    assert h2["all_fixture"] is True and h2["any_error"] is False


def test_payload_includes_source_health():
    p = build_intelligence_response(None, now=NOW)
    h = p["source_health"]
    assert set(h) >= {"by_mode", "any_error", "all_fixture", "overall"}
    assert h["all_fixture"] is True   # offline default


# --- per-event portfolio relevance (feed ranking) ------------------------

def test_events_carry_portfolio_relevance():
    p = build_intelligence_response(None, now=NOW)
    for e in p["events"]:
        assert "portfolio_abs_impact" in e
        assert "portfolio_net_impact" in e
        assert "holdings_hit" in e
        assert e["portfolio_abs_impact"] >= 0.0


def test_relevance_matches_driver_aggregation():
    p = build_intelligence_response(None, now=NOW)
    drivers = {d["event_id"]: d for d in p["portfolio"]["main_drivers"]}
    for e in p["events"]:
        if e["event_id"] in drivers:
            assert abs(e["portfolio_abs_impact"] - drivers[e["event_id"]]["abs_impact"]) < 1e-9
            assert e["holdings_hit"] == drivers[e["event_id"]]["holdings_hit"]


def test_some_event_has_nonzero_relevance():
    p = build_intelligence_response(None, now=NOW)
    assert any(e["portfolio_abs_impact"] > 0 for e in p["events"])
