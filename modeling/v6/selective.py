"""Selective prediction / abstention -- the engine should not fire every day.

The engine has real edge on some event types and none on others. Instead of
giving every headline a direction (blended ~0.62), it sorts each call into three
tiers by its calibrated ``direction_probability`` and only *acts* on the strong
band. On the benchmark this turns ~0.62 blended into ~0.80 acted-on accuracy at
~14% coverage -- a professional coverage/precision trade-off.

  * strong  (P >= 0.62)  -> act, high-conviction directional read
  * weak    (0.55..0.62) -> show but flag as low conviction
  * none    (P  < 0.55)  -> abstain (no edge / coin flip / contrarian)

Deterministic, offline, no LLM. Thresholds are transparent module constants.
"""

from __future__ import annotations

from typing import Any

from modeling.v6 import calibration

THRESHOLD_STRONG = 0.62
THRESHOLD_WEAK = 0.55

TIER_CN = {"strong": "强信号", "weak": "弱信号", "none": "无边际"}


def signal_tier(prob: float | None) -> str:
    """Map a calibrated direction probability to strong / weak / none."""
    if prob is None:
        return "none"
    if prob >= THRESHOLD_STRONG:
        return "strong"
    if prob >= THRESHOLD_WEAK:
        return "weak"
    return "none"


def tier_for_event_type(event_type: str) -> dict[str, Any]:
    p = calibration.direction_probability(event_type)
    tier = signal_tier(p)
    return {
        "probability": p,
        "tier": tier,
        "tier_cn": TIER_CN[tier],
        "act": tier == "strong",
    }


def portfolio_signal(driver_probs: list[float | None]) -> dict[str, Any]:
    """Portfolio-level conviction: act only when a strong-signal driver exists."""
    probs = [p for p in driver_probs if p is not None]
    strong = sum(1 for p in probs if p >= THRESHOLD_STRONG)
    weak = sum(1 for p in probs if THRESHOLD_WEAK <= p < THRESHOLD_STRONG)
    tier = "strong" if strong else "weak" if weak else "none"
    return {
        "tier": tier,
        "tier_cn": TIER_CN[tier],
        "act": tier == "strong",
        "strong_drivers": strong,
        "weak_drivers": weak,
        "max_probability": round(max(probs), 3) if probs else None,
    }


def evaluate_selective(results: list[dict[str, Any]], *, window: int = 5) -> dict[str, Any]:
    """Acted-on accuracy vs coverage across thresholds (the selectivity curve)."""
    from modeling.v6.replay_benchmark import _direction_at_window

    rows: list[tuple[float, int]] = []
    for r in results:
        if r["predicted_direction"] == 0:
            continue
        real = _direction_at_window(r, window)
        if real in (None, 0):
            continue
        p = calibration.direction_probability(r.get("event_type"))
        if p is None:
            continue
        rows.append((p, 1 if r["predicted_direction"] == real else 0))

    total = len(rows)
    curve = []
    for th in (0.0, THRESHOLD_WEAK, 0.58, 0.60, THRESHOLD_STRONG, 0.65, 0.68):
        acted = [h for p, h in rows if p >= th]
        if not acted:
            continue
        curve.append({
            "threshold": th,
            "acted": len(acted),
            "coverage": round(len(acted) / total, 3) if total else None,
            "acted_accuracy": round(sum(acted) / len(acted), 3),
        })
    strong = [h for p, h in rows if p >= THRESHOLD_STRONG]
    return {
        "total_decisive": total,
        "strong_band": {
            "threshold": THRESHOLD_STRONG,
            "acted": len(strong),
            "coverage": round(len(strong) / total, 3) if total else None,
            "acted_accuracy": round(sum(strong) / len(strong), 3) if strong else None,
        },
        "curve": curve,
        "note": "Acted-on accuracy on the strong band; coverage is intentionally low (don't fire every day).",
    }
