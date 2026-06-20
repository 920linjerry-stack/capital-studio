"""V6 -- future-event timing, anticipation ramp, and decay tests."""

from datetime import datetime, timedelta, timezone

from modeling.v6.schemas import MarketEvent, DIRECTION_BULLISH
from modeling.v6.timing import temporal_profile, parse_dt
from modeling.v6.exposure import build_portfolio
from modeling.v6.fixtures import load_fixture_events
from modeling.v6.impact_engine import analyze_portfolio, build_future_timeline

NOW = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)


def _sched(days, **kw):
    when = (NOW + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    base = dict(event_id="t", title="catalyst", event_type="cpi_release",
                direction=DIRECTION_BULLISH, magnitude=4.0, confidence=0.6,
                scheduled_at=when, effective_at=when)
    base.update(kw)
    return MarketEvent(**base)


def test_parse_dt_handles_z_suffix():
    dt = parse_dt("2026-06-20T12:00:00Z")
    assert dt is not None and dt.tzinfo is not None


def test_far_future_is_upcoming_low_weight():
    tp = temporal_profile(_sched(30), NOW)
    assert tp["phase"] == "upcoming"
    assert tp["is_future"] is True
    assert tp["time_weight"] == 0.0


def test_anticipation_ramps_up_as_date_approaches():
    far = temporal_profile(_sched(6), NOW)["time_weight"]
    near = temporal_profile(_sched(1), NOW)["time_weight"]
    assert near > far > 0.0
    assert temporal_profile(_sched(6), NOW)["phase"] == "anticipation"


def test_pre_release_live_peaks_at_anticipation():
    # imminent but NOT yet released: phase live, weight peaks at the priced-in
    # (anticipation) fraction -- the event has not happened yet.
    tp = temporal_profile(_sched(0.1, anticipation_score=0.55), NOW)
    assert tp["phase"] == "live"
    assert 0.0 < tp["time_weight"] <= 0.56


def test_just_released_is_live_full_weight():
    # released within the live window, no sell-news -> full weight, no flip.
    tp = temporal_profile(_sched(-0.05, sell_the_news_risk=0.0, priced_in_score=0.0,
                                 post_event_decay_hours=48), NOW)
    assert tp["phase"] == "live"
    assert tp["time_weight"] == 1.0
    assert tp["direction_factor"] == 1.0


def test_post_event_decays():
    # released 1h ago vs 60h ago -> later has smaller weight
    recent = temporal_profile(_sched(-1, post_event_decay_hours=48), NOW)
    old = temporal_profile(_sched(-60, post_event_decay_hours=48), NOW)
    assert recent["phase"] == "post_event"
    assert recent["time_weight"] > old["time_weight"]


def test_sell_the_news_flips_direction_after_release():
    # bullish event, high priced-in + sell-news, just released -> direction flips
    ev = _sched(-0.05, priced_in_score=0.9, sell_the_news_risk=0.9,
                post_event_decay_hours=48)
    tp = temporal_profile(ev, NOW)
    assert tp["direction_factor"] < 0  # realized move fades/flips
    assert tp["label"] == "利好出尽风险"


def test_recent_headline_without_schedule_decays_by_type():
    ts = (NOW - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ev = MarketEvent(event_id="r", title="x", event_type="risk_off",
                     direction=-1, magnitude=3, timestamp=ts, effective_at=ts)
    tp = temporal_profile(ev, NOW)
    assert tp["phase"] in ("post_event", "expired")
    assert 0.0 < tp["time_weight"] <= 1.0


def test_no_timestamp_is_full_weight_live():
    ev = MarketEvent(event_id="n", title="x", event_type="earnings_beat",
                     direction=1, magnitude=3)
    tp = temporal_profile(ev, NOW)
    assert tp["time_weight"] == 1.0
    assert tp["is_future"] is False


def test_future_events_included_in_scoring_and_timeline():
    events = load_fixture_events(now=NOW)
    pf = build_portfolio(None)
    res = analyze_portfolio(pf, events, now=NOW)
    # the timeline surfaces the four scheduled catalysts
    assert len(res["future_timeline"]) == 4
    # at least one future event pre-prices into a holding's score (nonzero)
    found = any(
        any(c.get("is_future") for c in h["contributions"])
        for h in res["holdings"]
    )
    assert found


def test_timeline_sorted_by_countdown():
    events = load_fixture_events(now=NOW)
    tl = build_future_timeline(events, build_portfolio(None)["positions"], NOW)
    days = [r["countdown_days"] for r in tl]
    assert days == sorted(days)


def test_age_info_fixture_and_past_and_future():
    from modeling.v6.timing import age_info
    # fixture mode -> honest label, not a fake age
    fx = MarketEvent(event_id="a", title="x", data_mode="fixture",
                     timestamp="2026-06-20T10:00:00Z")
    assert age_info(fx, NOW)["band"] == "fixture"
    # live past event -> hours/days-ago band
    past = MarketEvent(event_id="b", title="x", data_mode="live",
                       effective_at="2026-06-20T06:00:00Z")  # 6h before NOW
    a = age_info(past, NOW)
    assert a["band"] == "fresh" and "小时前" in a["label"]
    old = MarketEvent(event_id="c", title="x", data_mode="live",
                      effective_at="2026-06-10T12:00:00Z")  # 10d before NOW
    assert age_info(old, NOW)["band"] == "stale"
    # future scheduled -> 待公布
    fut = MarketEvent(event_id="d", title="x", data_mode="live",
                      scheduled_at="2026-06-25T12:00:00Z", effective_at="2026-06-25T12:00:00Z")
    assert age_info(fut, NOW)["band"] == "future"
