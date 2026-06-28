"""B2: deterministic macro-regime classifier (the "non-textbook" context layer).

The engine's flat per-event rules are context-free -- that is why the benchmark
shows ``rate_hike`` hitting only ~0.46 (a mechanical "hike = bearish" rule is
wrong when the hike is already priced into a hiking cycle). This module supplies
the missing market *state*: rate cycle, risk appetite, price trend, and
inflation direction, so a reaction can be read against the prevailing regime.

It is **offline and deterministic by default**, reading a committed snapshot
(``data/regime_snapshot.json``). An opt-in network refresh derives the same
fields from keyless yfinance index/price history -- never an LLM, never a key.

``regime_multiplier`` is a transparent, *labelled heuristic* (not yet learned):
a macro reaction that merely confirms the prevailing cycle is damped (more
priced-in), while a reaction that fights the cycle is left intact. It is exposed
as a pure function and surfaced as context; wiring it into live scoring is gated
behind a regime-labelled calibration refit so it never silently changes the
existing deterministic outputs.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).with_name("data")
_SNAPSHOT_JSON = _DATA_DIR / "regime_snapshot.json"

# Canonical labels.
RATE_CYCLES = ("hiking", "cutting", "hold")
RISK_STATES = ("risk_on", "risk_off", "neutral")
TRENDS = ("uptrend", "downtrend", "range")
INFLATION = ("rising", "falling", "stable")

_NEUTRAL = {
    "rate_cycle": "hold",
    "risk": "neutral",
    "trend": "range",
    "inflation": "stable",
    "source": "neutral_fallback",
    "data_mode": "unavailable",
    "as_of": None,
}

# Chinese labels for the cockpit.
LABELS_CN = {
    "hiking": "加息周期", "cutting": "降息周期", "hold": "利率观望",
    "risk_on": "风险偏好", "risk_off": "风险规避", "neutral": "情绪中性",
    "uptrend": "上行趋势", "downtrend": "下行趋势", "range": "区间震荡",
    "rising": "通胀上行", "falling": "通胀降温", "stable": "通胀平稳",
}


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


def regime_state(snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the current macro regime. Offline and deterministic by default."""
    data = snapshot if snapshot is not None else _load_snapshot()
    state = (data or {}).get("regime") if isinstance(data, dict) else None
    if not isinstance(state, dict):
        return dict(_NEUTRAL)
    out = dict(_NEUTRAL)
    for key in ("rate_cycle", "risk", "trend", "inflation"):
        if state.get(key) in _ALLOWED[key]:
            out[key] = state[key]
    out["source"] = state.get("source") or (data.get("_meta", {}) or {}).get("source", "snapshot")
    out["data_mode"] = state.get("data_mode", "fixture")
    out["as_of"] = state.get("as_of") or (data.get("_meta", {}) or {}).get("as_of")
    out["labels_cn"] = {k: LABELS_CN.get(out[k], out[k]) for k in ("rate_cycle", "risk", "trend", "inflation")}
    return out


_ALLOWED = {
    "rate_cycle": set(RATE_CYCLES),
    "risk": set(RISK_STATES),
    "trend": set(TRENDS),
    "inflation": set(INFLATION),
}

# Which macro event types "confirm" each cycle/state (so they are more priced-in
# when aligned). Damping factor < 1.0 reduces a confirming reaction's magnitude.
_CONFIRM = {
    "hiking": {"rate_hike", "macro_inflation_hot", "yields_up"},
    "cutting": {"rate_cut", "macro_inflation_cool", "yields_down"},
    "risk_off": {"risk_off", "bank_stress", "credit_stress"},
    "risk_on": {"risk_on", "ai_capex_semis"},
}
_PRICED_IN_DAMP = 0.7   # a fully-confirming, priced-in reaction keeps 70% weight
_AGAINST_BOOST = 1.15   # a reaction that fights the regime is a bigger surprise


def regime_multiplier(event_type: str, regime: dict[str, Any] | None) -> float:
    """Transparent heuristic: damp regime-confirming macro reactions, boost
    regime-fighting ones. 1.0 (no-op) for unknown types or a neutral regime.

    This is a *heuristic*, not a learned coefficient -- it is exposed for opt-in
    use and surfaced as context. Live scoring does not apply it by default.
    """
    if not event_type or not isinstance(regime, dict):
        return 1.0
    cycle = regime.get("rate_cycle")
    risk = regime.get("risk")
    confirms = _CONFIRM.get(cycle, set()) | _CONFIRM.get(risk, set())
    if not confirms:
        return 1.0
    if event_type in confirms:
        return _PRICED_IN_DAMP
    # An opposite macro print under a strong regime is a larger surprise.
    opposite = {
        "rate_hike": "rate_cut", "rate_cut": "rate_hike",
        "macro_inflation_hot": "macro_inflation_cool",
        "macro_inflation_cool": "macro_inflation_hot",
    }.get(event_type)
    if opposite and opposite in confirms:
        return _AGAINST_BOOST
    return 1.0


def refresh_regime_snapshot() -> dict[str, Any]:
    """Best-effort keyless yfinance refresh of the regime snapshot (opt-in)."""
    try:
        import yfinance as yf
    except ImportError:
        return _load_snapshot()

    def _series(ticker: str, period: str = "1y") -> list[float]:
        try:
            hist = yf.Ticker(ticker).history(period=period, auto_adjust=True)
            return [float(v) for v in hist["Close"].dropna().tolist()]
        except Exception:  # noqa: BLE001
            return []

    spy = _series("SPY")
    trend = "range"
    if len(spy) >= 200:
        sma200 = sum(spy[-200:]) / 200.0
        trend = "uptrend" if spy[-1] > sma200 * 1.01 else "downtrend" if spy[-1] < sma200 * 0.99 else "range"

    # ^VIX for risk appetite; ^IRX (13-week T-bill) slope for the rate cycle.
    vix = _series("^VIX", period="3mo")
    risk = "neutral"
    if vix:
        risk = "risk_off" if vix[-1] >= 22 else "risk_on" if vix[-1] <= 16 else "neutral"
    irx = _series("^IRX", period="6mo")
    rate_cycle = "hold"
    if len(irx) >= 60:
        rate_cycle = "hiking" if irx[-1] > irx[-60] + 0.15 else "cutting" if irx[-1] < irx[-60] - 0.15 else "hold"

    state = {
        "rate_cycle": rate_cycle, "risk": risk, "trend": trend,
        "inflation": "stable", "data_mode": "live",
        "source": "yfinance keyless index history", "as_of": _iso_now(),
    }
    payload = {"_meta": {"refreshed_at": _iso_now(), "source": "yfinance keyless index history"}, "regime": state}
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _SNAPSHOT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
