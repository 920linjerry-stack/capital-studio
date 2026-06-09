"""V4.6 LBO Scenario / Case Layer v1.

A light scenario-organization layer on top of the existing V4.0-V4.5 LBO engine.
It generates Base / Upside / Downside input payloads from the user's current Base
inputs using deterministic, transparent deltas, runs each payload through the
existing ``run_lbo()`` engine, attaches ``build_lbo_attribution()`` where
available, and assembles a single comparison view.

Discipline
----------
* This layer never re-implements LBO engine math. ``run_lbo()`` is the IRR / MOIC
  source of truth; ``build_lbo_attribution()`` is the attribution source of truth.
* Pure orchestration: no Flask dependency, no file I/O, no provider / market-data
  fetch, no scenario persistence.
* It does not mutate the caller's base inputs.
* Scenarios are deterministic modeling cases, not forecasts, probabilities,
  investment recommendations, or acquisition recommendations.
* Labels are Base / Upside / Downside (never Bull / Bear) to keep modeling-case
  language, not stock-market long/short language.
* A single canonical metric schema (:data:`SCENARIO_METRIC_SCHEMA`) is the only
  source of metric keys / labels / formats; UI, Excel and tests align to it.
"""

from __future__ import annotations

import copy
import math
from typing import Any

from modeling.lbo_calculator import run_lbo
from modeling.lbo_attribution import (
    build_lbo_attribution,
    MOIC_CONTRIBUTION_NOTE_EN,
    MOIC_CONTRIBUTION_NOTE_CN,
)


METHOD = "lbo_case_layer_v46"

# ── Canonical display schema (single source of truth) ────────────────────────
# UI comparison and the Excel Scenario Summary both render from this list. UI may
# hide / collapse rows on narrow screens, but must not invent a UI-only metric or
# an Excel-only metric. Tests align to this schema rather than hard-coding a
# second list of label strings.
SCENARIO_METRIC_SCHEMA: list[dict[str, str]] = [
    {"key": "irr", "label": "IRR", "format": "percent"},
    {"key": "moic", "label": "MOIC", "format": "multiple"},
    {"key": "sponsor_equity", "label": "Sponsor Equity", "format": "amount"},
    {"key": "exit_equity_value", "label": "Exit Equity Value", "format": "amount"},
    {"key": "remaining_debt", "label": "Remaining Debt", "format": "amount"},
    {"key": "debt_paydown", "label": "Debt Paydown", "format": "amount"},
    {"key": "ending_cash_balance", "label": "Ending Cash Balance", "format": "amount"},
    {"key": "covenant_status", "label": "Covenant Status", "format": "text"},
    {"key": "debt_service_failure", "label": "Debt Service Failure", "format": "boolean"},
    {"key": "revolver_draw_occurred", "label": "Revolver Draw Occurred", "format": "boolean"},
    {"key": "total_cash_interest", "label": "Total Cash Interest", "format": "amount"},
    {"key": "minimum_interest_coverage", "label": "Minimum Interest Coverage / DSCR", "format": "multiple"},
    {"key": "breach_years", "label": "Breach Years", "format": "text"},
    {"key": "suitability_status", "label": "Suitability Status", "format": "text"},
    {"key": "ebitda_growth_contribution", "label": "EBITDA Growth Contribution", "format": "amount"},
    {"key": "multiple_movement_contribution", "label": "Multiple Movement Contribution", "format": "amount"},
    {"key": "deleveraging_contribution", "label": "Deleveraging Contribution", "format": "amount"},
    {"key": "fees_drag", "label": "Fees Drag", "format": "amount"},
    {"key": "ending_cash_balance_contribution", "label": "Ending Cash Balance Contribution", "format": "amount"},
    {"key": "initial_cash_funding_contribution", "label": "Initial Cash Funding", "format": "amount"},
    {"key": "residual", "label": "Residual", "format": "amount"},
]

# Stable display sentinels (never show blank / Python None in UI / Excel).
NOT_APPLICABLE_SINGLE = "Not Applicable (single-tranche)"
UNAVAILABLE = "Unavailable"

SCENARIO_LABELS = {
    "base": "Base Case",
    "upside": "Upside Case",
    "downside": "Downside Case",
}

