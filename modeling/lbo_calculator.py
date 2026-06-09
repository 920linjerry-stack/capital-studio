"""V4.0 single-tranche LBO calculator.

This module is intentionally pure: it has no Flask dependency, performs no
file I/O, and does not call the DCF engine. The returned IRR / MOIC values are
the single source of truth for UI and Excel presentation layers.
"""

from __future__ import annotations

import math
from typing import Any

from modeling.lbo_capital_structure import (
    MULTI_TRANCHE_DISCLOSURES,
    build_capital_structure_summary,
    build_covenant_summary,
    build_maturity_wall,
    run_waterfall,
    validate_capital_structure,
)


AUDIT_DISCLOSURES = [
    "Interest is calculated on beginning debt balance. No iterative circular calculation is used.",
    "Exit multiple defaults to entry multiple unless explicitly changed.",
    "V4.0 assumes existing target net debt is refinanced or ignored; entry capital structure is modeled as new acquisition debt only.",
    "Simplified tax shield uses cash interest x tax rate. No full tax schedule, deferred tax or three-statement engine is modeled.",
    "V4.0 assumes 100% cash sweep and no cash balance bridge.",
    "Python run_lbo() is the source of truth for IRR / MOIC; UI and Excel only display and tie out to its output.",
]


def _flag(code: str, message: str, severity: str = "error") -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message}


def _error(flags: list[dict[str, str]]) -> dict[str, Any]:
    return {"status": "error", "returns": None, "flags": flags}


def _float(value: Any, default: float | None = None) -> float:
    if value is None:
        if default is None:
            raise ValueError("missing numeric value")
        return default
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite numeric value")
    return number


def _as_float_list(values: Any, field: str, flags: list[dict[str, str]]) -> list[float]:
    if not isinstance(values, list):
        flags.append(_flag("FORECAST_ARRAY_INVALID", f"{field} must be an array."))
        return []
    out: list[float] = []
    for i, value in enumerate(values):
        try:
            out.append(_float(value))
        except (TypeError, ValueError):
            flags.append(_flag("FORECAST_ARRAY_INVALID", f"{field}[{i}] must be a finite number."))
            return []
    return out


def _bool(value: Any, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "enabled", "on"}:
        return True
    if text in {"false", "0", "no", "n", "disabled", "off"}:
        return False
    return default


def _tax_settings(inputs: dict[str, Any], flags: list[dict[str, str]]) -> tuple[bool, float]:
    tax_shield_enabled = _bool(inputs.get("tax_shield_enabled"), True)
    try:
        tax_rate = _float(inputs.get("tax_rate", 0.25), 0.25)
    except (TypeError, ValueError):
        flags.append(_flag("TAX_RATE_INVALID", "tax_rate must be a finite number; 25.0% default was used.", "warning"))
        tax_rate = 0.25
    if tax_rate < 0.0 or tax_rate > 0.50:
        flags.append(_flag(
            "TAX_RATE_SANITY_WARNING",
            "tax_rate is outside the 0.0% to 50.0% sanity range; the supplied value was used.",
            "warning",
        ))
    return tax_shield_enabled, tax_rate


def _tax_row(gross_cash_taxes: float, cash_interest: float, tax_rate: float, enabled: bool) -> dict[str, Any]:
    tax_shield = cash_interest * tax_rate if enabled else 0.0
    levered_cash_taxes = max(0.0, gross_cash_taxes - tax_shield)
    return {
        "gross_cash_taxes": gross_cash_taxes,
        "tax_shield": tax_shield,
        "levered_cash_taxes": levered_cash_taxes,
        "tax_rate": tax_rate,
        "tax_shield_enabled": enabled,
    }


def _annual_irr(cash_flows: list[float]) -> float:
    if not cash_flows or not any(cf < 0 for cf in cash_flows) or not any(cf > 0 for cf in cash_flows):
        raise ValueError("cash flows need at least one positive and one negative value")

    def npv(rate: float) -> float:
        return sum(cf / ((1.0 + rate) ** i) for i, cf in enumerate(cash_flows))

    low = -0.999999
    high = 10.0
    low_v = npv(low)
    high_v = npv(high)
    while low_v * high_v > 0 and high < 1_000_000:
        high *= 2.0
        high_v = npv(high)
    if low_v * high_v > 0:
        raise ValueError("IRR root not bracketed")

    for _ in range(200):
        mid = (low + high) / 2.0
        mid_v = npv(mid)
        if abs(mid_v) < 1e-10:
            return mid
        if low_v * mid_v <= 0:
            high = mid
            high_v = mid_v
        else:
            low = mid
            low_v = mid_v
    return (low + high) / 2.0


