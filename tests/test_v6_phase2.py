"""Phase 2: regime classifier, calibrated probability, Brier + walk-forward,
portfolio concentration, and API surfacing. All deterministic and offline."""

from modeling.v6 import regime, calibration
from modeling.v6.api import build_intelligence_response
from modeling.v6.exposure import get_demo_portfolio


# --- B2: regime classifier --------------------------------------------------

def test_regime_state_loads_committed_snapshot():
    r = regime.regime_state()
    assert r["rate_cycle"] in regime.RATE_CYCLES
    assert r["risk"] in regime.RISK_STATES
    assert r["trend"] in regime.TRENDS
    assert r["inflation"] in regime.INFLATION
    assert "labels_cn" in r and r["labels_cn"]["rate_cycle"]


def test_regime_state_neutral_on_empty_snapshot():
    r = regime.regime_state(snapshot={})
    assert r["rate_cycle"] == "hold" and r["data_mode"] == "unavailable"


def test_regime_multiplier_damps_confirming_and_boosts_fighting():
    cutting = {"rate_cycle": "cutting", "risk": "neutral"}
    assert regime.regime_multiplier("rate_cut", cutting) < 1.0      # priced-in
    assert regime.regime_multiplier("rate_hike", cutting) > 1.0     # surprise
    assert regime.regime_multiplier("earnings_beat", cutting) == 1.0  # unrelated
    assert regime.regime_multiplier("rate_cut", None) == 1.0          # no-op


# --- C2: calibrated direction probability -----------------------------------

def test_direction_probability_in_unit_interval_and_shrinks():
    # Every type's probability is a valid number shrunk toward 0.5 (so a thin,
    # high-hit cell never reads as certainty) -- robust to data refits.
    types = calibration.load_calibration().get("types") or {}
    checked = 0
    for et, row in types.items():
        hr, n = row.get("hit_rate"), row.get("decisive_n") or 0
        if hr is None or n <= 0:
            continue
        p = calibration.direction_probability(et)
        assert p is not None and 0.0 <= p <= 1.0
        lo, hi = sorted([float(hr), 0.5])
        assert lo - 1e-9 <= p <= hi + 1e-9   # shrunk toward 0.5
        checked += 1
    assert checked > 0
    assert calibration.direction_probability("not_a_real_type") is None


def test_wilson_interval_bounds():
    lo, hi = calibration.wilson_interval(8, 10)
    assert 0.0 <= lo <= hi <= 1.0
    assert calibration.wilson_interval(0, 0) is None


# --- A3 + A2: Brier and walk-forward ----------------------------------------

def _benchmark_rows():
    from modeling.v6.replay_benchmark import load_benchmark_events, run_benchmark
    return run_benchmark(load_benchmark_events(), eval_window=5)


def test_calibration_report_brier_is_valid():
    from modeling.v6.replay_benchmark import calibration_report
    rep = calibration_report(_benchmark_rows())
    assert rep["decisive_scored"] > 0
    assert 0.0 <= rep["brier"] <= 1.0
    assert rep["reliability_bins"]


def test_walk_forward_is_out_of_time_and_valid():
    from modeling.v6.replay_benchmark import evaluate_walk_forward
    wf = evaluate_walk_forward(_benchmark_rows())
    assert wf["oos_decisive"] > 0
    assert 0.0 <= wf["oos_hit_rate"] <= 1.0
    assert 0.0 <= wf["oos_brier"] <= 1.0
    assert len(wf["per_fold"]) >= 1


# --- API surfacing (regime, concentration, per-event probability) -----------

def test_api_surfaces_regime_concentration_and_probability():
    payload = build_intelligence_response(
        get_demo_portfolio("us_megacap_tech"), portfolio_is_demo=True
    )
    assert "regime" in payload and payload["regime"]["rate_cycle"] in regime.RATE_CYCLES
    conc = payload["concentration"]
    assert conc["hhi"] is None or 0.0 <= conc["hhi"] <= 1.0
    # at least one classified event carries a calibrated probability
    probs = [e.get("direction_probability") for e in payload["events"]]
    assert any(p is not None for p in probs)


def test_api_payload_still_well_formed():
    payload = build_intelligence_response(get_demo_portfolio("ai_semis"), portfolio_is_demo=True)
    assert payload["portfolio"]["status"] in {"bullish", "bearish", "mixed", "neutral", "uncertain"}
    assert payload["data_mode"] == "sample"
