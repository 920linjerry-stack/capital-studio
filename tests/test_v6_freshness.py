"""V6 -- data-freshness grading + stale-data guard tests (no live network)."""

from datetime import datetime, timedelta, timezone

from modeling.v6.schemas import MarketEvent
from modeling.v6 import freshness as fr
from modeling.v6.api import build_intelligence_response

NOW = datetime(2026, 6, 23, 12, 0, 0, tzinfo=timezone.utc)


def _live_event(hours_ago: float, *, eid: str = "e", data_mode: str = "live") -> MarketEvent:
    ts = (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return MarketEvent(event_id=eid, title="headline", timestamp=ts,
                       effective_at=ts, data_mode=data_mode, source="Public News")


def _live_sources():
    return [{"source_id": "s1", "source_name": "Public News", "mode": "live",
             "last_success": "2026-06-23T11:59:00Z", "last_error": None}]


# --- per-event grading -----------------------------------------------------

def test_event_fresh_under_6h():
    assert fr.event_freshness(_live_event(1), NOW) == fr.FRESH


def test_event_delayed_8h():
    assert fr.event_freshness(_live_event(8), NOW) == fr.DELAYED


def test_event_stale_over_24h():
    assert fr.event_freshness(_live_event(30), NOW) == fr.STALE


def test_event_fixture_mode_is_fixture_not_aged():
    ev = _live_event(1, data_mode="fixture")
    assert fr.event_freshness(ev, NOW) == fr.FIXTURE


def test_event_missing_timestamp_is_unknown():
    ev = MarketEvent(event_id="x", title="no time", data_mode="live")
    assert fr.event_freshness(ev, NOW) == fr.UNKNOWN


def test_future_scheduled_event_is_not_stale():
    sched = (NOW + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ev = MarketEvent(event_id="f", title="FOMC", event_type="fomc_decision",
                     scheduled_at=sched, effective_at=sched, data_mode="live")
    state = fr.event_freshness(ev, NOW)
    assert state in (fr.SCHEDULED, fr.FUTURE_ACTIVE)
    assert state != fr.STALE


# --- top-level rollup ------------------------------------------------------

def test_top_level_fresh():
    block = fr.compute_freshness([_live_event(1)], _live_sources(), now=NOW)
    assert block["freshness_status"] == fr.FRESH
    assert block["freshness_warning_zh"] == ""
    assert block["live_event_count"] == 1


def test_top_level_delayed_at_8h():
    block = fr.compute_freshness([_live_event(8)], _live_sources(), now=NOW)
    assert block["freshness_status"] == fr.DELAYED


def test_top_level_stale_has_warning():
    block = fr.compute_freshness([_live_event(30)], _live_sources(), now=NOW)
    assert block["freshness_status"] == fr.STALE
    assert block["freshness_warning_zh"]            # non-empty
    assert block["stale_event_count"] == 1


def test_unknown_when_timestamps_missing_has_warning():
    ev = MarketEvent(event_id="x", title="no time", data_mode="live")
    block = fr.compute_freshness([ev], _live_sources(), now=NOW)
    assert block["freshness_status"] == fr.UNKNOWN
    assert block["freshness_warning_zh"]


def test_future_event_does_not_force_stale():
    sched = (NOW + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    future = MarketEvent(event_id="f", title="FOMC", event_type="fomc_decision",
                         scheduled_at=sched, effective_at=sched, data_mode="live")
    block = fr.compute_freshness([_live_event(1), future], _live_sources(), now=NOW)
    assert block["freshness_status"] == fr.FRESH
    assert block["stale_event_count"] == 0


def test_fixture_only_source_mode_and_warning():
    block = fr.compute_freshness(
        [_live_event(1, data_mode="fixture")],
        [{"source_id": "s", "source_name": "Fixture", "mode": "fixture"}],
        now=NOW,
    )
    assert block["source_mode"] == "fixture_fallback"
    assert block["freshness_status"] == fr.FIXTURE
    assert block["freshness_warning_zh"]


def test_source_failure_marks_error_mode_and_warning():
    block = fr.compute_freshness(
        [_live_event(1)],
        [{"source_id": "s", "source_name": "Yahoo", "mode": "error", "error": "boom"}],
        now=NOW,
    )
    assert block["source_mode"] == "error"
    assert block["freshness_warning_zh"]


def test_age_window_and_fetch_timestamps_surface():
    block = fr.compute_freshness(
        [_live_event(2, eid="a"), _live_event(20, eid="b")],
        _live_sources(), now=NOW,
        fetch_started_at="2026-06-23T11:58:00Z",
        fetch_finished_at="2026-06-23T11:59:00Z",
    )
    assert block["max_event_age_minutes"] == 1200.0       # 20h oldest
    assert block["newest_event_published_at"].endswith("Z")
    assert block["source_fetch_started_at"] == "2026-06-23T11:58:00Z"
    assert block["source_fetch_finished_at"] == "2026-06-23T11:59:00Z"
    assert block["source_last_success_at"] == "2026-06-23T11:59:00Z"


# --- API integration is additive ------------------------------------------

def test_api_includes_generated_at_and_freshness_block():
    r = build_intelligence_response(portfolio_is_demo=True)
    assert r["generated_at"].endswith("Z")
    assert "generated_at_local" in r
    assert r["source_mode"] == "fixture_fallback"
    assert r["freshness_status"] == "fixture"
    assert r["freshness_warning_zh"]                       # honest fixture notice
    fz = r["freshness"]
    for key in ("freshness_status", "freshness_label_zh", "source_mode",
                "newest_event_published_at", "oldest_event_published_at",
                "max_event_age_minutes", "event_count_by_freshness",
                "live_event_count", "fixture_event_count", "stale_event_count",
                "source_last_success_at", "source_last_error_at",
                "source_fetch_started_at", "source_fetch_finished_at"):
        assert key in fz


def test_api_event_rows_carry_freshness_status():
    r = build_intelligence_response(portfolio_is_demo=True)
    assert all("freshness_status" in e for e in r["events"])