def _resolve_cash_to_balance_sheet(
    debt: dict[str, Any],
    capital_structure: dict[str, Any],
    settings: dict[str, Any],
) -> tuple[float, list[dict[str, str]]]:
    """Resolve a single Cash to Balance Sheet figure for the multi-tranche path.

    ``debt.cash_to_balance_sheet`` (transaction level) is authoritative. If
    ``capital_structure.cash_balance_beginning`` was supplied and disagrees, the
    transaction value wins and a non-blocking conflict warning is emitted -- the
    two are never allowed to silently differ.
    """
    flags: list[dict[str, str]] = []
    ctbs_raw = debt.get("cash_to_balance_sheet")
    cs_begin = float(settings.get("cash_balance_beginning", 0.0) or 0.0)
    cs_begin_supplied = capital_structure.get("cash_balance_beginning") not in (None, "")

    if ctbs_raw in (None, ""):
        return cs_begin, flags

    cash_to_balance_sheet = _float(ctbs_raw, 0.0)
    if cs_begin_supplied and abs(cash_to_balance_sheet - cs_begin) > 1e-9:
        flags.append(_flag(
            "CASH_TO_BALANCE_SHEET_CONFLICT",
            "cash_to_balance_sheet and capital_structure.cash_balance_beginning "
            "differ; the transaction cash_to_balance_sheet value is used for both "
            "Sources & Uses and the waterfall beginning cash.",
            "warning",
        ))
    return cash_to_balance_sheet, flags


