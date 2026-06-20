"""Structural V6 classifier and exposure regression coverage."""

import pytest

from modeling.v6.classifier import (
    assign_direction,
    classify_event,
    classify_text,
    recognize_text,
)
from modeling.v6.exposure import get_profile
from modeling.v6.impact_engine import analyze_holding
from modeling.v6.schemas import MarketEvent
from modeling.v6.templates import contains_banned_phrase


def _event(title, ticker="AAPL", source_type="company"):
    return classify_event(MarketEvent(
        event_id="structural",
        title=title,
        source_type=source_type,
        related_tickers=[ticker] if ticker else [],
        confidence=0.8,
    ))


def _holding(title, ticker, *, source_type="company", related=None):
    event = classify_event(MarketEvent(
        event_id="holding",
        title=title,
        source_type=source_type,
        related_tickers=list(related or ([] if source_type == "macro" else [ticker])),
        confidence=0.8,
    ))
    return event, analyze_holding(get_profile(ticker), 1.0, [event])


def test_two_stage_recognition_is_separate_from_direction_assignment():
    recognized = recognize_text("Company raises guidance but margins weaken")
    assert {"guidance_raise", "margin_warning"} <= set(recognized["states"])
    assert "direction" not in recognized
    assigned = assign_direction(recognized)
    assert assigned["direction"] == 0
    assert "ambiguous_surprise" in assigned["flags"]


@pytest.mark.parametrize("title,state,direction", [
    ("FDA approves a new drug", "fda_approval", 1),
    ("FDA rejected the new therapy", "fda_rejection", -1),
    ("Regulators clear the transaction", "regulatory_approval", 1),
    ("Regulator blocks the transaction", "regulatory_rejection", -1),
])
def test_approval_and_rejection_states(title, state, direction):
    result = classify_text(title)
    assert state in result["states"]
    assert result["direction"] == direction


@pytest.mark.parametrize("title,state,direction", [
    ("Phase 3 trial meets its primary endpoint", "trial_success", 1),
    ("Clinical trial fails and misses the primary endpoint", "trial_failure", -1),
])
def test_trial_success_and_failure(title, state, direction):
    result = classify_text(title)
    assert state in result["states"]
    assert result["direction"] == direction


@pytest.mark.parametrize("title,state,direction", [
    ("Company raises its growth outlook", "guidance_raise", 1),
    ("Company lowered full-year guidance", "guidance_cut", -1),
    ("Net interest income remains under pressure", "margin_warning", -1),
])
def test_guidance_and_margin_morphology(title, state, direction):
    result = classify_text(title)
    assert state in result["states"]
    assert result["direction"] == direction


@pytest.mark.parametrize("title,state,direction", [
    ("Broker upgraded shares to overweight", "analyst_upgrade", 1),
    ("Broker initiates coverage at sell", "analyst_downgrade", -1),
    ("Analyst lifted the price target", "price_target_raise", 1),
    ("Analyst lowered its target price", "price_target_cut", -1),
    ("Analyst raises EPS estimates", "estimate_raise", 1),
    ("Analyst cuts revenue estimates", "estimate_cut", -1),
])
def test_institutional_action_morphology(title, state, direction):
    result = classify_text(title)
    assert state in result["states"]
    assert result["direction"] == direction


@pytest.mark.parametrize("title,state", [
    ("Regulators open an antitrust probe", "antitrust_probe"),
    ("Company faces a class action lawsuit", "lawsuit"),
    ("Agency investigation intensifies", "investigation"),
    ("SEC charges the company in enforcement action", "enforcement_action"),
])
def test_legal_and_enforcement_states_are_bearish(title, state):
    result = classify_text(title)
    assert state in result["states"]
    assert result["direction"] == -1


@pytest.mark.parametrize("title,state", [
    ("Major software outage disrupts customers", "outage"),
    ("Cyberattack causes a data breach", "cybersecurity_breach"),
    ("Automaker recalls vehicles in a product recall", "product_recall"),
])
def test_outage_cybersecurity_and_recall_states(title, state):
    result = classify_text(title)
    assert state in result["states"]
    assert result["direction"] == -1


@pytest.mark.parametrize("title,state", [
    ("Government imposes new export restrictions", "export_controls"),
    ("Country sanctions technology suppliers", "sanctions"),
    ("New tariffs announced on imports", "tariffs"),
])
def test_trade_policy_morphology(title, state):
    result = classify_text(title)
    assert state in result["states"]
    assert result["direction"] == -1


def test_cpi_hot_is_exposure_aware_across_growth_banks_gold_and_energy():
    event = _event("CPI hotter than expected", ticker="", source_type="macro")
    reads = {ticker: analyze_holding(get_profile(ticker), 1.0, [event])
             for ticker in ("QQQ", "JPM", "GLD", "XOM")}
    assert reads["QQQ"]["status"] == "bearish"
    assert reads["JPM"]["status"] == "mixed"
    assert reads["GLD"]["status"] == "mixed"
    assert reads["XOM"]["net_impact"] > 0


