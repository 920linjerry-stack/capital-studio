"""V4.2 LBO suitability gate.

Pure assessment layer: explains whether the target is suitable for LBO-style
modeling. It does not recalculate IRR/MOIC, does not call the network, and does
not block V4.0 run_lbo(). It only annotates the V4.1 defaults pipeline with a
suitable / borderline / unsuitable verdict, a Chinese rationale, and a set of
veto / penalty reasons.

Veto-first design: structural blockers (e.g. mega-cap financing infeasibility,
negative EBITDA, debt unserviceable even at minimum leverage) bypass the
penalty score and force ``unsuitable``. Non-blocking issues accumulate as
penalties on a 100-point pool and segment the remaining cases into
``suitable`` / ``borderline`` / ``unsuitable`` thresholds.

This module never produces buy/acquire/recommendation language. It only states
whether LBO is an appropriate modeling framework for the symbol.
"""

from __future__ import annotations

import math
from typing import Any


# Reporting-currency → USD multipliers used purely to size mega-cap / sponsor
# equity vetoes. V4.2 intentionally keeps this list narrow; missing currencies
# do not hard-error, they only suppress the USD size check.
FX_TO_USD: dict[str, float] = {
    "USD": 1.0,
    "HKD": 1.0 / 7.8,
    "CNY": 1.0 / 7.2,
    "EUR": 1.08,
    "GBP": 1.27,
    "JPY": 1.0 / 150.0,
}

# Size vetoes are evaluated only after every source value is normalized to raw
# absolute USD. V4.1 default-builder values are in millions of reporting
# currency; quote-provider market caps may arrive either as raw actuals or as
# millions, so _amount_to_usd_abs() owns that normalization.
MEGA_CAP_EV_USD_ABS = 100_000_000_000.0
SPONSOR_EQUITY_USD_ABS = 40_000_000_000.0
DSCR_THRESHOLD = 1.25

SUITABLE_MIN_SCORE = 70
BORDERLINE_MIN_SCORE = 40

DISCLOSURE_EN = (
    "Suitability gate assesses whether LBO is an appropriate modeling "
    "framework. It is not an investment recommendation or acquisition "
    "recommendation."
)
DISCLOSURE_CN = (
    "该判断仅用于评估 LBO 框架是否适合当前标的，不构成投资建议或收购建议。"
)


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


def _veto(code: str, message_cn: str, severity: str = "high") -> dict[str, str]:
    return {"code": code, "severity": severity, "message_cn": message_cn}


def _penalty(code: str, severity: str, message_cn: str, weight: int) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message_cn": message_cn, "weight": weight}


def _positive(code: str, message_cn: str) -> dict[str, str]:
    return {"code": code, "message_cn": message_cn}


def _flag(code: str, message: str, severity: str = "warning") -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message}


def _fx_to_usd(currency: str | None) -> float | None:
    if not currency:
        return None
    return FX_TO_USD.get(currency.upper())


def _amount_to_usd_abs(value: Any, currency: str | None, unit: str | None = None) -> float | None:
    """Normalize a local-currency amount to raw absolute USD for size vetoes.

    Supported units are ``actual``/``absolute``/``raw`` and
    ``millions``/``million``/``mn``. When a legacy caller passes no unit, values
    of at least 1e9 are treated as raw actuals; smaller values are treated as
    millions to preserve the existing defaults/quote contract.
    """
    amount = _to_float(value)
    fx = _fx_to_usd(currency)
    if amount is None or fx is None:
        return None
    normalized_unit = (unit or "").strip().lower()
    if normalized_unit in {"actual", "absolute", "raw", "usd_abs", "local_abs"}:
        local_abs = amount
    elif normalized_unit in {"millions", "million", "mn", "mm"}:
        local_abs = amount * 1_000_000.0
    elif normalized_unit in {"thousands", "thousand", "k"}:
        local_abs = amount * 1_000.0
    else:
        local_abs = amount if abs(amount) >= 1_000_000_000.0 else amount * 1_000_000.0
    return local_abs * fx


def _raw_amount_to_usd_abs(raw: dict[str, Any], keys: list[str], currency: str) -> float | None:
    for key in keys:
        if raw.get(key) is None:
            continue
        unit = raw.get(f"{key}_unit") or raw.get(f"{key}_units")
        return _amount_to_usd_abs(raw.get(key), currency, unit)
    return None


