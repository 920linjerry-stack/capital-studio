"""Pillar 4: crowding / priced-for-perfection proxy.

This module deliberately exposes a **price-based proxy**, not a valuation
percentile and not a fundamental estimate. It measures whether a ticker has
already run hard into a low-volatility/high-expectations setup, then lets the
impact engine modulate company/earnings reactions:

* high crowding damps positive expected bp, and can flip only at the extreme;
* high crowding amplifies negative expected bp;
* missing data returns a neutral 0.5 state whose multiplier is exactly 1.0.

Default operation is offline and deterministic from ``data/crowding_snapshot``.
Network refresh is opt-in only and uses yfinance's keyless price history.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).with_name("data")
_SNAPSHOT_JSON = _DATA_DIR / "crowding_snapshot.json"

NEUTRAL_SCORE = 0.5

# Heuristic, non-calibrated weights. They combine recent run-up, proximity to
# the 52-week high, and low realized vol. These are price proxies only.
_W_RUN_UP = 0.45
_W_PROXIMITY = 0.35
_W_LOW_VOL = 0.20


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_snapshot() -> dict[str, Any]:
    if not _SNAPSHOT_JSON.exists():
        return {}
    try:
        data = json.loads(_SNAPSHOT_JSON.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load_crowding_snapshot() -> dict[str, Any]:
    """Load committed crowding proxy snapshot. Offline and deterministic."""
    return _load_snapshot()


def neutral_state(ticker: str) -> dict[str, Any]:
    return {
        "ticker": (ticker or "").upper(),
        "priced_for_perfection": NEUTRAL_SCORE,
        "band": "neutral",
        "source": "neutral_fallback",
        "data_mode": "unavailable",
        "note": "No crowding proxy data; neutral 0.5 leaves V6 1-3 behavior unchanged.",
    }


def crowding_state(ticker: str, snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return one ticker's crowding / priced-for-perfection proxy state."""
    t = (ticker or "").upper()
    data = snapshot if snapshot is not None else _load_snapshot()
    row = (data.get("tickers") or {}).get(t)
    if not isinstance(row, dict):
        return neutral_state(t)
    score = _clamp(float(row.get("priced_for_perfection", NEUTRAL_SCORE)))
    out = dict(row)
    out["ticker"] = t
    out["priced_for_perfection"] = round(score, 4)
    out.setdefault("band", crowding_band(score))
    out.setdefault("source", data.get("_meta", {}).get("source", "snapshot"))
    out.setdefault("data_mode", "fixture")
    return out


def crowding_band(score: float) -> str:
    score = _clamp(float(score))
    if score >= 0.75:
        return "high"
    if score <= 0.25:
        return "low"
    return "neutral"


def reaction_multiplier(effective_direction: int, state: dict[str, Any] | None) -> float:
    """Crowding reaction multiplier for company/earnings events.

    Only the high-crowding half changes behavior. Low/neutral crowding leaves
    reactions unchanged so missing data (0.5) is an exact fallback.
    """
    if effective_direction == 0:
        return 1.0
    score = _clamp(float((state or {}).get("priced_for_perfection", NEUTRAL_SCORE)))
    if score < 0.75:
        return 1.0
    pressure = max(0.0, score - NEUTRAL_SCORE) / NEUTRAL_SCORE
    if effective_direction > 0:
        # At very high crowding the "good news already paid for" effect may
        # turn a positive headline into a small negative reaction.
        return round(1.0 - 1.25 * pressure, 4)
    return round(1.0 + 0.75 * pressure, 4)


def _pct_change(prices: list[float], days: int) -> float:
    if len(prices) <= days or prices[-days - 1] == 0:
        return 0.0
    return prices[-1] / prices[-days - 1] - 1.0


def _realized_vol(prices: list[float], days: int = 21) -> float:
    if len(prices) < days + 1:
        return 0.0
    rets = []
    for a, b in zip(prices[-days - 1:-1], prices[-days:]):
        if a > 0:
            rets.append(math.log(b / a))
    if len(rets) < 2:
        return 0.0
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) * math.sqrt(252)


def _score_from_metrics(run_3m: float, run_6m: float, proximity: float, vol: float) -> float:
    run_component = _clamp((0.65 * run_3m + 0.35 * run_6m + 0.10) / 0.80)
    proximity_component = _clamp((proximity - 0.70) / 0.30)
    low_vol_component = _clamp(1.0 - (vol / 0.60))
    return _clamp(
        _W_RUN_UP * run_component
        + _W_PROXIMITY * proximity_component
        + _W_LOW_VOL * low_vol_component
    )


def compute_crowding(tickers: list[str], *, allow_network: bool = False) -> dict[str, dict[str, Any]]:
    """Return crowding states for tickers; refresh via yfinance only when opted in."""
    tickers = sorted({t.upper() for t in tickers if t})
    if not allow_network:
        snap = _load_snapshot()
        return {t: crowding_state(t, snap) for t in tickers}
    return refresh_crowding_snapshot(tickers).get("tickers", {})


def refresh_crowding_snapshot(tickers: list[str]) -> dict[str, Any]:
    """Best-effort yfinance refresh into ``data/crowding_snapshot.json``."""
    try:
        import yfinance as yf
    except ImportError:
        return _load_snapshot()

    rows: dict[str, Any] = {}
    for ticker in sorted({t.upper() for t in tickers if t}):
        try:
            hist = yf.Ticker(ticker).history(period="1y", auto_adjust=True)
            closes = [float(v) for v in hist["Close"].dropna().tolist()]
            if len(closes) < 63:
                continue
            run_3m = _pct_change(closes, 63)
            run_6m = _pct_change(closes, min(126, len(closes) - 1))
            high_52w = max(closes)
            proximity = closes[-1] / high_52w if high_52w else NEUTRAL_SCORE
            vol = _realized_vol(closes)
            score = _score_from_metrics(run_3m, run_6m, proximity, vol)
            rows[ticker] = {
                "ticker": ticker,
                "priced_for_perfection": round(score, 4),
                "band": crowding_band(score),
                "run_up_3m": round(run_3m, 4),
                "run_up_6m": round(run_6m, 4),
                "proximity_to_52w_high": round(proximity, 4),
                "realized_vol_1m": round(vol, 4),
                "data_mode": "live",
                "source": "yfinance keyless adjusted close history",
            }
        except Exception:  # noqa: BLE001 - one ticker should not abort refresh
            continue

    payload = {
        "_meta": {
            "refreshed_at": _iso_now(),
            "source": "yfinance keyless adjusted close history",
            "method": "heuristic price-only crowding / priced-for-perfection proxy; not valuation",
            "weights": {"run_up": _W_RUN_UP, "proximity_to_high": _W_PROXIMITY, "low_vol": _W_LOW_VOL},
        },
        "tickers": rows,
    }
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _SNAPSHOT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