# V4.7.1: scenarios are a same-transaction sensitivity. Entry valuation, opening
# debt and sponsor equity are held constant; only operating performance, exit
# multiple, financing cost and (downside) capex / NWC stress are shocked. The
# downside is calibrated to a meaningful stress, not a token haircut.
SCENARIO_DELTA_KEYS = (
    "ebitda_pct_delta", "exit_multiple_delta", "interest_rate_delta",
    "capex_pct_delta", "nwc_pct_delta",
)
DEFAULT_SCENARIO_CONFIG: dict[str, dict[str, float]] = {
    "upside": {
        "ebitda_pct_delta": 0.10, "exit_multiple_delta": 0.5,
        "interest_rate_delta": -0.005, "capex_pct_delta": 0.0, "nwc_pct_delta": 0.0,
    },
    "downside": {
        "ebitda_pct_delta": -0.15, "exit_multiple_delta": -1.0,
        "interest_rate_delta": 0.01, "capex_pct_delta": 0.10, "nwc_pct_delta": 0.10,
    },
}

# ── Canonical disclosure strings ─────────────────────────────────────────────
DISCLOSURE_DETERMINISTIC_EN = (
    "Upside / Downside cases are deterministic modeling cases based on the current "
    "Base inputs. They are not forecasts, probabilities, or recommendations."
)
DISCLOSURE_DETERMINISTIC_CN = (
    "Upside / Downside 是基于当前 Base 假设的确定性建模情景，不代表预测、概率，也不构成投资或收购方面的建议。"
)
DISCLOSURE_MULTI_FACTOR_EN = (
    "Upside / Downside simultaneously adjust operating performance, exit multiple, "
    "and interest rate assumptions. The case spread reflects multi-factor stacking, "
    "not a single-variable sensitivity."
)
DISCLOSURE_MULTI_FACTOR_CN = (
    "Upside / Downside 同时调整经营表现、退出倍数和利率假设，因此情景区间反映多因素叠加，不是单变量敏感性。"
)
DISCLOSURE_INTEREST_RATE_EN = (
    "V4.6 applies the interest rate delta uniformly across debt tranches for "
    "scenario modeling. It does not distinguish fixed-rate vs floating-rate debt."
)
DISCLOSURE_INTEREST_RATE_CN = (
    "V4.6 的情景层会将利率变化统一作用于各债务档位，暂不区分固定利率与浮动利率债务。"
)
DISCLOSURE_MULTIPLE_MOVEMENT_EN = (
    "Multiple movement contribution isolates the value impact from exit multiple "
    "changes. Upside / Downside case returns may include multiple expansion or "
    "contraction by assumption."
)
DISCLOSURE_MULTIPLE_MOVEMENT_CN = (
    "倍数变化贡献用于单独展示退出倍数变化带来的价值影响。Upside / Downside 的回报可能包含假设性的倍数扩张或收缩。"
)
DISCLOSURE_LABELS_EN = (
    "LBO uses Upside / Downside case labels to describe modeling assumptions, not "
    "market views."
)
DISCLOSURE_LABELS_CN = (
    "LBO 使用 Upside / Downside 情景标签来描述建模假设，不代表市场多空观点。"
)
DISCLOSURE_SAME_TRANSACTION_EN = (
    "Scenario comparison is a same-transaction sensitivity: entry valuation, "
    "opening debt and sponsor equity are held constant."
)
DISCLOSURE_SAME_TRANSACTION_CN = (
    "情景对比为同一交易敏感性：入口估值、初始债务和 Sponsor Equity 保持不变。"
)
# Excel Scenario Summary required disclosures (slightly different wording).
DISCLOSURE_EXCEL_DETERMINISTIC = (
    "Scenarios are deterministic modeling cases based on user-configured deltas. "
    "They are not forecasts, probabilities, investment recommendations, or "
    "acquisition recommendations."
)
DISCLOSURE_EXCEL_MULTI_FACTOR = (
    "Scenario spreads reflect simultaneous changes to operating performance, exit "
    "multiple, and interest rate assumptions, not a single-variable sensitivity."
)

DISCLOSURES_EN = [
    DISCLOSURE_SAME_TRANSACTION_EN,
    DISCLOSURE_DETERMINISTIC_EN,
    DISCLOSURE_MULTI_FACTOR_EN,
    DISCLOSURE_INTEREST_RATE_EN,
    DISCLOSURE_MULTIPLE_MOVEMENT_EN,
    DISCLOSURE_LABELS_EN,
    DISCLOSURE_EXCEL_DETERMINISTIC,
    DISCLOSURE_EXCEL_MULTI_FACTOR,
]
DISCLOSURES_CN = [
    DISCLOSURE_SAME_TRANSACTION_CN,
    DISCLOSURE_DETERMINISTIC_CN,
    DISCLOSURE_MULTI_FACTOR_CN,
    DISCLOSURE_INTEREST_RATE_CN,
    DISCLOSURE_MULTIPLE_MOVEMENT_CN,
    DISCLOSURE_LABELS_CN,
]

