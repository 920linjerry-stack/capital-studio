"""V6 -- matching, scoring, aggregation, and portfolio-weighting tests."""


from modeling.v6.schemas import (
    MarketEvent,
    HoldingExposure,
    DIRECTION_BULLISH,
    DIRECTION_BEARISH,
)
from modeling.v6.exposure import build_portfolio, get_profile
from modeling.v6.fixtures import load_fixture_events
from modeling.v6.impact_engine import (
    match_event_to_holding,
    score_contribution,
    analyze_holding,
    analyze_portfolio,
)


# --- matching -------------------------------------------------------------

def test_direct_company_match_by_ticker():
    ev = MarketEvent(event_id="d1", title="Apple raises guidance",
                     event_type="guidance_raise", direction=DIRECTION_BULLISH,
                     magnitude=4.0, confidence=0.8, related_tickers=["AAPL"])
    aapl = get_profile("AAPL")
    contribs = match_event_to_holding(ev, aapl)
    channels = {c["channel"] for c in contribs}
    assert "direct" in channels
    direct = [c for c in contribs if c["channel"] == "direct"][0]
    assert direct["effective_direction"] == DIRECTION_BULLISH
    assert direct["relevance"] == 1.0


def test_macro_sensitivity_flips_sign_for_contra_holding():
    # A broadly-bullish rate cut should read BEARISH for a bank (negative beta).
    ev = MarketEvent(event_id="m1", title="Fed cuts rates",
                     event_type="rate_cut", direction=DIRECTION_BULLISH,
                     magnitude=4.0, confidence=0.8, affected_tags=["rates"])
    bank = get_profile("000001.SZ")
    growth = get_profile("AAPL")
    bank_dir = [c for c in match_event_to_holding(ev, bank) if "rates" in c["matched_terms"]][0]
    growth_dir = [c for c in match_event_to_holding(ev, growth) if "rates" in c["matched_terms"]][0]
    assert bank_dir["effective_direction"] == DIRECTION_BEARISH
    assert growth_dir["effective_direction"] == DIRECTION_BULLISH


def test_second_order_channel_matches_transmission_tag():
    ev = MarketEvent(event_id="s1", title="AI capex surges",
                     event_type="ai_capex_semis", direction=DIRECTION_BULLISH,
                     magnitude=4.0, confidence=0.7, affected_tags=["ai_capex"])
    # CATL has ai_capex as a second-order exposure (not a direct factor tag).
    catl = get_profile("300750.SZ")
    contribs = match_event_to_holding(ev, catl)
    assert any(c["channel"] == "second_order" for c in contribs)


def test_reflexivity_channel_for_sentiment_event():
    ev = MarketEvent(event_id="r1", title="Risk-off sell-off",
                     event_type="risk_off", direction=DIRECTION_BEARISH,
                     magnitude=3.0, confidence=0.6, affected_tags=["risk_sentiment"])
    broker = get_profile("600030.SS")  # high reflexivity
    contribs = match_event_to_holding(ev, broker)
    reflex = [c for c in contribs if c["channel"] == "reflexivity"]
    assert reflex and reflex[0]["effective_direction"] == DIRECTION_BEARISH


def test_no_match_returns_empty():
    ev = MarketEvent(event_id="n1", title="Unrelated headline",
                     event_type="uncategorized", direction=0, magnitude=1.0,
                     affected_tags=["totally_unrelated_tag"])
    holding = HoldingExposure(ticker="ZZZZ", factor_tags=["nothing"],
                              macro_sensitivity={}, second_order_exposure=[],
                              reflexivity_exposure=0.0)
    assert match_event_to_holding(ev, holding) == []


# --- scoring --------------------------------------------------------------

def test_scoring_formula_is_transparent_product():
    ev = MarketEvent(event_id="sc1", title="x", direction=DIRECTION_BULLISH,
                     magnitude=4.0, confidence=0.5)
    contrib = {"channel": "direct", "effective_direction": 1, "relevance": 0.5,
               "matched_terms": []}
    # weight*dir*mag*rel*conf*decay = 0.25*1*4*0.5*0.5*1 = 0.25
    assert score_contribution(ev, 0.25, contrib) == 0.25


