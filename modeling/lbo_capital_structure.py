"""V4.4 multi-tranche capital structure helpers.

Pure module: no Flask dependency, no file I/O, no DCF / provider calls. It owns
multi-tranche debt-schedule waterfall, covenant breach detection and the
maturity-wall view. ``run_lbo()`` in :mod:`modeling.lbo_calculator` remains the
single source of truth for IRR / MOIC; this module only produces the debt
schedule, covenant checks and maturity wall that ``run_lbo()`` assembles into
its multi-tranche output.

Design discipline
-----------------
* Interest is always computed on the beginning balance of each tranche. No
  iterative / circular calculation.
* The yearly waterfall order is fixed (opening -> cash before debt service ->
  interest -> mandatory amortization -> revolver draw for shortfall -> pay
  required debt service -> optional sweep -> ending balances -> ending cash ->
  covenants).
* In any single year the revolver may either draw (cash shortfall) or be the
  target of optional repayment, never both: ``revolver_draw *
  revolver_optional_repayment == 0``.
* Covenant detection only reports breach / headroom; it never blocks, cures, or
  uses deal-conclusion language.
"""

from __future__ import annotations

import math
from typing import Any


EPS = 1e-9

ALLOWED_TRANCHE_TYPES = {
    "revolver",
    "term_loan_a",
    "term_loan_b",
    "senior_notes",
    "mezz",
}

CASH_BRIDGE_NOTE_EN = (
    "Multi-tranche mode captures ending cash balance; legacy single-tranche mode "
    "does not model a cash balance bridge."
)
CASH_BRIDGE_NOTE_CN = (
    "当存在多余现金时，single-tranche 与 multi-tranche 口径可能不可直接比较："
    "multi-tranche 会捕捉期末现金余额，而旧 single-tranche 路径不建现金余额桥。"
)

MATURITY_WALL_NOTE_EN = (
    "Maturity wall shows debt outstanding at exit by maturity year, not original face value."
)

MULTI_TRANCHE_DISCLOSURES = [
    "V4.4 multi-tranche capital structure: interest is calculated on beginning debt balance by tranche; no iterative circular calculation is used.",
    "In any single year the revolver either draws to cover a cash shortfall or is repaid by optional sweep, never both.",
    "Optional cash sweep follows tranche sweep_priority ascending; sweep_priority is the sole ordering source of truth.",
    "Mandatory amortization uses each tranche's original opening balance and is capped by its beginning balance.",
    "Ending cash balance captures excess cash retained after debt is fully repaid; multi-tranche exit equity includes ending cash.",
    CASH_BRIDGE_NOTE_EN,
    "Covenant detection reports breach and headroom only. It does not block, cure, or constitute an investment or acquisition recommendation.",
    "Maturity wall is a display / audit view only. It does not model refinancing, amend-and-extend, or maturity default.",
    MATURITY_WALL_NOTE_EN,
    "V4.4 does not model PIK, dividend recap, refinancing, covenant cure, OID / fee accretion, or scenario storage; these are deferred future scope, not permanent prohibitions.",
]


def _flag(code: str, message: str, severity: str = "error") -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message}


def _num(value: Any, default: float | None = None) -> float:
    if value is None or value == "":
        if default is None:
            raise ValueError("missing numeric value")
        return default
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite numeric value")
    return number