def run_lbo(inputs: dict[str, Any]) -> dict[str, Any]:
    """Run an LBO model from a dict input schema.

    Backward compatible: without ``capital_structure.mode == "multi_tranche"``
    this runs the original V4.0 single-tranche path unchanged. With it, the
    V4.4 multi-tranche path runs instead. ``run_lbo()`` remains the IRR / MOIC
    source of truth in both modes.
    """
    capital_structure = inputs.get("capital_structure")
    if isinstance(capital_structure, dict) and capital_structure.get("mode") == "multi_tranche":
        return _run_lbo_multi_tranche(inputs, capital_structure)

    flags: list[dict[str, str]] = []
    try:
        transaction = inputs.get("transaction") or {}
        forecast = inputs.get("operating_forecast") or {}
        debt = inputs.get("debt") or {}

        entry_ebitda = _float(transaction.get("entry_ebitda"))
        entry_multiple = _float(transaction.get("entry_multiple"))
        exit_multiple = _float(transaction.get("exit_multiple", entry_multiple))
        exit_year = int(transaction.get("exit_year"))
        transaction_fees_pct_ev = _float(transaction.get("transaction_fees_pct_ev", 0.0), 0.0)

        cash_sweep_pct = _float(debt.get("cash_sweep_pct", 1.0), 1.0)
        cash_to_balance_sheet = _float(debt.get("cash_to_balance_sheet", 0.0), 0.0)
        interest_rate = _float(debt.get("interest_rate", 0.0), 0.0)
        mandatory_amortization_pct = _float(debt.get("mandatory_amortization_pct", 0.0), 0.0)

        years = forecast.get("years") or []
        revenue = _as_float_list(forecast.get("revenue"), "operating_forecast.revenue", flags)
        ebitda = _as_float_list(forecast.get("ebitda"), "operating_forecast.ebitda", flags)
        cash_taxes = _as_float_list(forecast.get("cash_taxes"), "operating_forecast.cash_taxes", flags)
        capex = _as_float_list(forecast.get("capex"), "operating_forecast.capex", flags)
        change_in_nwc = _as_float_list(forecast.get("change_in_nwc"), "operating_forecast.change_in_nwc", flags)
        tax_shield_enabled, tax_rate = _tax_settings(inputs, flags)
    except (TypeError, ValueError, KeyError):
        return _error([_flag("INPUT_SCHEMA_INVALID", "LBO inputs contain missing or invalid required fields.")])

    if flags:
        return _error(flags)

    if not isinstance(years, list):
        return _error([_flag("FORECAST_ARRAY_INVALID", "operating_forecast.years must be an array.")])

    n = len(years)
    array_lengths = {
        "years": n,
        "revenue": len(revenue),
        "ebitda": len(ebitda),
        "cash_taxes": len(cash_taxes),
        "capex": len(capex),
        "change_in_nwc": len(change_in_nwc),
    }
    if len(set(array_lengths.values())) != 1 or n == 0:
        return _error([_flag("FORECAST_LENGTH_MISMATCH", f"Forecast arrays must have matching non-zero length: {array_lengths}.")])

    if exit_year != n:
        return _error([_flag("EXIT_YEAR_MISMATCH", "V4.0 only supports exit in the final forecast year.")])
    if entry_ebitda <= 0:
        return _error([_flag("ENTRY_EBITDA_NON_POSITIVE", "entry_ebitda must be greater than zero.")])
    if entry_multiple <= 0:
        return _error([_flag("ENTRY_MULTIPLE_NON_POSITIVE", "entry_multiple must be greater than zero.")])
    if cash_sweep_pct != 1.0:
        return _error([_flag("CASH_SWEEP_LOCKED_V40", "V4.0 requires cash_sweep_pct = 1.0 because cash balance bridge is V4.1+ future scope.")])
    if cash_to_balance_sheet != 0.0:
        return _error([_flag("CASH_BALANCE_BRIDGE_LOCKED_V40", "V4.0 requires cash_to_balance_sheet = 0.0 because cash balance bridge is V4.1+ future scope.")])

    entry_ev = entry_ebitda * entry_multiple
    transaction_fees = entry_ev * transaction_fees_pct_ev
    total_uses = entry_ev + transaction_fees
    if debt.get("debt_amount") is not None:
        debt_amount = _float(debt.get("debt_amount"))
    else:
        debt_amount = entry_ebitda * _float(debt.get("leverage_multiple", 0.0), 0.0)

    if debt_amount < 0:
        return _error([_flag("DEBT_AMOUNT_NEGATIVE", "debt_amount must be greater than or equal to zero.")])
    if debt_amount > total_uses:
        return _error([_flag("DEBT_EXCEEDS_USES", "debt_amount cannot exceed total uses.")])

    sponsor_equity = total_uses - debt_amount
    if sponsor_equity <= 0:
        return _error([_flag("SPONSOR_EQUITY_NON_POSITIVE", "sponsor_equity must be greater than zero.")])

    debt_schedule: list[dict[str, Any]] = []
    beginning_debt = debt_amount
    original_debt = debt_amount
    for idx in range(n):
        cash_interest = beginning_debt * interest_rate
        taxes = _tax_row(cash_taxes[idx], cash_interest, tax_rate, tax_shield_enabled)
        cash_flow_before_debt_service = ebitda[idx] - taxes["levered_cash_taxes"] - capex[idx] - change_in_nwc[idx]
        cash_available_for_debt = cash_flow_before_debt_service - cash_interest
        mandatory_amortization = min(beginning_debt, original_debt * mandatory_amortization_pct)
        fcf_available_for_sweep = cash_available_for_debt - mandatory_amortization
        cash_after_interest_and_mandatory = cash_flow_before_debt_service - cash_interest - mandatory_amortization
        debt_service_failure = cash_available_for_debt < mandatory_amortization
        optional_repayment = min(
            max(0.0, fcf_available_for_sweep * cash_sweep_pct),
            beginning_debt - mandatory_amortization,
        )
        ending_debt = beginning_debt - mandatory_amortization - optional_repayment
        debt_schedule.append({
            "year": years[idx],
            "beginning_debt": beginning_debt,
            "cash_flow_before_debt_service": cash_flow_before_debt_service,
            "cash_interest": cash_interest,
            **taxes,
            "cash_available_for_debt": cash_available_for_debt,
            "mandatory_amortization": mandatory_amortization,
            "cash_after_interest_and_mandatory_amortization": cash_after_interest_and_mandatory,
            "fcf_available_for_sweep": fcf_available_for_sweep,
            "optional_repayment": optional_repayment,
            "ending_debt": ending_debt,
            "debt_service_failure": debt_service_failure,
        })
        beginning_debt = ending_debt

    exit_ebitda = ebitda[-1]
    exit_ev = exit_ebitda * exit_multiple
    remaining_debt = debt_schedule[-1]["ending_debt"]
    exit_equity_value = exit_ev - remaining_debt
    cash_flows = [-sponsor_equity] + [0.0] * (n - 1) + [exit_equity_value]
    try:
        irr = _annual_irr(cash_flows)
    except ValueError:
        return _error([_flag("IRR_CALCULATION_FAILED", "IRR calculation failed; no fallback return is provided.")])

    moic = exit_equity_value / sponsor_equity
    transaction_summary = {
        "entry_ebitda": entry_ebitda,
        "entry_multiple": entry_multiple,
        "entry_ev": entry_ev,
        "transaction_fees": transaction_fees,
        "cash_to_balance_sheet": cash_to_balance_sheet,
        "total_uses": total_uses,
        "debt_amount": debt_amount,
        "implied_leverage": (debt_amount / entry_ebitda) if entry_ebitda else None,
        "sponsor_equity": sponsor_equity,
        "exit_multiple": exit_multiple,
        "exit_year": exit_year,
    }
    exit_summary = {
        "exit_ebitda": exit_ebitda,
        "exit_multiple": exit_multiple,
        "exit_ev": exit_ev,
        "remaining_debt": remaining_debt,
        "ending_cash_balance": 0.0,
        "exit_equity_value": exit_equity_value,
        "debt_paydown": debt_amount - remaining_debt,
    }
    returns = {
        "irr": irr,
        "moic": moic,
        "sponsor_equity": sponsor_equity,
        "entry_ev": entry_ev,
        "exit_equity_value": exit_equity_value,
        "debt_paydown": debt_amount - remaining_debt,
        "remaining_debt": remaining_debt,
        "ending_cash_balance": 0.0,
        "cash_flows": cash_flows,
    }

    warning_flags = []
    if any(row["debt_service_failure"] for row in debt_schedule):
        warning_flags.append(_flag("DEBT_SERVICE_FAILURE", "Cash available for debt is below mandatory amortization in at least one year.", "warning"))
    if inputs.get("symbol", "").upper() == "AAPL":
        warning_flags.append(_flag("EARLY_LBO_SUITABILITY_REVIEW", "AAPL is not used as the V4.0 clean anchor; formal suitability gate is V4.2 future scope.", "warning"))

    return {
        "status": "ok",
        "symbol": inputs.get("symbol"),
        "currency": inputs.get("currency"),
        "transaction_summary": transaction_summary,
        "operating_forecast": {
            "years": years,
            "revenue": revenue,
            "ebitda": ebitda,
            "cash_taxes": cash_taxes,
            "gross_cash_taxes": cash_taxes,
            "tax_rate": tax_rate,
            "tax_shield_enabled": tax_shield_enabled,
            "tax_shield": [row["tax_shield"] for row in debt_schedule],
            "levered_cash_taxes": [row["levered_cash_taxes"] for row in debt_schedule],
            "capex": capex,
            "change_in_nwc": change_in_nwc,
        },
        "debt_schedule": debt_schedule,
        "exit": exit_summary,
        "returns": returns,
        "flags": warning_flags,
        "audit": {"disclosures": AUDIT_DISCLOSURES},
    }


