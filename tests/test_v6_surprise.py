"""Tests for V6 Pillar 5 structured surprise."""

from __future__ import annotations

from datetime import datetime, timezone

from modeling.v6 import surprise
from modeling.v6.impact_engine import analyze_holding
from modeling.v6.replay_benchmark import load_benchmark_events
from modeling.v6.schemas import MarketEvent, HoldingExposure

NOW = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)


def test_structured_surprise_requires_traceable_source():
    event = MarketEvent(
        event_id="cpi-no-source",
        title="CPI comes in above consensus",
        source_type="macro",
        event_type="macro_inflation_hot",
        direction=-1,
        actual=3.4,
        expected=3.2,
        surprise_std=0.1,
        higher_is_bullish=False,
    )
    assert surprise.surprise_score(event) is None
    assert surprise.effective_direction(event) is None


def test_macro_surprise_flips_direction_from_headline_when_actual_below_expected():
    event = MarketEvent(
        event_id="cpi-cool-actual",
        title="CPI inflation report",
        source_type="macro",
        event_type="macro_inflation_hot",
        direction=-1,
        magnitude=4,
        confidence=0.9,
        affected_tags=["inflation", "rates"],
        actual=3.0,
        expected=3.2,
        surprise_std=0.1,
        surprise_source="BLS CPI release and structured consensus fixture",
        surprise_label="CPI YoY vs consensus",
        surprise_unit="pct",
        higher_is_bullish=False,
    )
    assert surprise.surprise_score(event) == -2.0
    assert surprise.effective_direction(event) == 1


def test_no_surprise_data_keeps_existing_direction():
    event = MarketEvent(
        event_id="plain-rate-hike",
        title="Fed raises rates 25 basis points",
        source_type="macro",
        event_type="rate_hike",
        direction=-1,
        magnitude=4,
        confidence=0.8,
        affected_tags=["rates"],
    )
    exposure = HoldingExposure(ticker="QQQ", macro_sensitivity={"rates": 1.0})
    result = analyze_holding(exposure, 1.0, [event], NOW)
    assert result["status"] == "bearish"
    assert result["contributions"][0]["surprise"] is None


def test_zero_structured_surprise_produces_no_directional_call():
    event = MarketEvent(
        event_id="as-expected-hike",
        title="Fed raises rates 25 basis points",
        source_type="macro",
        event_type="rate_hike",
        direction=-1,
        magnitude=4,
        confidence=0.8,
        affected_tags=["rates"],
        actual=25,
        expected=25,
        surprise_std=25,
        surprise_source="Federal Reserve decision and structured consensus fixture",
        surprise_label="Fed funds target change vs expected",
        surprise_unit="bp",
        higher_is_bullish=False,
    )
    exposure = HoldingExposure(ticker="QQQ", macro_sensitivity={"rates": 1.0})
    result = analyze_holding(exposure, 1.0, [event], NOW)
    assert result["status"] == "neutral"
    assert result["event_count"] == 0


def test_proxy_surprise_is_labeled_separately_from_consensus():
    event = MarketEvent(
        event_id="proxy-only",
        title="NVIDIA beats estimates but expectations are elevated",
        source_type="company",
        event_type="earnings_beat",
        direction=1,
        proxy_surprise=-1.2,
        proxy_surprise_source="pre-event drift proxy; not consensus surprise",
    )
    payload = surprise.surprise_payload(event)
    assert payload["proxy_surprise"] == -1.2
    assert payload.get("kind") != "consensus_surprise"


def test_benchmark_loads_structured_macro_surprise_observations():
    event = next(e for e in load_benchmark_events() if e.event_id == "fomc-hike-2022-03-16")
    assert event.actual == 25
    assert event.expected == 25
    assert event.surprise_source
