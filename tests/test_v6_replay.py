"""V6 -- historical event replay validation tests."""

from modeling.v6.replay import (
    HistoricalEvent, to_market_event, replay_event, replay_all, evaluate,
    fixture_returns_adapter,
)
from modeling.v6.replay_fixtures import load_historical_events
from modeling.v6.templates import contains_banned_phrase


def _ev(**kw):
    base = dict(
        event_id="t1", event_time="2024-01-10T13:30:00Z",
        event_title="CPI report: inflation accelerates, hotter than expected",
        source_type="macro", affected_tickers=["TQQQ"],
        affected_tags=["inflation", "yields", "rates"], benchmark_ticker="QQQ",
        fixture_returns={"1": -0.05, "3": -0.04, "5": -0.03, "10": -0.02},
        fixture_benchmark_returns={"1": -0.02, "3": -0.015, "5": -0.01, "10": -0.005},
    )
    base.update(kw)
    return HistoricalEvent(**base)


# --- schema + no-lookahead -----------------------------------------------

def test_known_at_defaults_to_event_time_and_lookahead_ok():
    e = _ev()
    assert e.known_at == e.event_time
    assert e.lookahead_ok() is True


def test_lookahead_violation_detected():
    e = _ev(known_at="2024-01-12T00:00:00Z")  # after event_time
    assert e.lookahead_ok() is False


def test_conversion_does_not_leak_realized_returns():
    e = _ev()
    me = to_market_event(e)
    # the converted MarketEvent has no realized-return fields at all
    assert not hasattr(me, "fixture_returns")
    # classifier set a direction from the pre-event title only
    assert me.event_type == "macro_inflation_hot"
    assert me.direction == -1


# --- direction + evaluation ----------------------------------------------

def test_bearish_event_on_growth_is_hit_when_returns_negative():
    rows = replay_event(_ev())
    r = rows[0]
    assert r["ticker"] == "TQQQ"
    assert r["predicted_direction"] == -1     # bearish for leveraged Nasdaq
    assert r["realized_direction"] == -1
    assert r["result"] == "hit"
    assert r["decisive"] is True


def test_abnormal_return_is_stock_minus_benchmark():
    rows = replay_event(_ev())
    ew = rows[0]["returns"][5]
    assert abs(ew["abnormal"] - (ew["stock"] - ew["benchmark"])) < 1e-9


def test_no_call_when_v6_takes_no_side():
    # an unrecognised, untagged event -> V6 neutral -> no decisive call
    e = _ev(event_title="Company hosts annual employee picnic",
            event_type="uncategorized", affected_tags=[])
    r = replay_event(e)[0]
    assert r["predicted_direction"] == 0
    assert r["result"] == "no_call"
    assert r["decisive"] is False


def test_no_data_when_returns_missing():
    e = _ev(fixture_returns={}, fixture_benchmark_returns={})
    r = replay_event(e)[0]
    assert r["result"] in ("no_data", "no_call")


def test_fixture_returns_adapter_used_when_provided():
    e = _ev(fixture_returns={}, fixture_benchmark_returns={})
    adapter = fixture_returns_adapter({
        "TQQQ": {"1": -0.05, "3": -0.04, "5": -0.03, "10": -0.02},
        "QQQ": {"1": -0.02, "3": -0.015, "5": -0.01, "10": -0.005},
    })
    r = replay_event(e, adapter=adapter)[0]
    assert r["return_mode"] == "live"
    assert r["returns"][5]["stock"] == -0.03


# --- metrics --------------------------------------------------------------

def test_evaluate_metrics_shape_on_fixtures():
    res = replay_all(load_historical_events())
    m = evaluate(res)
    assert m["total"] == len(res)
    assert 0.0 <= m["hit_rate"] <= 1.0
    assert 0.0 <= m["weighted_hit_rate"] <= 1.0
    assert set(m["confusion_matrix"]) == {"tp", "fp", "tn", "fn"}
    assert set(m["calibration"]) == {"low", "medium", "high"}
    # the curated set should be mostly directionally plausible
    assert m["hit_rate"] >= 0.6
    # at least one honest miss is retained (the sell-the-news case)
    assert m["by_result"].get("miss", 0) >= 1


def test_all_fixtures_pass_no_lookahead():
    assert all(e.lookahead_ok() for e in load_historical_events())


def test_replay_conclusions_have_no_trading_advice():
    res = replay_all(load_historical_events())
    for r in res:
        assert contains_banned_phrase(r["conclusion"], ignore_quoted=True) is None
        assert contains_banned_phrase(r.get("notes", "") or "") is None


def test_replay_covers_diverse_categories():
    cats = {e.category for e in load_historical_events()}
    # macro, company, sentiment, regulatory, institutional themes represented
    assert len(cats) >= 4


def test_replay_is_internal_only_no_public_route():
    """Replay is an internal QA tool: no user-facing HTTP route should exist."""
    from app import app
    client = app.test_client()
    assert client.get("/api/modeling/v6/replay").status_code == 404
    assert client.get("/modeling/v6/replay").status_code == 404


def test_eval_window_selection_via_engine():
    events = load_historical_events()
    assert evaluate(replay_all(events, eval_window=10))["eval_window"] == 10
    assert evaluate(replay_all(events, eval_window=1))["eval_window"] == 1