def test_negative_direction_yields_negative_impact():
    ev = MarketEvent(event_id="sc2", title="x", direction=DIRECTION_BEARISH,
                     magnitude=3.0, confidence=1.0)
    contrib = {"channel": "direct", "effective_direction": -1, "relevance": 1.0,
               "matched_terms": []}
    assert score_contribution(ev, 0.5, contrib) < 0


# --- holding aggregation --------------------------------------------------

def test_conflicting_events_aggregate_to_mixed():
    bull = MarketEvent(event_id="c1", title="Apple raises guidance",
                       event_type="guidance_raise", direction=DIRECTION_BULLISH,
                       magnitude=4.0, confidence=0.8, related_tickers=["AAPL"])
    bear = MarketEvent(event_id="c2", title="Apple price target cut",
                       event_type="price_target_cut", direction=DIRECTION_BEARISH,
                       magnitude=4.0, confidence=0.8, related_tickers=["AAPL"])
    res = analyze_holding(get_profile("AAPL"), 1.0, [bull, bear])
    assert res["status"] == "mixed"
    assert res["bullish_count"] >= 1 and res["bearish_count"] >= 1


def test_all_bullish_events_aggregate_to_bullish():
    bull = MarketEvent(event_id="b1", title="Apple earnings beat",
                       event_type="earnings_beat", direction=DIRECTION_BULLISH,
                       magnitude=4.0, confidence=0.8, related_tickers=["AAPL"])
    res = analyze_holding(get_profile("AAPL"), 1.0, [bull])
    assert res["status"] == "bullish"
    assert res["net_impact"] > 0


def test_low_confidence_signal_reads_uncertain():
    weak = MarketEvent(event_id="u1", title="Apple minor note",
                       event_type="analyst_upgrade", direction=DIRECTION_BULLISH,
                       magnitude=2.0, confidence=0.2, related_tickers=["AAPL"])
    res = analyze_holding(get_profile("AAPL"), 1.0, [weak])
    assert res["status"] == "uncertain"


def test_holding_detail_groups_three_channels():
    res = analyze_holding(get_profile("AAPL"), 1.0, load_fixture_events())
    assert set(res["channels"].keys()) == {"direct", "second_order", "reflexivity"}


# --- portfolio weighting --------------------------------------------------

def test_portfolio_weighting_scales_impact():
    bull = MarketEvent(event_id="w1", title="Apple earnings beat",
                       event_type="earnings_beat", direction=DIRECTION_BULLISH,
                       magnitude=4.0, confidence=0.8, related_tickers=["AAPL"])
    heavy = build_portfolio([{"symbol": "AAPL", "weight": 0.9},
                             {"symbol": "0700.HK", "weight": 0.1}])
    light = build_portfolio([{"symbol": "AAPL", "weight": 0.1},
                             {"symbol": "0700.HK", "weight": 0.9}])
    r_heavy = analyze_portfolio(heavy, [bull])
    r_light = analyze_portfolio(light, [bull])
    # Same event, larger AAPL weight -> larger portfolio net impact.
    assert r_heavy["net_impact_score"] > r_light["net_impact_score"]


def test_equal_weight_fallback_is_flagged():
    pf = build_portfolio([{"symbol": "AAPL"}, {"symbol": "0700.HK"}])
    assert pf["weight_is_fallback"] is True
    assert pf["weighting"] == "equal-weight"
    res = analyze_portfolio(pf, load_fixture_events())
    assert res["weight_is_fallback"] is True


def test_synthetic_cost_basis_portfolio_runs_end_to_end():
    holdings = [
        {"symbol": "AAPL", "cost_price": 100.0, "quantity": 2.0},
        {"symbol": "0700.HK", "cost_price": 300.0, "quantity": 1.0},
    ]
    res = analyze_portfolio(build_portfolio(holdings), load_fixture_events())
    assert res["holdings_count"] == len(holdings)
    assert res["status"] in {"bullish", "bearish", "neutral", "mixed", "uncertain"}
    assert res["weighting"] == "cost-basis"
    assert res["main_drivers"]
    assert res["top_positive_contributors"] or res["top_negative_contributors"]