# Static downside guidance (does not require recomputing suitability here).
DOWNSIDE_GUIDANCE_EN = (
    "The Downside Case became unavailable because the company has limited EBITDA / "
    "cash-flow cushion under the selected deltas. Review suitability and operating "
    "assumptions before interpreting LBO outputs."
)
DOWNSIDE_GUIDANCE_CN = (
    "Downside 情景不可用，说明该标的在所选下行情景下 EBITDA / 现金流缓冲较薄。"
    "请结合 suitability 与经营假设复核后再解释 LBO 输出。"
)


def _flag(code: str, message: str, severity: str = "warning") -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def _resolve_config(scenario_config: dict | None) -> dict[str, dict[str, float]]:
    resolved = copy.deepcopy(DEFAULT_SCENARIO_CONFIG)
    if isinstance(scenario_config, dict):
        for case in ("upside", "downside"):
            overrides = scenario_config.get(case)
            if isinstance(overrides, dict):
                for key in SCENARIO_DELTA_KEYS:
                    if overrides.get(key) is not None:
                        resolved[case][key] = float(overrides[key])
    return resolved


def _apply_deltas(inputs: dict, deltas: dict[str, float]) -> dict:
    """Return a deep-copied input payload with deterministic scenario deltas
    applied. Does not mutate ``inputs``."""
    scn = copy.deepcopy(inputs)
    ebitda_pct = deltas.get("ebitda_pct_delta", 0.0)
    exit_multiple_delta = deltas.get("exit_multiple_delta", 0.0)
    interest_rate_delta = deltas.get("interest_rate_delta", 0.0)
    capex_pct = deltas.get("capex_pct_delta", 0.0)
    nwc_pct = deltas.get("nwc_pct_delta", 0.0)

    transaction = scn.setdefault("transaction", {})
    # V4.7.1 same-transaction sensitivity: Entry EBITDA / Entry Multiple are held
    # constant so Entry EV, Total Uses, opening debt and Sponsor Equity do not
    # change across scenarios. Only the OPERATING forecast is shocked.
    forecast = scn.setdefault("operating_forecast", {})
    for field in ("ebitda", "revenue"):
        values = forecast.get(field)
        if isinstance(values, list):
            forecast[field] = [_f(v) * (1.0 + ebitda_pct) for v in values]

    # Downside stress can also raise CapEx and Change in NWC (cash drains).
    for field, pct in (("capex", capex_pct), ("change_in_nwc", nwc_pct)):
        values = forecast.get(field)
        if isinstance(values, list) and pct:
            forecast[field] = [_f(v) * (1.0 + pct) for v in values]

    # Exit multiple: shift, floored at 0.0.
    entry_multiple = _f(transaction.get("entry_multiple"))
    current_exit = transaction.get("exit_multiple")
    base_exit = _f(current_exit) if current_exit is not None else entry_multiple
    transaction["exit_multiple"] = max(0.0, base_exit + exit_multiple_delta)

    # Interest rate: applied uniformly, floored at 0%.
    capital_structure = scn.get("capital_structure")
    if isinstance(capital_structure, dict) and capital_structure.get("mode") == "multi_tranche":
        for tranche in capital_structure.get("tranches") or []:
            if isinstance(tranche, dict) and tranche.get("interest_rate") is not None:
                tranche["interest_rate"] = max(0.0, _f(tranche.get("interest_rate")) + interest_rate_delta)
    else:
        debt = scn.setdefault("debt", {})
        if debt.get("interest_rate") is not None:
            debt["interest_rate"] = max(0.0, _f(debt.get("interest_rate")) + interest_rate_delta)

    return scn


def generate_scenario_inputs(base_inputs: dict, scenario_config: dict | None = None) -> dict:
    """Return scenario-specific input payloads for base / upside / downside.

    Does not run the model. Does not mutate ``base_inputs``.
    """
    base_inputs = base_inputs or {}
    config = _resolve_config(scenario_config)
    return {
        "base": copy.deepcopy(base_inputs),
        "upside": _apply_deltas(base_inputs, config["upside"]),
        "downside": _apply_deltas(base_inputs, config["downside"]),
    }


def _ebitda_non_positive(inputs: dict) -> bool:
    transaction = inputs.get("transaction") or {}
    entry = transaction.get("entry_ebitda")
    if entry is not None and _f(entry, 1.0) <= 0:
        return True
    ebitda = (inputs.get("operating_forecast") or {}).get("ebitda") or []
    return any(_f(v, 1.0) <= 0 for v in ebitda)


