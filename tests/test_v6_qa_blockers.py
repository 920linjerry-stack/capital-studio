"""Regression coverage for the V6 QA publication blockers."""

from pathlib import Path

import pytest

from modeling.v6.classifier import classify_event
from modeling.v6.exposure import get_profile
from modeling.v6.fixtures import load_fixture_events
from modeling.v6.impact_engine import analyze_holding, match_event_to_holding
from modeling.v6.replay import HistoricalEvent, replay_event, to_market_event
from modeling.v6.schemas import MarketEvent
from modeling.v6.sources.registry import ingest_events
from modeling.v6.templates import contains_banned_phrase


def _classified(
    event_id: str,
    title: str,
    *,
    source_type: str = "macro",
    ticker: str | None = None,
    magnitude: float = 4.0,
    confidence: float = 0.8,
) -> MarketEvent:
    return classify_event(MarketEvent(
        event_id=event_id,
        title=title,
        source_type=source_type,
        related_tickers=[ticker] if ticker else [],
        magnitude=magnitude,
        confidence=confidence,
    ))


def _historical(**overrides) -> HistoricalEvent:
    values = {
        "event_id": "qa-lookahead",
        "event_time": "2024-01-10T13:30:00Z",
        "known_at": "2024-01-10T13:30:00Z",
        "event_title": "Apple earnings beat estimates",
        "affected_tickers": ["AAPL"],
    }
    values.update(overrides)
    return HistoricalEvent(**values)


def test_core_replay_rejects_timestamp_and_explicit_flag_violations():
    late = _historical(known_at="2024-01-10T13:31:00Z")
    flagged = _historical(no_lookahead_flag=False)
    assert late.lookahead_ok() is False
    assert flagged.lookahead_ok() is False
    for unsafe in (late, flagged):
        with pytest.raises(ValueError, match="no-lookahead validation failed"):
            to_market_event(unsafe)
        with pytest.raises(ValueError, match="no-lookahead validation failed"):
            replay_event(unsafe)


def test_signed_discount_rate_factor_dominates_generic_aliases():
    event = MarketEvent(
        event_id="qa-factor-family",
        title="Hot CPI pushes rates and yields higher",
        source_type="macro",
        event_type="cpi_hot",
        direction=-1,
        magnitude=4.0,
        confidence=0.8,
        affected_tags=["rates", "rates_up", "yields", "yields_up"],
        recognized_states=["cpi_hot"],
    )
    macro = [
        row for row in match_event_to_holding(event, get_profile("AAPL"))
        if row["match_kind"] == "macro_factor"
    ]
    assert len(macro) == 1
    assert macro[0]["matched_terms"] == ["rates_up"]
    assert macro[0]["effective_direction"] == -1


def test_risk_on_does_not_score_risk_off_from_context_text():
    event = MarketEvent(
        event_id="qa-risk-regime",
        title="Risk appetite rebounds",
        summary="The move offsets an earlier global risk-off shock.",
        source_type="macro",
        event_type="risk_on",
        direction=1,
        magnitude=3.0,
        confidence=0.7,
        affected_tags=["risk_on", "risk_off", "risk_sentiment"],
        recognized_states=["risk_off"],
    )
    rows = match_event_to_holding(event, get_profile("AAPL"))
    assert not any("risk_off" in row["matched_terms"] for row in rows)
    reflexivity = [row for row in rows if row["channel"] == "reflexivity"]
    assert len(reflexivity) == 1
    assert reflexivity[0]["effective_direction"] == 1


def test_peer_and_etf_transmission_are_single_conservative_paths():
    event = _classified(
        "qa-peer",
        "NVIDIA beats estimates on surging AI chip demand",
        source_type="company",
        ticker="NVDA",
    )
    nvda = match_event_to_holding(event, get_profile("NVDA"))
    qqq = match_event_to_holding(event, get_profile("QQQ"))
    amd = match_event_to_holding(event, get_profile("AMD"))

    assert len(nvda) == 1 and nvda[0]["match_kind"] == "ticker"
    assert len(qqq) == 1
    assert qqq[0]["match_kind"] == "sector_transmission"
    assert qqq[0]["channel"] == "second_order"
    assert qqq[0]["relevance"] <= 0.35
    assert len(amd) == 1
    assert amd[0]["channel"] == "second_order"
    assert amd[0]["match_kind"] != "factor_tag"


def test_direct_company_evidence_is_not_overpowered_by_duplicate_macro_aliases():
    company = _classified(
        "qa-company",
        "Apple earnings beat estimates",
        source_type="company",
        ticker="AAPL",
    )
    hot_cpi = _classified("qa-cpi", "CPI hotter than expected")
    profile = get_profile("AAPL")

    company_only = analyze_holding(profile, 1.0, [company])
    macro_only = analyze_holding(profile, 1.0, [hot_cpi])
    combined = analyze_holding(profile, 1.0, [company, hot_cpi])

    assert company_only["status"] == "bullish" and company_only["net_impact"] > 0
    assert macro_only["status"] == "bearish" and macro_only["net_impact"] < 0
    assert combined["net_impact"] > 0

    company_rows = [row for row in combined["contributions"] if row["event_id"] == "qa-company"]
    macro_rows = [row for row in combined["contributions"] if row["event_id"] == "qa-cpi"]
    assert len(company_rows) == 1
    assert len({tuple(row["matched_terms"]) for row in macro_rows}) == len(macro_rows)
    discount_aliases = {"rates", "rates_up", "yields", "yields_up"}
    assert sum(bool(discount_aliases & set(row["matched_terms"])) for row in macro_rows) == 1


def test_fixture_labels_and_health_do_not_imply_licensed_live_sources():
    forbidden = {"Reuters", "Bloomberg", "GS Research", "MS Research", "Xinhua"}
    fixtures = load_fixture_events()
    assert not ({event.source for event in fixtures} & forbidden)
    assert all(event.source.startswith("Fixture ") for event in fixtures)

    _, statuses = ingest_events(allow_network=False)
    fixture_statuses = [status for status in statuses if status["mode"] == "fixture"]
    assert fixture_statuses
    assert all(status["reliability"] == "示例回退" for status in fixture_statuses)

    js = (Path(__file__).parents[1] / "static" / "modeling" / "js" / "v6.js").read_text(encoding="utf-8")
    assert "实时 · ${sourceLabel}" in js
    assert "</b> 正常</span>" not in js


def test_qa_repairs_keep_replay_private_and_outputs_advice_free():
    from app import app

    client = app.test_client()
    assert client.get("/modeling/v6/replay").status_code == 404
    assert client.get("/api/modeling/v6/replay").status_code == 404

    events = [
        _classified("qa-advice-company", "Apple earnings beat estimates", source_type="company", ticker="AAPL"),
        _classified("qa-advice-cpi", "CPI hotter than expected"),
    ]
    result = analyze_holding(get_profile("AAPL"), 1.0, events)
    assert contains_banned_phrase(result["conclusion"], ignore_quoted=True) is None
    for row in result["contributions"]:
        assert contains_banned_phrase(row["explanation"], ignore_quoted=True) is None
