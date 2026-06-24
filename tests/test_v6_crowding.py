"""Tests for V6 Pillar 4 crowding / priced-for-perfection proxy."""

from __future__ import annotations

from datetime import datetime, timezone

from modeling.v6 import crowding
from modeling.v6.impact_engine import analyze_holding
from modeling.v6.schemas import MarketEvent, HoldingExposure, DIRECTION_BULLISH

NOW = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)


def _earnings_beat(ticker: str) -> MarketEvent:
    return MarketEvent(
        event_id=f"beat-{ticker}",
        title=f"{ticker} beats estimates on strong AI demand",
        source_type="company",
        source="Fixture",
        timestamp="2026-06-24T12:00:00Z",
        event_type="earnings_beat",
        direction=DIRECTION_BULLISH,
        magnitude=4,
        confidence=0.8,
        affected_tags=["earnings"],
        related_tickers=[ticker],
    )


def test_crowding_snapshot_loads_as_price_proxy_not_valuation():
    snap = crowding.load_crowding_snapshot()
    assert snap.get("tickers")
    assert "price-only" in snap["_meta"]["method"]
    assert "not valuation" in snap["_meta"]["method"]
    avgo = crowding.crowding_state("AVGO", snap)
    assert avgo["band"] == "high"
    assert 0 <= avgo["priced_for_perfection"] <= 1


def test_missing_crowding_is_neutral_noop():
    state = crowding.crowding_state("NO_SUCH_TICKER", {"tickers": {}})
    assert state["priced_for_perfection"] == 0.5
    assert crowding.reaction_multiplier(1, state) == 1.0
    assert crowding.reaction_multiplier(-1, state) == 1.0


def test_high_crowding_earnings_beat_damps_or_flips_expected_bp():
    high = HoldingExposure(ticker="AVGO", name="Broadcom")
    low = HoldingExposure(ticker="UNH", name="UnitedHealth")
    high_result = analyze_holding(high, 1.0, [_earnings_beat("AVGO")], NOW)
    low_result = analyze_holding(low, 1.0, [_earnings_beat("UNH")], NOW)

    high_bp = high_result["expected_abnormal_bp"]
    low_bp = low_result["expected_abnormal_bp"]
    assert high_result["crowding_state"]["band"] == "high"
    assert low_result["crowding_state"]["priced_for_perfection"] < 0.5
    assert high_bp < low_bp
    assert low_bp > 0


def test_high_crowding_negative_event_is_amplified():
    event = MarketEvent(
        event_id="miss-AVGO",
        title="Broadcom misses estimates and cuts guidance",
        source_type="company",
        source="Fixture",
        timestamp="2026-06-24T12:00:00Z",
        event_type="earnings_miss",
        direction=-1,
        magnitude=4,
        confidence=0.8,
        affected_tags=["earnings", "guidance"],
        related_tickers=["AVGO"],
    )
    result = analyze_holding(HoldingExposure(ticker="AVGO"), 1.0, [event], NOW)
    row = result["contributions"][0]
    assert row["crowding_adjust"] > 1
    assert result["expected_abnormal_bp"] < 0
