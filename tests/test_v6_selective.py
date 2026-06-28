"""Selective prediction / abstention + sector-residualized abnormal returns."""

from modeling.v6 import selective
from modeling.v6.api import build_intelligence_response
from modeling.v6.exposure import get_demo_portfolio


def test_signal_tiers_by_threshold():
    assert selective.signal_tier(0.70) == "strong"
    assert selective.signal_tier(0.62) == "strong"
    assert selective.signal_tier(0.58) == "weak"
    assert selective.signal_tier(0.50) == "none"
    assert selective.signal_tier(None) == "none"


def test_portfolio_signal_acts_only_with_strong_driver():
    assert selective.portfolio_signal([0.70, 0.40])["act"] is True
    assert selective.portfolio_signal([0.58, 0.52])["act"] is False
    assert selective.portfolio_signal([0.58, 0.52])["tier"] == "weak"
    assert selective.portfolio_signal([0.40, None])["tier"] == "none"


def test_selectivity_curve_acted_accuracy_beats_blended():
    """Abstaining on low-confidence calls must raise acted-on accuracy."""
    from modeling.v6.replay_benchmark import load_benchmark_events, run_benchmark
    res = run_benchmark(load_benchmark_events(), eval_window=5)
    rep = selective.evaluate_selective(res)
    blended = next(c["acted_accuracy"] for c in rep["curve"] if c["threshold"] == 0.0)
    strong = rep["strong_band"]
    assert strong["acted_accuracy"] is not None
    assert strong["acted_accuracy"] > blended           # selectivity helps
    assert strong["coverage"] < 0.6                      # and it fires less often


def test_api_exposes_signal_and_event_tiers():
    p = build_intelligence_response(get_demo_portfolio("us_megacap_tech"), portfolio_is_demo=True)
    assert p["signal"]["tier"] in {"strong", "weak", "none"}
    assert all("signal_tier" in e for e in p["events"])


def test_sector_residualized_abnormal_present():
    """Single-name events should carry a sector-relative abnormal where available."""
    from modeling.v6.replay_benchmark import load_benchmark_events, run_benchmark
    res = run_benchmark(load_benchmark_events(), eval_window=5)
    have_sector = [r for r in res
                   if r["returns"].get(5, {}).get("sector_benchmark") is not None
                   and r["returns"][5].get("stock") is not None]
    assert have_sector, "expected some sector-residualized events"
    s = have_sector[0]["returns"][5]
    assert abs(s["abnormal"] - (s["stock"] - s["sector_benchmark"])) < 1e-9
