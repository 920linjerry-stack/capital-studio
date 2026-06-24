"""Tests for the V6 real event calendar (pillar 1)."""

from __future__ import annotations

from datetime import datetime, timezone

from modeling.v6 import calendar as cal
from modeling.v6 import timing

NOW = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)


def test_macro_events_have_fixed_dates_that_count_down():
    """A real calendar date is fixed: the countdown shrinks as `now` advances."""
    e_now = next(e for e in cal.build_calendar_events(["NVDA"], NOW, 90)
                 if e.event_id.startswith("cal-cpi"))
    later = NOW.replace(day=26)
    e_later = next(e for e in cal.build_calendar_events(["NVDA"], later, 90)
                   if e.event_id == e_now.event_id)
    assert e_now.scheduled_at == e_later.scheduled_at          # date is fixed
    cd_now = timing.temporal_profile(e_now, NOW)["countdown_days"]
    cd_later = timing.temporal_profile(e_later, later)["countdown_days"]
    assert cd_later < cd_now                                   # it actually counts down


def test_micron_bellwether_appears_even_when_not_held():
    evs = cal.build_calendar_events(["NVDA", "AAPL"], NOW, 90)
    mu = [e for e in evs if "MU" in e.related_tickers]
    assert mu, "Micron (MU) earnings should surface as a sector bellwether"
    assert mu[0].event_type == "earnings_date"
    assert mu[0].is_scheduled


def test_calendar_offline_uses_fixture_mode_no_network():
    evs = cal.build_calendar_events(["AAPL"], NOW, 120, allow_network=False)
    assert evs
    assert all(e.is_scheduled and e.scheduled_at for e in evs)
    assert evs == sorted(evs, key=lambda e: e.scheduled_at)
    # earnings events stay fixture-mode without network
    earn = [e for e in evs if e.event_type == "earnings_date"]
    assert earn and all(e.data_mode == "fixture" for e in earn)


def test_macro_direction_is_neutral_until_release():
    evs = cal.macro_calendar_events(NOW, 120)
    assert evs
    # we never fabricate a consensus lean for a scheduled release
    assert all(e.direction == 0 for e in evs)
    assert {e.event_type for e in evs} <= {"fomc_decision", "cpi_release", "jobs_report"}


def test_horizon_filters_far_future():
    near = cal.build_calendar_events(["NVDA"], NOW, 10)
    far = cal.build_calendar_events(["NVDA"], NOW, 120)
    assert len(near) < len(far)
    assert all(timing.temporal_profile(e, NOW)["countdown_days"] <= 10.5 for e in near)
