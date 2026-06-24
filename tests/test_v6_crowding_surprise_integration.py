"""Integration coverage for V6 Pillar 4/5 payloads."""

from __future__ import annotations

from datetime import datetime, timezone

from modeling.v6.api import build_intelligence_response
from modeling.v6.schemas import MarketEvent

NOW = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)


def test_api_exposes_crowding_state_on_holdings():
    response = build_intelligence_response(
        [{"ticker": "AVGO", "market_value": 1000}],
        events=[
            MarketEvent(
                event_id="avgo-beat",
                title="Broadcom beats estimates on AI demand",
                source_type="company",
                event_type="earnings_beat",
                direction=1,
                magnitude=4,
                confidence=0.8,
                affected_tags=["earnings"],
                related_tickers=["AVGO"],
            )
        ],
        now=NOW,
        include_calendar=False,
    )
    holding = response["portfolio"]["holdings"][0]
    assert holding["crowding_state"]["band"] == "high"
    assert "priced_for_perfection" in holding["crowding_state"]


def test_api_exposes_consensus_surprise_on_events_and_contributions():
    event = MarketEvent(
        event_id="cpi-cool",
        title="CPI inflation report",
        source_type="macro",
        event_type="macro_inflation_hot",
        direction=-1,
        magnitude=4,
        confidence=0.9,
        affected_tags=["rates"],
        actual=3.0,
        expected=3.2,
        surprise_std=0.1,
        surprise_source="BLS CPI release and structured consensus fixture",
        surprise_label="CPI YoY vs consensus",
        surprise_unit="pct",
        higher_is_bullish=False,
    )
    response = build_intelligence_response(
        [{"ticker": "QQQ", "market_value": 1000}],
        events=[event],
        now=NOW,
        include_calendar=False,
    )
    assert response["events"][0]["surprise"]["kind"] == "consensus_surprise"
    contribution = response["portfolio"]["holdings"][0]["contributions"][0]
    assert contribution["surprise"]["score"] == -2.0
    assert contribution["effective_direction"] == 1