def _unavailable_reason(key: str, label: str, inputs: dict, result: dict) -> tuple[str, str]:
    """Return ``(scenario_level_reason, comparison_reason)`` for a failed run."""
    if _ebitda_non_positive(inputs):
        return (
            f"{label} became unavailable because EBITDA became non-positive.",
            f"EBITDA became non-positive under {key} assumptions.",
        )
    error_flags = [f for f in (result.get("flags") or []) if f.get("severity") == "error"]
    if error_flags:
        message = error_flags[0].get("message") or "did not produce valid LBO returns."
        return (f"{label} is unavailable: {message}", message)
    return (
        f"{label} did not produce valid LBO returns.",
        f"{label} did not produce valid LBO returns.",
    )


def _run_one(key: str, inputs: dict) -> dict:
    label = SCENARIO_LABELS[key]
    result = run_lbo(inputs)
    if result.get("status") == "ok" and result.get("returns"):
        try:
            attribution = build_lbo_attribution(inputs, result)
        except Exception as exc:  # defensive: never let one scenario break others
            attribution = {
                "status": "unavailable",
                "components": [],
                "flags": [_flag("ATTRIBUTION_BUILD_FAILED", f"Attribution raised: {exc}")],
            }
        return {
            "label": label,
            "status": "ok",
            "inputs": inputs,
            "result": result,
            "attribution": attribution,
            "flags": list(result.get("flags") or []),
        }

    scenario_reason, comparison_reason = _unavailable_reason(key, label, inputs, result)
    return {
        "label": label,
        "status": "unavailable",
        "inputs": inputs,
        "result": None,
        "attribution": None,
        "unavailable_reason": scenario_reason,
        "comparison_reason": comparison_reason,
        "flags": list(result.get("flags") or []),
    }


def _extract_metrics(scenario: dict, base_suitability: dict | None) -> dict[str, Any]:
    result = scenario.get("result") or {}
    attribution = scenario.get("attribution") or {}
    returns = result.get("returns") or {}
    cap = result.get("capital_structure_summary") or {}
    is_multi = cap.get("mode") == "multi_tranche"
    debt_schedule = result.get("debt_schedule") or []
    covenant = result.get("covenant_summary") or {}

    comps: dict[str, Any] = {}
    if attribution.get("status") == "ok":
        comps = {c["key"]: c.get("value") for c in (attribution.get("components") or [])}

    metrics: dict[str, Any] = {
        "irr": returns.get("irr"),
        "moic": returns.get("moic"),
        "sponsor_equity": returns.get("sponsor_equity"),
        "exit_equity_value": returns.get("exit_equity_value"),
        "remaining_debt": returns.get("remaining_debt"),
        "debt_paydown": returns.get("debt_paydown"),
        "ending_cash_balance": returns.get("ending_cash_balance", 0.0),
        "debt_service_failure": any(bool(r.get("debt_service_failure")) for r in debt_schedule),
        "suitability_status": (base_suitability or {}).get("suitability") or "Not Assessed",
        "ebitda_growth_contribution": comps.get("ebitda_growth"),
        "multiple_movement_contribution": comps.get("multiple_movement"),
        "deleveraging_contribution": comps.get("deleveraging"),
        "fees_drag": comps.get("fees_drag"),
        "ending_cash_balance_contribution": comps.get("ending_cash_balance", 0.0),
        "initial_cash_funding_contribution": comps.get("initial_cash_funding", 0.0),
        "residual": comps.get("residual"),
    }

    if is_multi:
        metrics["total_cash_interest"] = sum(_f(r.get("total_cash_interest")) for r in debt_schedule)
        metrics["covenant_status"] = covenant.get("status")
        metrics["revolver_draw_occurred"] = any(_f(r.get("revolver_draw")) > 0 for r in debt_schedule)
        coverages = [
            c.get("interest_coverage")
            for c in (covenant.get("checks") or [])
            if c.get("interest_coverage") is not None
        ]
        metrics["minimum_interest_coverage"] = min(coverages) if coverages else None
        breach_years = covenant.get("breach_years") or []
        metrics["breach_years"] = ", ".join(str(y) for y in breach_years) if breach_years else "(none)"
    else:
        metrics["total_cash_interest"] = sum(_f(r.get("cash_interest")) for r in debt_schedule)
        metrics["covenant_status"] = NOT_APPLICABLE_SINGLE
        metrics["revolver_draw_occurred"] = NOT_APPLICABLE_SINGLE
        metrics["minimum_interest_coverage"] = NOT_APPLICABLE_SINGLE
        metrics["breach_years"] = NOT_APPLICABLE_SINGLE

    return metrics


