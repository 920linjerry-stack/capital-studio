"""V4.7 lightweight LBO return context.

This is a deliberately thin, single-line context layer for the LBO release
candidate. It reads only ``run_lbo()`` output plus the existing
``build_lbo_attribution()`` bridge and emits at most one short badge string.

Discipline
----------
* It is *context*, not a warning, not a suitability gate, and never a deal
  recommendation. It does not evaluate whether a transaction is good or bad,
  does not reference PE hurdles or market norms, and never says "should acquire"
  / "recommended".
* It performs no engine math: IRR comes from ``run_lbo``; component values come
  from the attribution bridge. This module only classifies them.
* Output is a single primary badge line (plus the list of all triggered codes
  for tests). UI / Excel render the one primary line only -- no paragraph layer.
"""

from __future__ import annotations

import math
from typing import Any


# ── Trigger thresholds ───────────────────────────────────────────────────────
LOW_RETURN_IRR_THRESHOLD = 0.10
# A component MOIC contribution at or below this magnitude is treated as "~0".
NEAR_ZERO_MOIC_CONTRIBUTION = 0.01
# Deleveraging MOIC contribution at or below this is "modest" / limited.
LIMITED_DELEVERAGING_THRESHOLD = 0.05
# At most this many badges are displayed (kept light, never a wall of badges).
MAX_DISPLAYED_BADGES = 2

# ── Canonical badge codes ────────────────────────────────────────────────────
LOW_RETURN_CONTEXT = "LOW_RETURN_CONTEXT"
DEBT_PAYDOWN_DRIVEN_CONTEXT = "DEBT_PAYDOWN_DRIVEN_CONTEXT"
DELEVERAGING_LED_CONTEXT = "DELEVERAGING_LED_CONTEXT"
GROWTH_DRIVEN_CONTEXT = "GROWTH_DRIVEN_CONTEXT"
LIMITED_DELEVERAGING_CONTEXT = "LIMITED_DELEVERAGING_CONTEXT"
EARLY_LIQUIDITY_PRESSURE_CONTEXT = "EARLY_LIQUIDITY_PRESSURE_CONTEXT"

# Priority order: the first triggered code becomes the displayed primary badge.
_PRIORITY = [
    LOW_RETURN_CONTEXT,
    EARLY_LIQUIDITY_PRESSURE_CONTEXT,
    DEBT_PAYDOWN_DRIVEN_CONTEXT,
    GROWTH_DRIVEN_CONTEXT,
    DELEVERAGING_LED_CONTEXT,
    LIMITED_DELEVERAGING_CONTEXT,
]

# Exact one-line strings. Kept short by contract: no disclaimers, no paragraphs.
_BADGES: dict[str, dict[str, str]] = {
    LOW_RETURN_CONTEXT: {
        "en": "Low return context: review attribution before interpreting the case.",
        "cn": "低回报提示：解释该情景前请先查看 attribution 来源。",
    },
    DEBT_PAYDOWN_DRIVEN_CONTEXT: {
        "en": "Debt paydown-driven: Base case return is mainly driven by deleveraging.",
        "cn": "债务偿还驱动：当前 Base case 回报主要来自 deleveraging。",
    },
    DELEVERAGING_LED_CONTEXT: {
        "en": "Deleveraging-led: deleveraging is the dominant positive return component.",
        "cn": "偿债主导：去杠杆是当前回报中最主要的正向贡献项。",
    },
    GROWTH_DRIVEN_CONTEXT: {
        "en": "Growth-driven case: return is mainly driven by EBITDA growth.",
        "cn": "增长驱动：当前回报主要来自 EBITDA 增长。",
    },
    LIMITED_DELEVERAGING_CONTEXT: {
        "en": "Limited deleveraging: debt paydown contributes modestly to returns.",
        "cn": "去杠杆有限：债务偿还对回报贡献较小。",
    },
    EARLY_LIQUIDITY_PRESSURE_CONTEXT: {
        "en": "Early liquidity pressure: revolver draw occurs during the hold period.",
        "cn": "前期流动性压力：持有期内需要动用 revolver。",
    },
}


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _none_result() -> dict[str, Any]:
    return {
        "status": "none",
        "severity": "context",
        "primary_code": None,
        "codes": [],
        "badges": [],
        "badge_en": "",
        "badge_cn": "",
    }


