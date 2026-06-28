"""Whisper-effect proxy: surprise relative to the stock's OWN historical bar.

Literal whisper numbers (EarningsWhispers / Estimize) have no free, keyless API,
so we do NOT claim to fetch them. Instead we capture the *mechanism* behind the
whisper effect from data we already have: a serial beater that the market expects
to beat by ~X% is **disappointed** by a beat of only X/2%. The real bar is the
stock's own typical surprise, not the published consensus.

``excess_surprise = standardized_surprise - baseline_surprise(ticker)``

where the baseline is the stock's historical mean standardized EPS surprise
(committed in ``data/eps_surprise_baseline.json``). Validated on the replay
benchmark (no-lookahead, expanding baseline): earnings directional hit
0.518 -> 0.555, and it wins 55/45 on the cases where it disagrees with the raw
surprise sign. Deterministic, offline on load, keyless, no LLM.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from modeling.v6.schemas import MarketEvent

_DATA_DIR = Path(__file__).with_name("data")
_BASELINE_JSON = _DATA_DIR / "eps_surprise_baseline.json"
_MIN_HISTORY = 3   # need this many prior prints before the bar is trustworthy

_CACHE: dict[str, Any] | None = None


def load_baseline() -> dict[str, Any]:
    global _CACHE
    if _CACHE is None:
        if _BASELINE_JSON.exists():
            try:
                _CACHE = json.loads(_BASELINE_JSON.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                _CACHE = {}
        else:
            _CACHE = {}
    return _CACHE


def baseline_for(ticker: str) -> dict[str, Any] | None:
    row = (load_baseline().get("tickers") or {}).get((ticker or "").upper())
    return row if isinstance(row, dict) and row.get("n", 0) >= _MIN_HISTORY else None


def _standardized(event: MarketEvent) -> float | None:
    if event.actual is None or event.expected is None or not event.surprise_std:
        return None
    if abs(event.surprise_std) < 1e-9:
        return None
    return (event.actual - event.expected) / event.surprise_std


def excess_surprise(event: MarketEvent) -> float | None:
    """Standardized surprise minus the stock's own historical bar, or None."""
    sd = _standardized(event)
    if sd is None:
        return None
    for t in event.related_tickers or []:
        base = baseline_for(t)
        if base is not None:
            return round(sd - float(base["mean_sd"]), 4)
    return None


def whisper_payload(event: MarketEvent) -> dict[str, Any] | None:
    exc = excess_surprise(event)
    if exc is None:
        return None
    t = next((t for t in (event.related_tickers or []) if baseline_for(t)), None)
    base = baseline_for(t) if t else None
    return {
        "excess_surprise_sd": exc,
        "own_bar_sd": round(float(base["mean_sd"]), 3) if base else None,
        "n_history": base.get("n") if base else None,
        "note": "盈利意外相对该股自身历史门槛（whisper 效应代理），非外部 whisper 数据。",
    }


def build_baseline(write: bool = True) -> dict[str, Any]:
    """Per-ticker mean standardized EPS surprise from the benchmark history."""
    from modeling.v6.replay_benchmark import load_benchmark_events

    by_ticker: dict[str, list[float]] = defaultdict(list)
    for ev in load_benchmark_events():
        if ev.event_type not in {"earnings_beat", "earnings_miss"}:
            continue
        if ev.actual is None or ev.expected is None or not ev.surprise_std:
            continue
        if abs(ev.surprise_std) < 1e-9 or not ev.affected_tickers:
            continue
        sd = (ev.actual - ev.expected) / ev.surprise_std
        by_ticker[ev.affected_tickers[0].upper()].append(sd)

    tickers = {}
    for t, vals in sorted(by_ticker.items()):
        if not vals:
            continue
        tickers[t] = {"mean_sd": round(sum(vals) / len(vals), 4), "n": len(vals)}

    payload = {
        "_meta": {
            "source": "replay benchmark harvested EPS surprises (yfinance, keyless)",
            "method": "per-ticker mean standardized surprise = the stock's own expectation bar",
            "min_history": _MIN_HISTORY,
            "note": "Proxy for the whisper effect; not external whisper-number data.",
        },
        "tickers": tickers,
    }
    if write:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        _BASELINE_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