def _run_lbo_multi_tranche(inputs: dict[str, Any], capital_structure: dict[str, Any]) -> dict[str, Any]:
    """V4.4 multi-tranche LBO path. Returns IRR / MOIC plus capital structure,
    covenant and maturity-wall output. Interest is on beginning balances only."""
    flags: list[dict[str, str]] = []
    try:
        transaction = inputs.get("transaction") or {}
        forecast = inputs.get("operating_forecast") or {}

        entry_ebitda = _float(transaction.get("entry_ebitda"))
        entry_multiple = _float(transaction.get("entry_multiple"))
        exit_multiple = _float(transaction.get("exit_multiple", entry_multiple))
        exit_year = int(transaction.get("exit_year"))
        transaction_fees_pct_ev = _float(transaction.get("transaction_fees_pct_ev", 0.0), 0.0)

        years = forecast.get("years") or []
        revenue = _as_float_list(forecast.get("revenue"), "operating_forecast.revenue", flags)
        ebitda = _as_float_list(forecast.get("ebitda"), "operating_forecast.ebitda", flags)
        cash_taxes = _as_float_list(forecast.get("cash_taxes"), "operating_forecast.cash_taxes", flags)
        capex = _as_float_list(forecast.get("capex"), "operating_forecast.capex", flags)
        change_in_nwc = _as_float_list(forecast.get("change_in_nwc"), "operating_forecast.change_in_nwc", flags)
        tax_shield_enabled, tax_rate = _tax_settings(inputs, flags)
    except (TypeError, ValueError, KeyError):
        return _error([_flag("INPUT_SCHEMA_INVALID", "LBO inputs contain missing or invalid required fields.")])

    if flags:
        return _error(flags)

    if not isinstance(years, list):
        return _error([_flag("FORECAST_ARRAY_INVALID", "operating_forecast.years must be an array.")])

    n = len(years)
    array_lengths = {
        "years": n,
        "revenue": len(revenue),
        "ebitda": len(ebitda),
        "cash_taxes": len(cash_taxes),
        "capex": len(capex),
        "change_in_nwc": len(change_in_nwc),
    }
    if len(set(array_lengths.values())) != 1 or n == 0:
        return _error([_flag("FORECAST_LENGTH_MISMATCH", f"Forecast arrays must have matching non-zero length: {array_lengths}.")])
    if exit_year != n:
        return _error([_flag("EXIT_YEAR_MISMATCH", "V4.0 only supports exit in the final forecast year.")])
    if entry_ebitda <= 0:
        return _error([_flag("ENTRY_EBITDA_NON_POSITIVE", "entry_ebitda must be greater than zero.")])
    if entry_multiple <= 0:
        return _error([_flag("ENTRY_MULTIPLE_NON_POSITIVE", "entry_multiple must be greater than zero.")])

    settings, cs_flags = validate_capital_structure(capital_structure)
    if settings is None:
        return _error(cs_flags)

    # V4.7.1 cash tie-out: Cash to Balance Sheet is a single figure that both
    # (a) increases Total Uses and Sponsor Equity at close, and (b) seeds the
    # waterfall's beginning cash. The transaction-level cash_to_balance_sheet is
    # authoritative; capital_structure.cash_balance_beginning must agree with it.
    cash_to_balance_sheet, cash_flags = _resolve_cash_to_balance_sheet(
        inputs.get("debt") or {}, capital_structure, settings,
    )
    settings["cash_balance_beginning"] = cash_to_balance_sheet

    entry_ev = entry_ebitda * entry_multiple
    transaction_fees = entry_ev * transaction_fees_pct_ev
    total_uses = entry_ev + transaction_fees + cash_to_balance_sheet
    total_opening_debt = sum(t["opening_balance"] for t in settings["tranches"])
    source_truth_flags: list[dict[str, str]] = []
    debt_block = inputs.get("debt") or {}
    if isinstance(debt_block, dict) and debt_block.get("debt_amount") not in (None, ""):
        try:
            supplied_debt_amount = _float(debt_block.get("debt_amount"), 0.0)
        except (TypeError, ValueError):
            supplied_debt_amount = None
        if supplied_debt_amount is None or abs(supplied_debt_amount - total_opening_debt) > 1e-6:
            source_truth_flags.append(_flag(
                "TRANCHE_DEBT_SOURCE_OF_TRUTH",
                "Multi-tranche mode uses the sum of selected tranche opening "
                "balances as opening debt; transaction-level debt_amount was "
                "ignored for opening debt sizing.",
                "warning",
            ))
    if total_opening_debt > total_uses:
        return _error([_flag("DEBT_EXCEEDS_USES", "Total opening tranche debt cannot exceed total uses.")])
    sponsor_equity = total_uses - total_opening_debt
    if sponsor_equity <= 0:
        return _error([_flag("SPONSOR_EQUITY_NON_POSITIVE", "sponsor_equity must be greater than zero.")])

    forecast_dict = {
        "years": years,
        "ebitda": ebitda,
        "cash_taxes": cash_taxes,
        "tax_rate": tax_rate,
        "tax_shield_enabled": tax_shield_enabled,
        "capex": capex,
        "change_in_nwc": change_in_nwc,
    }
    waterfall = run_waterfall(settings, forecast_dict)
    debt_schedule = waterfall["debt_schedule"]

    cap_summary = build_capital_structure_summary(settings, debt_schedule)
    covenant_summary = build_covenant_summary(settings, debt_schedule, ebitda)
    maturity = build_maturity_wall(settings, debt_schedule, exit_year)

    exit_ebitda = ebitda[-1]
    exit_ev = exit_ebitda * exit_multiple
    remaining_debt = cap_summary["total_ending_debt"]
    ending_cash_balance = cap_summary["ending_cash_balance"]
    exit_equity_value = exit_ev - remaining_debt + ending_cash_balance

    cash_flows = [-sponsor_equity] + [0.0] * (n - 1) + [exit_equity_value]
    try:
        irr = _annual_irr(cash_flows)
    except ValueError:
        return _error([_flag("IRR_CALCULATION_FAILED", "IRR calculation failed; no fallback return is provided.")])
    moic = exit_equity_value / sponsor_equity

    transaction_summary = {
        "entry_ebitda": entry_ebitda,
        "entry_multiple": entry_multiple,
        "entry_ev": entry_ev,
        "transaction_fees": transaction_fees,
        "cash_to_balance_sheet": cash_to_balance_sheet,
        "total_uses": total_uses,
        "debt_amount": total_opening_debt,
        "implied_leverage": (total_opening_debt / entry_ebitda) if entry_ebitda else None,
        "sponsor_equity": sponsor_equity,
        "exit_multiple": exit_multiple,
        "exit_year": exit_year,
        "capital_structure_mode": "multi_tranche",
    }
    exit_summary = {
        "exit_ebitda": exit_ebitda,
        "exit_multiple": exit_multiple,
        "exit_ev": exit_ev,
        "remaining_debt": remaining_debt,
        "ending_cash_balance": ending_cash_balance,
        "exit_equity_value": exit_equity_value,
        "debt_paydown": total_opening_debt - remaining_debt,
    }
    returns = {
        "irr": irr,
        "moic": moic,
        "sponsor_equity": sponsor_equity,
        "entry_ev": entry_ev,
        "exit_equity_value": exit_equity_value,
        "debt_paydown": total_opening_debt - remaining_debt,
        "remaining_debt": remaining_debt,
        "ending_cash_balance": ending_cash_balance,
        "cash_flows": cash_flows,
    }

    warning_flags: list[dict[str, str]] = []
    warning_flags.extend(source_truth_flags)
    warning_flags.extend(cash_flags)
    warning_flags.extend(waterfall["flags"])
    warning_flags.extend(covenant_summary.get("flags") or [])
    warning_flags.extend(maturity.get("flags") or [])

    return {
        "status": "ok",
        "symbol": inputs.get("symbol"),
        "currency": inputs.get("currency"),
        "transaction_summary": transaction_summary,
        "operating_forecast": {
            "years": years,
            "revenue": revenue,
            "ebitda": ebitda,
            "cash_taxes": cash_taxes,
            "gross_cash_taxes": cash_taxes,
            "tax_rate": tax_rate,
            "tax_shield_enabled": tax_shield_enabled,
            "tax_shield": [row.get("tax_shield") for row in debt_schedule],
            "levered_cash_taxes": [row.get("levered_cash_taxes") for row in debt_schedule],
            "capex": capex,
            "change_in_nwc": change_in_nwc,
        },
        "debt_schedule": debt_schedule,
        "capital_structure_summary": cap_summary,
        "covenant_summary": {k: v for k, v in covenant_summary.items() if k != "flags"},
        "maturity_wall": maturity["wall"],
        "exit": exit_summary,
        "returns": returns,
        "flags": warning_flags,
        "audit": {"disclosures": AUDIT_DISCLOSURES + MULTI_TRANCHE_DISCLOSURES},
    }