def _err_response(symbol: str, code: str, message_cn: str) -> dict[str, Any]:
    return {
        "status": "ok",
        "symbol": symbol,
        "suitability": "unsuitable",
        "score": None,
        "veto_triggered": True,
        "label_cn": "不适合 / 仅作机械建模参考",
        "summary_cn": message_cn,
        "veto_reasons": [_veto(code, message_cn)],
        "penalty_reasons": [],
        "positive_factors": [],
        "modeling_guidance_cn": "基础数据不满足 LBO 框架运行前提，请先复核 EBITDA / 经营预测数据。",
        "recommended_next_view": None,
        "flags": [_flag("LBO_SUITABILITY_REVIEW_REQUIRED",
                        "This company requires LBO suitability review before interpreting returns.")],
        "disclosure_en": DISCLOSURE_EN,
        "disclosure_cn": DISCLOSURE_CN,
    }


def assess_lbo_suitability(
    symbol: str,
    defaults_result: dict | None = None,
    raw_defaults: dict | None = None,
    lbo_result: dict | None = None,
) -> dict:
    """Assess whether ``symbol`` is suitable for LBO-style modeling.

    This is an explanatory gate, not an investment recommendation. It depends
    only on the V4.1 defaults result and the raw defaults/financials already
    fetched upstream; it never fetches data itself.
    """
    symbol = (symbol or (defaults_result or {}).get("symbol") or "SYNTH").upper()
    defaults_result = defaults_result or {}
    raw = raw_defaults or {}

    if defaults_result.get("status") == "error":
        codes = {f.get("code") for f in (defaults_result.get("flags") or [])}
        if "ENTRY_EBITDA_UNAVAILABLE" in codes:
            return _err_response(symbol, "ENTRY_EBITDA_NON_POSITIVE",
                                 "入场 EBITDA 不可用或非正，无法进入 LBO 框架判断。")
        if "EBITDA_NON_POSITIVE_IN_FORECAST" in codes:
            return _err_response(symbol, "FORECAST_EBITDA_NON_POSITIVE",
                                 "预测期内某年 EBITDA 非正，LBO 框架不适用。")
        return _err_response(symbol, "DEFAULTS_BUILD_FAILED",
                             "V4.1 默认结构构建失败，suitability 判断暂不可用。")

    assumptions = defaults_result.get("assumptions") or {}
    serviceability = defaults_result.get("serviceability") or {}
    defaults_flags = {f.get("code") for f in (defaults_result.get("flags") or [])}
    forecast = (defaults_result.get("defaults") or {}).get("operating_forecast") or {}

    currency = (defaults_result.get("currency") or raw.get("currency") or "USD").upper()
    entry_ebitda = _to_float(assumptions.get("entry_ebitda"))
    entry_multiple = _to_float(assumptions.get("entry_multiple"))
    transaction_fees_pct_ev = _to_float(assumptions.get("transaction_fees_pct_ev")) or 0.0
    debt_amount = _to_float(assumptions.get("debt_amount")) or 0.0

    # V4.1 defaults and run_lbo transaction summary amounts are in millions of
    # reporting currency until converted here to raw absolute USD.
    ev_local_millions: float | None = None
    sponsor_equity_local_millions: float | None = None
    if entry_ebitda and entry_multiple and entry_ebitda > 0 and entry_multiple > 0:
        ev_local_millions = entry_ebitda * entry_multiple
        sponsor_equity_local_millions = ev_local_millions * (1.0 + transaction_fees_pct_ev) - debt_amount

    # Prefer the realized values from the calculated LBO run if available.
    if lbo_result and lbo_result.get("status") == "ok":
        ts = lbo_result.get("transaction_summary") or {}
        ev_local_millions = _to_float(ts.get("entry_ev")) or ev_local_millions
        sponsor_equity_local_millions = _to_float(ts.get("sponsor_equity")) or sponsor_equity_local_millions

    fx = _fx_to_usd(currency)
    fx_available = fx is not None
    enterprise_value_usd_abs = (
        _amount_to_usd_abs(ev_local_millions, currency, "millions")
        if ev_local_millions is not None else None
    )
    sponsor_equity_usd_abs = (
        _amount_to_usd_abs(sponsor_equity_local_millions, currency, "millions")
        if sponsor_equity_local_millions is not None else None
    )
    raw_enterprise_value_usd_abs = _raw_amount_to_usd_abs(
        raw, ["enterprise_value", "enterpriseValue", "current_enterprise_value", "ev"], currency
    )
    if raw_enterprise_value_usd_abs is not None:
        enterprise_value_usd_abs = raw_enterprise_value_usd_abs
    market_cap_usd_abs = _raw_amount_to_usd_abs(raw, ["market_cap", "marketCap"], currency)

    veto_reasons: list[dict[str, Any]] = []
    penalty_reasons: list[dict[str, Any]] = []
    positive_factors: list[dict[str, str]] = []
    flags: list[dict[str, str]] = []
    recommended_next_view: str | None = None
    final_leverage = _to_float(serviceability.get("final_leverage"))
    min_dscr = _to_float(serviceability.get("minimum_dscr"))
    debt_service_pass = bool(serviceability.get("debt_service_pass"))

    # ---- VETO conditions ----------------------------------------------------
    forecast_ebitda = forecast.get("ebitda") if isinstance(forecast.get("ebitda"), list) else []
    if entry_ebitda is None or entry_ebitda <= 0:
        veto_reasons.append(_veto("ENTRY_EBITDA_NON_POSITIVE",
                                  "入场 EBITDA 不可用或非正，LBO 框架不适用。"))
    if any((isinstance(v, (int, float)) and v <= 0) for v in forecast_ebitda):
        veto_reasons.append(_veto("FORECAST_EBITDA_NON_POSITIVE",
                                  "预测期内某年 EBITDA 非正，LBO 框架不适用。"))

    if ("DEFAULT_DEBT_NOT_SERVICEABLE_AT_MIN_LEVERAGE" in defaults_flags or
        (not debt_service_pass and final_leverage is not None and final_leverage <= 1.0)):
        veto_reasons.append(_veto("NOT_SERVICEABLE_EVEN_AT_MIN_LEVERAGE",
                                  "即使将默认杠杆下调至 1.0x，目标仍无法通过简化偿债能力校验。"))
        recommended_next_view = None

    if fx_available:
        if sponsor_equity_usd_abs is not None and sponsor_equity_usd_abs >= SPONSOR_EQUITY_USD_ABS:
            veto_reasons.append(_veto("SPONSOR_EQUITY_CHECK_TOO_LARGE",
                                      "所需 sponsor equity 体量过大，典型 PE 杠杆收购融资可行性较弱。"))
            if recommended_next_view is None:
                recommended_next_view = "DCF"
        big_ev = enterprise_value_usd_abs is not None and enterprise_value_usd_abs >= MEGA_CAP_EV_USD_ABS
        big_mcap = market_cap_usd_abs is not None and market_cap_usd_abs >= MEGA_CAP_EV_USD_ABS
        if big_ev or big_mcap:
            veto_reasons.append(_veto("MEGA_CAP_FINANCING_FEASIBILITY",
                                      "公司体量过大（企业价值或市值已达大盘股级别），典型 PE 杠杆收购融资可行性较弱。"))
            if recommended_next_view is None:
                recommended_next_view = "DCF"
    else:
        flags.append(_flag("SIZE_USD_CONVERSION_UNAVAILABLE",
                           "Mega-cap / sponsor-equity USD veto skipped: reporting currency cannot be reliably converted to USD."))

    if enterprise_value_usd_abs is None and market_cap_usd_abs is None and sponsor_equity_usd_abs is None:
        flags.append(_flag("MARKET_SIZE_UNAVAILABLE",
                           "Market size data unavailable; mega-cap / sponsor equity USD veto was not evaluated."))

    # Deduplicate veto reasons by code while keeping order.
    seen_veto: set[str] = set()
    deduped_veto: list[dict[str, Any]] = []
    for reason in veto_reasons:
        code = reason["code"]
        if code in seen_veto:
            continue
        seen_veto.add(code)
        deduped_veto.append(reason)
    veto_reasons = deduped_veto

    # ---- Positive factors (always evaluated, even under veto) ---------------
    if entry_ebitda is not None and entry_ebitda > 0:
        positive_factors.append(_positive("POSITIVE_EBITDA", "入场 EBITDA 为正，LBO 模型至少可以机械运行。"))
    if debt_service_pass:
        positive_factors.append(_positive("SERVICEABILITY_PASS", "V4.1 简化偿债能力校验通过。"))
    if min_dscr is not None and min_dscr >= DSCR_THRESHOLD:
        positive_factors.append(_positive("DSCR_ABOVE_THRESHOLD",
                                          "最低 DSCR 不低于 1.25，简化偿债缓冲尚可。"))
    forecast_capex = forecast.get("capex") if isinstance(forecast.get("capex"), list) else []
    forecast_taxes = forecast.get("cash_taxes") if isinstance(forecast.get("cash_taxes"), list) else []
    forecast_nwc = forecast.get("change_in_nwc") if isinstance(forecast.get("change_in_nwc"), list) else []
    if forecast_ebitda and forecast_capex and forecast_taxes and forecast_nwc:
        cash_conversion = [
            forecast_ebitda[i] - forecast_taxes[i] - forecast_capex[i] - forecast_nwc[i]
            for i in range(min(len(forecast_ebitda), len(forecast_capex), len(forecast_taxes), len(forecast_nwc)))
        ]
        if cash_conversion and all(v > 0 for v in cash_conversion):
            positive_factors.append(_positive("POSITIVE_CASH_FLOW",
                                              "扣税、capex、营运资金后现金流仍为正。"))

    if veto_reasons:
        # Distressed cash flow / not serviceable → recommended_next_view None.
        veto_codes = {r["code"] for r in veto_reasons}
        if recommended_next_view is None and "NOT_SERVICEABLE_EVEN_AT_MIN_LEVERAGE" not in veto_codes:
            if any(code in veto_codes for code in (
                "MEGA_CAP_FINANCING_FEASIBILITY", "SPONSOR_EQUITY_CHECK_TOO_LARGE",
            )):
                recommended_next_view = "DCF"

        guidance_cn = (
            "该标的不适合直接用简化 LBO 框架解释；当前 IRR / MOIC 仅为机械建模输出，"
            "不应被解释为真实收购可行性判断。"
        )
        if "NOT_SERVICEABLE_EVEN_AT_MIN_LEVERAGE" in veto_codes:
            guidance_cn += "即使切换到 DCF 也需先复核 going-concern / 现金流质量。"

        return {
            "status": "ok",
            "symbol": symbol,
            "suitability": "unsuitable",
            "score": None,
            "veto_triggered": True,
            "label_cn": "不适合 / 仅作机械建模参考",
            "summary_cn": (
                "该标的触发 LBO 框架适配否决项，当前 LBO 输出只能作为机械建模练习，"
                "不应被解释为真实收购可行性。"
            ),
            "veto_reasons": veto_reasons,
            "penalty_reasons": [],
            "positive_factors": positive_factors,
            "modeling_guidance_cn": guidance_cn,
            "recommended_next_view": recommended_next_view,
            "flags": flags + [_flag("LBO_SUITABILITY_REVIEW_REQUIRED",
                                    "This company requires LBO suitability review before interpreting returns.")],
            "disclosure_en": DISCLOSURE_EN,
            "disclosure_cn": DISCLOSURE_CN,
        }

    # ---- Penalty scoring (no veto path) ------------------------------------
    score = 100

    # EBITDA decline / volatility.
    if len(forecast_ebitda) >= 2:
        yoy = []
        decline_hit = False
        for i in range(1, len(forecast_ebitda)):
            prior = forecast_ebitda[i - 1]
            curr = forecast_ebitda[i]
            if prior is None or prior <= 0:
                continue
            growth = curr / prior - 1.0
            yoy.append(growth)
            if growth <= -0.15:
                decline_hit = True
        if decline_hit:
            penalty_reasons.append(_penalty("EBITDA_DECLINE_RISK", "medium",
                                            "预测期内 EBITDA 同比下滑超过 15%，杠杆偿债压力放大。", 15))
            score -= 15
        if yoy and (max(yoy) - min(yoy)) > 0.30:
            penalty_reasons.append(_penalty("EBITDA_VOLATILITY_RISK", "medium",
                                            "EBITDA 同比波动幅度较大，杠杆模型敏感性较高。", 10))
            score -= 10

    # Haircut from V4.1 serviceability.
    if "LEVERAGE_HAIRCUT_APPLIED" in defaults_flags or serviceability.get("haircut_applied"):
        if debt_service_pass:
            penalty_reasons.append(_penalty("LEVERAGE_HAIRCUT_APPLIED", "medium",
                                            "默认杠杆已被偿债校验下调，债务承载能力低于惯例 5.0x 起点。", 15))
            score -= 15
            # Deep haircut: leverage cut below 3.5x signals materially weak
            # debt capacity even though serviceability technically passes.
            if final_leverage is not None and final_leverage < 3.5:
                penalty_reasons.append(_penalty("LEVERAGE_HAIRCUT_DEEP", "high",
                                                "默认杠杆被下调幅度较大，债务承载能力显著弱于典型 LBO 标的。", 20))
                score -= 20

    # DSCR consistency penalty (only relevant when no veto).
    if min_dscr is not None and min_dscr < DSCR_THRESHOLD and debt_service_pass:
        penalty_reasons.append(_penalty("DSCR_BELOW_THRESHOLD", "high",
                                        "最低 DSCR 低于 1.25，偿债安全垫较薄。", 20))
        score -= 20

    # Existing capital structure simplification.
    net_debt = _to_float(raw.get("net_debt"))
    net_cash = _to_float(raw.get("net_cash"))
    if net_cash is not None and net_cash > 0 or (net_debt is not None and net_debt < 0):
        penalty_reasons.append(_penalty("NET_CASH_STRUCTURE_REVIEW", "medium",
                                        "存量净现金结构使典型 LBO 资本结构假设失真，真实交易需要重新建模。", 10))
        score -= 10
        if recommended_next_view is None:
            recommended_next_view = "DCF"
    elif net_debt is None and net_cash is None:
        flags.append(_flag("EXISTING_NET_DEBT_UNAVAILABLE",
                           "Existing net debt data is unavailable; entry capital structure was simplified.",
                           severity="info"))

    # Entry multiple bands.
    if "ENTRY_MULTIPLE_PLACEHOLDER_USED" in defaults_flags:
        penalty_reasons.append(_penalty("ENTRY_MULTIPLE_PLACEHOLDER_USED", "low",
                                        "买入倍数使用占位默认值，需要用户手动校准。", 5))
        score -= 5
    if entry_multiple is not None:
        if entry_multiple > 30.0:
            penalty_reasons.append(_penalty("VERY_HIGH_ENTRY_MULTIPLE_LBO_MATH_WEAK", "high",
                                            "买入倍数极高，LBO 数学敏感性显著弱化。", 25))
            score -= 25
        elif entry_multiple > 20.0:
            penalty_reasons.append(_penalty("HIGH_ENTRY_MULTIPLE_LBO_MATH_WEAK", "medium",
                                            "买入倍数偏高，LBO 数学敏感性较弱。", 15))
            score -= 15
        elif entry_multiple < 4.0:
            penalty_reasons.append(_penalty("LOW_ENTRY_MULTIPLE_REVIEW", "low",
                                            "买入倍数偏低，建议复核 EBITDA 与企业价值口径。", 5))
            score -= 5

    if score >= SUITABLE_MIN_SCORE:
        suitability = "suitable"
        label_cn = "较适合"
        summary_cn = "该标的具备较稳定的 EBITDA / 偿债能力，LBO 可作为一个可用的建模视角。该判断不是交易建议。"
        guidance_cn = "可以将 LBO 作为主要建模视角之一；输出仍需结合业务理解复核。"
    elif score >= BORDERLINE_MIN_SCORE:
        suitability = "borderline"
        label_cn = "边缘 / 需复核"
        summary_cn = "该标的可以机械运行 LBO 模型，但部分关键条件需要复核，请谨慎解释 IRR / MOIC。"
        guidance_cn = "请逐项复核 penalty reasons 中的瑕疵，必要时调整默认杠杆 / 倍数后再解释 IRR。"
    else:
        suitability = "unsuitable"
        label_cn = "不适合 / 多项瑕疵累积"
        summary_cn = (
            "多项非致命性 LBO 适配瑕疵累积，当前 LBO 输出更多是机械建模结果，"
            "不应被解释为真实收购可行性。"
        )
        guidance_cn = "建议在解释 IRR / MOIC 前先逐项复核 penalty reasons。"

    flags.append(_flag("LBO_SUITABILITY_REVIEW_REQUIRED" if suitability != "suitable"
                      else "LBO_SUITABILITY_OK",
                       "Review LBO suitability summary before interpreting IRR / MOIC."
                       if suitability != "suitable"
                       else "LBO suitability gate passed; standard review still applies.",
                       severity=("warning" if suitability != "suitable" else "info")))

    return {
        "status": "ok",
        "symbol": symbol,
        "suitability": suitability,
        "score": score,
        "veto_triggered": False,
        "label_cn": label_cn,
        "summary_cn": summary_cn,
        "veto_reasons": [],
        "penalty_reasons": penalty_reasons,
        "positive_factors": positive_factors,
        "modeling_guidance_cn": guidance_cn,
        "recommended_next_view": recommended_next_view,
        "flags": flags,
        "disclosure_en": DISCLOSURE_EN,
        "disclosure_cn": DISCLOSURE_CN,
    }
