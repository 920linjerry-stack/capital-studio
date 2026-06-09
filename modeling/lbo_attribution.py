"""V4.3 LBO returns attribution bridge.

Pure explanatory layer: it decomposes the equity value created by a V4.0
single-tranche LBO into EBITDA growth, multiple movement, deleveraging and fee
drag, with an explicit residual safety valve. It reads only ``run_lbo()`` output
plus the original inputs; it never re-runs the LBO engine and never produces a
second IRR / MOIC truth set.

Design notes
------------
* MOIC / equity value bridge only. IRR is shown as headline, not attributed,
  because IRR is time-weighted and component IRR would be falsely precise.
* In the closed V4.0 structure (single tranche, 100% cash sweep, no cash
  balance bridge, no revolver) the residual should be ~0. A large residual is a
  safety-valve signal, not a routine attribution bucket.
* No deal-conclusion language. Only directional sources of modeled return.
"""

from __future__ import annotations

import math
from typing import Any


METHOD = "single_tranche_equity_value_bridge_v43"

DISCLOSURE_EN = (
    "Attribution bridge is a simplified equity value bridge. It explains model "
    "return sources directionally and is not an investment or acquisition "
    "recommendation."
)
DISCLOSURE_CN = (
    "回报归因桥是简化的股权价值桥，用于解释模型回报来源，不构成投资建议或收购建议。"
)
MOIC_CONTRIBUTION_NOTE_EN = (
    "Component MOIC contribution sums to MOIC - 1.0, not headline MOIC."
)
MOIC_CONTRIBUTION_NOTE_CN = (
    "各项 MOIC 贡献加总对应 MOIC - 1.0，不是 headline MOIC 本身。"
)


def _flag(code: str, message: str, severity: str = "warning") -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message}


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


def _pick(*values: Any) -> float | None:
    for value in values:
        number = _to_float(value)
        if number is not None:
            return number
    return None


def _direction(value: float, tolerance: float) -> str:
    if abs(value) <= tolerance:
        return "neutral"
    return "positive" if value > 0 else "negative"


def _unavailable(code: str, message: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "method": METHOD,
        "components": [],
        "flags": [_flag(code, message)],
    }


