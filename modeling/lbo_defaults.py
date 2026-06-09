"""V4.1 explainable default LBO structure builder.

This module builds starter assumptions only. It does not calculate IRR / MOIC
and does not change the V4.0 run_lbo() return engine.
"""

from __future__ import annotations

import math
from typing import Any


DSCR_THRESHOLD = 1.25
DEFAULT_ENTRY_MULTIPLE = 10.0
DEFAULT_INTEREST_RATE = 0.09
DEFAULT_FEES_PCT_EV = 0.02
DEFAULT_AMORTIZATION_PCT = 0.01
DEFAULT_EXIT_YEAR = 5
DEFAULT_TAX_RATE = 0.25


def _flag(severity: str, code: str, message: str) -> dict[str, str]:
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


def _first_number(data: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        value = _to_float(data.get(key))
        if value is not None:
            return value
    return None


def _numbers(values: Any) -> list[float] | None:
    if not isinstance(values, list) or not values:
        return None
    out = []
    for value in values:
        number = _to_float(value)
        if number is None:
            return None
        out.append(number)
    return out


def _core_provenance() -> dict[str, dict[str, str]]:
    return {
        "entry_ebitda": {
            "source": "financials_or_operating_forecast",
            "confidence": "medium",
            "rationale_cn": "使用最近可得 EBITDA / EBIT+D&A 作为入场 EBITDA 近似。",
        },
        "entry_multiple": {
            "source": "market_ev_ebitda_or_placeholder",
            "confidence": "low",
            "rationale_cn": "若无法可靠取得当前 EV/EBITDA，则使用保守占位默认值，用户应手动校准。",
        },
        "exit_multiple": {
            "source": "entry_multiple",
            "confidence": "policy",
            "rationale_cn": "退出倍数默认等于买入倍数，避免 Base case 依赖倍数扩张。",
        },
        "exit_year": {
            "source": "v41_policy_default",
            "confidence": "policy",
            "rationale_cn": "V4.1 仍只支持最终预测年退出，默认持有期为 5 年。",
        },
        "transaction_fees_pct_ev": {
            "source": "v41_simplified_fee_placeholder",
            "confidence": "policy",
            "rationale_cn": "用于粗略反映交易费用，V4.1 只做简化处理，用户可手动修改。",
        },
        "entry_structure": {
            "source": "v41_simplified_entry_structure",
            "confidence": "policy",
            "rationale_cn": "V4.1 假设存量净债务被再融资或暂不纳入，入场资本结构仅按新增收购债务建模；这会影响真实 sponsor equity，后续版本可扩展净债务桥。",
        },
        "leverage_multiple": {
            "source": "serviceability_builder_v41",
            "confidence": "medium",
            "rationale_cn": "默认杠杆先以 5.0x 作为惯例候选值，再用 DSCR 偿债覆盖校验；若不通过，则每次下调 0.5x，直到通过或降至 1.0x。",
        },
        "debt_amount": {
            "source": "entry_ebitda_x_final_leverage",
            "confidence": "medium",
            "rationale_cn": "默认债务金额等于入场 EBITDA 乘以通过偿债能力校验后的最终杠杆倍数。",
        },
        "interest_rate": {
            "source": "manual_market_convention_placeholder",
            "confidence": "low",
            "rationale_cn": "V4.1 暂不接入实时信贷市场利差，使用可修改的市场惯例占位值。",
        },
        "mandatory_amortization_pct": {
            "source": "v41_single_tranche_placeholder",
            "confidence": "policy",
            "rationale_cn": "默认按单档 TLB-like 简化债务处理，强制摊销为初始债务的 1.0%。",
        },
        "cash_sweep_pct": {
            "source": "v41_policy_locked",
            "confidence": "policy",
            "rationale_cn": "默认 100% 现金扫款；V4.1 不做现金余额桥或 partial sweep。",
        },
        "cash_to_balance_sheet": {
            "source": "v41_policy_locked",
            "confidence": "policy",
            "rationale_cn": "V4.1 不做现金余额桥，因此默认不向资产负债表留存现金。",
        },
        "tax_shield_serviceability": {
            "source": "v41_simplified_serviceability_check",
            "confidence": "medium",
            "rationale_cn": "V4.1 的偿债能力校验包含简化利息税盾，避免默认杠杆过度保守；但 V4.0 run_lbo 主引擎仍使用外生 cash taxes，IRR / MOIC 不单独建税盾。",
        },
    }


def _entry_ebitda(raw: dict[str, Any], flags: list[dict[str, str]]) -> float | None:
    direct = _first_number(raw, ["entry_ebitda", "ebitda", "ltm_ebitda"])
    if direct is not None:
        return direct
    ebit = _first_number(raw, ["ebit", "operating_income"])
    da = _first_number(raw, ["da", "d_and_a", "depreciation_amortization", "depreciationAndAmortization"])
    if ebit is not None and da is not None:
        return ebit + da
    if ebit is not None:
        flags.append(_flag("warning", "EBITDA_APPROXIMATED_BY_EBIT", "Entry EBITDA was approximated using EBIT because D&A was unavailable."))
        return ebit
    return None


def _forecast(raw: dict[str, Any], entry_ebitda: float) -> dict[str, list[float]]:
    forecast = raw.get("operating_forecast") if isinstance(raw.get("operating_forecast"), dict) else {}
    years = _numbers(forecast.get("years")) or [1, 2, 3, 4, 5]
    n = len(years)
    revenue = _numbers(forecast.get("revenue")) or _numbers(raw.get("revenue_path"))
    ebitda = _numbers(forecast.get("ebitda")) or _numbers(raw.get("ebitda_path"))
    cash_taxes = _numbers(forecast.get("cash_taxes")) or _numbers(raw.get("cash_taxes_path"))
    capex = _numbers(forecast.get("capex")) or _numbers(raw.get("capex_path"))
    change_in_nwc = _numbers(forecast.get("change_in_nwc")) or _numbers(raw.get("change_in_nwc_path"))

    revenue_scalar = _first_number(raw, ["revenue"]) or entry_ebitda * 5.0
    if revenue is None:
        revenue = [revenue_scalar] * n
    if ebitda is None:
        ebitda = [entry_ebitda] * n
    if cash_taxes is None:
        cash_taxes = [entry_ebitda * 0.10] * n
    if capex is None:
        capex = [entry_ebitda * 0.15] * n
    if change_in_nwc is None:
        change_in_nwc = [entry_ebitda * 0.02] * n
    return {
        "years": years[:n],
        "revenue": revenue[:n],
        "ebitda": ebitda[:n],
        "cash_taxes": cash_taxes[:n],
        "capex": capex[:n],
        "change_in_nwc": change_in_nwc[:n],
    }


def _infer_tax_rate(raw: dict[str, Any], forecast: dict[str, list[float]], flags: list[dict[str, str]]) -> tuple[float, str]:
    tax_rate = _to_float(raw.get("tax_rate"))
    if tax_rate is not None and 0 <= tax_rate <= 0.35:
        return tax_rate, "raw_defaults.tax_rate"
    raw_forecast = raw.get("operating_forecast") if isinstance(raw.get("operating_forecast"), dict) else {}
    has_cash_tax_observation = (
        isinstance(raw_forecast, dict) and isinstance(raw_forecast.get("cash_taxes"), list)
    ) or isinstance(raw.get("cash_taxes_path"), list)
    if not has_cash_tax_observation:
        flags.append(_flag("warning", "TAX_RATE_PLACEHOLDER_USED", "Tax rate was unavailable; V4.1 serviceability check used a 25% placeholder."))
        return DEFAULT_TAX_RATE, "placeholder"
    cash_taxes = forecast["cash_taxes"][0] if forecast["cash_taxes"] else None
    ebit = _first_number(raw, ["ebit", "operating_income"])
    if cash_taxes is not None and ebit and ebit > 0:
        return min(0.35, max(0.0, cash_taxes / ebit)), "cash_taxes_over_ebit"
    ebitda = forecast["ebitda"][0] if forecast["ebitda"] else None
    if cash_taxes is not None and ebitda and ebitda > 0:
        return min(0.35, max(0.0, cash_taxes / ebitda)), "cash_taxes_over_ebitda"
    flags.append(_flag("warning", "TAX_RATE_PLACEHOLDER_USED", "Tax rate was unavailable; V4.1 serviceability check used a 25% placeholder."))
    return DEFAULT_TAX_RATE, "placeholder"


def _entry_multiple(raw: dict[str, Any], entry_ebitda: float, flags: list[dict[str, str]]) -> float:
    explicit = _to_float(raw.get("entry_multiple"))
    if explicit and explicit > 0:
        return explicit
    ev = _first_number(raw, ["enterprise_value", "current_enterprise_value", "ev"])
    if ev and ev > 0 and entry_ebitda > 0:
        multiple = ev / entry_ebitda
        if 1.0 <= multiple <= 40.0:
            return multiple
    flags.append(_flag("warning", "ENTRY_MULTIPLE_PLACEHOLDER_USED", "Reliable market EV/EBITDA was unavailable; entry multiple uses a 10.0x placeholder."))
    return DEFAULT_ENTRY_MULTIPLE


def _serviceability_for_leverage(
    forecast: dict[str, list[float]],
    entry_ebitda: float,
    leverage: float,
    interest_rate: float,
    mandatory_amortization_pct: float,
    tax_rate: float,
) -> dict[str, Any]:
    original_debt = entry_ebitda * leverage
    beginning_debt = original_debt
    yearly = []
    min_dscr = None
    min_year = None
    pass_all = True
    structure_anomaly = False
    for idx, year in enumerate(forecast["years"]):
        cash_interest = beginning_debt * interest_rate
        mandatory_amortization = min(beginning_debt, original_debt * mandatory_amortization_pct)
        tax_shield = cash_interest * tax_rate
        unlevered_cash_taxes = forecast["cash_taxes"][idx]
        effective_cash_taxes = max(0.0, unlevered_cash_taxes - tax_shield)
        cash_before_debt_service = (
            forecast["ebitda"][idx]
            - effective_cash_taxes
            - forecast["capex"][idx]
            - forecast["change_in_nwc"][idx]
        )
        total_debt_service = cash_interest + mandatory_amortization
        if total_debt_service <= 0:
            dscr = None
            period_pass = False
            structure_anomaly = True
        else:
            dscr = cash_before_debt_service / total_debt_service
            period_pass = dscr >= DSCR_THRESHOLD and cash_before_debt_service > 0
            if min_dscr is None or dscr < min_dscr:
                min_dscr = dscr
                min_year = year
        fcf_after_service = cash_before_debt_service - total_debt_service
        optional_repayment = min(max(0.0, fcf_after_service), max(0.0, beginning_debt - mandatory_amortization))
        ending_debt = beginning_debt - mandatory_amortization - optional_repayment
        yearly.append({
            "year": year,
            "beginning_debt": beginning_debt,
            "cash_interest": cash_interest,
            "mandatory_amortization": mandatory_amortization,
            "unlevered_cash_taxes": unlevered_cash_taxes,
            "tax_shield": tax_shield,
            "effective_cash_taxes": effective_cash_taxes,
            "cash_before_debt_service": cash_before_debt_service,
            "total_debt_service": total_debt_service,
            "dscr": dscr,
            "pass": period_pass,
        })
        pass_all = pass_all and period_pass
        beginning_debt = ending_debt
    return {
        "leverage": leverage,
        "debt_amount": original_debt,
        "pass": pass_all and not structure_anomaly,
        "minimum_dscr": min_dscr,
        "minimum_dscr_year": min_year,
        "yearly_serviceability": yearly,
        "structure_anomaly": structure_anomaly,
    }


def _base_candidate_leverage(forecast: dict[str, list[float]], flags: list[dict[str, str]]) -> float | None:
    ebitda = forecast["ebitda"]
    if any(value <= 0 for value in ebitda):
        flags.append(_flag("error", "EBITDA_NON_POSITIVE_IN_FORECAST", "Forecast EBITDA must be positive in every year to build clean LBO defaults."))
        return None
    for idx in range(1, len(ebitda)):
        prior = ebitda[idx - 1]
        if prior <= 0:
            flags.append(_flag("error", "EBITDA_NON_POSITIVE_IN_FORECAST", "Forecast EBITDA must be positive in every year to build clean LBO defaults."))
            return None
        if ebitda[idx] / prior - 1.0 <= -0.15:
            flags.append(_flag("warning", "EBITDA_DECLINE_RISK_DEFAULT_LEVERAGE_REDUCED", "Forecast EBITDA declines by more than 15%; base candidate leverage was reduced to 3.0x."))
            return 3.0
    return 5.0


def _lbo_payload(symbol: str, currency: str, assumptions: dict[str, float], forecast: dict[str, list[float]]) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "currency": currency,
        "transaction": {
            "entry_ebitda": assumptions["entry_ebitda"],
            "entry_multiple": assumptions["entry_multiple"],
            "exit_multiple": assumptions["exit_multiple"],
            "exit_year": int(assumptions["exit_year"]),
            "transaction_fees_pct_ev": assumptions["transaction_fees_pct_ev"],
        },
        "operating_forecast": forecast,
        "debt": {
            "leverage_multiple": assumptions["leverage_multiple"],
            "debt_amount": assumptions["debt_amount"],
            "interest_rate": assumptions["interest_rate"],
            "mandatory_amortization_pct": assumptions["mandatory_amortization_pct"],
            "cash_sweep_pct": assumptions["cash_sweep_pct"],
            "cash_to_balance_sheet": assumptions["cash_to_balance_sheet"],
        },
    }


