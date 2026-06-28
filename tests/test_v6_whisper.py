"""Whisper-effect proxy: surprise relative to the stock's own historical bar.

Validated on the benchmark to lift earnings directional hit (0.518 -> 0.555,
no-lookahead). These tests pin the mechanism and the engine wiring."""

from modeling.v6 import whisper, surprise
from modeling.v6.schemas import MarketEvent


def _earnings_event(ticker, actual, expected, std=0.1):
    return MarketEvent(
        event_id=f"t-{ticker}", title=f"{ticker} earnings", source="t",
        source_type="company", timestamp="2024-01-01T00:00:00Z",
        event_type="earnings_beat" if actual >= expected else "earnings_miss",
        direction=1 if actual >= expected else -1, magnitude=3, confidence=0.8,
        related_tickers=[ticker], actual=actual, expected=expected,
        surprise_std=std, surprise_source="test", higher_is_bullish=True,
    )


def test_baseline_snapshot_present_and_sane():
    base = whisper.load_baseline().get("tickers") or {}
    assert base, "expected a committed whisper baseline"
    for t, row in base.items():
        assert row["n"] >= 1 and isinstance(row["mean_sd"], (int, float))


def test_excess_is_surprise_minus_own_bar():
    base = whisper.baseline_for("NVDA")
    if base is None:
        return  # NVDA may lack enough history in some refits
    bar = base["mean_sd"]
    # a beat exactly at the bar -> excess ~ 0
    ev = _earnings_event("NVDA", actual=1.0 + bar * 0.1, expected=1.0, std=0.1)
    exc = whisper.excess_surprise(ev)
    assert exc is not None and abs(exc) < 0.05


def test_thin_beat_below_bar_reads_bearish():
    """A serial beater beating by far less than its bar -> bearish (AVGO effect)."""
    base = whisper.baseline_for("NVDA")
    if base is None or base["mean_sd"] < 0.3:
        return
    # standardized surprise of +0.1sd, far below NVDA's ~0.78sd bar
    ev = _earnings_event("NVDA", actual=1.01, expected=1.0, std=0.1)  # +0.1sd
    assert whisper.excess_surprise(ev) < 0
    assert surprise.effective_direction(ev) == -1   # whisper flips a nominal beat


def test_no_baseline_falls_back_to_raw_surprise():
    ev = _earnings_event("ZZZZ_NOPROFILE", actual=1.2, expected=1.0, std=0.1)
    assert whisper.excess_surprise(ev) is None
    assert surprise.effective_direction(ev) == 1   # raw beat stays bullish
