"""V6 -- scoring transparency, payload metadata, and summary tests."""

from datetime import datetime, timezone

from modeling.v6.api import build_intelligence_response
from modeling.v6.exposure import build_portfolio, DEMO_PORTFOLIOS
from modeling.v6.fixtures import load_fixture_events
from modeling.v6.impact_engine import analyze_portfolio

NOW = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)


def _res(name="us_megacap_tech"):
    holdings = DEMO_PORTFOLIOS[name]["holdings"]
    return analyze_portfolio(build_portfolio(holdings), load_fixture_events(now=NOW), now=NOW)


def test_holding_channel_scores_present_and_sum_consistent():
    res = _res()
    for h in res["holdings"]:
        cs = h["channel_scores"]
        assert set(cs) == {"direct", "second_order", "reflexivity", "future"}
        # direct+second_order+reflexivity equals net (future overlaps, excluded)
        recon = cs["direct"] + cs["second_order"] + cs["reflexivity"]
        assert abs(recon - h["net_impact"]) < 1e-4   # per-field rounding drift


def test_portfolio_channel_aggregate_matches_holdings():
    res = _res()
    for ch in ("direct", "second_order", "reflexivity", "future"):
        agg = sum(h["channel_scores"][ch] for h in res["holdings"])
        assert abs(agg - res["channel_scores"][ch]) < 1e-5


def test_disagreement_index_bounds_and_meaning():
    res = _res("balanced")   # mixed exposures -> some disagreement
    assert 0.0 <= res["disagreement"] <= 1.0
    # a one-sided single bullish event has zero disagreement
    from modeling.v6.schemas import MarketEvent, DIRECTION_BULLISH
    one = [MarketEvent(event_id="x", title="Apple earnings beat", event_type="earnings_beat",
                       direction=DIRECTION_BULLISH, magnitude=4, confidence=0.8,
                       related_tickers=["AAPL"])]
    r = analyze_portfolio(build_portfolio([{"symbol": "AAPL", "weight": 1.0}]), one, now=NOW)
    assert r["disagreement"] == 0.0


def test_coverage_reports_holdings_with_events():
    res = _res()
    assert 0.0 <= res["coverage"] <= 1.0
    assert res["covered_holdings"] <= res["holdings_count"]


def test_matched_tags_listed_per_holding():
    res = _res()
    aapl = next(h for h in res["holdings"] if h["ticker"] == "AAPL")
    assert "AAPL" in aapl["matched_tags"]
    assert isinstance(aapl["matched_tags"], list)


def test_payload_metadata_shape():
    p = build_intelligence_response(None, now=NOW)
    assert p["version"].startswith("v6.")
    assert p["generated_at"].endswith("Z")
    s = p["summary"]
    assert set(s["by_direction"]) == {"bullish", "bearish", "neutral"}
    assert sum(s["by_direction"].values()) == p["event_count"]
    assert s["scheduled_count"] >= 4   # the bundled future catalysts
    assert s["by_event_type"] and s["by_source_type"] and s["by_data_mode"]


def test_risk_summary_lists_negatives_and_priced_in():
    p = build_intelligence_response(None, now=NOW)
    r = p["risks"]
    assert all(d["net_impact"] < 0 for d in r["top_negative_drivers"])
    # earnings (sell-news 0.45) and product (0.5) qualify as priced-in catalysts
    assert any(d["event_type"] in ("earnings_date", "product_launch")
               for d in r["priced_in_catalysts"])


def test_macro_does_not_swamp_direct_company_event():
    # A direct earnings beat should dominate a single broad macro print for a
    # holding, because macro relevance is damped.
    from modeling.v6.schemas import MarketEvent, DIRECTION_BULLISH, DIRECTION_BEARISH
    from modeling.v6.exposure import get_profile
    from modeling.v6.impact_engine import analyze_holding
    company = MarketEvent(event_id="c", title="Apple earnings beat", event_type="earnings_beat",
                          direction=DIRECTION_BULLISH, magnitude=4, confidence=0.8,
                          related_tickers=["AAPL"])
    macro = MarketEvent(event_id="m", title="Treasury yields rise", event_type="yields_up",
                        direction=DIRECTION_BEARISH, magnitude=3, confidence=0.6,
                        affected_tags=["yields"])
    res = analyze_holding(get_profile("AAPL"), 1.0, [company, macro], now=NOW)
    # net should remain bullish: the direct company event outweighs the macro one
    assert res["net_impact"] > 0
    assert res["status"] in ("bullish", "mixed")