def build_lbo_defaults(symbol: str, raw_defaults: dict | None = None) -> dict[str, Any]:
    """Build explainable default LBO assumptions for V4.1."""
    raw = raw_defaults or {}
    symbol = (symbol or raw.get("symbol") or "SYNTH").upper()
    currency = (raw.get("currency") or "USD").upper()
    flags: list[dict[str, str]] = []
    provenance = _core_provenance()

    entry_ebitda = _entry_ebitda(raw, flags)
    if entry_ebitda is None or entry_ebitda <= 0:
        return {
            "status": "error",
            "symbol": symbol,
            "currency": currency,
            "assumptions": None,
            "defaults": None,
            "provenance": provenance,
            "serviceability": None,
            "flags": flags + [_flag("error", "ENTRY_EBITDA_UNAVAILABLE", "Entry EBITDA is unavailable or non-positive; LBO defaults cannot be built.")],
        }

    forecast = _forecast(raw, entry_ebitda)
    base_leverage = _base_candidate_leverage(forecast, flags)
    if base_leverage is None:
        return {
            "status": "error",
            "symbol": symbol,
            "currency": currency,
            "assumptions": None,
            "defaults": None,
            "provenance": provenance,
            "serviceability": None,
            "flags": flags,
        }

    tax_rate, tax_rate_source = _infer_tax_rate(raw, forecast, flags)
    entry_multiple = _entry_multiple(raw, entry_ebitda, flags)
    exit_multiple = entry_multiple

    selected = None
    leverage = base_leverage
    while leverage >= 1.0:
        check = _serviceability_for_leverage(
            forecast,
            entry_ebitda,
            leverage,
            DEFAULT_INTEREST_RATE,
            DEFAULT_AMORTIZATION_PCT,
            tax_rate,
        )
        selected = check
        if check["pass"]:
            break
        leverage = round(leverage - 0.5, 10)

    assert selected is not None
    debt_service_pass = bool(selected["pass"])
    final_leverage = selected["leverage"]
    haircut_applied = final_leverage < base_leverage or not debt_service_pass
    if haircut_applied and debt_service_pass:
        flags.append(_flag("warning", "LEVERAGE_HAIRCUT_APPLIED", "Candidate leverage was reduced to pass serviceability check."))
    elif not debt_service_pass:
        flags.append(_flag("warning", "DEFAULT_DEBT_NOT_SERVICEABLE_AT_MIN_LEVERAGE", "Even 1.0x default leverage does not pass V4.1 simplified DSCR serviceability check."))
    if selected.get("structure_anomaly"):
        flags.append(_flag("warning", "DEBT_SERVICE_STRUCTURE_ANOMALY", "Debt service was non-positive in at least one serviceability period."))

    assumptions = {
        "entry_ebitda": entry_ebitda,
        "entry_multiple": entry_multiple,
        "exit_multiple": exit_multiple,
        "exit_year": DEFAULT_EXIT_YEAR,
        "transaction_fees_pct_ev": DEFAULT_FEES_PCT_EV,
        "leverage_multiple": final_leverage,
        "debt_amount": entry_ebitda * final_leverage,
        "interest_rate": DEFAULT_INTEREST_RATE,
        "mandatory_amortization_pct": DEFAULT_AMORTIZATION_PCT,
        "cash_sweep_pct": 1.0,
        "cash_to_balance_sheet": 0.0,
        "tax_rate": tax_rate,
        "tax_shield_enabled": True,
    }
    serviceability = {
        "initial_candidate_leverage": base_leverage,
        "final_leverage": final_leverage,
        "haircut_applied": haircut_applied,
        "debt_service_pass": debt_service_pass,
        "minimum_dscr": selected["minimum_dscr"],
        "minimum_dscr_year": selected["minimum_dscr_year"],
        "dscr_threshold": DSCR_THRESHOLD,
        "tax_shield_included_for_serviceability": True,
        "tax_rate_used": tax_rate,
        "tax_rate_source": tax_rate_source,
        "yearly_serviceability": selected["yearly_serviceability"],
    }
    status = "ok" if debt_service_pass else "warning"
    defaults = _lbo_payload(symbol, currency, assumptions, forecast)
    defaults["tax_rate"] = tax_rate
    defaults["tax_shield_enabled"] = True
    defaults["audit"] = {
        "scope": "V4.1 default structure builder creates explainable, editable modeling starter assumptions only.",
        "deferred_scope": "Multi-tranche debt, revolver, covenants, scenarios, suitability gate, rollover, PIK, dividend recap, add-on M&A, precedent LBO comps, real-time credit spreads, and M&A module are deferred scope.",
    }
    if flags:
        defaults["early_flags"] = flags

    return {
        "status": status,
        "symbol": symbol,
        "currency": currency,
        "assumptions": assumptions,
        "defaults": defaults,
        "provenance": provenance,
        "serviceability": serviceability,
        "flags": flags,
    }
