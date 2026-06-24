"""Tests for V6 learned sector contagion / read-through (pillar 3)."""

from __future__ import annotations

from datetime import datetime, timezone

from modeling.v6 import contagion as ct
from modeling.v6.impact_engine import match_event_to_holding, analyze_portfolio
from modeling.v6.exposure import get_profile, build_portfolio
from modeling.v6.schemas import MarketEvent

NOW = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)


def test_read_through_same_cluster_positive_cross_cluster_zero():
    assert ct.read_through("AVGO", "NVDA") > 0          # both AI/semis
    assert ct.read_through("MU", "AMD") > 0
    assert ct.read_through("AVGO", "JPM") == 0          # semis -> banks: none
    assert ct.read_through("NVDA", "NVDA") == 0         # self: none


def test_read_through_bounded():
    data = ct.load_contagion()
    cap = data["_meta"]["max_read_through"]
    for spec in data["clusters"].values():
        assert 0 <= spec["coefficient"] <= cap


def test_cluster_resolution_prefers_specific():
    # NVDA is in ai_semis; QQQ sits in multiple but resolves deterministically
    assert ct.cluster_of("NVDA") == "ai_semis"
    assert ct.cluster_of("JPM") == "banks"
    assert ct.cluster_of("ZZZZ") is None


def test_pure_earnings_bellwether_reaches_peer_via_contagion():
    # "MU reports earnings" carries no semis tag, so the only path to NVDA is the
    # learned read-through -- this is the AVGO effect.
    mu = MarketEvent(event_id="t-mu", title="Micron reports quarterly earnings",
                     source_type="company", event_type="earnings_date",
                     direction=-1, magnitude=4.0, affected_tags=["earnings", "guidance"],
                     related_tickers=["MU"])
    contribs = match_event_to_holding(mu, get_profile("NVDA"))
    kinds = [c["match_kind"] for c in contribs]
    assert "contagion" in kinds
    contagion_c = next(c for c in contribs if c["match_kind"] == "contagion")
    assert contagion_c["effective_direction"] == -1
    assert contagion_c["channel"] == "second_order"


def test_contagion_does_not_double_count_when_factor_path_exists():
    # An event WITH an explicit semis tag already transmits via the factor/sector
    # path; contagion must not add a second overlapping contribution.
    ev = MarketEvent(event_id="t-ai", title="NVIDIA beats on surging AI chip demand",
                     source_type="company", event_type="ai_capex_semis",
                     direction=1, magnitude=4.0,
                     affected_tags=["ai_capex", "semiconductors"], related_tickers=["NVDA"])
    amd = match_event_to_holding(ev, get_profile("AMD"))
    second_order = [c for c in amd if c["channel"] == "second_order"]
    assert len(second_order) == 1
    assert second_order[0]["match_kind"] != "contagion"


def test_contagion_visible_in_portfolio_payload():
    # Hold NVDA + AMD; an MU bellwether earnings should read through to both.
    holdings = [{"symbol": "NVDA", "weight": 0.5}, {"symbol": "AMD", "weight": 0.5}]
    mu = MarketEvent(event_id="t-mu2", title="Micron reports quarterly earnings",
                     source_type="company", event_type="earnings_date",
                     direction=-1, magnitude=4.0, affected_tags=["earnings", "guidance"],
                     related_tickers=["MU"])
    res = analyze_portfolio(build_portfolio(holdings), [mu], now=NOW)
    matched = {t for h in res["holdings"] for t in h["matched_tags"]}
    assert any("MU→" in t for t in matched)
