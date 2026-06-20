"""V6 -- Chinese template quality + broad-portfolio robustness tests."""

from datetime import datetime, timezone

from modeling.v6 import templates
from modeling.v6.exposure import build_portfolio, DEMO_PORTFOLIOS, get_profile
from modeling.v6.fixtures import load_fixture_events
from modeling.v6.impact_engine import analyze_portfolio

NOW = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)


def _all_generated(res):
    out = [res["conclusion"]]
    for h in res["holdings"]:
        out.append(h["conclusion"])
        for r in h["contributions"]:
            out.append(r["explanation"])
    return out


def test_explanations_are_chinese_and_advice_free():
    res = analyze_portfolio(build_portfolio(None), load_fixture_events(now=NOW), now=NOW)
    texts = _all_generated(res)
    # at least one CJK character in the generated conclusion
    assert any("一" <= ch <= "鿿" for ch in res["conclusion"])
    for s in texts:
        assert templates.contains_banned_phrase(s, ignore_quoted=True) is None


def test_status_and_channel_labels_localized():
    assert templates.status_cn("mixed") == "多空分歧"
    assert templates.status_cn("bullish") == "偏利好"
    assert templates.channel_cn("second_order") == "二次传导"
    assert templates.event_type_cn("rate_cut") == "降息"


def test_chinese_banned_phrase_detected():
    assert templates.contains_banned_phrase("建议买入该股票") == "建议买入"
    assert templates.contains_banned_phrase("设置止损位") == "止损位"
    # a quoted English headline mentioning sell-off is data, not advice
    assert templates.contains_banned_phrase('该事件 "risk-off sell-off" 被识别',
                                            ignore_quoted=True) is None


def test_temporal_clause_present_for_future_event():
    res = analyze_portfolio(build_portfolio(None), load_fixture_events(now=NOW), now=NOW)
    joined = " ".join(_all_generated(res))
    # anticipation / decay phrasing should appear somewhere
    assert ("预期" in joined) or ("衰减" in joined)


def test_all_demo_portfolios_run_without_collapse():
    events = load_fixture_events(now=NOW)
    for name in DEMO_PORTFOLIOS:
        holdings = DEMO_PORTFOLIOS[name]["holdings"]
        res = analyze_portfolio(build_portfolio(holdings), events, now=NOW)
        assert res["holdings_count"] == len(holdings)
        assert res["status"] in {"bullish", "bearish", "neutral", "mixed", "uncertain"}
        for h in res["holdings"]:
            assert h["status"] in {"bullish", "bearish", "neutral", "mixed", "uncertain"}


def test_broad_tickers_have_profiles():
    for t in ["AMD", "TSLA", "META", "GOOGL", "JPM", "XOM", "UNH", "TSM",
              "QQQ", "TQQQ", "SGOV", "GLD"]:
        assert get_profile(t) is not None


def test_unknown_ticker_uses_generic_profile_not_crash():
    res = analyze_portfolio(build_portfolio([{"symbol": "ZZZZ", "weight": 1.0}]),
                            load_fixture_events(now=NOW), now=NOW)
    assert res["holdings_count"] == 1
    assert res["holdings"][0]["matched_profile"] is False
