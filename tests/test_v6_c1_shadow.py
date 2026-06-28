"""C1 shadow model -- shadow-mode only, time-based split, never promoted blindly."""

from modeling.v6 import c1_shadow as c1
from modeling.v6.schemas import MarketEvent


def _earnings_event(ticker="NVDA", actual=1.0, expected=0.9):
    return MarketEvent(
        event_id="x", title=f"{ticker} earnings", source="t", source_type="company",
        timestamp="2024-01-01T00:00:00Z", event_type="earnings_beat", direction=1,
        magnitude=3, confidence=0.8, related_tickers=[ticker], actual=actual,
        expected=expected, surprise_std=0.1, surprise_source="t", higher_is_bullish=True,
    )


def test_train_returns_valid_scorecard():
    r = c1.train("postprint")
    assert r["status"] in {"ok", "shadow_under_review", "insufficient_sample"}
    if r["status"] == "insufficient_sample":
        return
    assert 0.0 <= r["shadow_oos"]["accuracy"] <= 1.0
    assert 0.0 <= r["shadow_oos"]["brier"] <= 1.0
    assert r["rule_baseline_oos_accuracy"] is not None
    assert set(r["feature_boundary"]) == set(r["features"])


def test_not_promoted_unless_beats_rule():
    r = c1.train("postprint")
    if r["status"] == "ok":
        assert r["shadow_oos"]["accuracy"] > r["rule_baseline_oos_accuracy"]


def test_time_split_is_deterministic_no_shuffle():
    a = c1.train("postprint")["coefficients_standardized"]
    b = c1.train("postprint")["coefficients_standardized"]
    assert a == b  # deterministic; no random shuffle
    # dataset is sorted ascending by event_time
    samples = c1.build_dataset("postprint")["samples"]
    times = [s["event_time"] for s in samples]
    assert times == sorted(times)


def test_postprint_feature_boundaries_flag_lookahead():
    for f in ("std_surprise", "whisper_excess"):
        assert "post-print only" in c1.FEATURE_BOUNDARY[f]


def test_shadow_for_event_is_shadow_only_and_safe():
    s = c1.shadow_for_event(_earnings_event())
    assert s["shadow_model_status"] == "shadow_only"
    assert s["shadow_signal_tier"] in {"strong", "weak", "none", "no_edge"}
    assert s["shadow_probability"] is None or 0.0 <= s["shadow_probability"] <= 1.0
    assert isinstance(s["shadow_missing_features"], list)


def test_shadow_for_event_records_missing_features_when_no_surprise():
    ev = MarketEvent(event_id="m", title="macro", source="t", source_type="macro",
                     timestamp="2024-01-01T00:00:00Z", event_type="rate_hike", direction=-1,
                     magnitude=3, confidence=0.8, related_tickers=["QQQ"])
    s = c1.shadow_for_event(ev)
    assert "std_surprise" in s["shadow_missing_features"]