def summarize_scenario_results(scenario_outputs: dict, base_suitability: dict | None = None) -> dict:
    """Build the comparison summary from per-scenario ``run_lbo`` / attribution
    outputs. Reads Python outputs only; does not recalculate engine math."""
    order = ["base", "upside", "downside"]
    metrics_by_scenario: dict[str, dict[str, Any]] = {}
    statuses: dict[str, dict[str, Any]] = {}

    for key in order:
        scenario = scenario_outputs.get(key) or {}
        status = scenario.get("status", "unavailable")
        if status == "ok":
            metrics_by_scenario[key] = _extract_metrics(scenario, base_suitability)
            statuses[key] = {"status": "ok"}
        else:
            metrics_by_scenario[key] = {}
            statuses[key] = {
                "status": "unavailable",
                "reason": scenario.get("comparison_reason")
                or scenario.get("unavailable_reason")
                or f"{SCENARIO_LABELS.get(key, key)} is unavailable.",
            }

    def cell(key: str, metric_key: str) -> Any:
        if statuses[key]["status"] != "ok":
            return UNAVAILABLE
        value = metrics_by_scenario[key].get(metric_key)
        if value is None:
            return "n/a"
        return value

    rows = []
    for entry in SCENARIO_METRIC_SCHEMA:
        rows.append({
            "key": entry["key"],
            "metric": entry["label"],
            "format": entry["format"],
            "base": cell("base", entry["key"]),
            "upside": cell("upside", entry["key"]),
            "downside": cell("downside", entry["key"]),
        })

    return {
        "metric_schema": copy.deepcopy(SCENARIO_METRIC_SCHEMA),
        "rows": rows,
        "scenario_statuses": statuses,
        "flags": [],
    }


def build_lbo_scenarios(
    base_inputs: dict,
    scenario_config: dict | None = None,
    base_suitability: dict | None = None,
) -> dict:
    """Build Base / Upside / Downside scenario inputs, run each through the
    existing LBO engine, and assemble a comparison summary.

    Pure orchestration layer. No Flask dependency, no file I/O, no provider
    fetch. Does not calculate IRR / MOIC itself and does not mutate
    ``base_inputs``.
    """
    base_inputs = base_inputs or {}
    config = _resolve_config(scenario_config)
    scenario_inputs = generate_scenario_inputs(base_inputs, scenario_config)

    scenarios: dict[str, dict[str, Any]] = {}
    for key in ("base", "upside", "downside"):
        scenarios[key] = _run_one(key, scenario_inputs[key])

    ok_keys = [k for k, v in scenarios.items() if v["status"] == "ok"]
    failed_keys = [k for k, v in scenarios.items() if v["status"] != "ok"]

    disclosures = list(DISCLOSURES_EN)
    notes = {
        "same_transaction_note_en": DISCLOSURE_SAME_TRANSACTION_EN,
        "same_transaction_note_cn": DISCLOSURE_SAME_TRANSACTION_CN,
        "moic_contribution_note_en": MOIC_CONTRIBUTION_NOTE_EN,
        "moic_contribution_note_cn": MOIC_CONTRIBUTION_NOTE_CN,
        "downside_guidance_en": DOWNSIDE_GUIDANCE_EN,
        "downside_guidance_cn": DOWNSIDE_GUIDANCE_CN,
    }

    if not ok_keys:
        return {
            "status": "error",
            "method": METHOD,
            "scenario_config": config,
            "canonical_metric_schema": copy.deepcopy(SCENARIO_METRIC_SCHEMA),
            "scenarios": scenarios,
            "comparison": None,
            "disclosures": disclosures,
            "disclosures_cn": list(DISCLOSURES_CN),
            "notes": notes,
            "flags": [_flag(
                "ALL_SCENARIOS_UNAVAILABLE",
                "No scenario produced valid LBO returns.",
                "error",
            )],
        }

    comparison = summarize_scenario_results(scenarios, base_suitability)

    flags: list[dict[str, str]] = []
    if failed_keys:
        status = "warning"
        for key in failed_keys:
            flags.append(_flag(
                "SCENARIO_UNAVAILABLE",
                scenarios[key].get("unavailable_reason")
                or f"{SCENARIO_LABELS[key]} is unavailable.",
            ))
    else:
        status = "ok"

    return {
        "status": status,
        "method": METHOD,
        "scenario_config": config,
        "canonical_metric_schema": copy.deepcopy(SCENARIO_METRIC_SCHEMA),
        "scenarios": scenarios,
        "comparison": comparison,
        "disclosures": disclosures,
        "disclosures_cn": list(DISCLOSURES_CN),
        "notes": notes,
        "flags": flags,
    }