def validate_capital_structure(capital_structure: Any) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    """Validate and normalize a ``capital_structure`` input block.

    Returns ``(settings, flags)``. If ``flags`` contains any error-severity flag
    the structure is invalid and the caller must surface a hard error; in that
    case ``settings`` is ``None``.
    """
    flags: list[dict[str, str]] = []
    if not isinstance(capital_structure, dict):
        return None, [_flag("CAPITAL_STRUCTURE_INVALID", "capital_structure must be an object.")]

    raw_tranches = capital_structure.get("tranches")
    if not isinstance(raw_tranches, list) or not raw_tranches:
        return None, [_flag("NO_TRANCHES", "capital_structure.tranches must be a non-empty array.")]

    seen_ids: set[str] = set()
    norm_tranches: list[dict[str, Any]] = []
    for i, raw in enumerate(raw_tranches):
        if not isinstance(raw, dict):
            flags.append(_flag("TRANCHE_INVALID", f"tranches[{i}] must be an object."))
            continue

        tid = str(raw.get("id") or "").strip()
        if not tid:
            flags.append(_flag("EMPTY_TRANCHE_ID", f"tranches[{i}].id must be a non-empty string."))
            continue
        if tid in seen_ids:
            flags.append(_flag("DUPLICATE_TRANCHE_ID", f"Duplicate tranche id '{tid}'."))
            continue
        seen_ids.add(tid)

        ttype = str(raw.get("type") or "").strip()
        if ttype not in ALLOWED_TRANCHE_TYPES:
            flags.append(_flag("INVALID_TRANCHE_TYPE", f"tranche '{tid}' has invalid type '{ttype}'."))
            continue

        if bool(raw.get("pik_enabled", False)):
            flags.append(_flag("PIK_NOT_SUPPORTED_V44", f"tranche '{tid}' requested PIK; PIK is not supported in V4.4."))
            continue

        try:
            opening_balance = _num(raw.get("opening_balance", 0.0), 0.0)
            commitment = _num(raw.get("commitment", opening_balance), opening_balance)
            interest_rate = _num(raw.get("interest_rate", 0.0), 0.0)
            mandatory_amortization_pct = _num(raw.get("mandatory_amortization_pct", 0.0), 0.0)
            maturity_year = int(raw.get("maturity_year", 0))
        except (TypeError, ValueError):
            flags.append(_flag("TRANCHE_FIELD_INVALID", f"tranche '{tid}' has a non-numeric field."))
            continue

        if opening_balance < -EPS:
            flags.append(_flag("NEGATIVE_OPENING_BALANCE", f"tranche '{tid}' opening_balance must be >= 0."))
            continue
        if commitment < opening_balance - EPS:
            flags.append(_flag("COMMITMENT_BELOW_OPENING_BALANCE", f"tranche '{tid}' commitment is below opening_balance."))
            continue
        if interest_rate < -EPS:
            flags.append(_flag("NEGATIVE_INTEREST_RATE", f"tranche '{tid}' interest_rate must be >= 0."))
            continue
        if mandatory_amortization_pct < -EPS:
            flags.append(_flag("NEGATIVE_AMORTIZATION_PCT", f"tranche '{tid}' mandatory_amortization_pct must be >= 0."))
            continue
        if maturity_year < 1:
            flags.append(_flag("INVALID_MATURITY_YEAR", f"tranche '{tid}' maturity_year must be >= 1."))
            continue

        is_revolver = ttype == "revolver"
        draw_allowed = bool(raw.get("draw_allowed", is_revolver))
        if is_revolver and not draw_allowed:
            flags.append(_flag("REVOLVER_DRAW_NOT_ALLOWED", f"revolver tranche '{tid}' must have draw_allowed=True."))
            continue
        if not is_revolver and draw_allowed:
            flags.append(_flag("NON_REVOLVER_DRAW_ALLOWED", f"non-revolver tranche '{tid}' must have draw_allowed=False."))
            continue

        optional_repay_allowed = bool(raw.get("optional_repay_allowed", True))
        sweep_priority_raw = raw.get("sweep_priority")
        if optional_repay_allowed:
            if sweep_priority_raw is None or isinstance(sweep_priority_raw, bool) or not float(sweep_priority_raw).is_integer():
                flags.append(_flag("INVALID_SWEEP_PRIORITY", f"tranche '{tid}' must have an integer sweep_priority when optional_repay_allowed is True."))
                continue
            sweep_priority = int(sweep_priority_raw)
        else:
            sweep_priority = None

        norm_tranches.append({
            "id": tid,
            "name": str(raw.get("name") or tid),
            "type": ttype,
            "opening_balance": opening_balance,
            "original_opening_balance": opening_balance,
            "commitment": commitment,
            "interest_rate": interest_rate,
            "mandatory_amortization_pct": mandatory_amortization_pct,
            "maturity_year": maturity_year,
            "cash_pay": bool(raw.get("cash_pay", True)),
            "sweep_priority": sweep_priority,
            "draw_allowed": draw_allowed,
            "optional_repay_allowed": optional_repay_allowed,
            "is_revolver": is_revolver,
        })

    if flags:
        return None, flags
    if not norm_tranches:
        return None, [_flag("NO_TRANCHES", "capital_structure.tranches contained no valid tranches.")]

    try:
        cash_balance_beginning = _num(capital_structure.get("cash_balance_beginning", 0.0), 0.0)
        minimum_cash_balance = _num(capital_structure.get("minimum_cash_balance", 0.0), 0.0)
    except (TypeError, ValueError):
        return None, [_flag("CAPITAL_STRUCTURE_INVALID", "cash_balance_beginning / minimum_cash_balance must be numeric.")]

    covenants_raw = capital_structure.get("covenants") or {}
    covenants: dict[str, float | None] = {"max_net_debt_ebitda": None, "min_interest_coverage": None}
    if isinstance(covenants_raw, dict):
        for key in ("max_net_debt_ebitda", "min_interest_coverage"):
            value = covenants_raw.get(key)
            if value is not None and value != "":
                try:
                    covenants[key] = _num(value)
                except (TypeError, ValueError):
                    return None, [_flag("COVENANT_THRESHOLD_INVALID", f"covenants.{key} must be numeric.")]

    settings = {
        "mode": "multi_tranche",
        "tranches": norm_tranches,
        "cash_balance_beginning": cash_balance_beginning,
        "minimum_cash_balance": minimum_cash_balance,
        "cash_sweep_enabled": bool(capital_structure.get("cash_sweep_enabled", True)),
        "covenants": covenants,
    }
    return settings, []