def test_cpi_cool_supports_duration_but_preserves_bank_and_gold_contra_channels():
    event = _event("CPI cooler than expected as inflation cools", ticker="", source_type="macro")
    qqq = analyze_holding(get_profile("QQQ"), 1.0, [event])
    jpm = analyze_holding(get_profile("JPM"), 1.0, [event])
    gld = analyze_holding(get_profile("GLD"), 1.0, [event])
    assert qqq["net_impact"] > 0
    assert jpm["net_impact"] < 0
    assert gld["status"] == "mixed"


def test_jobs_hot_and_weak_keep_opposing_factor_channels():
    hot = _event("Payrolls stronger than expected", ticker="", source_type="macro")
    weak = _event("Payroll growth slows and unemployment rises", ticker="", source_type="macro")
    assert analyze_holding(get_profile("QQQ"), 1.0, [hot])["net_impact"] < 0
    assert analyze_holding(get_profile("JPM"), 1.0, [hot])["status"] == "mixed"
    assert analyze_holding(get_profile("IWM"), 1.0, [weak])["status"] == "mixed"
    assert analyze_holding(get_profile("JPM"), 1.0, [weak])["net_impact"] < 0


def test_oil_supply_shock_splits_energy_benefit_from_duration_pressure():
    event = _event("OPEC cuts production and crude oil rises", ticker="", source_type="macro")
    for ticker in ("XOM", "CVX", "XLE", "USO"):
        assert analyze_holding(get_profile(ticker), 1.0, [event])["net_impact"] > 0
    for ticker in ("QQQ", "TQQQ", "XLK"):
        assert analyze_holding(get_profile(ticker), 1.0, [event])["net_impact"] < 0


def test_gold_keeps_inflation_haven_support_and_yield_dollar_pressure_separate():
    event = _event(
        "Inflation fear rises while real yields surge and dollar strengthens",
        ticker="", source_type="macro",
    )
    result = analyze_holding(get_profile("GLD"), 1.0, [event])
    assert result["status"] == "mixed"
    assert {row["effective_direction"] for row in result["contributions"]} == {-1, 1}


def test_bank_rate_benefit_is_distinct_from_credit_stress_harm():
    rates = _event("Fed turns hawkish and signals higher for longer", ticker="", source_type="macro")
    stress = _event("Banking stress deepens with deposit outflows", ticker="", source_type="macro")
    for ticker in ("JPM", "BAC", "GS", "XLF"):
        assert analyze_holding(get_profile(ticker), 1.0, [rates])["net_impact"] > 0
        assert analyze_holding(get_profile(ticker), 1.0, [stress])["net_impact"] < 0


def test_sector_etf_transmission_is_explicit_and_conservative():
    outage = _event("Major software outage disrupts global systems", ticker="CRWD")
    _, xlk = outage, analyze_holding(get_profile("XLK"), 1.0, [outage])
    approval = _event("FDA approves a new Lilly drug", ticker="LLY", source_type="official")
    xlv = analyze_holding(get_profile("XLV"), 1.0, [approval])
    bank_rule = _event(
        "Regulators propose stronger capital requirements for large banks",
        ticker="JPM", source_type="official",
    )
    xlf = analyze_holding(get_profile("XLF"), 1.0, [bank_rule])
    assert xlk["net_impact"] < 0
    assert xlv["net_impact"] > 0
    assert xlf["net_impact"] < 0
    assert any(row["match_kind"] == "sector_transmission" for row in xlk["contributions"])
    assert max(abs(row["relevance"]) for row in xlk["contributions"]) <= 0.35


@pytest.mark.parametrize("title", [
    "Shares fall despite an earnings beat",
    "Stock drops after results beat expectations",
    "Earnings beat but the company cuts guidance",
    "Good news priced in after an earnings beat",
])
def test_headline_surprise_conflicts_are_mixed_and_lower_confidence(title):
    event, result = _holding(title, "AAPL")
    assert event.direction == 0
    assert event.classification_confidence < 1.0
    assert result["status"] == "mixed"
    assert "ambiguous_surprise" in event.classification_flags


def test_vague_headline_stays_low_confidence_instead_of_forcing_direction():
    event = _event("Apple files quarterly report on Form 10-Q")
    assert event.direction == 0
    assert event.classification_confidence == 0.6
    assert "surprise_unknown" in event.classification_flags


def test_confounded_broad_market_language_reduces_confidence():
    event = _event("Global risk-off shock deepens on recession fears", ticker="", source_type="sentiment")
    assert event.classification_confidence <= 0.75
    assert "confounded_market_context" in event.classification_flags




def test_structural_outputs_contain_no_advice_language():
    for title, ticker in (
        ("FDA approves a new drug", "LLY"),
        ("Major software outage disrupts systems", "XLK"),
        ("Shares fall despite an earnings beat", "AAPL"),
    ):
        _, result = _holding(title, ticker)
        assert contains_banned_phrase(result["conclusion"], ignore_quoted=True) is None
