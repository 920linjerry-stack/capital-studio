"""Tests for V6 learned bp calibration (pillar 2)."""

from __future__ import annotations

from datetime import datetime, timezone

from modeling.v6 import calibration as cb
from modeling.v6.api import build_intelligence_response
from modeling.v6.exposure import get_demo_portfolio

NOW = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)


def test_calibration_file_loads_with_units():
    calib = cb.load_calibration()
    assert calib.get("types"), "committed calibration.json should be present"
    meta = calib["_meta"]
    assert meta["global_mean_bp"] > 0
    for row in calib["types"].values():
        assert row["expected_abs_bp"] > 0
        assert row["n"] >= 1


def test_expected_move_bp_known_and_fallback():
    # a known type returns its shrunk estimate; an unknown one falls back global
    assert cb.expected_move_bp("earnings_beat") > 0
    assert cb.expected_move_bp("totally_unknown_type") == cb.global_mean_bp()


def test_contribution_bp_sign_and_scaling():
    up = cb.contribution_bp(event_type="rate_cut", effective_direction=1,
                            relevance=1.0, confidence=1.0)
    down = cb.contribution_bp(event_type="rate_cut", effective_direction=-1,
                              relevance=1.0, confidence=1.0)
    assert up > 0 and down < 0 and abs(up) == abs(down)
    # relevance damps the magnitude
    damped = cb.contribution_bp(event_type="rate_cut", effective_direction=1,
                                relevance=0.3, confidence=1.0)
    assert 0 < damped < up
    # neutral direction => no expected move
    assert cb.contribution_bp(event_type="rate_cut", effective_direction=0,
                              relevance=1.0, confidence=1.0) == 0


def test_scheduled_potential_bp_uses_realized_proxies():
    # earnings_date has no realized history of its own; proxy to beat/miss
    proxy = cb.scheduled_potential_bp("earnings_date")
    avg = (cb.expected_move_bp("earnings_beat") + cb.expected_move_bp("earnings_miss")) / 2
    assert abs(proxy - round(avg, 1)) < 1e-6


def test_portfolio_payload_exposes_bp():
    holdings = get_demo_portfolio("us_megacap_tech")
    r = build_intelligence_response(holdings, now=NOW, portfolio_is_demo=True)
    pf = r["portfolio"]
    assert "expected_abnormal_bp" in pf and "expected_abs_bp" in pf
    assert pf["expected_abs_bp"] >= abs(pf["expected_abnormal_bp"])
    # every holding carries the calibrated readout too
    assert all("expected_abnormal_bp" in h for h in pf["holdings"])