def run_waterfall(settings: dict[str, Any], forecast: dict[str, list[float]]) -> dict[str, Any]:
    """Run the fixed-order multi-tranche cash waterfall over the forecast years.

    Returns a dict with ``debt_schedule`` (list of yearly rows), aggregate
    ``flags`` and convenience totals. Pure: state is carried explicitly between
    years; interest uses beginning balances only.
    """
    tranches = settings["tranches"]
    minimum_cash_balance = settings["minimum_cash_balance"]
    cash_sweep_enabled = settings["cash_sweep_enabled"]

    years = forecast["years"]
    ebitda = forecast["ebitda"]
    cash_taxes = forecast["cash_taxes"]
    tax_rate = float(forecast.get("tax_rate", 0.25) or 0.0)
    tax_shield_enabled = bool(forecast.get("tax_shield_enabled", True))
    capex = forecast["capex"]
    change_in_nwc = forecast["change_in_nwc"]
    n = len(years)

    flags: list[dict[str, str]] = []
    beginning_balance = {t["id"]: t["opening_balance"] for t in tranches}
    beginning_cash = settings["cash_balance_beginning"]
    revolver = next((t for t in tranches if t["is_revolver"]), None)

    debt_schedule: list[dict[str, Any]] = []
    for idx in range(n):
        # Step 3 - interest on beginning balance
        cash_interest = {t["id"]: beginning_balance[t["id"]] * t["interest_rate"] for t in tranches}
        total_cash_interest = sum(cash_interest.values())
        tax_shield = total_cash_interest * tax_rate if tax_shield_enabled else 0.0
        levered_cash_taxes = max(0.0, cash_taxes[idx] - tax_shield)

        # Step 2 - operating cash flow before debt service. Tax shield is
        # computed from beginning-balance interest above, so no circularity is
        # introduced. The legacy waterfall cash_before_debt_service also carries
        # beginning cash.
        cash_flow_before_debt_service = (
            ebitda[idx] - levered_cash_taxes - capex[idx] - change_in_nwc[idx]
        )
        cash_before_debt_service = cash_flow_before_debt_service + beginning_cash

        # Step 4 - mandatory amortization (uses original opening balance, capped by beginning)
        mandatory = {}
        for t in tranches:
            if t["is_revolver"]:
                mandatory[t["id"]] = 0.0
                continue
            scheduled = t["original_opening_balance"] * t["mandatory_amortization_pct"]
            mandatory[t["id"]] = min(beginning_balance[t["id"]], scheduled)
        total_mandatory = sum(mandatory.values())

        # Step 5 - revolver draw only if cash shortfall
        draw = {t["id"]: 0.0 for t in tranches}
        revolver_draw = 0.0
        debt_service_failure = False
        required_debt_service = total_cash_interest + total_mandatory
        cash_shortfall = required_debt_service - cash_before_debt_service
        if cash_shortfall > EPS:
            if revolver is None:
                debt_service_failure = True
                flags.append(_flag(
                    "CASH_SHORTFALL_NO_REVOLVER",
                    f"Year {years[idx]}: cash before debt service is below required debt service and no revolver exists.",
                    "warning",
                ))
            else:
                available_capacity = max(0.0, revolver["commitment"] - beginning_balance[revolver["id"]])
                revolver_draw = min(cash_shortfall, available_capacity)
                draw[revolver["id"]] = revolver_draw
                unfunded = cash_shortfall - revolver_draw
                if unfunded > EPS:
                    debt_service_failure = True
                    flags.append(_flag(
                        "REVOLVER_CAPACITY_EXCEEDED",
                        f"Year {years[idx]}: revolver capacity is insufficient to fund the cash shortfall.",
                        "warning",
                    ))

        # Step 6 - pay required debt service
        cash_after_required_debt_service = (
            cash_before_debt_service + revolver_draw - total_cash_interest - total_mandatory
        )
        cash_after_interest_and_mandatory = (
            cash_flow_before_debt_service - total_cash_interest - total_mandatory
        )
        if cash_after_required_debt_service < -EPS:
            debt_service_failure = True
            flags.append(_flag(
                "UNFUNDED_CASH_SHORTFALL",
                f"Year {years[idx]}: required debt service could not be funded; unfunded cash shortfall remains.",
                "warning",
            ))

        # Step 7 - optional sweep only if excess cash exists and revolver did not draw
        optional = {t["id"]: 0.0 for t in tranches}
        total_optional = 0.0
        if (
            cash_sweep_enabled
            and revolver_draw <= EPS
            and cash_after_required_debt_service > minimum_cash_balance + EPS
        ):
            cash_available = max(0.0, cash_after_required_debt_service - minimum_cash_balance)
            sweepable = [t for t in tranches if t["optional_repay_allowed"]]
            sweepable.sort(key=lambda t: (t["sweep_priority"], t["id"]))
            for t in sweepable:
                if cash_available <= EPS:
                    break
                balance_after_mandatory = beginning_balance[t["id"]] + draw[t["id"]] - mandatory[t["id"]]
                if balance_after_mandatory <= EPS:
                    continue
                repay = min(cash_available, balance_after_mandatory)
                optional[t["id"]] = repay
                cash_available -= repay
            total_optional = sum(optional.values())

        # Step 8 - ending balances
        ending_balance = {}
        for t in tranches:
            tid = t["id"]
            end = beginning_balance[tid] + draw[tid] - mandatory[tid] - optional[tid]
            if end < -EPS:
                flags.append(_flag(
                    "TRANCHE_BALANCE_NEGATIVE_CLAMPED",
                    f"Year {years[idx]}: tranche '{tid}' ending balance computed below zero and was clamped.",
                    "warning",
                ))
                end = 0.0
            ending_balance[tid] = max(0.0, end)

        # Step 9 - ending cash balance
        ending_cash = cash_after_required_debt_service - total_optional

        total_beginning_debt = sum(beginning_balance.values())
        total_ending_debt = sum(ending_balance.values())

        row_tranches = []
        for t in tranches:
            tid = t["id"]
            tr = {
                "id": tid,
                "name": t["name"],
                "type": t["type"],
                "beginning_balance": beginning_balance[tid],
                "draw": draw[tid],
                "cash_interest": cash_interest[tid],
                "mandatory_amortization": mandatory[tid],
                "optional_repayment": optional[tid],
                "ending_balance": ending_balance[tid],
            }
            if t["is_revolver"]:
                tr["available_capacity"] = max(0.0, t["commitment"] - ending_balance[tid])
            row_tranches.append(tr)

        debt_schedule.append({
            "year": years[idx],
            "cash_flow_before_debt_service": cash_flow_before_debt_service,
            "cash_before_debt_service": cash_before_debt_service,
            "total_cash_interest": total_cash_interest,
            "gross_cash_taxes": cash_taxes[idx],
            "tax_shield": tax_shield,
            "levered_cash_taxes": levered_cash_taxes,
            "tax_rate": tax_rate,
            "tax_shield_enabled": tax_shield_enabled,
            "total_mandatory_amortization": total_mandatory,
            "revolver_draw": revolver_draw,
            "cash_after_interest_and_mandatory_amortization": cash_after_interest_and_mandatory,
            "cash_after_required_debt_service": cash_after_required_debt_service,
            "total_optional_repayment": total_optional,
            "ending_cash_balance": ending_cash,
            "total_beginning_debt": total_beginning_debt,
            "total_ending_debt": total_ending_debt,
            "debt_service_failure": debt_service_failure,
            "tranches": row_tranches,
        })

        beginning_balance = ending_balance
        beginning_cash = ending_cash

    return {
        "debt_schedule": debt_schedule,
        "flags": flags,
    }


