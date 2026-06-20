"""V6 -- deterministic event classifier tests."""

import pytest

from modeling.v6.classifier import classify_text, classify_event
from modeling.v6.schemas import (
    MarketEvent,
    DIRECTION_BULLISH,
    DIRECTION_BEARISH,
    DIRECTION_NEUTRAL,
)


@pytest.mark.parametrize("title,etype,direction", [
    ("Goldman upgrades Tesla to buy", "analyst_upgrade", DIRECTION_BULLISH),
    ("Analyst downgrades Meta to underweight", "analyst_downgrade", DIRECTION_BEARISH),
    ("Broker raises price target on Apple", "price_target_raise", DIRECTION_BULLISH),
    ("Bank cuts price target on Nvidia", "price_target_cut", DIRECTION_BEARISH),
    ("Microsoft earnings beat estimates", "earnings_beat", DIRECTION_BULLISH),
    ("Intel misses estimates on weak demand", "earnings_miss", DIRECTION_BEARISH),
    ("Company raises guidance for full year", "guidance_raise", DIRECTION_BULLISH),
    ("Retailer cuts guidance amid soft sales", "guidance_cut", DIRECTION_BEARISH),
    ("CPI hotter than expected in May print", "macro_inflation_hot", DIRECTION_BEARISH),
    ("Inflation eases as disinflation continues", "macro_inflation_cool", DIRECTION_BULLISH),
    ("Fed cuts rates by 25bp", "rate_cut", DIRECTION_BULLISH),
    ("Central bank hikes rates again", "rate_hike", DIRECTION_BEARISH),
    ("Treasury yields rise to new highs", "yields_up", DIRECTION_BEARISH),
    ("Bond yields fall after auction", "yields_down", DIRECTION_BULLISH),
    ("Regulator opens antitrust probe", "lawsuit_investigation", DIRECTION_BEARISH),
    ("New tariff and export control announced", "regulatory_risk", DIRECTION_BEARISH),
    ("Hyperscaler AI capex surges; chip demand tight", "ai_capex_semis", DIRECTION_BULLISH),
    ("Markets in broad risk-off sell-off", "risk_off", DIRECTION_BEARISH),
    ("Relief rally lifts risk appetite", "risk_on", DIRECTION_BULLISH),
])
def test_classify_covers_required_event_types(title, etype, direction):
    res = classify_text(title)
    assert res["event_type"] == etype
    assert res["direction"] == direction
    assert 1.0 <= res["magnitude"] <= 5.0


def test_word_boundary_prevents_ban_in_bank_false_positive():
    # "bank" must not trip the regulatory_risk "ban" phrase.
    res = classify_text("Bank reports steady deposit growth")
    assert res["event_type"] != "regulatory_risk"


def test_unmatched_headline_is_neutral_uncategorized():
    res = classify_text("Company hosts annual employee picnic")
    assert res["event_type"] == "uncategorized"
    assert res["direction"] == DIRECTION_NEUTRAL


def test_classifier_is_deterministic():
    a = classify_text("Fed cuts rates as inflation cools in China")
    b = classify_text("Fed cuts rates as inflation cools in China")
    assert a == b


def test_classify_event_preserves_curated_fields_but_merges_tags():
    ev = MarketEvent(
        event_id="x1",
        title="Apple raises guidance; China demand strong",
        event_type="guidance_raise",
        direction=DIRECTION_BULLISH,
        magnitude=4.0,
        affected_tags=["earnings"],
    )
    classify_event(ev)
    # curated fields kept
    assert ev.event_type == "guidance_raise"
    assert ev.direction == DIRECTION_BULLISH
    # text-derived tag merged
    assert "china_demand" in ev.affected_tags
    assert "earnings" in ev.affected_tags


def test_classify_event_overwrite_reclassifies():
    ev = MarketEvent(event_id="x2", title="Fed hikes rates sharply")
    classify_event(ev, overwrite=True)
    assert ev.event_type == "rate_hike"
    assert ev.direction == DIRECTION_BEARISH