def build_return_context(lbo_result: dict | None, attribution: dict | None = None) -> dict:
    """Classify an LBO result into at most one lightweight return-context badge.

    Pure function. Returns ``status == "none"`` when nothing triggers, otherwise
    ``status == "ok"`` with a single ``primary_code`` / ``badge_en`` / ``badge_cn``
    plus the full ordered ``codes`` list. ``severity`` is always ``"context"`` --
    this layer never emits a warning or a recommendation.
    """
    lbo_result = lbo_result or {}
    if lbo_result.get("status") != "ok":
        return _none_result()

    returns = lbo_result.get("returns") or {}
    irr = _to_float(returns.get("irr"))

    # Component MOIC contributions come straight from the attribution bridge.
    contributions: dict[str, float] = {}
    if attribution and attribution.get("status") == "ok":
        for comp in attribution.get("components") or []:
            key = comp.get("key")
            value = _to_float(comp.get("moic_contribution"))
            if key is not None and value is not None:
                contributions[key] = value

    ebitda_growth = contributions.get("ebitda_growth")
    multiple_movement = contributions.get("multiple_movement")
    deleveraging = contributions.get("deleveraging")
    component_values = [
        v for k, v in contributions.items() if k != "residual" and v is not None
    ]

    # Revolver draw during the hold period (multi-tranche schedules only).
    revolver_draw_occurred = False
    for row in lbo_result.get("debt_schedule") or []:
        draw = _to_float(row.get("revolver_draw"))
        if draw is not None and draw > 0:
            revolver_draw_occurred = True
            break

    codes: list[str] = []

    # 1. Low return context: IRR below threshold.
    if irr is not None and irr < LOW_RETURN_IRR_THRESHOLD:
        codes.append(LOW_RETURN_CONTEXT)

    # 2. Debt paydown-driven: operating growth and multiple movement both ~0.
    if (
        ebitda_growth is not None
        and multiple_movement is not None
        and abs(ebitda_growth) <= NEAR_ZERO_MOIC_CONTRIBUTION
        and abs(multiple_movement) <= NEAR_ZERO_MOIC_CONTRIBUTION
    ):
        codes.append(DEBT_PAYDOWN_DRIVEN_CONTEXT)

    # 3. Deleveraging-led: deleveraging is the dominant positive component.
    if deleveraging is not None and deleveraging > NEAR_ZERO_MOIC_CONTRIBUTION:
        if component_values and deleveraging >= max(component_values):
            codes.append(DELEVERAGING_LED_CONTEXT)

    # 4. Growth-driven: EBITDA growth is the dominant positive component.
    if ebitda_growth is not None and ebitda_growth > NEAR_ZERO_MOIC_CONTRIBUTION:
        if component_values and ebitda_growth >= max(component_values):
            codes.append(GROWTH_DRIVEN_CONTEXT)

    # 5. Limited deleveraging: deleveraging is positive but modest.
    if (
        deleveraging is not None
        and NEAR_ZERO_MOIC_CONTRIBUTION < deleveraging <= LIMITED_DELEVERAGING_THRESHOLD
    ):
        codes.append(LIMITED_DELEVERAGING_CONTEXT)

    # 6. Early liquidity pressure: revolver draw occurred during the hold.
    if revolver_draw_occurred:
        codes.append(EARLY_LIQUIDITY_PRESSURE_CONTEXT)

    if not codes:
        return _none_result()

    ordered = [code for code in _PRIORITY if code in codes]
    displayed = ordered[:MAX_DISPLAYED_BADGES]
    badges = [
        {"code": code, "badge_en": _BADGES[code]["en"], "badge_cn": _BADGES[code]["cn"]}
        for code in displayed
    ]
    primary = ordered[0]
    return {
        "status": "ok",
        "severity": "context",
        "primary_code": primary,
        "codes": ordered,
        "badges": badges,
        "badge_en": _BADGES[primary]["en"],
        "badge_cn": _BADGES[primary]["cn"],
    }