def build_lbo_attribution(inputs: dict, lbo_result: dict) -> dict:
    """Build the LBO returns attribution bridge from ``run_lbo()`` output.

    Pure function: no Flask dependency, no file I/O, no provider fetch. Does not
    recalculate headline IRR / MOIC.
    """
    inputs = inputs or {}
    lbo_result = lbo_result or {}

    if lbo_result.get("status") != "ok" or not lbo_result.get("returns"):
        return _unavailable(
            "ATTRIBUTION_UNAVAILABLE_LBO_NOT_OK",
            "Attribution is unavailable because LBO run did not produce valid returns.",
        )

    ts = lbo_result.get("transaction_summary") or {}
    ex = lbo_result.get("exit") or {}
    ret = lbo_result.get("returns") or {}
    debt_schedule = lbo_result.get("debt_schedule") or []
    cap_summary = lbo_result.get("capital_structure_summary") or {}
    is_multi_tranche = cap_summary.get("mode") == "multi_tranche"
    transaction_inputs = inputs.get("transaction") or {}
    currency = lbo_result.get("currency") or inputs.get("currency")

    flags: list[dict[str, str]] = []

    entry_ebitda = _pick(ts.get("entry_ebitda"), transaction_inputs.get("entry_ebitda"))
    entry_multiple = _pick(ts.get("entry_multiple"), transaction_inputs.get("entry_multiple"))
    transaction_fees = _pick(ts.get("transaction_fees"))
    sponsor_equity = _pick(ts.get("sponsor_equity"), ret.get("sponsor_equity"))
    original_debt = _pick(cap_summary.get("total_opening_debt"), ts.get("debt_amount"))
    exit_ebitda = _pick(ex.get("exit_ebitda"))
    exit_multiple = _pick(ex.get("exit_multiple"), ts.get("exit_multiple"), transaction_inputs.get("exit_multiple"))
    remaining_debt = _pick(cap_summary.get("total_ending_debt"), ex.get("remaining_debt"), ret.get("remaining_debt"))
    ending_cash_balance = _pick(cap_summary.get("ending_cash_balance"), ex.get("ending_cash_balance"), ret.get("ending_cash_balance"))
    exit_equity_value = _pick(ex.get("exit_equity_value"), ret.get("exit_equity_value"))
    cash_to_balance_sheet = _pick(ts.get("cash_to_balance_sheet"))
    moic = _pick(ret.get("moic"))
    irr = _pick(ret.get("irr"))

    if sponsor_equity is None or sponsor_equity <= 0:
        return _unavailable(
            "ATTRIBUTION_UNAVAILABLE_SPONSOR_EQUITY_NON_POSITIVE",
            "Attribution is unavailable because sponsor equity is missing or non-positive.",
        )
    if exit_equity_value is None:
        return _unavailable(
            "ATTRIBUTION_UNAVAILABLE_EXIT_EQUITY_MISSING",
            "Attribution is unavailable because exit equity value is missing.",
        )

    entry_ebitda = entry_ebitda if entry_ebitda is not None else 0.0
    exit_ebitda = exit_ebitda if exit_ebitda is not None else entry_ebitda
    original_debt = original_debt if original_debt is not None else 0.0
    remaining_debt = remaining_debt if remaining_debt is not None else 0.0

    if entry_multiple is None:
        entry_multiple = 0.0
        flags.append(_flag(
            "ATTRIBUTION_ENTRY_MULTIPLE_UNAVAILABLE",
            "Entry multiple is unavailable; EBITDA growth contribution may be understated.",
        ))
    if exit_multiple is None:
        exit_multiple = entry_multiple

    ebitda_growth = (exit_ebitda - entry_ebitda) * entry_multiple
    multiple_movement = exit_ebitda * (exit_multiple - entry_multiple)
    deleveraging = original_debt - remaining_debt

    if transaction_fees is None:
        transaction_fees = 0.0
        flags.append(_flag(
            "TRANSACTION_FEES_UNAVAILABLE",
            "Transaction fees are unavailable; fee drag is set to zero.",
        ))
    fees_drag = -transaction_fees

    if remaining_debt > original_debt:
        flags.append(_flag(
            "DEBT_INCREASED_DURING_HOLD",
            "Remaining debt exceeds original debt; deleveraging contribution is negative.",
        ))

    ending_cash_balance = ending_cash_balance if ending_cash_balance is not None else 0.0
    cash_to_balance_sheet = cash_to_balance_sheet if cash_to_balance_sheet is not None else 0.0
    initial_cash_funding = -cash_to_balance_sheet if cash_to_balance_sheet > 0 else 0.0

    target = exit_equity_value - sponsor_equity
    component_sum_before_residual = (
        ebitda_growth
        + multiple_movement
        + deleveraging
        + fees_drag
        + initial_cash_funding
    )
    if is_multi_tranche:
        component_sum_before_residual += ending_cash_balance
    residual = target - component_sum_before_residual
    residual_abs = abs(residual)

    tolerance_abs = max(1e-6, abs(target) * 1e-6)
    large_residual_threshold = max(1e-6, abs(target) * 0.05)
    mathematical_tie_out_pass = residual_abs <= tolerance_abs
    directional_bridge_pass = residual_abs <= large_residual_threshold

    if not directional_bridge_pass:
        flags.append(_flag(
            "ATTRIBUTION_RESIDUAL_LARGE",
            "Attribution residual exceeds 5% of equity value creation; treat the bridge as directional only.",
        ))

    total_fcf_for_sweep = sum(max(0.0, _to_float(row.get("fcf_available_for_sweep")) or 0.0) for row in debt_schedule)
    total_optional = sum(max(0.0, _to_float(row.get("optional_repayment")) or 0.0) for row in debt_schedule)
    unswept_cash = total_fcf_for_sweep - total_optional
    retained_cash_threshold = max(1e-6, abs(sponsor_equity) * 1e-4)
    if not is_multi_tranche and remaining_debt <= tolerance_abs and unswept_cash > retained_cash_threshold:
        flags.append(_flag(
            "ATTRIBUTION_RETAINED_CASH_NOT_MODELED",
            "Residual interpretation note: the simplified V4.0 structure does not model "
            "retained cash after debt is fully repaid; excess FCF does not enter exit "
            "equity, so the bridge should be interpreted as directional.",
        ))

    def _moic_contribution(value: float) -> float:
        return value / sponsor_equity

    components = [
        {
            "key": "ebitda_growth",
            "label_en": "EBITDA growth",
            "label_cn": "EBITDA 增长贡献",
            "value": ebitda_growth,
            "moic_contribution": _moic_contribution(ebitda_growth),
            "direction": _direction(ebitda_growth, tolerance_abs),
            "rationale_en": (
                "Exit EBITDA is above entry EBITDA at the entry multiple."
                if ebitda_growth > tolerance_abs else
                ("Exit EBITDA is below entry EBITDA at the entry multiple."
                 if ebitda_growth < -tolerance_abs else
                 "Exit EBITDA is broadly in line with entry EBITDA.")
            ),
            "rationale_cn": (
                "退出 EBITDA 高于入场 EBITDA，在买入倍数不变下提升企业价值。"
                if ebitda_growth > tolerance_abs else
                ("退出 EBITDA 低于入场 EBITDA，经营层面对企业价值形成拖累。"
                 if ebitda_growth < -tolerance_abs else
                 "退出 EBITDA 与入场 EBITDA 基本持平，经营增长贡献接近 0。")
            ),
        },
        {
            "key": "multiple_movement",
            "label_en": "Multiple movement",
            "label_cn": "估值倍数变化贡献",
            "value": multiple_movement,
            "moic_contribution": _moic_contribution(multiple_movement),
            "direction": _direction(multiple_movement, tolerance_abs),
            "rationale_en": (
                "Exit multiple is above entry multiple."
                if multiple_movement > tolerance_abs else
                ("Exit multiple is below entry multiple."
                 if multiple_movement < -tolerance_abs else
                 "Exit multiple equals entry multiple.")
            ),
            "rationale_cn": (
                "退出倍数高于买入倍数，回报部分来自 multiple expansion。"
                if multiple_movement > tolerance_abs else
                ("退出倍数低于买入倍数，回报受到 multiple contraction 拖累。"
                 if multiple_movement < -tolerance_abs else
                 "退出倍数等于买入倍数，因此 Base case 不依赖倍数扩张。")
            ),
        },
        {
            "key": "deleveraging",
            "label_en": "Deleveraging",
            "label_cn": "债务偿还贡献",
            "value": deleveraging,
            "moic_contribution": _moic_contribution(deleveraging),
            "direction": _direction(deleveraging, tolerance_abs),
            "rationale_en": (
                "Debt is paid down during the hold period."
                if deleveraging > tolerance_abs else
                ("Net debt increases during the hold period."
                 if deleveraging < -tolerance_abs else
                 "Net debt is broadly unchanged during the hold period.")
            ),
            "rationale_cn": (
                "持有期内自由现金流用于偿还债务，提升退出时归属 sponsor 的股权价值。"
                if deleveraging > tolerance_abs else
                ("持有期内债务净额上升，对退出股权价值形成拖累。"
                 if deleveraging < -tolerance_abs else
                 "持有期内债务净额基本未变，偿债贡献接近 0。")
            ),
        },
        {
            "key": "fees_drag",
            "label_en": "Fees drag",
            "label_cn": "交易费用拖累",
            "value": fees_drag,
            "moic_contribution": _moic_contribution(fees_drag),
            "direction": _direction(fees_drag, tolerance_abs),
            "rationale_en": "Transaction fees increase initial sponsor equity and reduce MOIC contribution.",
            "rationale_cn": "交易费用增加初始 sponsor equity，降低回报倍数。",
        },
        {
            "key": "residual",
            "label_en": "Residual",
            "label_cn": "Residual / 其他差异",
            "value": residual,
            "moic_contribution": _moic_contribution(residual),
            "direction": _direction(residual, tolerance_abs),
            "rationale_en": (
                "Captures any path difference between the bridge and the full model output; "
                "normally near zero in the closed V4.0 structure."
            ),
            "rationale_cn": "用于承接归因桥与完整模型之间的路径差异；在 V4.0 当前封闭结构下通常应接近 0。",
        },
    ]

    if is_multi_tranche:
        components.insert(len(components) - 1, {
            "key": "ending_cash_balance",
            "label_en": "Ending cash balance",
            "label_cn": "期末现金余额贡献",
            "value": ending_cash_balance,
            "moic_contribution": _moic_contribution(ending_cash_balance),
            "direction": _direction(ending_cash_balance, tolerance_abs) if ending_cash_balance > tolerance_abs else "neutral",
            "rationale_en": (
                "Multi-tranche mode captures cash retained after debt repayment; "
                "ending cash increases exit equity value."
            ),
            "rationale_cn": "多档债务模式会捕捉债务偿还后的期末现金余额，该现金增加退出股权价值。",
        })
    if cash_to_balance_sheet > tolerance_abs:
        components.insert(len(components) - 1, {
            "key": "initial_cash_funding",
            "label_en": "Initial Cash Funding",
            "label_cn": "初始现金注入",
            "value": initial_cash_funding,
            "moic_contribution": _moic_contribution(initial_cash_funding),
            "direction": _direction(initial_cash_funding, tolerance_abs),
            "rationale_en": "Cash funded to the balance sheet at close is included in sponsor equity.",
            "rationale_cn": "交易日注入资产负债表的现金已包含在 Sponsor Equity 中。",
        })

    method = "multi_tranche_equity_value_bridge_v44" if is_multi_tranche else METHOD

    return {
        "status": "ok",
        "method": method,
        "currency": currency,
        "headline": {
            "sponsor_equity": sponsor_equity,
            "exit_equity_value": exit_equity_value,
            "equity_value_creation": target,
            "moic": moic,
            "irr": irr,
        },
        "components": components,
        "tie_out": {
            "target_equity_value_creation": target,
            "component_sum_before_residual": component_sum_before_residual,
            "residual": residual,
            "residual_abs": residual_abs,
            "tolerance_abs": tolerance_abs,
            "large_residual_threshold": large_residual_threshold,
            "mathematical_tie_out_pass": mathematical_tie_out_pass,
            "directional_bridge_pass": directional_bridge_pass,
        },
        "notes": {
            "moic_contribution_note_en": MOIC_CONTRIBUTION_NOTE_EN,
            "moic_contribution_note_cn": MOIC_CONTRIBUTION_NOTE_CN,
            "disclosure_en": DISCLOSURE_EN,
            "disclosure_cn": DISCLOSURE_CN,
        },
        "flags": flags,
    }
