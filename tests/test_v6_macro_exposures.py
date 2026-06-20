"""Regression coverage for V6's asset-specific macro factor exposures."""

from modeling.v6.classifier import classify_event, classify_text
from modeling.v6.exposure import get_profile
from modeling.v6.impact_engine import analyze_holding
from modeling.v6.schemas import MarketEvent, DIRECTION_BEARISH
from modeling.v6.templates import contains_banned_phrase


def _macro(event_id: str, title: str, tags: list[str]) -> MarketEvent:
    event = MarketEvent(
        event_id=event_id,
        title=title,
        source_type="macro",
        direction=DIRECTION_BEARISH,
        magnitude=4.0,
        confidence=0.8,
        affected_tags=tags,
    )
    return classify_event(event)


def test_oil_shock_is_positive_for_energy_not_leveraged_growth():
    event = _macro(
        "oil",
        "OPEC supply cut drives crude up; inflation accelerates",
        ["inflation", "commodities", "oil"],
    )
    assert "oil_up" in event.affected_tags
    assert analyze_holding(get_profile("XOM"), 1.0, [event])["net_impact"] > 0
    assert analyze_holding(get_profile("XLE"), 1.0, [event])["net_impact"] > 0
    assert analyze_holding(get_profile("USO"), 1.0, [event])["net_impact"] > 0
    assert analyze_holding(get_profile("TQQQ"), 1.0, [event])["net_impact"] < 0


def test_hot_cpi_remains_bearish_for_duration_and_leveraged_tech():
    event = _macro(
        "cpi",
        "CPI hotter than expected as Treasury yields surge",
        ["inflation", "yields", "rates"],
    )
    for ticker in ("QQQ", "TQQQ", "XLK", "NVDA"):
        result = analyze_holding(get_profile(ticker), 1.0, [event])
        assert result["net_impact"] < 0
        assert result["status"] == "bearish"


def test_credit_stress_overrides_rate_benefit_for_banks_and_financials():
    event = _macro(
        "credit",
        "Banking stress and deposit outflows worsen even as rates stay high",
        ["credit_stress", "rates"],
    )
    for ticker in ("JPM", "BAC", "GS", "XLF"):
        result = analyze_holding(get_profile(ticker), 1.0, [event])
        assert result["net_impact"] < 0
        assert any("credit_stress" in row["matched_terms"]
                   for row in result["contributions"])


def test_gold_preserves_conflict_between_inflation_fear_and_real_yields():
    event = _macro(
        "gold",
        "Inflation fear rises while real yields surge and the dollar strengthens",
        ["inflation_fear", "real_yields_up", "dollar_up"],
    )
    result = analyze_holding(get_profile("GLD"), 1.0, [event])
    directions = {row["effective_direction"] for row in result["contributions"]}
    assert directions == {-1, 1}
    assert result["status"] == "mixed"


def test_required_factor_profile_vocabulary_is_present():
    assert {"commodity_beneficiary", "oil_up_beneficiary", "inflation_hedge"} <= set(get_profile("XOM").factor_tags)
    assert {"inflation_hedge", "safe_haven", "real_yields_sensitive", "dollar_sensitive"} <= set(get_profile("GLD").factor_tags)
    assert {"credit_stress_sensitive", "yield_curve_sensitive", "bank_rate_beneficiary"} <= set(get_profile("JPM").factor_tags)
    assert {"high_duration_growth", "leveraged_growth"} <= set(get_profile("TQQQ").factor_tags)


def test_macro_output_contains_no_trading_advice_wording():
    event = _macro("oil", "OPEC supply cut drives crude up", ["oil_up"])
    for ticker in ("XOM", "QQQ", "GLD", "JPM"):
        result = analyze_holding(get_profile(ticker), 1.0, [event])
        assert contains_banned_phrase(result["conclusion"], ignore_quoted=True) is None


def test_classifier_emits_explicit_factor_state_tags():
    result = classify_text(
        "Banking stress rises as the yield curve steepens; real yields surge and dollar strengthens"
    )
    assert {"credit_stress", "yield_curve_steepening", "real_yields_up", "dollar_up"} <= set(result["tags"])