def build_capital_structure_summary(settings: dict[str, Any], debt_schedule: list[dict[str, Any]]) -> dict[str, Any]:
    tranches = settings["tranches"]
    total_opening_debt = sum(t["opening_balance"] for t in tranches)
    final = debt_schedule[-1]
    total_ending_debt = final["total_ending_debt"]
    ending_cash_balance = final["ending_cash_balance"]

    year1 = debt_schedule[0]
    weighted_interest = sum(tr["cash_interest"] for tr in year1["tranches"])
    weighted_base = sum(tr["beginning_balance"] for tr in year1["tranches"])
    weighted_avg_rate = (weighted_interest / weighted_base) if weighted_base > EPS else 0.0

    final_by_id = {tr["id"]: tr for tr in final["tranches"]}
    summary_tranches = []
    for t in tranches:
        ft = final_by_id.get(t["id"], {})
        summary_tranches.append({
            "id": t["id"],
            "name": t["name"],
            "type": t["type"],
            "opening_balance": t["opening_balance"],
            "ending_balance": ft.get("ending_balance", 0.0),
            "interest_rate": t["interest_rate"],
            "maturity_year": t["maturity_year"],
        })

    return {
        "mode": "multi_tranche",
        "total_opening_debt": total_opening_debt,
        "total_ending_debt": total_ending_debt,
        "ending_cash_balance": ending_cash_balance,
        "net_debt_at_exit": total_ending_debt - ending_cash_balance,
        "weighted_avg_cash_interest_rate_year_1": weighted_avg_rate,
        "single_vs_multi_cash_bridge_note": CASH_BRIDGE_NOTE_EN,
        "single_vs_multi_cash_bridge_note_cn": CASH_BRIDGE_NOTE_CN,
        "tranches": summary_tranches,
    }


def build_covenant_summary(
    settings: dict[str, Any],
    debt_schedule: list[dict[str, Any]],
    forecast_ebitda: list[float],
) -> dict[str, Any]:
    covenants = settings["covenants"]
    max_leverage = covenants.get("max_net_debt_ebitda")
    min_coverage = covenants.get("min_interest_coverage")
    has_thresholds = max_leverage is not None or min_coverage is not None

    checks: list[dict[str, Any]] = []
    flags: list[dict[str, str]] = []
    breach_years: list[Any] = []
    any_unavailable = False

    for idx, row in enumerate(debt_schedule):
        year = row["year"]
        covenant_ebitda = forecast_ebitda[idx]
        total_ending_debt = row["total_ending_debt"]
        ending_cash = row["ending_cash_balance"]
        total_cash_interest = row["total_cash_interest"]
        net_debt = total_ending_debt - ending_cash

        is_net_cash = net_debt < -EPS
        net_debt_ebitda: float | None = None
        leverage_breach = False
        leverage_headroom: float | None = None

        if covenant_ebitda <= EPS:
            any_unavailable = True
            flags.append(_flag(
                "COVENANT_EBITDA_NON_POSITIVE",
                f"Year {year}: covenant EBITDA is non-positive; leverage covenant is treated as unavailable / high risk.",
                "warning",
            ))
        elif is_net_cash:
            # Net cash position: do not present a misleading negative leverage.
            net_debt_ebitda = None
            leverage_breach = False
            leverage_headroom = None
        else:
            net_debt_ebitda = net_debt / covenant_ebitda
            if max_leverage is not None:
                leverage_headroom = max_leverage - net_debt_ebitda
                leverage_breach = net_debt_ebitda > max_leverage + EPS

        interest_coverage: float | None = None
        interest_coverage_breach = False
        interest_coverage_headroom: float | None = None
        if total_cash_interest <= EPS:
            interest_coverage = None
            flags.append(_flag(
                "INTEREST_COVERAGE_UNAVAILABLE",
                f"Year {year}: total cash interest is zero; interest coverage is unavailable (not shown as infinite pass).",
                "warning",
            ))
        elif covenant_ebitda > EPS:
            interest_coverage = covenant_ebitda / total_cash_interest
            if min_coverage is not None:
                interest_coverage_headroom = interest_coverage - min_coverage
                interest_coverage_breach = interest_coverage < min_coverage - EPS

        if leverage_breach or interest_coverage_breach:
            breach_years.append(year)

        checks.append({
            "year": year,
            "net_debt": net_debt,
            "ebitda": covenant_ebitda,
            "is_net_cash": is_net_cash,
            "net_debt_ebitda": net_debt_ebitda,
            "max_net_debt_ebitda": max_leverage,
            "leverage_headroom": leverage_headroom,
            "leverage_breach": leverage_breach,
            "interest_coverage": interest_coverage,
            "min_interest_coverage": min_coverage,
            "interest_coverage_headroom": interest_coverage_headroom,
            "interest_coverage_breach": interest_coverage_breach,
        })

    if breach_years:
        status = "breach"
        flags.append(_flag(
            "COVENANT_BREACH_DETECTED",
            f"Covenant breach detected in year(s): {', '.join(str(y) for y in breach_years)}.",
            "warning",
        ))
    elif not has_thresholds or any_unavailable:
        status = "unavailable"
    else:
        status = "pass"

    return {
        "status": status,
        "max_net_debt_ebitda": max_leverage,
        "min_interest_coverage": min_coverage,
        "breach_years": breach_years,
        "checks": checks,
        "flags": flags,
    }


def build_maturity_wall(settings: dict[str, Any], debt_schedule: list[dict[str, Any]], exit_year: int) -> dict[str, Any]:
    tranches = settings["tranches"]
    final_by_id = {tr["id"]: tr for tr in debt_schedule[-1]["tranches"]}

    by_year: dict[int, dict[str, Any]] = {}
    flags: list[dict[str, str]] = []
    for t in tranches:
        my = int(t["maturity_year"])
        outstanding = final_by_id.get(t["id"], {}).get("ending_balance", 0.0)
        bucket = by_year.setdefault(my, {
            "year": my,
            "maturing_debt": 0.0,
            "maturing_debt_basis": "outstanding_at_exit",
            "disclosure": MATURITY_WALL_NOTE_EN,
            "tranches": [],
        })
        bucket["maturing_debt"] += outstanding
        bucket["tranches"].append(t["name"])
        if my <= exit_year:
            flags.append(_flag(
                "DEBT_MATURITY_WITHIN_HOLD_PERIOD",
                f"Tranche '{t['name']}' matures in year {my}, within the hold period (exit year {exit_year}); refinancing is not modeled.",
                "warning",
            ))

    wall = [by_year[y] for y in sorted(by_year)]
    return {"wall": wall, "flags": flags}
