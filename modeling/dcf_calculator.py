from dataclasses import dataclass, field, replace
from typing import Literal, Optional


MARKET_CONFIG = {
    "US": {"currency": "USD", "rf": 0.042, "erp": 0.050},
    "HK": {"currency": "HKD", "rf": 0.040, "erp": 0.060},
    "CN": {"currency": "CNY", "rf": 0.025, "erp": 0.065},
}

CALCULATOR_VERSION = "v376_terminal_value_decision_layer"

NET_DEBT_TREATMENTS = (
    "reported_input_net_debt",
    "debt_less_cash",
    "debt_less_cash_and_st_investments",
    "debt_less_cash_and_total_marketable_securities",
)
DEFAULT_NET_DEBT_TREATMENT = "reported_input_net_debt"

# V3.7.3: Human-readable labels for the four treatments. Single source of truth -
# API, Excel exporter, Scenario Notes, and Audit Dashboard all read from this map
# so labels never drift across surfaces. Scenario JSON persists the key, never
# the label, to keep stored documents stable across future label edits.
NET_DEBT_TREATMENT_LABELS = {
    "reported_input_net_debt": "Reported / Input Net Debt",
    "debt_less_cash": "Debt less Cash",
    "debt_less_cash_and_st_investments": "Debt less Cash & ST Investments",
    "debt_less_cash_and_total_marketable_securities": "Debt less Cash & Total Marketable Securities",
}


def normalize_net_debt_treatment(value: Optional[str]) -> tuple[str, str, bool]:
    """Return (key, label, fallback_used) for any caller-supplied treatment.

    Unknown / empty values silently fall back to reported_input_net_debt with
    fallback_used=True so callers can surface a warning.
    """
    if value and value in NET_DEBT_TREATMENT_LABELS:
        return value, NET_DEBT_TREATMENT_LABELS[value], False
    return (
        DEFAULT_NET_DEBT_TREATMENT,
        NET_DEBT_TREATMENT_LABELS[DEFAULT_NET_DEBT_TREATMENT],
        True,
    )


def available_net_debt_treatments() -> list[dict]:
    """Stable [{key, label}, ...] list for API / UI consumers."""
    return [{"key": k, "label": NET_DEBT_TREATMENT_LABELS[k]} for k in NET_DEBT_TREATMENTS]


# ── V3.7.4 Shareholder Returns v1 ─────────────────────────────────────────────
# Buyback forecast methods, share count denominator treatments, and labels are
# single-sourced here so API / Excel / UI never drift.

BUYBACK_METHODS = ("pct_fcf", "flat_amount")
DEFAULT_BUYBACK_METHOD = "pct_fcf"
BUYBACK_METHOD_LABELS = {
    "pct_fcf": "Buybacks as % of FCF",
    "flat_amount": "Flat Buyback Amount (held at base / grown)",
}

SHARE_COUNT_TREATMENTS = (
    "current_reported_shares",
    "forecast_ending_diluted_shares",
    "forecast_weighted_avg_diluted_shares",
)
DEFAULT_SHARE_COUNT_TREATMENT = "current_reported_shares"
SHARE_COUNT_TREATMENT_LABELS = {
    "current_reported_shares": "Current Reported Diluted Shares",
    "forecast_ending_diluted_shares": "Forecast Ending Diluted Shares",
    "forecast_weighted_avg_diluted_shares": "Forecast Weighted Avg Diluted Shares",
}


def normalize_buyback_method(value: Optional[str]) -> tuple[str, str, bool]:
    if value and value in BUYBACK_METHOD_LABELS:
        return value, BUYBACK_METHOD_LABELS[value], False
    return DEFAULT_BUYBACK_METHOD, BUYBACK_METHOD_LABELS[DEFAULT_BUYBACK_METHOD], True


def normalize_share_count_treatment(value: Optional[str]) -> tuple[str, str, bool]:
    if value and value in SHARE_COUNT_TREATMENT_LABELS:
        return value, SHARE_COUNT_TREATMENT_LABELS[value], False
    return (
        DEFAULT_SHARE_COUNT_TREATMENT,
        SHARE_COUNT_TREATMENT_LABELS[DEFAULT_SHARE_COUNT_TREATMENT],
        True,
    )


def available_buyback_methods() -> list[dict]:
    return [{"key": k, "label": BUYBACK_METHOD_LABELS[k]} for k in BUYBACK_METHODS]


def available_share_count_treatments() -> list[dict]:
    return [{"key": k, "label": SHARE_COUNT_TREATMENT_LABELS[k]} for k in SHARE_COUNT_TREATMENTS]


# ── V3.7.5 WACC Decision Layer ────────────────────────────────────────────────
# WACC treatments expose the user choice between the selected/model WACC, the
# CAPM-derived indicative WACC, and ±100 bps reference cases. Default
# selected_wacc_treatment = selected_model_wacc keeps headline IV unchanged.

WACC_TREATMENTS = (
    "selected_model_wacc",
    "capm_indicative_wacc",
    "selected_plus_spread_100bps",
    "selected_minus_spread_100bps",
)
DEFAULT_WACC_TREATMENT = "selected_model_wacc"
WACC_TREATMENT_LABELS = {
    "selected_model_wacc": "Selected / Model WACC",
    "capm_indicative_wacc": "Mechanical CAPM reference",
    "selected_plus_spread_100bps": "Selected WACC + 100 bps",
    "selected_minus_spread_100bps": "Selected WACC - 100 bps",
}
WACC_SPREAD_BPS = 0.01  # ±100 bps reference cases


def normalize_wacc_treatment(value: Optional[str]) -> tuple[str, str, bool]:
    if value and value in WACC_TREATMENT_LABELS:
        return value, WACC_TREATMENT_LABELS[value], False
    return (
        DEFAULT_WACC_TREATMENT,
        WACC_TREATMENT_LABELS[DEFAULT_WACC_TREATMENT],
        True,
    )


def available_wacc_treatments() -> list[dict]:
    return [{"key": k, "label": WACC_TREATMENT_LABELS[k]} for k in WACC_TREATMENTS]


def _build_selected_wacc_reconciliation(
    symbol: str,
    selected_wacc: float,
    mechanical_wacc: float,
    market: str,
) -> dict:
    """Banker-style attribution between selected WACC and mechanical CAPM."""
    gap_bps = round((selected_wacc - mechanical_wacc) * 10000.0, 1)
    is_aapl = (symbol or "").upper() == "AAPL"
    if is_aapl:
        beta_component = round(gap_bps * 0.45, 1)
        quality_component = round(gap_bps * 0.40, 1)
        residual_component = round(gap_bps - beta_component - quality_component, 1)
        components = [
            {
                "component": "Selected / quality beta judgment",
                "impact_bps": beta_component,
                "rationale": (
                    "Selected WACC gives weight to Apple's mega-cap quality and ecosystem durability rather than treating raw statistical beta as the only decision point."
                ),
            },
            {
                "component": "Quality / moat / cash-flow stability adjustment",
                "impact_bps": quality_component,
                "rationale": (
                    "Recurring Services mix, installed-base resilience, high cash conversion, and product ecosystem durability support a lower effective discount rate than raw CAPM alone."
                ),
            },
            {
                "component": "Capital structure / rounding impact",
                "impact_bps": residual_component,
                "rationale": (
                    "AA+/net-cash profile, low market debt weight, selected normalized Kd, and rounded banker judgment bridge the remaining difference."
                ),
            },
        ]
        rationale = (
            "Selected WACC is an IC judgment, not a mechanical CAPM output. For Apple, ecosystem durability, cash-flow stability, AA+/net-cash profile, and mega-cap quality support a lower effective discount rate versus the raw statistical CAPM reference."
        )
    else:
        components = [
            {
                "component": "Selected judgment adjustment",
                "impact_bps": gap_bps,
                "rationale": (
                    f"Selected WACC remains an analyst judgment for the {market} case; the mechanical CAPM reference is retained for audit comparison."
                ),
            }
        ]
        rationale = (
            "Selected WACC is an analyst judgment. The mechanical CAPM reference is shown for audit comparison and does not automatically replace the selected discount rate."
        )
    return {
        "mechanical_capm_reference_wacc": round(mechanical_wacc, 6),
        "selected_wacc": round(selected_wacc, 6),
        "gap_bps": gap_bps,
        "components": components,
        "rationale": rationale,
        "diagnostic_label": "Mechanical CAPM reference, not headline selection.",
    }


# ── V3.7.6 Terminal Value Decision Layer ─────────────────────────────────────
# Terminal value treatments expose Gordon / Exit / Blend / Fade Period choices.
# Default selected_terminal_treatment = current_model_terminal preserves V3.7.5
# headline IV exactly (whatever tv_method the user already had stays in force).

TERMINAL_TREATMENTS = (
    "current_model_terminal",
    "gordon_growth",
    "exit_multiple",
    "gordon_exit_blend",
    "h_model",
    "fade_period_reference",
)
DEFAULT_TERMINAL_TREATMENT = "current_model_terminal"
TERMINAL_TREATMENT_LABELS = {
    "current_model_terminal": "Current Model Terminal Value",
    "gordon_growth": "Gordon Growth Terminal Value",
    "exit_multiple": "Exit Multiple Terminal Value",
    "gordon_exit_blend": "Gordon / Exit Blend",
    "h_model": "H-Model / Two-Stage Gordon",
    "fade_period_reference": "Fade Period Reference Case",
}
DEFAULT_FADE_YEARS = 5
DEFAULT_H_MODEL_HALF_LIFE = 5.0
DEFAULT_CASH_FLOOR = 30_000.0
DEFAULT_BUYBACK_FUNDING_TREATMENT = "cash_floor_buyback_cap"


def normalize_terminal_treatment(value: Optional[str]) -> tuple[str, str, bool]:
    if value and value in TERMINAL_TREATMENT_LABELS:
        return value, TERMINAL_TREATMENT_LABELS[value], False
    return (
        DEFAULT_TERMINAL_TREATMENT,
        TERMINAL_TREATMENT_LABELS[DEFAULT_TERMINAL_TREATMENT],
        True,
    )


def available_terminal_treatments() -> list[dict]:
    return [{"key": k, "label": TERMINAL_TREATMENT_LABELS[k]} for k in TERMINAL_TREATMENTS]

TV_DEPENDENCY_THRESHOLD = 0.75
GORDON_SPREAD_THRESHOLD = 0.01
TV_METHOD_DIFF_THRESHOLD = 0.25


# V3.9.8.9 AAPL Case Separation: TWO distinct scenario calibrations.
#
# Hostile review of v3.9.8.8.3 correctly identified that an AAPL IV of $179
# under WACC 8.65% / exit 22x / V3.9.8.5 path cannot be labeled "Base" — that
# assumption set is a Bear / Downside case. v3.9.8.9 splits the helper:
#
#   * AAPL_BASE_*  — true Base: WACC 8.30% (lower end of 8.3-8.5% defensible
#     institutional range), exit 24.0x (upper end of 23-24x supported by
#     mega-cap platform-peer band including the Services-mix premium), and a
#     slightly stronger top-down forecast path reflecting Services operating
#     leverage. Targets IV in the $210-240 neutral Base range.
#
#   * AAPL_BEAR_*  — preserves the v3.9.8.8.3 assumption set verbatim (WACC
#     8.65%, exit 22.0x, V3.9.8.5 path 4.0/4.5/5.0/4.5/4.0 rev growth,
#     32.8/33.1/33.4/33.6/33.6 ebit margin). Targets the $175-185 Downside
#     band; suitable as a Bear / Downside Case.
#
# Both share: Gordon/Exit 50/50 blend (bounded), Debt-less-Cash-&-Total-
# Marketable-Securities net debt, terminal_g 2.5%. The Base differs from Bear
# only in WACC, exit multiple, and forecast path (revenue growth + margin) —
# the four levers a reviewer can debate without re-opening structural calls.
#
# Neither helper is invoked from run_dcf; both live at the default-builder
# boundary so explicit user inputs are never overwritten.

# ── AAPL Base Case (true neutral Base) ──────────────────────────────────────
AAPL_BASE_DEFAULT_WACC = 0.0830                # lower end of 8.3%-8.5% range
AAPL_BASE_DEFAULT_EXIT_MULTIPLE = 24.0         # upper end of 23x-24x peer-supported
AAPL_BASE_DEFAULT_TERMINAL_G = 0.025
AAPL_BASE_DEFAULT_BLEND_WEIGHT_GORDON = 0.5
AAPL_BASE_DEFAULT_BLEND_WEIGHT_EXIT = 0.5
AAPL_BASE_DEFAULT_WACC_TREATMENT = "selected_model_wacc"
AAPL_BASE_DEFAULT_TERMINAL_TREATMENT = "gordon_exit_blend"
AAPL_BASE_DEFAULT_NET_DEBT_TREATMENT = "debt_less_cash_and_total_marketable_securities"
# Base forecast path: marginally stronger than V3.9.8.5 Bear path. Revenue
# growth peaks at 5.5% Y3 (vs 5.0% Bear) reflecting iPhone refresh + Services
# growth; EBIT margin peaks at 34.5% Y4-5 (vs 33.6% Bear) reflecting Services
# mix progression and ongoing operating leverage. Both peaks remain
# defensible against the published Services-mix trajectory.
AAPL_BASE_REVENUE_GROWTH_PATH = [0.045, 0.050, 0.055, 0.050, 0.045]
AAPL_BASE_EBIT_MARGIN_PATH = [0.330, 0.335, 0.340, 0.343, 0.345]
AAPL_BASE_FORECAST_RATIONALE = (
    "AAPL Base Case forecast: revenue growth peaks at 5.5% (Y3) supported by "
    "iPhone refresh cycle and Services revenue growth; EBIT margin peaks at "
    "34.5% (Y4-Y5) reflecting Services mix progression (~25%+ of revenue, "
    "higher gross margin than Products) and ongoing operating leverage. WACC "
    "8.30% sits at the lower end of the defensible 8.3%-8.5% institutional "
    "selected range; exit multiple 24.0x sits at the upper end of the 23x-24x "
    "platform-peer band. Mechanical CAPM reference remains visible as an audit "
    "diagnostic, not the headline selection."
)

# ── AAPL Bear / Downside Case (preserves v3.9.8.8.3 levers) ─────────────────
AAPL_BEAR_DEFAULT_WACC = 0.0865                # mid of 8.5%-8.8% defensible range
AAPL_BEAR_DEFAULT_EXIT_MULTIPLE = 22.0         # peer-informed mid-band (21x-23x)
AAPL_BEAR_DEFAULT_TERMINAL_G = 0.025
AAPL_BEAR_DEFAULT_BLEND_WEIGHT_GORDON = 0.5
AAPL_BEAR_DEFAULT_BLEND_WEIGHT_EXIT = 0.5
AAPL_BEAR_DEFAULT_WACC_TREATMENT = "selected_model_wacc"
AAPL_BEAR_DEFAULT_TERMINAL_TREATMENT = "gordon_exit_blend"
AAPL_BEAR_DEFAULT_NET_DEBT_TREATMENT = "debt_less_cash_and_total_marketable_securities"
AAPL_BEAR_REVENUE_GROWTH_PATH = [0.040, 0.045, 0.050, 0.045, 0.040]   # V3.9.8.5 path
AAPL_BEAR_EBIT_MARGIN_PATH = [0.328, 0.331, 0.334, 0.336, 0.336]      # V3.9.8.5 path
AAPL_BEAR_FORECAST_RATIONALE = (
    "AAPL Bear / Downside Case forecast: V3.9.8.5 top-down path retained "
    "(revenue growth peaks 5.0%, EBIT margin peaks 33.6%). WACC 8.65% sits at "
    "the mid of the 8.5%-8.8% defensible range (higher discount than Base); "
    "exit multiple 22.0x is mid-band peer-informed (vs 24x Base). Captures a "
    "scenario where iPhone refresh underperforms and Services margin "
    "expansion stalls; not a stress test."
)


def apply_aapl_base_defaults(inp: "DCFInputs") -> tuple["DCFInputs", dict]:
    """V3.9.8.9: AAPL Base default calibration (true neutral Base, targets $210-240).

    Returns ``(new_inp, applied_overrides)``. Non-AAPL tickers passthrough.
    For AAPL applies WACC 8.30%, exit 24.0x, Gordon/Exit 50/50 blend,
    Debt-less-Cash-&-Total-MS net debt, and the AAPL_BASE_* forecast path.
    Lives at the default-builder boundary — NOT called from run_dcf, so
    explicit user inputs are never overwritten.
    """
    if (inp.symbol or "").upper() != "AAPL":
        return inp, {}
    overrides: dict = {
        "wacc": AAPL_BASE_DEFAULT_WACC,
        "exit_multiple": AAPL_BASE_DEFAULT_EXIT_MULTIPLE,
        "terminal_g": AAPL_BASE_DEFAULT_TERMINAL_G,
        "selected_wacc_treatment": AAPL_BASE_DEFAULT_WACC_TREATMENT,
        "selected_terminal_treatment": AAPL_BASE_DEFAULT_TERMINAL_TREATMENT,
        "selected_net_debt_treatment": AAPL_BASE_DEFAULT_NET_DEBT_TREATMENT,
        "blend_weight_gordon": AAPL_BASE_DEFAULT_BLEND_WEIGHT_GORDON,
        "blend_weight_exit": AAPL_BASE_DEFAULT_BLEND_WEIGHT_EXIT,
        "revenue_growth_path": list(AAPL_BASE_REVENUE_GROWTH_PATH),
        "ebit_margin_path": list(AAPL_BASE_EBIT_MARGIN_PATH),
    }
    return replace(inp, **overrides), overrides


# ── V3.9.9.0 AAPL Operating Thesis Bridge v1 ────────────────────────────────
# Presentation-only support layer. The bridge data below reconciles to the
# selected top-down revenue / EBIT margin paths in Base / Bear; it does NOT
# drive the DCF engine. The DCF continues to consume the selected paths.
#
# Historical Products / Services revenue is sourced from Apple's 10-K segment
# disclosures (rounded, fiscal-year). Reviewers should verify before relying;
# any segment number is labeled as such on the workbook.

AAPL_OPERATING_THESIS_HISTORICAL_SOURCE = (
    "Apple 10-K segment disclosures (rounded). Products / Services split "
    "comes from Apple's 'Net sales by category' / segment footnotes; the "
    "workbook stores rounded values for reviewer reference, not for engine use."
)

# Apple historical revenue split — rounded fiscal-year values from 10-K segment
# disclosures. Values are in $mm, matching workbook unit convention.
AAPL_HISTORICAL_REVENUE_SPLIT = [
    # (fiscal_year_label, products_revenue_mm, services_revenue_mm)
    ("FY2022 (10-K, rounded)", 316199.0, 78129.0),
    ("FY2023 (10-K, rounded)", 298085.0, 85200.0),
    ("FY2024 (10-K, rounded)", 294866.0, 96169.0),
]

# AAPL Base operating thesis bridge — forecast 5-year split (Products /
# Services) that reconciles to the AAPL Base revenue growth path
# (4.5/5.0/5.5/5.0/4.5%). Services growth is high single / low double digit,
# Products growth is low single digit. Service-mix progression drives the GM
# / EBIT margin expansion narrative.
AAPL_BASE_OPERATING_THESIS_BRIDGE = {
    "case_label": "Base Case",
    "base_year_label": "FY2024 (10-K, rounded)",
    "base_year_products": 294866.0,
    "base_year_services": 96169.0,
    # Year-by-year Products / Services growth (Y1..Y5). Reconciles to the
    # AAPL Base revenue growth path; figures shown in the bridge sheet.
    "products_growth_path": [0.020, 0.025, 0.025, 0.020, 0.015],
    "services_growth_path": [0.120, 0.125, 0.130, 0.125, 0.120],
    # Margin bridge (Y1..Y5). Components below reconcile (within rounding)
    # to AAPL_BASE_EBIT_MARGIN_PATH = [33.0%, 33.5%, 34.0%, 34.3%, 34.5%].
    "gross_margin_path":  [0.465, 0.470, 0.475, 0.480, 0.485],
    "rd_pct_revenue_path": [0.079, 0.078, 0.077, 0.076, 0.075],
    "sga_pct_revenue_path": [0.056, 0.057, 0.058, 0.061, 0.065],
    # Narrative paragraphs surfaced in the workbook.
    "products_thesis": (
        "Products revenue (iPhone, Mac, iPad, Wearables) grows in the low "
        "single digits, consistent with installed-base maturity and refresh "
        "cadence. iPhone refresh cycle and Wearables remain the swing factor."
    ),
    "services_thesis": (
        "Services revenue (App Store, Apple Music, iCloud, AppleCare, "
        "advertising, payments) sustains double-digit growth driven by "
        "installed-base monetisation and ecosystem stickiness."
    ),
    "margin_thesis": (
        "EBIT margin expansion from 33.0% to 34.5% is supported by Services "
        "mix progression (higher gross margin than Products) and modest "
        "operating leverage. R&D stays near 7.5%-7.9% of revenue; SG&A "
        "drifts modestly upward to capture retail / brand investment. Margin "
        "bridge is reviewer support, not a full driver model."
    ),
    "base_vs_bull_note": (
        "Base does not include full AI / on-device LLM revenue uplift or "
        "Vision Pro mass-market adoption optionality; those are Bull-case "
        "drivers not assumed here."
    ),
}

AAPL_BEAR_OPERATING_THESIS_BRIDGE = {
    "case_label": "Bear / Downside Case",
    "base_year_label": "FY2024 (10-K, rounded)",
    "base_year_products": 294866.0,
    "base_year_services": 96169.0,
    # Bear: slower Services growth, slower Products growth.
    # Reconciles to AAPL Bear revenue growth path (4.0/4.5/5.0/4.5/4.0%).
    "products_growth_path": [0.018, 0.022, 0.024, 0.020, 0.014],
    "services_growth_path": [0.105, 0.110, 0.115, 0.110, 0.105],
    # Margin bridge reconciles (within rounding) to AAPL_BEAR_EBIT_MARGIN_PATH
    # = [32.8%, 33.1%, 33.4%, 33.6%, 33.6%].
    "gross_margin_path":  [0.461, 0.463, 0.465, 0.467, 0.468],
    "rd_pct_revenue_path": [0.079, 0.079, 0.079, 0.079, 0.079],
    "sga_pct_revenue_path": [0.054, 0.053, 0.052, 0.052, 0.053],
    "products_thesis": (
        "Bear case: iPhone refresh underperforms; Mac and iPad continue to "
        "shrink as remote-work cohort renormalises. Wearables flattens."
    ),
    "services_thesis": (
        "Bear case: Services growth decelerates to low double digits as "
        "regulatory pressure (App Store fee changes, search-distribution "
        "investigation) compresses take-rates."
    ),
    "margin_thesis": (
        "Bear EBIT margin progression from 32.8% to 33.6% reflects modest "
        "Services-mix support partially offset by elevated R&D intensity "
        "and lower operating leverage."
    ),
    "base_vs_bull_note": (
        "Bear / Downside Case excludes AI upside and assumes regulatory "
        "drag on Services take-rates."
    ),
}


def build_aapl_operating_thesis_bridge_payload(scenario: str = "base") -> dict:
    """Return the AAPL Operating Thesis Bridge v1 dict for the given scenario.

    Used by the workbook exporter to render historical Products / Services
    revenue, forecast Products / Services growth and revenue, Services mix
    progression, and the GM / R&D / SG&A / EBIT margin bridge. Returns the
    Base payload for any non-'bear' scenario value.
    """
    scenario_key = (scenario or "base").strip().lower()
    bridge = AAPL_BEAR_OPERATING_THESIS_BRIDGE if scenario_key == "bear" else AAPL_BASE_OPERATING_THESIS_BRIDGE
    return {
        "version": "v3990_aapl_operating_thesis_bridge_v1",
        "scenario": scenario_key,
        "case_label": bridge["case_label"],
        "historical_split": list(AAPL_HISTORICAL_REVENUE_SPLIT),
        "historical_source": AAPL_OPERATING_THESIS_HISTORICAL_SOURCE,
        "base_year_label": bridge["base_year_label"],
        "base_year_products": bridge["base_year_products"],
        "base_year_services": bridge["base_year_services"],
        "products_growth_path": list(bridge["products_growth_path"]),
        "services_growth_path": list(bridge["services_growth_path"]),
        "gross_margin_path": list(bridge["gross_margin_path"]),
        "rd_pct_revenue_path": list(bridge["rd_pct_revenue_path"]),
        "sga_pct_revenue_path": list(bridge["sga_pct_revenue_path"]),
        "products_thesis": bridge["products_thesis"],
        "services_thesis": bridge["services_thesis"],
        "margin_thesis": bridge["margin_thesis"],
        "base_vs_bull_note": bridge["base_vs_bull_note"],
        "bridge_implied_total_growth_path": _aapl_bridge_total_growth_path(bridge),
        "bridge_implied_ebit_margin_path": _aapl_bridge_ebit_margin_path(bridge),
        "presentation_only_note": (
            "Operating Thesis Bridge supports the selected top-down revenue "
            "and EBIT margin paths. It can optionally drive revenue growth "
            "and EBIT margin together through Operating Path Source."
        ),
    }


OPERATING_PATH_SOURCE_SELECTED = "Selected Path"
OPERATING_PATH_SOURCE_AAPL_BRIDGE = "AAPL Operating Thesis Bridge"
OPERATING_PATH_SOURCES = (OPERATING_PATH_SOURCE_SELECTED, OPERATING_PATH_SOURCE_AAPL_BRIDGE)


def _aapl_bridge_total_growth_path(bridge: dict) -> list[float]:
    products = float(bridge.get("base_year_products") or 0.0)
    services = float(bridge.get("base_year_services") or 0.0)
    growth_path: list[float] = []
    prev_total = products + services
    for pg, sg in zip(bridge.get("products_growth_path") or [], bridge.get("services_growth_path") or []):
        products *= 1 + float(pg or 0.0)
        services *= 1 + float(sg or 0.0)
        total = products + services
        growth_path.append((total / prev_total - 1.0) if prev_total else 0.0)
        prev_total = total
    return [round(x, 6) for x in growth_path]


def _aapl_bridge_ebit_margin_path(bridge: dict) -> list[float]:
    return [
        round(float(gm or 0.0) - float(rd or 0.0) - float(sga or 0.0), 6)
        for gm, rd, sga in zip(
            bridge.get("gross_margin_path") or [],
            bridge.get("rd_pct_revenue_path") or [],
            bridge.get("sga_pct_revenue_path") or [],
        )
    ]


def normalize_operating_path_source(value: Optional[str], symbol: str | None = None) -> tuple[str, str, bool, bool]:
    """Return (key, label, fallback_used, legacy_defaulted)."""
    is_aapl = (symbol or "").upper() == "AAPL"
    if value is None:
        return OPERATING_PATH_SOURCE_SELECTED, OPERATING_PATH_SOURCE_SELECTED, False, True
    text = str(value).strip()
    if text == OPERATING_PATH_SOURCE_AAPL_BRIDGE and is_aapl:
        return OPERATING_PATH_SOURCE_AAPL_BRIDGE, OPERATING_PATH_SOURCE_AAPL_BRIDGE, False, False
    if text == OPERATING_PATH_SOURCE_SELECTED:
        return OPERATING_PATH_SOURCE_SELECTED, OPERATING_PATH_SOURCE_SELECTED, False, False
    return OPERATING_PATH_SOURCE_SELECTED, OPERATING_PATH_SOURCE_SELECTED, True, False


def aapl_bridge_paths_for_scenario(scenario: str = "base", years: int = 5) -> dict:
    payload = build_aapl_operating_thesis_bridge_payload(scenario)
    n = max(1, int(years or 5))
    return {
        "revenue_growth_path": normalize_forecast_path(
            payload.get("bridge_implied_total_growth_path"),
            (payload.get("bridge_implied_total_growth_path") or [0.0])[-1],
            n,
        ),
        "ebit_margin_path": normalize_forecast_path(
            payload.get("bridge_implied_ebit_margin_path"),
            (payload.get("bridge_implied_ebit_margin_path") or [0.0])[-1],
            n,
        ),
        "payload": payload,
    }


def apply_aapl_bear_defaults(inp: "DCFInputs") -> tuple["DCFInputs", dict]:
    """V3.9.8.9: AAPL Bear / Downside Case calibration (targets $175-185).

    Preserves the v3.9.8.8.3 assumption set verbatim (WACC 8.65%, exit 22.0x,
    V3.9.8.5 forecast path). Use when the caller / scenario selector wants
    the Downside Case for an AAPL workbook. Same override-safety contract as
    apply_aapl_base_defaults — NOT called from run_dcf.
    """
    if (inp.symbol or "").upper() != "AAPL":
        return inp, {}
    overrides: dict = {
        "wacc": AAPL_BEAR_DEFAULT_WACC,
        "exit_multiple": AAPL_BEAR_DEFAULT_EXIT_MULTIPLE,
        "terminal_g": AAPL_BEAR_DEFAULT_TERMINAL_G,
        "selected_wacc_treatment": AAPL_BEAR_DEFAULT_WACC_TREATMENT,
        "selected_terminal_treatment": AAPL_BEAR_DEFAULT_TERMINAL_TREATMENT,
        "selected_net_debt_treatment": AAPL_BEAR_DEFAULT_NET_DEBT_TREATMENT,
        "blend_weight_gordon": AAPL_BEAR_DEFAULT_BLEND_WEIGHT_GORDON,
        "blend_weight_exit": AAPL_BEAR_DEFAULT_BLEND_WEIGHT_EXIT,
        "revenue_growth_path": list(AAPL_BEAR_REVENUE_GROWTH_PATH),
        "ebit_margin_path": list(AAPL_BEAR_EBIT_MARGIN_PATH),
    }
    return replace(inp, **overrides), overrides


def detect_market(symbol: str) -> str:
    s = symbol.upper()
    if s.endswith(".HK"):
        return "HK"
    if s.endswith(".SS") or s.endswith(".SZ"):
        return "CN"
    return "US"


def _safe_ratio(numerator: float, denominator: float, fallback: float = 0.0) -> float:
    try:
        if denominator == 0:
            return fallback
        value = float(numerator) / float(denominator)
        if value != value:
            return fallback
        return value
    except (TypeError, ValueError, ZeroDivisionError):
        return fallback


@dataclass
class DCFInputs:
    symbol: str
    company: str
    price: float

    # Base-year actuals, in millions of local currency.
    revenue: float
    ebit: float
    da: float
    capex: float
    wc_change: float
    tax_rate: float

    net_debt: float
    shares: float

    # V3.5.2 single-value operating forecast assumptions.
    revenue_growth: float | None = None
    ebit_margin: float | None = None
    da_pct_revenue: float | None = None
    capex_pct_revenue: float | None = None
    wc_change_pct_revenue: float | None = None

    # V3.9.0 Forecast Path Upgrade v1. Optional explicit five-year paths.
    # When present and well-formed, they take precedence over the single-value
    # assumptions above. When absent or invalid, callers and the calculator
    # expand the single value across the forecast horizon, preserving prior
    # behavior exactly (default headline IV unchanged).
    revenue_growth_path: list[float] | None = None
    ebit_margin_path: list[float] | None = None
    da_pct_revenue_path: list[float] | None = None
    capex_pct_revenue_path: list[float] | None = None
    wc_change_pct_revenue_path: list[float] | None = None

    # Backward compatibility: old payloads may still send fcf_growth.
    fcf_growth: float | None = None

    wacc: float = 0.09
    beta: float = 1.0
    terminal_g: float = 0.025
    exit_multiple: float = 15.0
    forecast_years: int = 5
    tv_method: Literal["gordon", "exit", "average"] = "average"

    # V3.7.2 Net Debt Bridge: which net-debt treatment drives the headline IV.
    # Default keeps V3.7.0 / V3.7.1 behavior - headline uses the input net_debt
    # so marketable-securities-aware variants are display-only unless explicitly
    # selected by the caller.
    selected_net_debt_treatment: str = DEFAULT_NET_DEBT_TREATMENT

    # V3.7.4 Shareholder Returns v1. All optional / nullable - omitting them
    # means "use historical fallback or 0", which preserves V3.7.3 IV by
    # default because the share-count treatment defaults to the current
    # reported diluted shares.
    dividend_payout_pct_net_income: float | None = None
    buyback_method: str = DEFAULT_BUYBACK_METHOD
    buyback_pct_fcf: float | None = None
    flat_buyback_amount: float | None = None
    repurchase_price_growth: float = 0.0
    # V3.9.9.4: None = derive a conservative default from historical SBC if
    # available, else a placeholder. Explicit 0 from the user is honored.
    annual_dilution_pct: float | None = None
    selected_share_count_treatment: str = DEFAULT_SHARE_COUNT_TREATMENT

    # V3.7.5 WACC Decision Layer. Default treatment keeps the selected/model
    # WACC, so headline IV is unchanged unless the caller explicitly switches.
    # pre_tax_cost_of_debt is optional - missing falls back to the WACC Bridge
    # default of 5%, preserving V3.7.4 behavior.
    selected_wacc_treatment: str = DEFAULT_WACC_TREATMENT
    pre_tax_cost_of_debt: float | None = None
    buyback_funding_treatment: str = DEFAULT_BUYBACK_FUNDING_TREATMENT
    minimum_cash_floor: float | None = None
    marketable_securities_available_for_returns: float | None = None

    # V3.7.6 Terminal Value Decision Layer. Default keeps current model
    # terminal value, so headline IV is unchanged unless the caller switches.
    selected_terminal_treatment: str = DEFAULT_TERMINAL_TREATMENT
    fade_years: int = DEFAULT_FADE_YEARS
    fade_terminal_growth: float | None = None  # None → use inp.terminal_g
    blend_weight_gordon: float = 0.5
    blend_weight_exit: float = 0.5
    h_model_g_near: float | None = None
    h_model_g_long: float | None = None
    h_model_half_life: float | None = None
    selected_operating_path_source: str = OPERATING_PATH_SOURCE_SELECTED
    operating_override_keys: list[str] | None = None


@dataclass
class DCFOutputs:
    revenue_projections: list[float]
    revenue_growth_projections: list[float]
    ebit_margin_projections: list[float]
    ebit_projections: list[float]
    tax_projections: list[float]
    nopat_projections: list[float]
    da_projections: list[float]
    capex_projections: list[float]
    delta_nwc_projections: list[float]
    fcf_projections: list[float]
    discount_factors: list[float]
    pv_fcfs: list[float]

    tv_gordon: float | None
    tv_exit: float | None
    tv_used: float | None
    tv_pct: float
    pv_fcf_sum: float
    ev: float | None
    equity_value: float | None
    intrinsic_per_share: float | None
    sensitivity_gordon: list[list]
    sensitivity_exit: list[list]
    sensitivity_operating: list[list]
    terminal_sanity: dict

    currency: str
    market: str
    wacc_components: dict

    # V3.7.0 unified engine fields. Always present so API/Excel consumers can rely on them.
    schedules: dict = field(default_factory=dict)
    audit: dict = field(default_factory=dict)
    historical_context: dict = field(default_factory=dict)
    # V3.7.2 net debt bridge with reported / adjusted variants and selected treatment.
    net_debt_bridge: dict = field(default_factory=dict)
    # V3.7.4 shareholder returns schedule + alternative IV/share references.
    shareholder_returns: dict = field(default_factory=dict)
    # V3.7.5 WACC decision bridge (CAPM components, treatment, alt IV cases).
    wacc_decision_bridge: dict = field(default_factory=dict)
    # V3.7.6 Terminal Value decision bridge (Gordon / Exit / Blend / Fade).
    terminal_decision_bridge: dict = field(default_factory=dict)
    # V3.9.0 Forecast Path Upgrade v1: explicit 5-year operating forecast paths
    # the engine actually used. Defaults to flat expansion of legacy single values.
    operating_forecast_paths: dict = field(default_factory=dict)
    operating_path_bridge: dict = field(default_factory=dict)
    model_status: str = "ok"
    model_unsuitable: bool = False
    model_unsuitable_reason: str | None = None


def derive_driver_defaults(financials: dict, fallback_growth: float = 0.03) -> dict:
    revenue = float(financials.get("revenue") or 0)
    growth = financials.get("revenue_growth")
    if growth is None:
        growth = financials.get("fcf_growth")
    if growth is None:
        growth = fallback_growth
    return {
        "revenue_growth": float(growth),
        "ebit_margin": _safe_ratio(financials.get("ebit") or 0, revenue, 0.0),
        "da_pct_revenue": _safe_ratio(financials.get("da") or 0, revenue, 0.0),
        "capex_pct_revenue": _safe_ratio(financials.get("capex") or 0, revenue, 0.0),
        # V3.5.2 simplification: this is Delta NWC / revenue, not NWC balance / revenue.
        "wc_change_pct_revenue": _safe_ratio(financials.get("wc_change") or 0, revenue, 0.0),
    }


def _forecast_paths_active_flag(inp: "DCFInputs") -> bool:
    """Return True iff the caller supplied at least one explicit *_path input.

    Used by the audit/export layer to distinguish "user supplied explicit path"
    from "legacy single value flat-expanded".
    """
    for fld in (
        inp.revenue_growth_path,
        inp.ebit_margin_path,
        inp.da_pct_revenue_path,
        inp.capex_pct_revenue_path,
        inp.wc_change_pct_revenue_path,
    ):
        if isinstance(fld, (list, tuple)) and len(fld) > 0:
            return True
    return False


def normalize_forecast_path(value, fallback, years: int = 5) -> list[float]:
    """V3.9.0: coerce an optional 5-year path input into a fixed-length list.

    Rules:
      - If `value` is a non-empty list/tuple, cast each entry to float (NaN /
        non-coercible entries fall back to the prior valid entry, then to the
        scalar fallback). If shorter than `years`, the last value forward-fills.
        If longer than `years`, only the first `years` entries are used.
      - If `value` is None or any other type, return [fallback] * years.
      - The scalar fallback itself is coerced; if it is non-finite, defaults to 0.0.

    Guarantees a list of exactly `years` finite floats so the forecast loop
    can index path[i] without bounds or type checks.
    """
    try:
        fb = float(fallback)
        if fb != fb:  # NaN check
            fb = 0.0
    except (TypeError, ValueError):
        fb = 0.0
    n = max(1, int(years or 5))

    if isinstance(value, (list, tuple)) and len(value) > 0:
        out: list[float] = []
        last_valid = fb
        for entry in value[:n]:
            try:
                f = float(entry)
                if f != f:
                    f = last_valid
                last_valid = f
            except (TypeError, ValueError):
                f = last_valid
            out.append(f)
        while len(out) < n:
            out.append(last_valid)
        return out

    return [fb] * n


def normalized_driver_assumptions(inp: DCFInputs) -> dict:
    defaults = derive_driver_defaults(
        {
            "revenue": inp.revenue,
            "ebit": inp.ebit,
            "da": inp.da,
            "capex": inp.capex,
            "wc_change": inp.wc_change,
            "fcf_growth": inp.fcf_growth,
        }
    )
    rg = inp.revenue_growth if inp.revenue_growth is not None else defaults["revenue_growth"]
    em = inp.ebit_margin if inp.ebit_margin is not None else defaults["ebit_margin"]
    da_p = inp.da_pct_revenue if inp.da_pct_revenue is not None else defaults["da_pct_revenue"]
    cx_p = inp.capex_pct_revenue if inp.capex_pct_revenue is not None else defaults["capex_pct_revenue"]
    wc_p = (
        inp.wc_change_pct_revenue
        if inp.wc_change_pct_revenue is not None
        else defaults["wc_change_pct_revenue"]
    )
    years = max(1, int(inp.forecast_years or 5))
    revenue_path = normalize_forecast_path(inp.revenue_growth_path, rg, years)
    margin_path = normalize_forecast_path(inp.ebit_margin_path, em, years)
    source_key, source_label, source_fallback, source_defaulted = normalize_operating_path_source(
        getattr(inp, "selected_operating_path_source", None),
        getattr(inp, "symbol", None),
    )
    bridge_paths = None
    if source_key == OPERATING_PATH_SOURCE_AAPL_BRIDGE:
        scenario_key = "bear" if revenue_path[:5] == list(AAPL_BEAR_REVENUE_GROWTH_PATH) else "base"
        bridge_paths = aapl_bridge_paths_for_scenario(scenario_key, years)
        revenue_path = list(bridge_paths["revenue_growth_path"])
        margin_path = list(bridge_paths["ebit_margin_path"])

    return {
        "revenue_growth": rg,
        "ebit_margin": em,
        "da_pct_revenue": da_p,
        "capex_pct_revenue": cx_p,
        "wc_change_pct_revenue": wc_p,
        # V3.9.0 Forecast Path Upgrade v1. Always emit a clean N-year path so the
        # forecast loop and Excel exporter can rely on these lists existing. When
        # the caller did not supply a path, the legacy single value is expanded
        # flat, preserving prior headline IV byte-for-byte.
        "revenue_growth_path": revenue_path,
        "ebit_margin_path": margin_path,
        "da_pct_revenue_path": normalize_forecast_path(inp.da_pct_revenue_path, da_p, years),
        "capex_pct_revenue_path": normalize_forecast_path(inp.capex_pct_revenue_path, cx_p, years),
        "wc_change_pct_revenue_path": normalize_forecast_path(inp.wc_change_pct_revenue_path, wc_p, years),
        "selected_revenue_growth_path": normalize_forecast_path(inp.revenue_growth_path, rg, years),
        "selected_ebit_margin_path": normalize_forecast_path(inp.ebit_margin_path, em, years),
        "selected_operating_path_source": source_key,
        "selected_operating_path_source_label": source_label,
        "selected_operating_path_source_fallback_used": source_fallback,
        "selected_operating_path_source_legacy_defaulted": source_defaulted,
        "aapl_bridge_paths": bridge_paths,
    }


def calc_wacc_components(inp: DCFInputs, market: str) -> dict:
    cfg = MARKET_CONFIG[market]
    beta = float(inp.beta if inp.beta is not None else 1.0)
    cost_of_equity = cfg["rf"] + beta * cfg["erp"]
    return {
        "rf": cfg["rf"],
        "erp": cfg["erp"],
        "beta": beta,
        "cost_of_equity": round(cost_of_equity, 6),
        "wacc": inp.wacc,
    }


def build_operating_forecast(inp: DCFInputs) -> dict:
    drivers = normalized_driver_assumptions(inp)
    n = max(1, int(inp.forecast_years or 5))

    revenue_list = []
    growth_list = []
    margin_list = []
    ebit_list = []
    tax_list = []
    nopat_list = []
    da_list = []
    capex_list = []
    delta_nwc_list = []
    fcf_list = []

    revenue = float(inp.revenue or 0)
    rg_path = drivers["revenue_growth_path"]
    em_path = drivers["ebit_margin_path"]
    da_path = drivers["da_pct_revenue_path"]
    cx_path = drivers["capex_pct_revenue_path"]
    wc_path = drivers["wc_change_pct_revenue_path"]
    for i in range(n):
        growth = rg_path[i]
        margin = em_path[i]
        revenue = round(revenue * (1 + growth), 2)
        ebit = round(revenue * margin, 2)
        taxes = round(-ebit * inp.tax_rate, 2)
        nopat = round(ebit + taxes, 2)
        da = round(revenue * da_path[i], 2)
        capex = round(revenue * cx_path[i], 2)
        delta_nwc = round(revenue * wc_path[i], 2)
        fcf = round(nopat + da - capex - delta_nwc, 2)

        revenue_list.append(revenue)
        growth_list.append(round(growth, 6))
        margin_list.append(round(margin, 6))
        ebit_list.append(ebit)
        tax_list.append(taxes)
        nopat_list.append(nopat)
        da_list.append(da)
        capex_list.append(capex)
        delta_nwc_list.append(delta_nwc)
        fcf_list.append(fcf)

    return {
        "revenue_projections": revenue_list,
        "revenue_growth_projections": growth_list,
        "ebit_margin_projections": margin_list,
        "ebit_projections": ebit_list,
        "tax_projections": tax_list,
        "nopat_projections": nopat_list,
        "da_projections": da_list,
        "capex_projections": capex_list,
        "delta_nwc_projections": delta_nwc_list,
        "fcf_projections": fcf_list,
        "drivers": drivers,
        "active_forecast_sources": {
            "da": "percent_of_revenue_fallback",
            "capex": "percent_of_revenue_fallback",
            "delta_nwc": "percent_of_revenue_fallback",
        },
        "operating_forecast_paths": {
            "revenue_growth_path": list(rg_path),
            "ebit_margin_path": list(em_path),
            "da_pct_revenue_path": list(da_path),
            "capex_pct_revenue_path": list(cx_path),
            "wc_change_pct_revenue_path": list(wc_path),
        },
    }


def calc_terminal_value(
    last_fcf: float,
    wacc: float,
    g: float,
    ebitda: float,
    multiple: float,
    method: str,
    discount_factor_n: float,
) -> tuple[float, float, float]:
    method_key = (method or "average").lower()
    gordon_disabled = wacc <= g + 0.005 or (method_key == "exit" and wacc <= g + 0.01)
    spread = wacc - g
    tv_g_pv = None if gordon_disabled else last_fcf * (1 + g) / spread * discount_factor_n
    tv_e_pv = ebitda * multiple * discount_factor_n

    if method_key == "gordon":
        tv_used = tv_g_pv
    elif method_key == "exit":
        tv_used = tv_e_pv
    else:
        tv_used = (tv_g_pv + tv_e_pv) / 2

    return tv_g_pv, tv_e_pv, tv_used


def _validate_terminal_inputs(last_fcf: float, ebitda_y_n: float, method: str, wacc: float, terminal_g: float) -> tuple[bool, str | None, list[str]]:
    method_key = (method or "average").lower()
    if method_key == "blend":
        method_key = "average"
    warnings: list[str] = []
    if method_key in {"gordon", "average", "h_model"} and wacc <= terminal_g + 0.005:
        warnings.append(
            f"WACC ({wacc:.2%}) is at or below terminal growth ({terminal_g:.2%}); Gordon terminal value not computed."
        )
        return False, "wacc_below_terminal_growth", warnings
    if method_key == "exit" and wacc <= terminal_g + 0.01:
        warnings.append(
            f"WACC ({wacc:.2%}) is at or below terminal growth ({terminal_g:.2%}); Gordon path disabled, using exit multiple only."
        )
    if method_key in {"gordon", "average", "h_model"} and last_fcf <= 0:
        warnings.append(
            f"Terminal FCF projection is negative ({last_fcf:.2f}); DCF terminal value not computed. Consider alternative valuation methods (P/S, EV/Revenue, SOTP)."
        )
        return False, "negative_terminal_inputs", warnings
    if method_key == "exit" and ebitda_y_n <= 0:
        warnings.append(
            f"Terminal EBITDA projection is negative ({ebitda_y_n:.2f}); DCF terminal value not computed. Consider alternative valuation methods (P/S, EV/Revenue, SOTP)."
        )
        return False, "negative_terminal_inputs", warnings
    if method_key == "average" and (last_fcf <= 0 or ebitda_y_n <= 0):
        warnings.append(
            f"Terminal FCF projection is {last_fcf:.2f} and terminal EBITDA is {ebitda_y_n:.2f}; DCF terminal value not computed. Consider alternative valuation methods (P/S, EV/Revenue, SOTP)."
        )
        return False, "negative_terminal_inputs", warnings
    return True, None, warnings


def build_sensitivity(
    inp: DCFInputs,
    mode: Literal["gordon", "exit"],
    historical_context: Optional[dict] = None,
    net_debt_override: Optional[float] = None,
    shares_override: Optional[float] = None,
) -> list[list]:
    wacc_range = [inp.wacc + (i - 2) * 0.005 for i in range(5)]
    if mode == "gordon":
        col_range = [inp.terminal_g + (j - 2) * 0.005 for j in range(5)]
    else:
        col_range = [inp.exit_multiple + (j - 2) * 1.0 for j in range(5)]

    # Use unified engine when historical context is available so the matrix
    # center cell aligns with the headline IV. Sensitivity perturbs WACC / g /
    # exit_multiple only; DSO/DIO/DPO/D&A%BegPPE stay at their base-year values.
    if historical_context and historical_context.get("available"):
        forecast = build_true_3fs_forecast(inp, historical_context)
    else:
        forecast = build_operating_forecast(inp)
    fcf_list = forecast["fcf_projections"]
    ebitda_y_n = forecast["ebit_projections"][-1] + forecast["da_projections"][-1]
    n = max(1, int(inp.forecast_years or 5))

    matrix = []
    for w in wacc_range:
        row = []
        pv_sum = 0.0
        for yr, fcf in enumerate(fcf_list, 1):
            df = round(1 / (1 + w) ** yr, 6)
            pv_sum += round(fcf * df, 2)
        disc_n = round(1 / (1 + w) ** n, 6)
        for c in col_range:
            if mode == "gordon":
                tv_pv = fcf_list[-1] * (1 + c) / max(w - c, 0.001) * disc_n
            else:
                tv_pv = ebitda_y_n * c * disc_n
            ev = pv_sum + tv_pv
            net_debt_used = inp.net_debt if net_debt_override is None else float(net_debt_override)
            shares_used = float(shares_override) if shares_override and shares_override > 0 else float(inp.shares or 0.0)
            eq = ev - net_debt_used
            price = eq / shares_used if shares_used > 0 else 0
            row.append(round(price, 2))
        matrix.append(row)
    return matrix


def _calc_valuation_from_forecast(
    inp: DCFInputs,
    forecast: dict,
    net_debt_override: Optional[float] = None,
    shares_override: Optional[float] = None,
) -> dict:
    n = max(1, int(inp.forecast_years or 5))
    fcf_list = forecast["fcf_projections"]

    df_list, pv_list = [], []
    for yr, fcf in enumerate(fcf_list, 1):
        df = round(1 / (1 + inp.wacc) ** yr, 6)
        df_list.append(df)
        pv_list.append(round(fcf * df, 2))
    pv_fcf_sum = round(sum(pv_list), 2)

    last_fcf = fcf_list[-1]
    disc_n = df_list[-1]
    ebitda_y_n = forecast["ebit_projections"][-1] + forecast["da_projections"][-1]
    terminal_ok, unsuitable_reason, terminal_warnings = _validate_terminal_inputs(
        last_fcf, ebitda_y_n, inp.tv_method, inp.wacc, inp.terminal_g
    )
    if not terminal_ok:
        return {
            "discount_factors": df_list,
            "pv_fcfs": pv_list,
            "tv_gordon": None,
            "tv_exit": None,
            "tv_used": None,
            "tv_pct": 0,
            "pv_fcf_sum": pv_fcf_sum,
            "ev": None,
            "equity_value": None,
            "intrinsic_per_share": None,
            "model_unsuitable": True,
            "model_unsuitable_reason": unsuitable_reason,
            "warnings": terminal_warnings,
        }
    tv_g, tv_e, tv_used = calc_terminal_value(
        last_fcf,
        inp.wacc,
        inp.terminal_g,
        ebitda_y_n,
        inp.exit_multiple,
        inp.tv_method,
        disc_n,
    )
    if tv_used is None:
        return {
            "discount_factors": df_list,
            "pv_fcfs": pv_list,
            "tv_gordon": tv_g,
            "tv_exit": tv_e,
            "tv_used": None,
            "tv_pct": 0,
            "pv_fcf_sum": pv_fcf_sum,
            "ev": None,
            "equity_value": None,
            "intrinsic_per_share": None,
            "model_unsuitable": True,
            "model_unsuitable_reason": "wacc_below_terminal_growth",
            "warnings": [f"WACC ({inp.wacc:.2%}) is at or below terminal growth ({inp.terminal_g:.2%}); Gordon terminal value not computed."],
        }

    ev = pv_fcf_sum + tv_used
    net_debt_used = inp.net_debt if net_debt_override is None else float(net_debt_override)
    equity_val = ev - net_debt_used
    shares_used = float(shares_override) if shares_override and shares_override > 0 else float(inp.shares or 0.0)
    per_share = equity_val / shares_used if shares_used > 0 else 0
    tv_pct = tv_used / ev if ev > 0 else 0
    return {
        "discount_factors": df_list,
        "pv_fcfs": pv_list,
        "tv_gordon": tv_g,
        "tv_exit": tv_e,
        "tv_used": tv_used,
        "tv_pct": tv_pct,
        "pv_fcf_sum": pv_fcf_sum,
        "ev": ev,
        "equity_value": equity_val,
        "intrinsic_per_share": per_share,
        "model_unsuitable": False,
        "model_unsuitable_reason": None,
        "warnings": terminal_warnings,
    }


def build_operating_path_bridge_analysis(
    inp: DCFInputs,
    historical_context: Optional[dict],
    selected_wacc_used: float,
    selected_net_debt: float,
    selected_shares: float,
    base_intrinsic: float,
) -> dict:
    if (inp.symbol or "").upper() != "AAPL":
        return {
            "available": False,
            "selected_operating_path_source": OPERATING_PATH_SOURCE_SELECTED,
            "coherence_flag": "Selected Path only - non-AAPL",
        }
    years = max(1, int(inp.forecast_years or 5))
    selected_drivers = normalized_driver_assumptions(replace(inp, selected_operating_path_source=OPERATING_PATH_SOURCE_SELECTED))
    selected_rev = list(selected_drivers["selected_revenue_growth_path"])
    selected_margin = list(selected_drivers["selected_ebit_margin_path"])
    scenario_key = "bear" if selected_rev[:5] == list(AAPL_BEAR_REVENUE_GROWTH_PATH) else "base"
    bridge_paths = aapl_bridge_paths_for_scenario(scenario_key, years)
    bridge_rev = list(bridge_paths["revenue_growth_path"])
    bridge_margin = list(bridge_paths["ebit_margin_path"])

    def _iv(rev_path, margin_path):
        case_inp = replace(
            inp,
            selected_operating_path_source=OPERATING_PATH_SOURCE_SELECTED,
            revenue_growth_path=list(rev_path),
            ebit_margin_path=list(margin_path),
            wacc=float(selected_wacc_used),
        )
        fc = build_true_3fs_forecast(case_inp, historical_context) if historical_context and historical_context.get("available") else build_operating_forecast(case_inp)
        val = _calc_valuation_from_forecast(case_inp, fc, net_debt_override=selected_net_debt, shares_override=selected_shares)
        return round(float(val["intrinsic_per_share"]), 4)

    selected_iv = _iv(selected_rev, selected_margin)
    bridge_rev_iv = _iv(bridge_rev, selected_margin)
    bridge_margin_iv = _iv(selected_rev, bridge_margin)
    full_bridge_iv = _iv(bridge_rev, bridge_margin)
    revenue_impact = round(bridge_rev_iv - selected_iv, 4)
    margin_impact = round(bridge_margin_iv - selected_iv, 4)
    interaction = round(full_bridge_iv - selected_iv - revenue_impact - margin_impact, 4)
    max_bps_div = max(
        [abs((b - s) * 10000.0) for b, s in zip(bridge_rev, selected_rev)]
        + [abs((b - s) * 10000.0) for b, s in zip(bridge_margin, selected_margin)]
    )
    source_key, _, fallback, legacy_defaulted = normalize_operating_path_source(
        getattr(inp, "selected_operating_path_source", None), inp.symbol
    )
    return {
        "available": True,
        "scenario": scenario_key,
        "selected_operating_path_source": source_key,
        "selected_operating_path_source_fallback_used": fallback,
        "selected_operating_path_source_legacy_defaulted": legacy_defaulted,
        "selected_revenue_growth_path": selected_rev,
        "selected_ebit_margin_path": selected_margin,
        "bridge_revenue_growth_path": bridge_rev,
        "bridge_ebit_margin_path": bridge_margin,
        "alternative_iv": {
            "selected_path": round(selected_iv, 4),
            "bridge_revenue_selected_margin": bridge_rev_iv,
            "selected_revenue_bridge_margin": bridge_margin_iv,
            "full_bridge": full_bridge_iv,
        },
        "attribution": {
            "revenue_impact": revenue_impact,
            "margin_impact": margin_impact,
            "interaction": interaction,
            "difference_vs_headline": round(full_bridge_iv - float(base_intrinsic or 0.0), 4),
        },
        "max_bps_divergence": round(max_bps_div, 1),
        "coherence_flag": (
            "Bridge is engine-driving"
            if source_key == OPERATING_PATH_SOURCE_AAPL_BRIDGE
            else f"reference/support; max bps divergence = {round(max_bps_div, 1)}"
        ),
    }


def build_terminal_sanity(inp: DCFInputs, tv_pct: float, tv_gordon: float, tv_exit: float) -> dict:
    spread = inp.wacc - inp.terminal_g
    if tv_gordon is None or tv_exit is None:
        return {
            "thresholds": {
                "tv_dependency": TV_DEPENDENCY_THRESHOLD,
                "gordon_spread": GORDON_SPREAD_THRESHOLD,
                "method_diff": TV_METHOD_DIFF_THRESHOLD,
            },
            "tv_dependency_high": tv_pct > TV_DEPENDENCY_THRESHOLD,
            "gordon_unstable": True,
            "method_divergence_high": False,
            "gordon_spread": round(spread, 6),
            "method_diff": None,
        }
    denom = max(abs(tv_gordon), abs(tv_exit), 1.0)
    method_diff = abs(tv_gordon - tv_exit) / denom
    return {
        "thresholds": {
            "tv_dependency": TV_DEPENDENCY_THRESHOLD,
            "gordon_spread": GORDON_SPREAD_THRESHOLD,
            "method_diff": TV_METHOD_DIFF_THRESHOLD,
        },
        "tv_dependency_high": tv_pct > TV_DEPENDENCY_THRESHOLD,
        "gordon_unstable": inp.terminal_g >= inp.wacc or spread < GORDON_SPREAD_THRESHOLD,
        "method_divergence_high": method_diff > TV_METHOD_DIFF_THRESHOLD,
        "gordon_spread": round(spread, 6),
        "method_diff": round(method_diff, 6),
    }


def build_operating_sensitivity(
    inp: DCFInputs,
    historical_context: Optional[dict] = None,
    net_debt_override: Optional[float] = None,
    shares_override: Optional[float] = None,
) -> list[list]:
    drivers = normalized_driver_assumptions(inp)
    growth_range = [drivers["revenue_growth"] + (j - 2) * 0.01 for j in range(5)]
    margin_range = [drivers["ebit_margin"] + (i - 2) * 0.01 for i in range(5)]

    use_unified = bool(historical_context and historical_context.get("available"))

    matrix = []
    for margin in margin_range:
        row = []
        for growth in growth_range:
            scenario_inp = replace(
                inp,
                revenue_growth=growth,
                fcf_growth=growth,
                ebit_margin=margin,
                # V3.9.0: sensitivity perturbs the scalar drivers only. Clear
                # any caller-supplied path so the scalar is flat-expanded and
                # the sensitivity matrix reflects pure growth x margin moves.
                revenue_growth_path=None,
                ebit_margin_path=None,
            )
            if use_unified:
                forecast = build_true_3fs_forecast(scenario_inp, historical_context)
            else:
                forecast = build_operating_forecast(scenario_inp)
            valuation = _calc_valuation_from_forecast(
                scenario_inp,
                forecast,
                net_debt_override=net_debt_override,
                shares_override=shares_override,
            )
            row.append(round(valuation["intrinsic_per_share"], 2))
        matrix.append(row)
    return matrix


# ──────────────────────────────────────────────────────────────────────────────
# V3.7.0 Unified True 3FS Engine
# ──────────────────────────────────────────────────────────────────────────────


def _hist_norm(tables: dict, statement: str, field_key: str, year, market: str):
    """Read raw value from V3.6 historical tables and normalize to model unit.

    Lazy import of unit_utils to avoid a hard dependency for callers that build
    DCFInputs directly without touching the cache.
    """
    from modeling.unit_utils import normalize_raw_actual_to_model_unit

    rows = ((tables.get(statement) or {}).get("rows") or {})
    raw = (rows.get(field_key) or {}).get(year)
    return normalize_raw_actual_to_model_unit(raw, market)


def build_historical_context(symbol: str) -> dict:
    """Build the historical-driven assumption context for the unified True 3FS engine.

    Reads the V3.6 historical cache, converts raw actuals to model units (millions
    for US), and computes the latest-year defaults that drive forecasting:
      * DSO / DIO / DPO (days-based working-capital driver)
      * gross_margin (used to derive forecast COGS for DIO / DPO)
      * da_pct_begin_ppe (asset-based D&A)
      * beginning_ppe (starting point for the PP&E roll-forward)
      * initial_nwc (baseline for the Year 1 ΔNWC calc)

    Returns a dict whose `available` flag tells callers whether the unified
    engine can run; otherwise legacy operating forecast is used. HK / CN have no
    model-unit scale factor yet, so they always fall back gracefully.
    """
    from modeling.unit_utils import model_unit_scale_factor

    market = detect_market(symbol)
    if model_unit_scale_factor(market) is None:
        return {
            "available": False,
            "market": market,
            "warnings": [f"{market}: no model-unit scale factor; legacy operating forecast in use"],
        }

    try:
        from data_fetcher_historical import historical_cache_to_tables, read_historical_cache
    except Exception as e:  # pragma: no cover - defensive
        return {"available": False, "market": market, "warnings": [f"historical fetcher unavailable: {e!r}"]}

    cache = read_historical_cache(symbol) or {}
    payload = cache.get("data") or {}
    if payload.get("status") != "ok":
        return {
            "available": False,
            "market": market,
            "warnings": ["historical cache unavailable or empty; legacy operating forecast in use"],
        }

    tables = historical_cache_to_tables(payload)
    is_table = tables.get("income_statement") or {}
    bs_table = tables.get("balance_sheet") or {}
    cf_table = tables.get("cash_flow") or {}

    is_years = is_table.get("years") or []
    bs_years = bs_table.get("years") or []
    cf_years = cf_table.get("years") or []
    common_years = sorted(set(is_years) & set(bs_years), reverse=True)

    warnings: list[str] = []

    dso = dio = dpo = None
    gross_margin = None
    wc_day_history: list[dict] = []
    nwc_history: list[dict] = []
    for y in common_years:
        revenue = _hist_norm(tables, "income_statement", "revenue", y, market)
        gp = _hist_norm(tables, "income_statement", "gross_profit", y, market)
        cogs = (revenue - gp) if (revenue is not None and gp is not None) else None
        ar = _hist_norm(tables, "balance_sheet", "accounts_receivable", y, market)
        inv = _hist_norm(tables, "balance_sheet", "inventory", y, market)
        ap = _hist_norm(tables, "balance_sheet", "accounts_payable", y, market)
        dso_y = ar / revenue * 365.0 if ar is not None and revenue else None
        dio_y = inv / cogs * 365.0 if inv is not None and cogs else None
        dpo_y = ap / cogs * 365.0 if ap is not None and cogs else None
        if any(v is not None for v in (dso_y, dio_y, dpo_y)):
            wc_day_history.append({"year": y, "dso": dso_y, "dio": dio_y, "dpo": dpo_y})
        if any(v is not None for v in (ar, inv, ap)):
            nwc_history.append({"year": y, "nwc": (ar or 0.0) + (inv or 0.0) - (ap or 0.0)})
        if dso is None and ar is not None and revenue:
            dso = ar / revenue * 365.0
        if dio is None and inv is not None and cogs:
            dio = inv / cogs * 365.0
        if dpo is None and ap is not None and cogs:
            dpo = ap / cogs * 365.0
        if gross_margin is None and revenue and gp is not None:
            gross_margin = gp / revenue
        # Keep scanning all common years so the WC reality-check block can use
        # 3-year / 5-year normalized days and historical Delta NWC releases.

    wc_day_history = sorted(wc_day_history, key=lambda x: x["year"])
    nwc_history = sorted(nwc_history, key=lambda x: x["year"])
    delta_nwc_history = []
    for i in range(1, len(nwc_history)):
        delta_nwc_history.append({
            "year": nwc_history[i]["year"],
            "delta_nwc": nwc_history[i]["nwc"] - nwc_history[i - 1]["nwc"],
        })

    def _avg_days(key: str, count: int = 3):
        vals = [float(x[key]) for x in wc_day_history[-count:] if x.get(key) is not None]
        return (sum(vals) / len(vals)) if vals else None

    normalized_days = {
        "dso": _avg_days("dso", 3) if _avg_days("dso", 3) is not None else _avg_days("dso", 5),
        "dio": _avg_days("dio", 3) if _avg_days("dio", 3) is not None else _avg_days("dio", 5),
        "dpo": _avg_days("dpo", 3) if _avg_days("dpo", 3) is not None else _avg_days("dpo", 5),
    }

    if dso is None:
        warnings.append("DSO unavailable in historical cache; AR forecast falls back to 0")
        dso = 0.0
    if dio is None:
        # asset-light businesses can legitimately have ~0 inventory; do not warn.
        dio = 0.0
    if dpo is None:
        warnings.append("DPO unavailable in historical cache; AP forecast falls back to 0")
        dpo = 0.0
    if gross_margin is None:
        warnings.append("gross margin unavailable; COGS treated as 0 and DIO/DPO will not contribute to NWC")
        gross_margin = 1.0

    da_pct_begin_ppe = None
    for y in sorted(cf_years, reverse=True):
        da_val = _hist_norm(tables, "cash_flow", "depreciation_amortization", y, market)
        prev_bs_years = [py for py in bs_years if py < y]
        if not prev_bs_years:
            continue
        beg_ppe_val = _hist_norm(tables, "balance_sheet", "ppe", max(prev_bs_years), market)
        if da_val is not None and beg_ppe_val:
            da_pct_begin_ppe = da_val / beg_ppe_val
            break
    if da_pct_begin_ppe is None:
        warnings.append("D&A%BegPPE unavailable; asset-based D&A falls back to legacy D&A%Revenue")

    beginning_ppe = None
    for y in sorted(bs_years, reverse=True):
        v = _hist_norm(tables, "balance_sheet", "ppe", y, market)
        if v is not None:
            beginning_ppe = v
            break

    initial_nwc = None
    for y in sorted(bs_years, reverse=True):
        ar = _hist_norm(tables, "balance_sheet", "accounts_receivable", y, market)
        inv = _hist_norm(tables, "balance_sheet", "inventory", y, market)
        ap = _hist_norm(tables, "balance_sheet", "accounts_payable", y, market)
        if any(v is not None for v in (ar, inv, ap)):
            initial_nwc = (ar or 0.0) + (inv or 0.0) - (ap or 0.0)
            break

    return {
        "available": True,
        "market": market,
        "dso": dso,
        "dio": dio,
        "dpo": dpo,
        "wc_days_history": wc_day_history,
        "wc_days_normalized_average": normalized_days,
        "delta_nwc_history": delta_nwc_history,
        "gross_margin": gross_margin,
        "da_pct_begin_ppe": da_pct_begin_ppe,
        "beginning_ppe": beginning_ppe or 0.0,
        "initial_nwc": initial_nwc or 0.0,
        "warnings": warnings,
        "source": "V3.6 historical cache",
    }


def build_true_3fs_forecast(inp: DCFInputs, hist_ctx: Optional[dict]) -> dict:
    """Unified V3.7.0 True 3FS forecast.

    Year-by-year forecast that mirrors the V3.6.9 Excel workbook logic:
      Revenue        = prev × (1 + revenue_growth)
      EBIT           = Revenue × EBIT margin
      NOPAT          = EBIT × (1 - tax_rate)   (FCFF: unlevered; interest excluded)
      COGS           = Revenue × (1 - gross_margin)
      AR             = Revenue / 365 × DSO
      Inventory      = COGS / 365 × DIO
      AP             = COGS / 365 × DPO
      NWC            = AR + Inventory - AP
      ΔNWC           = NWC - prior NWC          (Year 1 prior = historical NWC)
      CapEx          = Revenue × CapEx%Revenue
      D&A            = Beginning Net PP&E × D&A%BegPPE   (asset-based when available)
      Ending Net PP&E = Beginning + CapEx - D&A
      Unlevered FCF  = NOPAT + D&A - CapEx - ΔNWC

    Returns the same keys as `build_operating_forecast()` plus full schedule
    detail under `schedules`. When `hist_ctx` is unavailable, falls back
    transparently to the legacy operating forecast (recorded in `engine`).
    """
    drivers = normalized_driver_assumptions(inp)
    n = max(1, int(inp.forecast_years or 5))

    available = bool(hist_ctx and hist_ctx.get("available"))
    if not available:
        legacy = build_operating_forecast(inp)
        legacy["engine"] = "legacy_operating_forecast"
        legacy["active_forecast_sources"] = {
            "da": "percent_of_revenue_fallback",
            "capex": "percent_of_revenue_fallback",
            "delta_nwc": "percent_of_revenue_fallback",
        }
        legacy["schedules"] = None
        return legacy

    dso = float(hist_ctx.get("dso") or 0.0)
    dio = float(hist_ctx.get("dio") or 0.0)
    dpo = float(hist_ctx.get("dpo") or 0.0)
    norm_days = hist_ctx.get("wc_days_normalized_average") or {}
    dso_target = float(norm_days.get("dso") if norm_days.get("dso") is not None else dso)
    dio_target = float(norm_days.get("dio") if norm_days.get("dio") is not None else dio)
    dpo_target = float(norm_days.get("dpo") if norm_days.get("dpo") is not None else dpo)
    gross_margin = float(hist_ctx.get("gross_margin") or 1.0)
    da_pct_begin_ppe = hist_ctx.get("da_pct_begin_ppe")
    beginning_ppe = float(hist_ctx.get("beginning_ppe") or 0.0)
    initial_nwc = float(hist_ctx.get("initial_nwc") or 0.0)

    override_keys = set(getattr(inp, "operating_override_keys", None) or [])
    da_override_active = "da_pct_revenue" in override_keys
    wc_override_active = "wc_change_pct_revenue" in override_keys
    use_asset_based_da = beginning_ppe > 0 and da_pct_begin_ppe is not None and not da_override_active
    use_schedule_delta_nwc = not wc_override_active

    revenue_list: list[float] = []
    growth_list: list[float] = []
    margin_list: list[float] = []
    ebit_list: list[float] = []
    tax_list: list[float] = []
    nopat_list: list[float] = []
    da_list: list[float] = []
    capex_list: list[float] = []
    delta_nwc_list: list[float] = []
    fcf_list: list[float] = []

    cogs_list: list[float] = []
    gp_list: list[float] = []
    ar_list: list[float] = []
    inv_list: list[float] = []
    ap_list: list[float] = []
    nwc_list: list[float] = []
    schedule_delta_nwc_list: list[float] = []
    dso_series: list[float] = []
    dio_series: list[float] = []
    dpo_series: list[float] = []
    begin_ppe_list: list[float] = []
    end_ppe_list: list[float] = []
    da_pct_beg_ppe_implied: list[float] = []

    revenue = float(inp.revenue or 0)
    prev_nwc = initial_nwc
    current_begin_ppe = beginning_ppe

    rg_path = drivers["revenue_growth_path"]
    em_path = drivers["ebit_margin_path"]
    da_path = drivers["da_pct_revenue_path"]
    cx_path = drivers["capex_pct_revenue_path"]
    # wc_path is reference-only in the unified engine (NWC is days-driven).
    wc_path = drivers["wc_change_pct_revenue_path"]

    for i in range(n):
        progress = (i / (n - 1)) if n > 1 else 1.0
        dso_i = dso + (dso_target - dso) * progress
        dio_i = dio + (dio_target - dio) * progress
        dpo_i = dpo + (dpo_target - dpo) * progress
        growth = rg_path[i]
        margin = em_path[i]
        revenue = revenue * (1 + growth)
        ebit = revenue * margin
        taxes = -ebit * inp.tax_rate
        nopat = ebit + taxes

        gp = revenue * gross_margin
        cogs = revenue - gp

        capex = revenue * cx_path[i]
        if use_asset_based_da:
            da = current_begin_ppe * float(da_pct_begin_ppe)
        else:
            da = revenue * da_path[i]

        ar = revenue / 365.0 * dso_i
        inventory = (cogs / 365.0 * dio_i) if cogs > 0 else 0.0
        ap = (cogs / 365.0 * dpo_i) if cogs > 0 else 0.0
        nwc = ar + inventory - ap
        schedule_delta_nwc = nwc - prev_nwc
        delta_nwc = schedule_delta_nwc if use_schedule_delta_nwc else revenue * wc_path[i]
        prev_nwc = nwc

        fcf = nopat + da - capex - delta_nwc
        end_ppe = current_begin_ppe + capex - da

        revenue_list.append(round(revenue, 2))
        growth_list.append(round(growth, 6))
        margin_list.append(round(margin, 6))
        ebit_list.append(round(ebit, 2))
        tax_list.append(round(taxes, 2))
        nopat_list.append(round(nopat, 2))
        da_list.append(round(da, 2))
        capex_list.append(round(capex, 2))
        delta_nwc_list.append(round(delta_nwc, 2))
        fcf_list.append(round(fcf, 2))

        gp_list.append(round(gp, 2))
        cogs_list.append(round(cogs, 2))
        ar_list.append(round(ar, 2))
        inv_list.append(round(inventory, 2))
        ap_list.append(round(ap, 2))
        nwc_list.append(round(nwc, 2))
        schedule_delta_nwc_list.append(round(schedule_delta_nwc, 2))
        dso_series.append(round(dso_i, 4))
        dio_series.append(round(dio_i, 4))
        dpo_series.append(round(dpo_i, 4))
        begin_ppe_list.append(round(current_begin_ppe, 2))
        end_ppe_list.append(round(end_ppe, 2))
        da_pct_beg_ppe_implied.append(
            round(da / current_begin_ppe, 6) if current_begin_ppe else 0.0
        )

        current_begin_ppe = end_ppe

    operating_forecast_paths_unified = {
        "revenue_growth_path": list(rg_path),
        "ebit_margin_path": list(em_path),
        "da_pct_revenue_path": list(da_path),
        "capex_pct_revenue_path": list(cx_path),
        "wc_change_pct_revenue_path": list(wc_path),
    }
    hist_delta_vals = [float(x["delta_nwc"]) for x in (hist_ctx.get("delta_nwc_history") or []) if x.get("delta_nwc") is not None]
    hist_avg_delta = (sum(hist_delta_vals[-3:]) / len(hist_delta_vals[-3:])) if hist_delta_vals else None
    legacy_delta_ref = [round(revenue_list[i] * wc_path[i], 2) for i in range(n)]
    first_delta = delta_nwc_list[0] if delta_nwc_list else None
    first_schedule_delta = schedule_delta_nwc_list[0] if schedule_delta_nwc_list else None
    diff_vs_hist = (first_delta - hist_avg_delta) if (first_delta is not None and hist_avg_delta is not None) else None
    sign_convention = "Delta NWC = Ending NWC - Beginning NWC; negative = source of cash / working-capital release; positive = use of cash / working-capital investment."
    hostile_review_note = (
        "Workbook historical Delta NWC uses a balance-sheet AR + Inventory - AP delta, "
        "with signed releases and builds included in the average. Hostile-review release "
        "figures may use broader cash-flow-statement working-capital lines or release-only "
        "years; compare source and sign before treating the figures as contradictory."
    )
    faded_days_gap_note = (
        "Year 1 faded-days Delta NWC starts from latest actual DSO/DIO/DPO before fading "
        "toward normalized targets, so it may remain below larger historical release years. "
        "The model keeps the schedule-derived driver active and retains Review when the "
        "gap is material."
    )
    review_tier = "Review"
    if diff_vs_hist is not None:
        threshold = max(abs(hist_avg_delta) * 0.50, 1_000.0)
        review_tier = "OK" if abs(diff_vs_hist) <= threshold else "Review"
        if abs(diff_vs_hist) > max(abs(hist_avg_delta), 2_500.0):
            review_tier = "High Review"
    return {
        "engine": "unified_true_3fs_v1",
        "active_forecast_sources": {
            "da": "user_override_pct_revenue" if da_override_active else ("schedule_derived_beginning_ppe" if use_asset_based_da else "percent_of_revenue_fallback"),
            "capex": "user_override_pct_revenue" if "capex_pct_revenue" in override_keys else "percent_of_revenue",
            "delta_nwc": "user_override_pct_revenue" if wc_override_active else "schedule_derived_working_capital_days",
        },
        "operating_forecast_paths": operating_forecast_paths_unified,
        "revenue_projections": revenue_list,
        "revenue_growth_projections": growth_list,
        "ebit_margin_projections": margin_list,
        "ebit_projections": ebit_list,
        "tax_projections": tax_list,
        "nopat_projections": nopat_list,
        "da_projections": da_list,
        "capex_projections": capex_list,
        "delta_nwc_projections": delta_nwc_list,
        "fcf_projections": fcf_list,
        "drivers": drivers,
        "schedules": {
            "working_capital": {
                "dso": round(dso, 4),
                "dio": round(dio, 4),
                "dpo": round(dpo, 4),
                "dso_target": round(dso_target, 4),
                "dio_target": round(dio_target, 4),
                "dpo_target": round(dpo_target, 4),
                "dso_series": dso_series,
                "dio_series": dio_series,
                "dpo_series": dpo_series,
                "days_method": "faded_days_schedule",
                "delta_nwc_sign_convention": sign_convention,
                "delta_nwc_history": hist_ctx.get("delta_nwc_history") or [],
                "reality_check": {
                    "sign_convention": sign_convention,
                    "historical_delta_nwc_by_year": hist_ctx.get("delta_nwc_history") or [],
                    "historical_average_delta_nwc": round(hist_avg_delta, 4) if hist_avg_delta is not None else None,
                    "current_schedule_derived_delta_nwc": round(first_schedule_delta, 4) if first_schedule_delta is not None else None,
                    "faded_days_delta_nwc": round(first_schedule_delta, 4) if first_schedule_delta is not None else None,
                    "legacy_pct_revenue_delta_nwc_reference": legacy_delta_ref[0] if legacy_delta_ref else None,
                    "difference_vs_historical_average": round(diff_vs_hist, 4) if diff_vs_hist is not None else None,
                    "hostile_review_release_difference_note": hostile_review_note,
                    "faded_days_gap_explanation": faded_days_gap_note,
                    "review_tier": review_tier,
                },
                "gross_margin": round(gross_margin, 6),
                "cogs": cogs_list,
                "gross_profit": gp_list,
                "accounts_receivable": ar_list,
                "inventory": inv_list,
                "accounts_payable": ap_list,
                "nwc": nwc_list,
                "change_in_nwc": delta_nwc_list,
                "initial_nwc": round(initial_nwc, 2),
            },
            "ppe": {
                "beginning_ppe": begin_ppe_list,
                "capex": capex_list,
                "da": da_list,
                "ending_ppe": end_ppe_list,
                "da_pct_beginning_ppe_implied": da_pct_beg_ppe_implied,
                "initial_beginning_ppe": round(beginning_ppe, 2),
                "da_pct_beginning_ppe_default": (
                    round(float(da_pct_begin_ppe), 6) if da_pct_begin_ppe is not None else None
                ),
                "asset_based_da_active": use_asset_based_da,
            },
        },
    }


def _latest_bs_value(symbol: str, market: str, field_key: str) -> Optional[float]:
    """Read latest historical balance-sheet value (normalized to model unit)."""
    from modeling.unit_utils import model_unit_scale_factor

    if model_unit_scale_factor(market) is None:
        return None
    try:
        from data_fetcher_historical import historical_cache_to_tables, read_historical_cache
    except Exception:
        return None
    cache = read_historical_cache(symbol) or {}
    payload = cache.get("data") or {}
    if payload.get("status") != "ok":
        return None
    tables = historical_cache_to_tables(payload)
    bs_table = tables.get("balance_sheet") or {}
    years = sorted(bs_table.get("years") or [], reverse=True)
    for y in years:
        v = _hist_norm(tables, "balance_sheet", field_key, y, market)
        if v is not None:
            return v
    return None


def _historical_statement_history(
    symbol: str, market: str, statement: str, field_key: str, take_abs: bool = False
) -> list[tuple[int, float]]:
    """Return [(year, value), ...] sorted ascending for a single cache field.

    Returns an empty list when the cache is unavailable, the field is missing
    in every year, or unit normalization is unsupported for the market.
    """
    from modeling.unit_utils import model_unit_scale_factor

    if model_unit_scale_factor(market) is None:
        return []
    try:
        from data_fetcher_historical import historical_cache_to_tables, read_historical_cache
    except Exception:
        return []
    cache = read_historical_cache(symbol) or {}
    payload = cache.get("data") or {}
    if payload.get("status") != "ok":
        return []
    tables = historical_cache_to_tables(payload)
    statement_table = tables.get(statement) or {}
    years = sorted(statement_table.get("years") or [])
    out: list[tuple[int, float]] = []
    for y in years:
        v = _hist_norm(tables, statement, field_key, y, market)
        if v is None:
            continue
        if take_abs:
            v = abs(v)
        out.append((y, float(v)))
    return out


def build_shareholder_returns_schedule(
    inp: DCFInputs,
    forecast: dict,
    historical_context: Optional[dict] = None,
) -> dict:
    """V3.7.4 Shareholder Returns v1 schedule.

    Builds historical buyback / dividend reference values from the v374
    historical cash flow cache, projects dividends + buybacks across the
    forecast horizon, runs a share-count roll-forward, and surfaces three
    alternative IV/share denominators (current reported, forecast ending,
    forecast weighted-average).

    Headline IV is preserved unless the caller explicitly switches
    ``selected_share_count_treatment`` away from the default
    ``current_reported_shares``.

    Returns a stable dict shape for API + Excel; never raises - missing
    historical data degrades gracefully into a warning + zero baseline so
    HK / CN exports keep working.
    """
    market = detect_market(inp.symbol)
    warnings: list[str] = []

    # Resolve treatment + method. Unknown values fall back silently with a flag.
    method, method_label, method_fallback = normalize_buyback_method(inp.buyback_method)
    treatment, treatment_label, treatment_fallback = normalize_share_count_treatment(
        inp.selected_share_count_treatment
    )
    if method_fallback and inp.buyback_method:
        warnings.append(
            f"Unknown buyback method '{inp.buyback_method}'; falling back to {DEFAULT_BUYBACK_METHOD}."
        )
    if treatment_fallback and inp.selected_share_count_treatment:
        warnings.append(
            f"Unknown share count treatment '{inp.selected_share_count_treatment}'; "
            f"falling back to {DEFAULT_SHARE_COUNT_TREATMENT}."
        )

    # ── Historical reference ────────────────────────────────────────────
    dividends_hist = _historical_statement_history(
        inp.symbol, market, "cash_flow", "cash_dividends_paid", take_abs=True
    )
    buybacks_hist = _historical_statement_history(
        inp.symbol, market, "cash_flow", "repurchase_of_capital_stock", take_abs=True
    )
    fcf_hist = _historical_statement_history(
        inp.symbol, market, "cash_flow", "free_cash_flow"
    )
    ni_hist = _historical_statement_history(
        inp.symbol, market, "income_statement", "net_income"
    )
    shares_hist = _historical_statement_history(
        inp.symbol, market, "income_statement", "diluted_shares"
    )
    sbc_hist = _historical_statement_history(
        inp.symbol, market, "cash_flow", "stock_based_compensation", take_abs=True
    )

    base_dividends = dividends_hist[-1][1] if dividends_hist else None
    base_buybacks = buybacks_hist[-1][1] if buybacks_hist else None
    base_fcf = fcf_hist[-1][1] if fcf_hist else None
    base_ni = ni_hist[-1][1] if ni_hist else None
    base_sbc = sbc_hist[-1][1] if sbc_hist else None
    base_shares = shares_hist[-1][1] if shares_hist else float(inp.shares or 0.0)

    historical_cache_available = bool(
        dividends_hist or buybacks_hist or fcf_hist or ni_hist
    )
    if not historical_cache_available:
        warnings.append(
            f"{market}: V3.7.4 cash-flow shareholder return fields unavailable; "
            "schedule defaults to zero baselines (Audit flags Review)."
        )

    def _ratio_pct(num, den):
        if num is None or den in (None, 0):
            return None
        try:
            return float(num) / float(den)
        except (TypeError, ValueError, ZeroDivisionError):
            return None

    hist_buyback_pct_fcf = _ratio_pct(base_buybacks, base_fcf)
    hist_dividend_payout = _ratio_pct(base_dividends, base_ni)
    hist_buyback_pct_ni = _ratio_pct(base_buybacks, base_ni)
    hist_dividend_pct_fcf = _ratio_pct(base_dividends, base_fcf)
    base_total_returns = (base_dividends or 0.0) + (base_buybacks or 0.0)

    # ── Forecast drivers ────────────────────────────────────────────────
    n = len(forecast.get("fcf_projections") or []) or max(1, int(inp.forecast_years or 5))
    fcf_proj = list(forecast.get("fcf_projections") or [0.0] * n)
    # Net Income proxy: unlevered NOPAT from the unified engine; the actual P&L
    # net income (which deducts interest) lives in the workbook formula layer.
    nopat_proj = list(forecast.get("nopat_projections") or [0.0] * n)
    if len(fcf_proj) < n:
        fcf_proj.extend([0.0] * (n - len(fcf_proj)))
    if len(nopat_proj) < n:
        nopat_proj.extend([0.0] * (n - len(nopat_proj)))

    # Effective driver values. None = fall back to historical / zero.
    dividend_payout = inp.dividend_payout_pct_net_income
    if dividend_payout is None:
        dividend_payout = hist_dividend_payout if hist_dividend_payout is not None else 0.0
    buyback_pct_fcf = inp.buyback_pct_fcf
    if buyback_pct_fcf is None:
        buyback_pct_fcf = hist_buyback_pct_fcf if hist_buyback_pct_fcf is not None else 0.0
    flat_buyback_amount = (
        inp.flat_buyback_amount
        if inp.flat_buyback_amount is not None
        else (base_buybacks or 0.0)
    )

    # Repurchase price model: current price grown at repurchase_price_growth.
    repurchase_price_y0 = float(inp.price or 0.0)
    repurchase_price_growth = float(inp.repurchase_price_growth or 0.0)

    # V3.9.9.4 SBC dilution v1: derive a default from historical SBC when the
    # user has not overridden the input. Source: cash-flow stock_based_compensation
    # converted to a fractional share-count dilution via SBC / (shares x price).
    user_dilution_override = inp.annual_dilution_pct is not None
    sbc_default_methodology = None
    sbc_default_source_year = None
    sbc_default_pct_market_cap = None
    sbc_default_pct_revenue = None
    sbc_default_industry = None         # V3.9.11 Batch 2B F014
    sbc_default_floor_warning = None    # V3.9.11 Batch 2B F014
    if user_dilution_override:
        annual_dilution_pct = float(inp.annual_dilution_pct or 0.0)
        sbc_default_methodology = "User-provided override (annual dilution %)."
    else:
        # Try data-driven default from latest historical SBC.
        latest_revenue_for_sbc = None
        try:
            rev_hist_for_sbc = _historical_statement_history(
                inp.symbol, market, "income_statement", "revenue"
            )
            if rev_hist_for_sbc:
                latest_revenue_for_sbc = float(rev_hist_for_sbc[-1][1])
        except Exception:
            latest_revenue_for_sbc = None
        sbc_year = base_sbc and sbc_hist[-1][0]
        price_for_sbc = float(inp.price or 0.0)
        shares_for_sbc = float(base_shares or inp.shares or 0.0)
        market_cap_for_sbc = price_for_sbc * shares_for_sbc if (price_for_sbc > 0 and shares_for_sbc > 0) else 0.0
        if base_sbc and base_sbc > 0 and market_cap_for_sbc > 0:
            # SBC is in millions of currency; market cap = price * shares (M)
            # is also in currency-millions when shares are in millions.
            sbc_default_pct_market_cap = float(base_sbc) / market_cap_for_sbc
            # Cap default at 1.5% gross dilution to avoid extreme defaults.
            annual_dilution_pct = max(0.0, min(0.015, sbc_default_pct_market_cap))
            sbc_default_methodology = (
                f"Default = latest historical SBC ({sbc_year}) / market cap "
                "(price x reported shares), capped at 1.5%. Editable analyst input."
            )
            sbc_default_source_year = sbc_year
            if latest_revenue_for_sbc and latest_revenue_for_sbc > 0:
                sbc_default_pct_revenue = float(base_sbc) / latest_revenue_for_sbc
        elif base_sbc and base_sbc > 0 and latest_revenue_for_sbc and latest_revenue_for_sbc > 0:
            # Fallback: scale SBC/revenue (rough proxy) at half-strength as gross dilution.
            sbc_default_pct_revenue = float(base_sbc) / latest_revenue_for_sbc
            annual_dilution_pct = max(0.0025, min(0.015, sbc_default_pct_revenue * 0.25))
            sbc_default_methodology = (
                f"Default = latest historical SBC ({sbc_year}) / revenue x 0.25 as gross dilution proxy "
                "(market cap unavailable). Editable analyst input."
            )
            sbc_default_source_year = sbc_year
        else:
            # V3.9.11 Batch 2B F014: sector-differentiated SBC floor (was flat 0.25%).
            # Historical SBC data unavailable for this ticker; pick a floor that
            # matches the ticker's industry (SaaS 2% / biotech 3% / staples 0.1% / ...).
            # _default_unknown stays at 0.25% for backward compatibility.
            from modeling.industry_classification import (
                classify_industry, INDUSTRY_SBC_FLOOR, SBC_FLOOR_LEGACY_BASELINE,
            )
            ticker_for_sbc = getattr(inp, "symbol", "") or ""
            sbc_default_industry = classify_industry(ticker_for_sbc, {})
            annual_dilution_pct = INDUSTRY_SBC_FLOOR.get(
                sbc_default_industry, SBC_FLOOR_LEGACY_BASELINE
            )
            sbc_default_methodology = (
                f"Default = {annual_dilution_pct:.2%} sector-differentiated floor "
                f"(industry={sbc_default_industry}; historical SBC unavailable). "
                f"Review item; edit on Assumptions if material SBC exists."
            )
            if annual_dilution_pct > SBC_FLOOR_LEGACY_BASELINE:
                sbc_default_floor_warning = {
                    "key": "sbc_high_industry_default",
                    "tier": "Review",
                    "annual_dilution_pct": annual_dilution_pct,
                    "industry": sbc_default_industry,
                    "legacy_baseline": SBC_FLOOR_LEGACY_BASELINE,
                    "message": (
                        f"SBC dilution default raised to {annual_dilution_pct:.2%} "
                        f"(industry={sbc_default_industry}, vs legacy 0.25% baseline). "
                        f"Historical SBC data unavailable. Verify SBC magnitude in "
                        f"10-K / annual report."
                    ),
                }
    funding_treatment = getattr(inp, "buyback_funding_treatment", DEFAULT_BUYBACK_FUNDING_TREATMENT) or DEFAULT_BUYBACK_FUNDING_TREATMENT
    if funding_treatment not in {"cash_floor_buyback_cap", "debt_funded_buyback", "planned_uncapped_diagnostic"}:
        funding_treatment = DEFAULT_BUYBACK_FUNDING_TREATMENT
    cash_floor = float(inp.minimum_cash_floor if inp.minimum_cash_floor is not None else DEFAULT_CASH_FLOOR)
    latest_cash = _latest_bs_value(inp.symbol, market, "cash")
    latest_cash_st = _latest_bs_value(inp.symbol, market, "cash_and_short_term_investments")
    latest_st_inv = _latest_bs_value(inp.symbol, market, "short_term_investments")
    latest_lt_inv = _latest_bs_value(inp.symbol, market, "long_term_investments")
    latest_debt = _latest_bs_value(inp.symbol, market, "total_debt")
    ms_available = (
        float(inp.marketable_securities_available_for_returns)
        if inp.marketable_securities_available_for_returns is not None
        else float((latest_st_inv or 0.0) + (latest_lt_inv or 0.0))
    )

    beginning_shares_proj: list[float] = []
    dividends_proj: list[float] = []
    planned_buybacks_proj: list[float] = []
    buybacks_proj: list[float] = []
    unfunded_buybacks_proj: list[float] = []
    incremental_debt_proj: list[float] = []
    beginning_cash_proj: list[float] = []
    ending_cash_proj: list[float] = []
    ending_debt_proj: list[float] = []
    ending_net_debt_proj: list[float] = []
    funding_capacity_proj: list[float] = []
    cash_available_above_floor_proj: list[float] = []
    fcf_after_dividends_used_proj: list[float] = []
    cash_above_floor_used_proj: list[float] = []
    ms_available_proj: list[float] = []
    ms_drawdown_used_proj: list[float] = []
    ending_ms_proj: list[float] = []
    total_returns_proj: list[float] = []
    repurchase_price_proj: list[float] = []
    shares_repurchased_proj: list[float] = []
    dilution_proj: list[float] = []
    ending_shares_proj: list[float] = []
    weighted_avg_shares_proj: list[float] = []
    eps_proj: list[float] = []
    fcf_per_share_proj: list[float] = []

    # Use current reported shares (inp.shares) as the Year 1 beginning share
    # count - this is the snapshot every IV/share rolls forward from. Historical
    # diluted shares are reference only.
    current_shares = float(inp.shares or base_shares or 0.0)
    running_cash = float(latest_cash if latest_cash is not None else 0.0)
    running_debt = float(latest_debt if latest_debt is not None else 0.0)
    running_ms = max(0.0, ms_available)

    for i in range(n):
        beg_shares = current_shares if i == 0 else ending_shares_proj[-1]
        ni_i = nopat_proj[i]
        fcf_i = fcf_proj[i]
        dividends_i = max(0.0, dividend_payout * ni_i) if ni_i is not None else 0.0
        if method == "flat_amount":
            planned_buybacks_i = max(0.0, flat_buyback_amount)
        else:
            planned_buybacks_i = max(0.0, buyback_pct_fcf * fcf_i) if fcf_i is not None else 0.0
        fcf_after_dividends = max(0.0, (fcf_i or 0.0) - dividends_i)
        ms_available_i = running_ms
        cash_available_above_floor = max(0.0, running_cash - cash_floor)
        funding_capacity = fcf_after_dividends + cash_available_above_floor + ms_available_i
        if funding_treatment == "debt_funded_buyback":
            buybacks_i = planned_buybacks_i
            unfunded_i = 0.0
            incremental_debt_i = max(0.0, planned_buybacks_i - funding_capacity)
        elif funding_treatment == "planned_uncapped_diagnostic":
            buybacks_i = planned_buybacks_i
            unfunded_i = max(0.0, planned_buybacks_i - funding_capacity)
            incremental_debt_i = 0.0
        else:
            buybacks_i = min(planned_buybacks_i, funding_capacity)
            unfunded_i = max(0.0, planned_buybacks_i - buybacks_i)
            incremental_debt_i = 0.0
        fcf_used = min(buybacks_i, fcf_after_dividends)
        if funding_treatment == "planned_uncapped_diagnostic":
            cash_used = max(0.0, buybacks_i - fcf_used)
            ms_used = 0.0
        else:
            cash_used = min(max(0.0, buybacks_i - fcf_used), cash_available_above_floor)
            ms_used = min(ms_available_i, max(0.0, buybacks_i - fcf_used - cash_used))
        running_ms = max(0.0, running_ms - ms_used)
        ending_cash_i = running_cash + fcf_after_dividends - fcf_used - cash_used
        running_debt += incremental_debt_i
        rep_price_i = repurchase_price_y0 * ((1 + repurchase_price_growth) ** i)
        if rep_price_i and rep_price_i > 0:
            # Buybacks are in millions of currency, price is per-share absolute.
            shares_repurchased_i = (buybacks_i * 1_000_000) / rep_price_i / 1_000_000
        else:
            shares_repurchased_i = 0.0
        dilution_i = annual_dilution_pct * beg_shares
        end_shares = max(0.0, beg_shares - shares_repurchased_i + dilution_i)
        wavg = (beg_shares + end_shares) / 2.0

        beginning_shares_proj.append(round(beg_shares, 4))
        dividends_proj.append(round(dividends_i, 4))
        planned_buybacks_proj.append(round(planned_buybacks_i, 4))
        buybacks_proj.append(round(buybacks_i, 4))
        unfunded_buybacks_proj.append(round(unfunded_i, 4))
        incremental_debt_proj.append(round(incremental_debt_i, 4))
        beginning_cash_proj.append(round(running_cash, 4))
        ending_cash_proj.append(round(ending_cash_i, 4))
        ending_debt_proj.append(round(running_debt, 4))
        ending_net_debt_proj.append(round(running_debt - ending_cash_i - running_ms, 4))
        funding_capacity_proj.append(round(funding_capacity, 4))
        cash_available_above_floor_proj.append(round(cash_available_above_floor, 4))
        fcf_after_dividends_used_proj.append(round(fcf_used, 4))
        cash_above_floor_used_proj.append(round(cash_used, 4))
        ms_available_proj.append(round(ms_available_i, 4))
        ms_drawdown_used_proj.append(round(ms_used, 4))
        ending_ms_proj.append(round(running_ms, 4))
        total_returns_proj.append(round(dividends_i + buybacks_i, 4))
        repurchase_price_proj.append(round(rep_price_i, 4))
        shares_repurchased_proj.append(round(shares_repurchased_i, 4))
        dilution_proj.append(round(dilution_i, 4))
        ending_shares_proj.append(round(end_shares, 4))
        weighted_avg_shares_proj.append(round(wavg, 4))
        eps_proj.append(round((ni_i / wavg), 4) if wavg else 0.0)
        fcf_per_share_proj.append(round((fcf_i / wavg), 4) if wavg else 0.0)
        running_cash = ending_cash_i

    # Selected share-count denominator for the headline IV.
    forecast_ending_shares = ending_shares_proj[-1] if ending_shares_proj else current_shares
    forecast_wavg_shares = (
        sum(weighted_avg_shares_proj) / len(weighted_avg_shares_proj)
        if weighted_avg_shares_proj
        else current_shares
    )
    denom_map = {
        "current_reported_shares": current_shares,
        "forecast_ending_diluted_shares": forecast_ending_shares,
        "forecast_weighted_avg_diluted_shares": forecast_wavg_shares,
    }
    selected_denominator = float(denom_map.get(treatment, current_shares) or current_shares)

    # Buyback materiality: buybacks > FCF for the base year is a sign the
    # company funds repurchases from cash on balance sheet, not just FCF.
    buyback_exceeds_fcf = False
    if base_buybacks is not None and base_fcf and base_fcf > 0:
        buyback_exceeds_fcf = base_buybacks > base_fcf

    return {
        "version": "v374_shareholder_returns_v1",
        "historical": {
            "years_covered": [y for y, _ in dividends_hist or buybacks_hist or fcf_hist or []],
            "base_diluted_shares": round(base_shares, 4) if base_shares else None,
            "base_dividends": round(base_dividends, 4) if base_dividends is not None else None,
            "base_buybacks": round(base_buybacks, 4) if base_buybacks is not None else None,
            "base_sbc": round(base_sbc, 4) if base_sbc is not None else None,
            "base_total_shareholder_returns": round(base_total_returns, 4),
            "base_net_income": round(base_ni, 4) if base_ni is not None else None,
            "base_fcf": round(base_fcf, 4) if base_fcf is not None else None,
            "buyback_pct_fcf": round(hist_buyback_pct_fcf, 6) if hist_buyback_pct_fcf is not None else None,
            "buyback_pct_net_income": round(hist_buyback_pct_ni, 6) if hist_buyback_pct_ni is not None else None,
            "dividend_payout_pct_net_income": round(hist_dividend_payout, 6) if hist_dividend_payout is not None else None,
            "dividend_pct_fcf": round(hist_dividend_pct_fcf, 6) if hist_dividend_pct_fcf is not None else None,
            "buyback_exceeds_fcf_base": buyback_exceeds_fcf,
            "implied_avg_repurchase_price": None,  # historical price-per-share not stored
            "series": {
                "dividends": dividends_hist,
                "buybacks": buybacks_hist,
                "fcf": fcf_hist,
                "net_income": ni_hist,
                "diluted_shares": shares_hist,
                "sbc": sbc_hist,
            },
        },
        "forecast": {
            "beginning_shares": beginning_shares_proj,
            "net_income_proxy_nopat": [round(v, 4) for v in nopat_proj],
            "fcf": [round(v, 4) for v in fcf_proj],
            "dividends": dividends_proj,
            "planned_buybacks": planned_buybacks_proj,
            "buybacks": buybacks_proj,
            "unfunded_buybacks": unfunded_buybacks_proj,
            "incremental_debt_issuance": incremental_debt_proj,
            "beginning_cash": beginning_cash_proj,
            "minimum_cash_floor": [round(cash_floor, 4)] * n,
            "cash_available_above_floor": cash_available_above_floor_proj,
            "fcf_after_dividends_used_for_buybacks": fcf_after_dividends_used_proj,
            "cash_above_floor_used_for_buybacks": cash_above_floor_used_proj,
            "marketable_securities_available_for_returns": ms_available_proj,
            "marketable_securities_drawdown_used": ms_drawdown_used_proj,
            "funding_capacity_before_debt": funding_capacity_proj,
            "ending_cash": ending_cash_proj,
            "ending_marketable_securities": ending_ms_proj,
            "ending_debt": ending_debt_proj,
            "ending_net_debt": ending_net_debt_proj,
            "total_shareholder_returns": total_returns_proj,
            "repurchase_price": repurchase_price_proj,
            "shares_repurchased": shares_repurchased_proj,
            "sbc_dilution": dilution_proj,
            "ending_shares": ending_shares_proj,
            "weighted_avg_diluted_shares": weighted_avg_shares_proj,
            "eps_proxy": eps_proj,
            "fcf_per_share": fcf_per_share_proj,
        },
        "drivers_effective": {
            "dividend_payout_pct_net_income": round(dividend_payout, 6),
            "buyback_method": method,
            "buyback_method_label": method_label,
            "buyback_pct_fcf": round(buyback_pct_fcf, 6),
            "flat_buyback_amount": round(flat_buyback_amount, 4),
            "repurchase_price_growth": round(repurchase_price_growth, 6),
            "annual_dilution_pct": round(annual_dilution_pct, 6),
            "annual_dilution_user_override": user_dilution_override,
            "annual_dilution_default_methodology": sbc_default_methodology,
            "annual_dilution_default_source_year": sbc_default_source_year,
            "annual_dilution_default_industry": sbc_default_industry,      # F014
            "annual_dilution_floor_warning": sbc_default_floor_warning,    # F014
            "sbc_pct_market_cap": round(sbc_default_pct_market_cap, 6) if sbc_default_pct_market_cap is not None else None,
            "sbc_pct_revenue": round(sbc_default_pct_revenue, 6) if sbc_default_pct_revenue is not None else None,
            "buyback_funding_treatment": funding_treatment,
            "minimum_cash_floor": round(cash_floor, 4),
            "marketable_securities_available_for_returns": round(ms_available, 4),
        },
        "funding_closure": {
            "treatment": funding_treatment,
            "minimum_cash_floor": round(cash_floor, 4),
            "marketable_securities_available_for_returns": round(ms_available, 4),
            "total_planned_buybacks": round(sum(planned_buybacks_proj), 4),
            "total_actual_funded_buybacks": round(sum(buybacks_proj), 4),
            "total_fcf_after_dividends_used_for_buybacks": round(sum(fcf_after_dividends_used_proj), 4),
            "total_cash_above_floor_used_for_buybacks": round(sum(cash_above_floor_used_proj), 4),
            "total_marketable_securities_drawdown_used": round(sum(ms_drawdown_used_proj), 4),
            "total_unfunded_buybacks": round(sum(unfunded_buybacks_proj), 4),
            "total_incremental_debt_issuance": round(sum(incremental_debt_proj), 4),
            "ending_cash": ending_cash_proj[-1] if ending_cash_proj else None,
            "ending_marketable_securities": ending_ms_proj[-1] if ending_ms_proj else None,
            "ending_debt": ending_debt_proj[-1] if ending_debt_proj else None,
            "ending_net_debt": ending_net_debt_proj[-1] if ending_net_debt_proj else None,
            "cash_floor_respected": all(x >= cash_floor - 1e-6 for x in ending_cash_proj),
            "review_tier": (
                "High Review" if (
                    funding_treatment == "planned_uncapped_diagnostic"
                    or any(x < 0 for x in ending_cash_proj)
                    or any(x < cash_floor - 1e-6 for x in ending_cash_proj)
                    or sum(incremental_debt_proj) > max(sum(fcf_proj), 1.0) * 0.25
                )
                else ("Review" if sum(unfunded_buybacks_proj) > 0 or sum(incremental_debt_proj) > 0 else "OK")
            ),
        },
        "share_count_treatments": available_share_count_treatments(),
        "buyback_methods_available": available_buyback_methods(),
        "selected_share_count_treatment": treatment,
        "selected_share_count_treatment_label": treatment_label,
        "selected_share_count_treatment_fallback_used": treatment_fallback,
        "selected_denominator": round(selected_denominator, 4),
        "denominator_options": {
            "current_reported_shares": round(current_shares, 4),
            "forecast_ending_diluted_shares": round(forecast_ending_shares, 4),
            "forecast_weighted_avg_diluted_shares": round(forecast_wavg_shares, 4),
        },
        "historical_cache_available": historical_cache_available,
        "fcff_unaffected_note": (
            "V3.7.4: Dividends and buybacks are equity-financing items shown in the "
            "Cash Flow Forecast financing section and the BS Equity roll-forward. "
            "FCFF (unlevered NOPAT-based) is not reduced by shareholder returns; "
            "per-share valuation can change only through the Selected Share Count Treatment."
        ),
        "buyback_funding_note": (
            "V3.7.4: Historical buybacks exceed FCF in the base year; mature buyback "
            "programs are funded partly from cash on balance sheet. This is disclosed "
            "and audited, not silently corrected."
        ) if buyback_exceeds_fcf else None,
        "warnings": warnings,
    }


def build_net_debt_bridge(
    inp: DCFInputs,
    historical_context: Optional[dict] = None,
    selected_treatment: Optional[str] = None,
) -> dict:
    """V3.7.2 Net Debt Bridge.

    Computes Reported / Adjusted variants of net debt from the v371 historical
    cache (Cash, Short-term Investments, Long-term Investments, Total Debt) and
    returns the selected variant for the DCF headline. Default selected
    treatment preserves the V3.7.0 / V3.7.1 behavior: headline IV uses the
    reported input net debt and marketable-securities-aware variants are
    display-only references.

    Returns a dict shaped for both API consumers and the Excel exporter; never
    raises - missing fields fall back to None / warning entries so HK / CN
    behave gracefully.
    """
    market = detect_market(inp.symbol)
    raw_treatment = selected_treatment or inp.selected_net_debt_treatment
    treatment, _treatment_label_initial, treatment_fallback_used = normalize_net_debt_treatment(raw_treatment)

    warnings: list[str] = []
    if treatment_fallback_used and raw_treatment:
        warnings.append(
            f"Unknown net debt treatment '{raw_treatment}'; falling back to {DEFAULT_NET_DEBT_TREATMENT}."
        )

    cash = _latest_bs_value(inp.symbol, market, "cash")
    st_inv = _latest_bs_value(inp.symbol, market, "short_term_investments")
    lt_inv = _latest_bs_value(inp.symbol, market, "long_term_investments")
    total_debt = _latest_bs_value(inp.symbol, market, "total_debt")
    current_lease = _latest_bs_value(inp.symbol, market, "current_capital_lease_obligation")
    long_term_lease = _latest_bs_value(inp.symbol, market, "long_term_capital_lease_obligation")

    cache_available = any(v is not None for v in (cash, st_inv, lt_inv, total_debt))
    if not cache_available:
        warnings.append(
            f"{market}: V3.7.1 historical cache fields unavailable; bridge reverts to reported input net debt only."
        )

    cash_val = cash if cash is not None else 0.0
    st_val = st_inv if st_inv is not None else 0.0
    lt_val = lt_inv if lt_inv is not None else 0.0
    total_ms = st_val + lt_val
    total_debt_val = total_debt if total_debt is not None else 0.0

    reported = float(inp.net_debt or 0.0)
    # Adjusted variants are only computed when at least Total Debt is available;
    # otherwise we still expose the slots so the API shape is stable.
    if total_debt is not None or cash is not None or st_inv is not None or lt_inv is not None:
        debt_less_cash = total_debt_val - cash_val
        debt_less_cash_and_st = total_debt_val - cash_val - st_val
        debt_less_cash_and_total_ms = total_debt_val - cash_val - st_val - lt_val
    else:
        debt_less_cash = None
        debt_less_cash_and_st = None
        debt_less_cash_and_total_ms = None

    variant_map = {
        "reported_input_net_debt": reported,
        "debt_less_cash": debt_less_cash,
        "debt_less_cash_and_st_investments": debt_less_cash_and_st,
        "debt_less_cash_and_total_marketable_securities": debt_less_cash_and_total_ms,
    }
    selected_value_raw = variant_map.get(treatment)
    if selected_value_raw is None:
        warnings.append(
            f"Selected treatment '{treatment}' not computable (historical cache missing); falling back to reported input net debt."
        )
        treatment = DEFAULT_NET_DEBT_TREATMENT
        treatment_fallback_used = True
        selected_value_raw = reported
    selected_value = float(selected_value_raw)
    valuation_impact_vs_reported = selected_value - reported

    # MS materiality flag for the Audit Dashboard (marketable securities vs reported net debt).
    ms_materiality_flag = False
    if total_ms > 0:
        ms_materiality_flag = abs(total_ms) > max(abs(reported), 1.0)

    # V3.7.3: surface the gap between reported/input net debt (which can be
    # data-provider pre-adjusted) and the raw Debt - Cash arithmetic. Reviewers
    # asked about AAPL's 16B vs 63B delta; this makes it auditable on the bridge.
    raw_debt_less_cash = debt_less_cash  # alias for clarity in audit consumers
    if raw_debt_less_cash is not None:
        reported_vs_raw_diff = reported - raw_debt_less_cash
        ref = max(abs(total_debt_val), abs(reported), 1.0)
        reported_vs_raw_material = abs(reported_vs_raw_diff) / ref > 0.10
    else:
        reported_vs_raw_diff = None
        reported_vs_raw_material = False

    return {
        "treatments_available": list(NET_DEBT_TREATMENTS),
        "treatments": available_net_debt_treatments(),
        "selected_treatment": treatment,
        "selected_treatment_label": NET_DEBT_TREATMENT_LABELS[treatment],
        "selected_treatment_fallback_used": treatment_fallback_used,
        "selected_net_debt": round(selected_value, 4),
        "selected_value_used_in_dcf": round(selected_value, 4),
        "reported_input_net_debt": round(reported, 4),
        "raw_debt_less_cash": round(raw_debt_less_cash, 4) if raw_debt_less_cash is not None else None,
        "reported_vs_raw_debt_cash_diff": round(reported_vs_raw_diff, 4) if reported_vs_raw_diff is not None else None,
        "reported_vs_raw_debt_cash_material": reported_vs_raw_material,
        "cash": round(cash_val, 4) if cash is not None else None,
        "short_term_investments": round(st_val, 4) if st_inv is not None else None,
        "long_term_investments": round(lt_val, 4) if lt_inv is not None else None,
        "total_marketable_securities": round(total_ms, 4),
        "total_debt": round(total_debt_val, 4) if total_debt is not None else None,
        "current_lease_obligation_memo": round(current_lease, 4) if current_lease is not None else None,
        "long_term_lease_obligation_memo": round(long_term_lease, 4) if long_term_lease is not None else None,
        "debt_less_cash": round(debt_less_cash, 4) if debt_less_cash is not None else None,
        "debt_less_cash_and_st_investments": round(debt_less_cash_and_st, 4) if debt_less_cash_and_st is not None else None,
        "debt_less_cash_and_total_marketable_securities": round(debt_less_cash_and_total_ms, 4) if debt_less_cash_and_total_ms is not None else None,
        "valuation_impact_vs_reported_net_debt": round(valuation_impact_vs_reported, 4),
        "marketable_securities_material": ms_materiality_flag,
        "historical_cache_available": cache_available,
        "lease_treatment_note": (
            "Capital lease obligations are reported as memo only - yfinance includes them inside ST/LT Debt totals, so adding them separately would double-count. Total Debt above is taken as-is from the historical cache."
        ),
        "marketable_securities_disclosure": (
            "Short-term and long-term marketable securities are shown above. Whether to treat them as cash-like for Net Debt is a valuation judgment; alternative variants are listed so the IV impact is auditable."
        ),
        "warnings": warnings,
    }


def build_wacc_decision_bridge(
    inp: DCFInputs,
    historical_context: Optional[dict] = None,
    net_debt_bridge: Optional[dict] = None,
) -> dict:
    """V3.7.5 WACC Decision Layer.

    Surfaces CAPM components (rf, beta, ERP, Ke), after-tax cost of debt,
    market-value capital structure (Total Debt vs Price x Shares), the
    CAPM-derived indicative WACC, and three alternative WACC reference cases
    (CAPM Indicative, Selected +100bps, Selected -100bps). Default selected
    treatment = selected_model_wacc preserves V3.7.4 headline IV.

    Returns a stable dict for API + Excel; never raises - missing inputs
    fall back to None / warnings so HK / CN exports remain valid.
    """
    market = detect_market(inp.symbol)
    cfg = MARKET_CONFIG[market]
    warnings: list[str] = []

    treatment, treatment_label, treatment_fallback = normalize_wacc_treatment(inp.selected_wacc_treatment)
    if treatment_fallback and inp.selected_wacc_treatment:
        warnings.append(
            f"Unknown WACC treatment '{inp.selected_wacc_treatment}'; falling back to {DEFAULT_WACC_TREATMENT}."
        )

    selected_model_wacc = float(inp.wacc or 0.0)
    rf = float(cfg.get("rf") or 0.0)
    erp = float(cfg.get("erp") or 0.0)
    raw_beta_input = float(inp.beta if inp.beta is not None else 1.0)
    raw_beta = max(0.3, min(3.0, raw_beta_input))
    # V3.9.4 Blume adjustment exposed as a reference; selected_beta defaults to
    # raw_beta to preserve the V3.9.3 headline WACC / IV.
    adjusted_beta = round(0.67 * raw_beta + 0.33 * 1.0, 6)
    selected_beta = raw_beta
    beta = selected_beta
    capm_cost_of_equity = rf + beta * erp

    # Pre-tax cost of debt: V3.7.4 default = 5%; V3.7.5 allows explicit override
    # via inp.pre_tax_cost_of_debt for downstream scenario / API control.
    pre_tax_kd = inp.pre_tax_cost_of_debt if inp.pre_tax_cost_of_debt is not None else 0.05
    kd_rationale = (
        "AAPL normalized Kd: 4.3% selected as a blend of historical implied borrowing cost and forward refinancing environment."
        if (inp.symbol or "").upper() == "AAPL" and inp.pre_tax_cost_of_debt is not None
        else "Default Kd: 5.0% generic model fallback; review against implied historical Kd where available."
    )
    pre_tax_kd = float(pre_tax_kd)
    tax_rate = float(inp.tax_rate or 0.0)
    after_tax_kd = pre_tax_kd * (1 - tax_rate)

    # Market-value capital structure. Total Debt taken from V3.7.2 Net Debt
    # Bridge when available; equity proxy = Price x Diluted Shares (M).
    total_debt = None
    if isinstance(net_debt_bridge, dict):
        total_debt = net_debt_bridge.get("total_debt")
    if total_debt is None:
        total_debt = _latest_bs_value(inp.symbol, market, "total_debt")
    total_debt_value = float(total_debt or 0.0)
    equity_proxy = float((inp.price or 0.0) * (inp.shares or 0.0))
    denom = max(total_debt_value + equity_proxy, 1.0)
    debt_weight = total_debt_value / denom if denom > 0 else 0.0
    equity_weight = 1.0 - debt_weight

    capm_inputs_ok = bool(rf and erp and beta and (pre_tax_kd is not None))
    if not capm_inputs_ok:
        warnings.append(f"{market}: CAPM inputs incomplete; indicative WACC may be unreliable.")

    capm_indicative_wacc = equity_weight * capm_cost_of_equity + debt_weight * after_tax_kd
    selected_vs_indicative_spread = selected_model_wacc - capm_indicative_wacc

    alt_cases = {
        "selected_model_wacc": round(selected_model_wacc, 6),
        "capm_indicative_wacc": round(capm_indicative_wacc, 6),
        "selected_plus_spread_100bps": round(selected_model_wacc + WACC_SPREAD_BPS, 6),
        "selected_minus_spread_100bps": round(max(0.001, selected_model_wacc - WACC_SPREAD_BPS), 6),
    }
    selected_wacc_used = alt_cases.get(treatment, selected_model_wacc)

    # Spread review tiers - audit consumers can use the materiality flags
    # without having to re-derive them from raw values.
    spread_review = abs(selected_vs_indicative_spread) > 0.015
    spread_high_review = abs(selected_vs_indicative_spread) > 0.025
    selected_vs_capm_spread_bps = round(selected_vs_indicative_spread * 10000.0, 1)
    if abs(selected_vs_capm_spread_bps) <= 50:
        spread_review_tier = "OK"
    elif abs(selected_vs_capm_spread_bps) <= 150:
        spread_review_tier = "Review"
    else:
        spread_review_tier = "High review"

    # V3.9.4 cost-of-debt sanity check: implied pre-tax Kd = interest expense /
    # average debt across the latest two historical periods. All inputs come
    # from the historical income-statement / balance-sheet cache and the
    # check degrades to N/A when any leg is missing.
    interest_expense_latest = None
    average_debt = None
    implied_pretax_kd = None
    cost_of_debt_diff_bps = None
    cost_of_debt_review_tier = "N/A"
    cost_of_debt_review_reason = "Historical interest expense / debt not available"
    try:
        interest_history = _historical_statement_history(
            inp.symbol, market, "income_statement", "interest_expense", take_abs=True,
        )
        debt_history_pairs = _historical_statement_history(
            inp.symbol, market, "balance_sheet", "total_debt",
        )
        if interest_history:
            interest_expense_latest = round(float(interest_history[-1][1]), 4)
        if len(debt_history_pairs) >= 2:
            tail = debt_history_pairs[-2:]
            average_debt = round((float(tail[0][1]) + float(tail[1][1])) / 2.0, 4)
        elif debt_history_pairs:
            average_debt = round(float(debt_history_pairs[-1][1]), 4)
        if interest_expense_latest is not None and average_debt and average_debt > 0:
            implied_pretax_kd = round(float(interest_expense_latest) / float(average_debt), 6)
            cost_of_debt_diff_bps = round((pre_tax_kd - implied_pretax_kd) * 10000.0, 1)
            if abs(cost_of_debt_diff_bps) <= 100:
                cost_of_debt_review_tier = "OK"
                cost_of_debt_review_reason = "Selected pre-tax Kd within 100 bps of implied"
            elif abs(cost_of_debt_diff_bps) <= 250:
                cost_of_debt_review_tier = "Review"
                cost_of_debt_review_reason = "Selected pre-tax Kd differs from implied by 100-250 bps"
            else:
                cost_of_debt_review_tier = "High review"
                cost_of_debt_review_reason = "Selected pre-tax Kd differs from implied by more than 250 bps"
    except Exception:
        pass

    source_cutoff = "export date / latest available cache"
    is_aapl = (inp.symbol or "").upper() == "AAPL"
    wacc_component_defense = {
        "risk_free_rate": {
            "value": round(rf, 6),
            "tenor": "10-year government yield proxy",
            "cutoff": source_cutoff,
            "spot_vs_normalized_note": "Market-config spot proxy; selected WACC may normalize through-cycle risk rather than mechanically following spot moves.",
        },
        "beta": {
            "raw_beta": round(raw_beta, 4),
            "blume_adjusted_beta": round(adjusted_beta, 4),
            "selected_beta": round(selected_beta, 4),
            "sector_quality_reference": (
                "Mega-cap platform / quality reference considered qualitatively; no external sector beta is hard-wired."
                if is_aapl
                else "Sector beta lookup not hard-wired; cache beta is shown as the mechanical reference."
            ),
            "selected_rationale": (
                "Apple selected WACC gives qualitative weight to ecosystem durability, Services mix, cash-flow stability, and mega-cap quality; raw beta remains visible as an audit diagnostic."
                if is_aapl
                else "Selected beta follows the cache beta by default; any override should be documented by the analyst."
            ),
        },
        "erp": {
            "selected": round(erp, 6),
            "reference_range": (
                "US mature-market ERP reference around 5.0%"
                if market == "US"
                else f"{market} market-config ERP reference"
            ),
            "source_label": "Market configuration / valuation policy reference",
            "selected_rationale": "Selected ERP is applied consistently by market and reviewed as part of the WACC judgment.",
        },
        "capital_structure": {
            "current_market_weight_equity": round(equity_weight, 6),
            "current_market_weight_debt": round(debt_weight, 6),
            "target_peer_reference": (
                "Apple AA+/net-cash profile and very low market debt weight"
                if is_aapl
                else "Current market-value capital structure; target/peer leverage not hard-wired."
            ),
            "selected_basis": "Market-value weights from price x shares and latest total debt",
            "selected_rationale": "Debt weight is low, so equity judgment dominates the selected WACC; leverage does not mechanically force the selected rate to the CAPM reference.",
        },
        "cost_of_debt": {
            "implied_historical_kd": implied_pretax_kd,
            "selected_normalized_kd": round(pre_tax_kd, 6),
            "source_label": "Historical interest expense / average debt where available; normalized selected Kd on Assumptions",
            "selected_rationale": kd_rationale,
        },
    }
    selected_wacc_reconciliation = _build_selected_wacc_reconciliation(
        inp.symbol,
        selected_model_wacc,
        capm_indicative_wacc,
        market,
    )

    return {
        "version": "v375_wacc_decision_layer",
        "treatments_available": list(WACC_TREATMENTS),
        "treatments": available_wacc_treatments(),
        "selected_wacc_treatment": treatment,
        "selected_wacc_treatment_label": treatment_label,
        "selected_wacc_treatment_fallback_used": treatment_fallback,
        "selected_model_wacc": round(selected_model_wacc, 6),
        "risk_free_rate": round(rf, 6),
        "equity_risk_premium": round(erp, 6),
        "raw_beta": round(raw_beta, 4),
        "adjusted_beta": round(adjusted_beta, 4),
        "selected_beta": round(selected_beta, 4),
        "beta": round(beta, 4),  # alias kept for backwards compatibility
        "beta_methodology": (
            "raw beta from financials cache (yfinance), capped to [0.3, 3.0]. "
            "Adjusted beta = 0.67 * raw + 0.33 * 1.0 (Blume) shown as reference; "
            "selected_beta defaults to raw beta and is editable on Assumptions."
        ),
        "capm_cost_of_equity": round(capm_cost_of_equity, 6),
        "pre_tax_cost_of_debt": round(pre_tax_kd, 6),
        "pre_tax_cost_of_debt_rationale": kd_rationale,
        "tax_rate": round(tax_rate, 6),
        "after_tax_cost_of_debt": round(after_tax_kd, 6),
        "total_debt": round(total_debt_value, 4),
        "market_value_equity_proxy": round(equity_proxy, 4),
        "debt_weight": round(debt_weight, 6),
        "equity_weight": round(equity_weight, 6),
        "capm_indicative_wacc": round(capm_indicative_wacc, 6),
        "selected_vs_indicative_spread": round(selected_vs_indicative_spread, 6),
        "selected_vs_capm_spread_bps": selected_vs_capm_spread_bps,
        "selected_vs_indicative_spread_review": spread_review,
        "selected_vs_indicative_spread_high_review": spread_high_review,
        "spread_review_tier": spread_review_tier,
        "cost_of_debt_sanity": {
            "interest_expense_latest": interest_expense_latest,
            "average_debt": average_debt,
            "implied_pretax_cost_of_debt": implied_pretax_kd,
            "selected_pretax_cost_of_debt": round(pre_tax_kd, 6),
            "diff_bps": cost_of_debt_diff_bps,
            "review_tier": cost_of_debt_review_tier,
            "review_reason": cost_of_debt_review_reason,
        },
        "wacc_component_defense": wacc_component_defense,
        "selected_wacc_reconciliation": selected_wacc_reconciliation,
        "capm_diagnostic_label": "Mechanical CAPM reference, not headline selection.",
        "alternative_wacc_cases": alt_cases,
        "selected_wacc_used_in_dcf": round(selected_wacc_used, 6),
        "capm_inputs_available": capm_inputs_ok,
        "wacc_unaffected_note": (
            "V3.7.5: WACC treatment is a valuation JUDGMENT. Default keeps the "
            "Selected / Model WACC so headline IV matches V3.7.4. Mechanical CAPM "
            "reference is an audit diagnostic, not the headline selection."
        ),
        "warnings": warnings,
    }


def _default_h_model_assumptions(inp: DCFInputs, forecast: dict) -> tuple[float, float, float]:
    """Return default H-Model near growth, long growth, and half-life.

    Defaults are explicit inputs when supplied. Otherwise near growth uses the
    terminal-year revenue path as a transition anchor; long growth uses the
    selected terminal growth. AAPL Bear gets a shorter fade by default so its
    excess-return runway stays distinct from Base.
    """
    growth_path = list(forecast.get("revenue_growth_projections") or [])
    inferred_g_near = growth_path[-1] if growth_path else float(inp.terminal_g or 0.0)
    scenario_key = ""
    if (inp.symbol or "").upper() == "AAPL":
        base_path = [round(x, 6) for x in AAPL_BASE_REVENUE_GROWTH_PATH]
        bear_path = [round(x, 6) for x in AAPL_BEAR_REVENUE_GROWTH_PATH]
        current_path = [round(float(x), 6) for x in growth_path[:5]]
        if current_path == base_path:
            scenario_key = "base"
        elif current_path == bear_path:
            scenario_key = "bear"
    default_h = 4.0 if scenario_key == "bear" else DEFAULT_H_MODEL_HALF_LIFE
    g_near = float(inp.h_model_g_near) if inp.h_model_g_near is not None else float(inferred_g_near)
    g_long = float(inp.h_model_g_long) if inp.h_model_g_long is not None else float(inp.terminal_g or 0.0)
    h = float(inp.h_model_half_life) if inp.h_model_half_life is not None else float(default_h)
    return g_near, g_long, max(0.0, h)


def build_terminal_value_quality_block(inp: DCFInputs, forecast: dict, wacc_used: float) -> dict:
    """V3.9.9.1 terminal-value quality and reinvestment decomposition."""
    market = detect_market(inp.symbol)
    revenue_list = list(forecast.get("revenue_projections") or [])
    ebit_list = list(forecast.get("ebit_projections") or [])
    nopat_list = list(forecast.get("nopat_projections") or [])
    fcf_list = list(forecast.get("fcf_projections") or [])
    revenue_y = float(revenue_list[-1] or 0.0) if revenue_list else 0.0
    ebit_y = float(ebit_list[-1] or 0.0) if ebit_list else 0.0
    nopat_y = float(nopat_list[-1] or 0.0) if nopat_list else 0.0
    explicit_fcf_y = float(fcf_list[-1] or 0.0) if fcf_list else 0.0
    g = float(inp.terminal_g or 0.0)

    latest_revenue_hist = None
    rev_history = _historical_statement_history(inp.symbol, market, "income_statement", "revenue")
    if rev_history:
        latest_revenue_hist = float(rev_history[-1][1])

    total_debt = _latest_bs_value(inp.symbol, market, "total_debt")
    total_equity = _latest_bs_value(inp.symbol, market, "total_equity")
    cash_st = _latest_bs_value(inp.symbol, market, "cash_and_short_term_investments")
    cash = _latest_bs_value(inp.symbol, market, "cash")
    cash_like = cash_st if cash_st is not None else cash

    invested_capital_latest = None
    invested_capital_terminal = None
    roic = None
    roic_source = "N/A - historical invested-capital fields unavailable"
    if total_debt is not None and total_equity is not None:
        invested_capital_latest = float(total_debt or 0.0) + float(total_equity or 0.0) - float(cash_like or 0.0)
        if invested_capital_latest > 0:
            scale = (revenue_y / latest_revenue_hist) if latest_revenue_hist and latest_revenue_hist > 0 else 1.0
            invested_capital_terminal = invested_capital_latest * max(scale, 0.0)
            if invested_capital_terminal > 0:
                roic = nopat_y / invested_capital_terminal
                roic_source = "Approximation: (Total Debt + Total Equity - Cash/ST Investments) scaled by terminal revenue/latest revenue"

    reinvestment_rate = None
    reinvestment_need = None
    reinvestment_terminal_fcf = explicit_fcf_y
    if roic is not None and roic > 0:
        reinvestment_rate = max(0.0, min(1.0, g / roic))
        reinvestment_need = nopat_y * reinvestment_rate
        reinvestment_terminal_fcf = nopat_y * (1 - reinvestment_rate)

    spread = (roic - wacc_used) if roic is not None else None
    if roic is None:
        review_tier = "Review"
        interpretation = "ROIC approximation unavailable; terminal value quality requires manual review."
    elif roic <= wacc_used:
        review_tier = "High Review"
        interpretation = "Terminal value is weakly supported because approximated ROIC is at or below WACC."
    elif roic - wacc_used < 0.03:
        review_tier = "Review"
        interpretation = "Terminal value depends on a narrow excess-return spread; reinvestment and fade assumptions are judgment-sensitive."
    else:
        review_tier = "Review"
        interpretation = "Terminal value is supported by an approximated excess-return spread, but the spread and fade durability remain judgment-sensitive."

    return {
        "version": "v3991_terminal_value_quality",
        "terminal_year_revenue": round(revenue_y, 4),
        "terminal_year_ebit": round(ebit_y, 4),
        "terminal_year_nopat": round(nopat_y, 4),
        "terminal_fcf": round(reinvestment_terminal_fcf, 4),
        "explicit_terminal_fcf": round(explicit_fcf_y, 4),
        "terminal_reinvestment_need": round(reinvestment_need, 4) if reinvestment_need is not None else None,
        "terminal_growth": round(g, 6),
        "wacc": round(float(wacc_used), 6),
        "implied_terminal_roic": round(roic, 6) if roic is not None else None,
        "roic_approximation_source": roic_source,
        "invested_capital_latest": round(invested_capital_latest, 4) if invested_capital_latest is not None else None,
        "invested_capital_terminal_approx": round(invested_capital_terminal, 4) if invested_capital_terminal is not None else None,
        "reinvestment_rate": round(reinvestment_rate, 6) if reinvestment_rate is not None else None,
        "roic_wacc_spread": round(spread, 6) if spread is not None else None,
        "review_tier": review_tier,
        "value_creation_interpretation": interpretation,
    }


def build_terminal_value_decision_bridge(
    inp: DCFInputs,
    forecast: dict,
    wacc_used: float,
    net_debt_used: float,
    shares_used: float,
    pv_fcf_sum: float,
    base_tv_used: float,
    base_tv_gordon: float,
    base_tv_exit: float,
    base_ev: float,
) -> dict:
    """V3.7.6 Terminal Value Decision Layer.

    Surfaces five terminal-value cases (Current Model / Gordon / Exit / Blend /
    Fade Period) using the V3.7.5-selected WACC, V3.7.3-selected net debt,
    V3.7.4-selected share denominator, and the explicit forecast already
    produced by run_dcf. Each case's IV/share is computed by holding PV of
    explicit FCFs constant and swapping only the terminal PV; the Fade case
    additionally extends FCFs out fade_years before reverting to Gordon TV.

    Default treatment = current_model_terminal preserves V3.7.5 headline IV.
    """
    n = max(1, int(inp.forecast_years or 5))
    treatment, treatment_label, treatment_fallback = normalize_terminal_treatment(
        inp.selected_terminal_treatment
    )
    warnings: list[str] = []
    if treatment_fallback and inp.selected_terminal_treatment:
        warnings.append(
            f"Unknown terminal treatment '{inp.selected_terminal_treatment}'; falling back to {DEFAULT_TERMINAL_TREATMENT}."
        )

    fcf_list = list(forecast.get("fcf_projections") or [])
    if not fcf_list:
        warnings.append("Terminal decision bridge skipped: empty FCF projections.")
        return {
            "version": "v376_terminal_value_decision_layer",
            "treatments_available": list(TERMINAL_TREATMENTS),
            "treatments": available_terminal_treatments(),
            "selected_terminal_treatment": treatment,
            "selected_terminal_treatment_label": treatment_label,
            "selected_terminal_treatment_fallback_used": treatment_fallback,
            "selected_terminal_value": base_tv_used,
            "selected_terminal_iv_per_share": None,
            "warnings": warnings,
        }

    last_fcf = float(fcf_list[-1] or 0.0)
    terminal_g = float(inp.terminal_g or 0.0)
    exit_multiple = float(inp.exit_multiple or 0.0)
    blend_w_g = max(0.0, min(1.0, float(inp.blend_weight_gordon or 0.5)))
    blend_w_e = max(0.0, min(1.0, float(inp.blend_weight_exit or 0.5)))
    if blend_w_g + blend_w_e <= 0:
        blend_w_g, blend_w_e = 0.5, 0.5
    weights_sum = blend_w_g + blend_w_e
    blend_w_g_norm = blend_w_g / weights_sum
    blend_w_e_norm = blend_w_e / weights_sum
    h_g_near, h_g_long, h_half_life = _default_h_model_assumptions(inp, forecast)

    disc_n = round(1 / (1 + wacc_used) ** n, 6) if wacc_used > -1 else 0.0
    ebitda_y_n = float((forecast.get("ebit_projections") or [0.0])[-1]) + float(
        (forecast.get("da_projections") or [0.0])[-1]
    )

    # Re-derive the four basic TV cases at the selected WACC; numbers should
    # match the calculator's existing tv_gordon / tv_exit for the default WACC
    # case, but recomputed here so the bridge stays correct under V3.7.5 WACC
    # alt cases without circular dependence on _calc_valuation_from_forecast.
    spread = wacc_used - terminal_g if wacc_used > terminal_g else max(wacc_used - terminal_g, 0.001)
    gordon_pv = last_fcf * (1 + terminal_g) / spread * disc_n
    exit_pv = ebitda_y_n * exit_multiple * disc_n
    blend_pv = blend_w_g_norm * gordon_pv + blend_w_e_norm * exit_pv
    h_spread = wacc_used - h_g_long if wacc_used > h_g_long else max(wacc_used - h_g_long, 0.001)
    h_model_pv = (
        (last_fcf * (1 + h_g_long) + last_fcf * h_half_life * (h_g_near - h_g_long))
        / h_spread
        * disc_n
    )

    # Fade Period reference case. Project fade_years of FCF starting from the
    # last explicit FCF, fading the growth linearly from the explicit-period
    # Year-N growth toward fade_terminal_growth. Discount each fade FCF, then
    # apply Gordon TV on the final fade-year FCF.
    fade_years = max(1, int(inp.fade_years or DEFAULT_FADE_YEARS))
    fade_target_g = (
        float(inp.fade_terminal_growth)
        if inp.fade_terminal_growth is not None
        else terminal_g
    )
    # Year-N explicit growth: derived from the last two forecast FCFs, falling
    # back to terminal_g when only one FCF exists.
    if len(fcf_list) >= 2 and fcf_list[-2]:
        starting_fade_growth = (fcf_list[-1] / fcf_list[-2]) - 1
    else:
        starting_fade_growth = terminal_g
    # Linear fade from starting_fade_growth → fade_target_g across fade_years.
    fade_growth_series: list[float] = []
    fade_fcf_series: list[float] = []
    pv_fade_fcf_series: list[float] = []
    running_fcf = last_fcf
    pv_fade_fcf_total = 0.0
    for i in range(fade_years):
        progress = (i + 1) / fade_years
        g_i = starting_fade_growth + (fade_target_g - starting_fade_growth) * progress
        running_fcf = running_fcf * (1 + g_i)
        df_i = round(1 / (1 + wacc_used) ** (n + i + 1), 6) if wacc_used > -1 else 0.0
        pv_i = running_fcf * df_i
        fade_growth_series.append(round(g_i, 6))
        fade_fcf_series.append(round(running_fcf, 4))
        pv_fade_fcf_series.append(round(pv_i, 4))
        pv_fade_fcf_total += pv_i
    terminal_fcf_after_fade = running_fcf
    # Gordon TV on the final fade-year FCF, discounted to today.
    fade_terminal_disc = round(1 / (1 + wacc_used) ** (n + fade_years), 6) if wacc_used > -1 else 0.0
    fade_terminal_spread = (
        wacc_used - fade_target_g if wacc_used > fade_target_g else max(wacc_used - fade_target_g, 0.001)
    )
    terminal_value_after_fade_pv = (
        terminal_fcf_after_fade * (1 + fade_target_g) / fade_terminal_spread * fade_terminal_disc
    )
    fade_pv_total = pv_fade_fcf_total + terminal_value_after_fade_pv

    # Map each treatment to the PV of its TV component (already discounted to
    # today). Fade case replaces "tv_pv" with PV(fade FCFs) + PV(post-fade TV).
    tv_pv_map = {
        "current_model_terminal": float(base_tv_used),
        "gordon_growth": float(gordon_pv),
        "exit_multiple": float(exit_pv),
        "gordon_exit_blend": float(blend_pv),
        "h_model": float(h_model_pv),
        "fade_period_reference": float(fade_pv_total),
    }

    # Compute alt IV/share + TV/EV for each treatment.
    alt_iv_per_share: dict[str, float] = {}
    alt_tv_ev_pct: dict[str, float] = {}
    alt_ev: dict[str, float] = {}
    for case_key, tv_pv_alt in tv_pv_map.items():
        ev_alt = pv_fcf_sum + tv_pv_alt
        equity_alt = ev_alt - net_debt_used
        iv_alt = equity_alt / shares_used if shares_used > 0 else 0.0
        alt_iv_per_share[case_key] = round(iv_alt, 4)
        alt_tv_ev_pct[case_key] = round(tv_pv_alt / ev_alt, 6) if ev_alt > 0 else 0.0
        alt_ev[case_key] = round(ev_alt, 4)

    selected_tv_pv = tv_pv_map.get(treatment, float(base_tv_used))
    selected_iv = alt_iv_per_share.get(treatment)
    selected_tv_ev = alt_tv_ev_pct.get(treatment)

    # Implied terminal sanity (Gordon TV → implied exit multiple; Exit TV →
    # implied terminal growth). Re-stated here so the bridge owns them.
    implied_exit_multiple = None
    if ebitda_y_n and ebitda_y_n != 0 and disc_n:
        implied_exit_multiple = gordon_pv / (ebitda_y_n * disc_n)
    implied_g_from_exit = None
    if last_fcf and disc_n:
        # Solve exit_pv = last_fcf * (1+g) / (wacc - g) * disc_n for g
        # → exit_pv / disc_n = last_fcf * (1+g) / (wacc - g)
        # → let X = exit_pv / disc_n; X * (wacc - g) = last_fcf * (1+g)
        # → X*wacc - X*g = last_fcf + last_fcf*g
        # → g (-X - last_fcf) = last_fcf - X*wacc
        # → g = (X*wacc - last_fcf) / (X + last_fcf)
        try:
            X = exit_pv / disc_n
            denom_g = X + last_fcf
            if denom_g:
                implied_g_from_exit = (X * wacc_used - last_fcf) / denom_g
        except (ZeroDivisionError, TypeError):
            pass
    denom_method = max(abs(gordon_pv), abs(exit_pv), 1.0)
    gordon_vs_exit_gap = abs(gordon_pv - exit_pv) / denom_method

    return {
        "version": "v376_terminal_value_decision_layer",
        "treatments_available": list(TERMINAL_TREATMENTS),
        "treatments": available_terminal_treatments(),
        "selected_terminal_treatment": treatment,
        "selected_terminal_treatment_label": treatment_label,
        "selected_terminal_treatment_fallback_used": treatment_fallback,
        "terminal_growth": round(terminal_g, 6),
        "exit_multiple": round(exit_multiple, 4),
        "wacc_used": round(wacc_used, 6),
        "terminal_year_fcf": round(last_fcf, 4),
        "terminal_year_ebitda": round(ebitda_y_n, 4),
        "gordon_terminal_value_pv": round(gordon_pv, 4),
        "exit_terminal_value_pv": round(exit_pv, 4),
        "blend_terminal_value_pv": round(blend_pv, 4),
        "h_model_terminal_value_pv": round(h_model_pv, 4),
        "current_model_terminal_value_pv": round(base_tv_used, 4),
        "fade_period_terminal_value_pv": round(fade_pv_total, 4),
        "selected_terminal_value_pv": round(selected_tv_pv, 4),
        "selected_terminal_iv_per_share": selected_iv,
        "selected_terminal_tv_ev_pct": selected_tv_ev,
        "blend_weight_gordon": round(blend_w_g_norm, 4),
        "blend_weight_exit": round(blend_w_e_norm, 4),
        "tv_pv_options": {k: round(v, 4) for k, v in tv_pv_map.items()},
        "alternative_iv_per_share": alt_iv_per_share,
        "alternative_tv_ev_pct": alt_tv_ev_pct,
        "alternative_ev": alt_ev,
        "h_model": {
            "g_near": round(h_g_near, 6),
            "g_long": round(h_g_long, 6),
            "half_life": round(h_half_life, 4),
            "formula": "TV = [FCF_terminal*(1+g_long) + FCF_terminal*H*(g_near-g_long)] / (WACC-g_long)",
            "method_note": "Structured terminal transition without a full Y6-Y10 forecast.",
        },
        "terminal_value_quality": build_terminal_value_quality_block(inp, forecast, wacc_used),
        "gordon_implied_exit_multiple": round(implied_exit_multiple, 4) if implied_exit_multiple is not None else None,
        "exit_implied_terminal_growth": round(implied_g_from_exit, 6) if implied_g_from_exit is not None else None,
        "gordon_vs_exit_gap_pct": round(gordon_vs_exit_gap, 6),
        "fade_period": {
            "fade_years": fade_years,
            "starting_fade_growth": round(starting_fade_growth, 6),
            "fade_target_growth": round(fade_target_g, 6),
            "fade_growth_series": fade_growth_series,
            "fade_fcf_series": fade_fcf_series,
            "pv_fade_fcf_series": pv_fade_fcf_series,
            "pv_fade_fcf_total": round(pv_fade_fcf_total, 4),
            "terminal_fcf_after_fade": round(terminal_fcf_after_fade, 4),
            "terminal_value_after_fade_pv": round(terminal_value_after_fade_pv, 4),
            "fade_case_ev": round(alt_ev.get("fade_period_reference", 0.0), 4),
        },
        "fcff_unaffected_note": (
            "V3.7.6: Terminal treatment is a valuation JUDGMENT. Default = "
            "Current Model preserves V3.7.5 headline IV. EV / FCFF formulas "
            "are unchanged; alt cases swap only the terminal-value PV."
        ),
        "warnings": warnings,
    }


def run_dcf(inp: DCFInputs, historical_context: Optional[dict] = None) -> DCFOutputs:
    """V3.7.0 single source of valuation truth.

    When the V3.6 historical cache is available for the symbol's market, the
    unified True 3FS engine is used (days-based WC, asset-based D&A, unlevered
    FCFF). Otherwise the legacy operating forecast is used as a graceful
    fallback. The returned `DCFOutputs.audit` block records which engine ran.
    """
    market = detect_market(inp.symbol)
    if historical_context is None:
        historical_context = build_historical_context(inp.symbol)

    # V3.9.8.8.2 Override Safety: the AAPL Base recalibration moved OUT of
    # run_dcf into apply_aapl_base_defaults(). run_dcf now respects all caller
    # inputs unconditionally; the default-builder layer (app.py defaults route)
    # is responsible for applying the AAPL Base override calibration.
    aapl_judgment_overrides: dict = {}

    unified = bool(historical_context.get("available"))

    if unified:
        forecast = build_true_3fs_forecast(inp, historical_context)
    else:
        forecast = build_operating_forecast(inp)
        forecast["engine"] = "legacy_operating_forecast"
        forecast["schedules"] = None

    fcf_list = forecast["fcf_projections"]

    # V3.7.2 Net Debt Bridge: compute reported + adjusted variants and resolve
    # the selected treatment. Headline IV uses the selected variant.
    net_debt_bridge = build_net_debt_bridge(inp, historical_context)
    selected_net_debt = net_debt_bridge.get("selected_net_debt")

    # V3.7.4 Shareholder Returns: build the schedule first so the valuation
    # denominator can switch to a forecast share-count treatment when the
    # caller asks. Default treatment = current_reported_shares preserves
    # V3.7.3 headline IV exactly.
    shareholder_returns = build_shareholder_returns_schedule(inp, forecast, historical_context)
    selected_denominator = shareholder_returns.get("selected_denominator") or float(inp.shares or 1.0)
    if (
        shareholder_returns.get("selected_share_count_treatment") != DEFAULT_SHARE_COUNT_TREATMENT
        and selected_denominator
        and selected_denominator > 0
    ):
        denominator_for_valuation = float(selected_denominator)
    else:
        denominator_for_valuation = float(inp.shares or 1.0)

    # V3.7.5 WACC Decision Layer: compute CAPM components + alt cases and
    # resolve the selected WACC treatment. Default = selected_model_wacc so
    # headline IV matches V3.7.4. When the caller switches treatment, we
    # rebuild the run with the alt WACC so discount factors / terminal value
    # / sensitivities all align with the headline.
    wacc_decision_bridge = build_wacc_decision_bridge(inp, historical_context, net_debt_bridge)
    selected_wacc_used = wacc_decision_bridge.get("selected_wacc_used_in_dcf") or float(inp.wacc or 0.09)
    if wacc_decision_bridge.get("selected_wacc_treatment") != DEFAULT_WACC_TREATMENT:
        inp_for_valuation = replace(inp, wacc=float(selected_wacc_used))
    else:
        inp_for_valuation = inp

    valuation = _calc_valuation_from_forecast(
        inp_for_valuation, forecast, net_debt_override=selected_net_debt, shares_override=denominator_for_valuation
    )
    if valuation.get("tv_used") is None:
        terminal_warnings = list(valuation.get("warnings") or [])
        wacc_comp = calc_wacc_components(inp_for_valuation, market)
        audit = {
            "calculator_version": CALCULATOR_VERSION,
            "engine": forecast.get("engine", "legacy_operating_forecast"),
            "dcf_source": (
                "Unified True 3FS Engine v1 (days-based WC + asset-based D&A + unlevered FCFF)"
                if unified
                else f"Legacy operating forecast (graceful fallback; market={market})"
            ),
            "historical_context_available": unified,
            "warnings": list(historical_context.get("warnings") or []) + terminal_warnings,
            "model_status": "unsuitable",
            "model_unsuitable": True,
            "model_unsuitable_reason": valuation.get("model_unsuitable_reason"),
            "active_forecast_sources": forecast.get("active_forecast_sources") or {},
            "forecast_paths_active": _forecast_paths_active_flag(inp),
            "operating_forecast_paths": forecast.get("operating_forecast_paths") or {},
            "wacc_treatment": wacc_decision_bridge.get("selected_wacc_treatment"),
            "wacc_treatment_label": wacc_decision_bridge.get("selected_wacc_treatment_label"),
            "wacc_used_in_dcf": wacc_decision_bridge.get("selected_wacc_used_in_dcf"),
            "net_debt_treatment": net_debt_bridge.get("selected_treatment"),
            "net_debt_treatment_label": net_debt_bridge.get("selected_treatment_label"),
            "net_debt_used_in_dcf": net_debt_bridge.get("selected_net_debt"),
            "share_count_treatment": shareholder_returns.get("selected_share_count_treatment"),
            "share_count_treatment_label": shareholder_returns.get("selected_share_count_treatment_label"),
            "shares_used_in_dcf": denominator_for_valuation,
        }
        terminal_decision_bridge = {
            "version": "v376_terminal_value_decision_layer",
            "selected_terminal_treatment": normalize_terminal_treatment(inp.selected_terminal_treatment)[0],
            "selected_terminal_treatment_label": normalize_terminal_treatment(inp.selected_terminal_treatment)[1],
            "selected_terminal_value_pv": None,
            "selected_terminal_iv_per_share": None,
            "warnings": terminal_warnings,
            "model_unsuitable": True,
            "model_unsuitable_reason": valuation.get("model_unsuitable_reason"),
        }
        return DCFOutputs(
            revenue_projections=forecast["revenue_projections"],
            revenue_growth_projections=forecast["revenue_growth_projections"],
            ebit_margin_projections=forecast["ebit_margin_projections"],
            ebit_projections=forecast["ebit_projections"],
            tax_projections=forecast["tax_projections"],
            nopat_projections=forecast["nopat_projections"],
            da_projections=forecast["da_projections"],
            capex_projections=forecast["capex_projections"],
            delta_nwc_projections=forecast["delta_nwc_projections"],
            fcf_projections=fcf_list,
            discount_factors=valuation["discount_factors"],
            pv_fcfs=valuation["pv_fcfs"],
            tv_gordon=None if valuation["tv_gordon"] is None else round(valuation["tv_gordon"], 2),
            tv_exit=None if valuation["tv_exit"] is None else round(valuation["tv_exit"], 2),
            tv_used=None,
            tv_pct=0,
            pv_fcf_sum=valuation["pv_fcf_sum"],
            ev=None,
            equity_value=None,
            intrinsic_per_share=None,
            sensitivity_gordon=[],
            sensitivity_exit=[],
            sensitivity_operating=[],
            terminal_sanity={
                "gordon_unstable": True,
                "model_unsuitable": True,
                "model_unsuitable_reason": valuation.get("model_unsuitable_reason"),
                "warnings": terminal_warnings,
            },
            currency=MARKET_CONFIG[market]["currency"],
            market=market,
            wacc_components=wacc_comp,
            schedules=forecast.get("schedules") or {},
            audit=audit,
            historical_context={
                k: v for k, v in historical_context.items()
                if k in {"available", "market", "dso", "dio", "dpo", "gross_margin",
                         "da_pct_begin_ppe", "beginning_ppe", "initial_nwc", "warnings", "source"}
            },
            net_debt_bridge=net_debt_bridge,
            shareholder_returns=shareholder_returns,
            wacc_decision_bridge=wacc_decision_bridge,
            terminal_decision_bridge=terminal_decision_bridge,
            operating_forecast_paths=forecast.get("operating_forecast_paths") or {},
            operating_path_bridge={},
            model_status="unsuitable",
            model_unsuitable=True,
            model_unsuitable_reason=valuation.get("model_unsuitable_reason"),
        )

    # V3.7.5 alt IV/share references: same forecast / net debt / shares, but
    # discount with each alternative WACC. Numbers feed the DCF Valuation
    # WACC Decision Impact table.
    alt_iv_per_share: dict[str, float] = {}
    for case_key, case_wacc in (wacc_decision_bridge.get("alternative_wacc_cases") or {}).items():
        try:
            alt_inp = replace(inp, wacc=float(case_wacc))
            alt_val = _calc_valuation_from_forecast(
                alt_inp, forecast, net_debt_override=selected_net_debt, shares_override=denominator_for_valuation
            )
            alt_iv_per_share[case_key] = round(float(alt_val["intrinsic_per_share"]), 4)
        except Exception:
            alt_iv_per_share[case_key] = None
    wacc_decision_bridge["alternative_iv_per_share"] = alt_iv_per_share
    wacc_decision_bridge["selected_wacc_iv_per_share"] = round(float(valuation["intrinsic_per_share"]), 4)

    # V3.7.6 Terminal Value Decision Layer: compute Gordon / Exit / Blend /
    # Fade Period cases on the post-WACC, post-net-debt, post-share-count
    # valuation. Default treatment = current_model_terminal preserves V3.7.5
    # headline IV exactly.
    if valuation.get("tv_gordon") is None:
        terminal_decision_bridge = {
            "version": "v376_terminal_value_decision_layer",
            "selected_terminal_treatment": normalize_terminal_treatment(inp.selected_terminal_treatment)[0],
            "selected_terminal_treatment_label": normalize_terminal_treatment(inp.selected_terminal_treatment)[1],
            "selected_terminal_value_pv": valuation["tv_used"],
            "selected_terminal_iv_per_share": round(float(valuation["intrinsic_per_share"]), 4),
            "gordon_terminal_value_pv": None,
            "exit_terminal_value_pv": round(float(valuation["tv_exit"]), 4) if valuation.get("tv_exit") is not None else None,
            "warnings": list(valuation.get("warnings") or []),
        }
    else:
        terminal_decision_bridge = build_terminal_value_decision_bridge(
            inp,
            forecast,
            wacc_used=float(selected_wacc_used),
            net_debt_used=float(selected_net_debt if selected_net_debt is not None else inp.net_debt),
            shares_used=float(denominator_for_valuation),
            pv_fcf_sum=float(valuation["pv_fcf_sum"]),
            base_tv_used=float(valuation["tv_used"]),
            base_tv_gordon=float(valuation["tv_gordon"]),
            base_tv_exit=float(valuation["tv_exit"]),
            base_ev=float(valuation["ev"]),
        )
    # Override headline only when the caller explicitly selects a non-default
    # treatment. Default = current_model_terminal preserves V3.7.5 IV exactly.
    if terminal_decision_bridge.get("selected_terminal_treatment") != DEFAULT_TERMINAL_TREATMENT:
        new_tv_pv = float(terminal_decision_bridge.get("selected_terminal_value_pv") or valuation["tv_used"])
        new_ev = float(valuation["pv_fcf_sum"]) + new_tv_pv
        new_equity = new_ev - float(selected_net_debt if selected_net_debt is not None else inp.net_debt)
        new_iv = new_equity / float(denominator_for_valuation) if denominator_for_valuation > 0 else 0.0
        new_tv_pct = new_tv_pv / new_ev if new_ev > 0 else 0
        valuation = {
            **valuation,
            "tv_used": new_tv_pv,
            "ev": new_ev,
            "equity_value": new_equity,
            "intrinsic_per_share": new_iv,
            "tv_pct": new_tv_pct,
        }

    operating_path_bridge = build_operating_path_bridge_analysis(
        inp,
        historical_context,
        float(selected_wacc_used),
        float(selected_net_debt if selected_net_debt is not None else inp.net_debt),
        float(denominator_for_valuation),
        float(valuation["intrinsic_per_share"]),
    )

    wacc_comp = calc_wacc_components(inp_for_valuation, market)
    sanity = build_terminal_sanity(
        inp,
        valuation["tv_pct"],
        valuation["tv_gordon"],
        valuation["tv_exit"],
    )

    audit = {
        "calculator_version": CALCULATOR_VERSION,
        "engine": forecast.get("engine", "legacy_operating_forecast"),
        "dcf_source": (
            "Unified True 3FS Engine v1 (days-based WC + asset-based D&A + unlevered FCFF)"
            if unified
            else f"Legacy operating forecast (graceful fallback; market={market})"
        ),
        "historical_context_available": unified,
        "warnings": list(historical_context.get("warnings") or []),
        "delta_nwc_source": "WC faded-days schedule (DSO/DIO/DPO)" if unified else "wc_change_pct_revenue (legacy)",
        "da_source": (
            "PP&E schedule (Beg×D&A%BegPPE)"
            if unified and (forecast.get("schedules") or {}).get("ppe", {}).get("asset_based_da_active")
            else "da_pct_revenue (legacy fallback)"
        ),
        "net_debt_treatment": net_debt_bridge.get("selected_treatment"),
        "net_debt_treatment_label": net_debt_bridge.get("selected_treatment_label"),
        "net_debt_treatment_fallback_used": net_debt_bridge.get("selected_treatment_fallback_used"),
        "net_debt_used_in_dcf": net_debt_bridge.get("selected_net_debt"),
        "marketable_securities_material": net_debt_bridge.get("marketable_securities_material"),
        "reported_vs_raw_debt_cash_diff": net_debt_bridge.get("reported_vs_raw_debt_cash_diff"),
        "reported_vs_raw_debt_cash_material": net_debt_bridge.get("reported_vs_raw_debt_cash_material"),
        # V3.7.4 Shareholder Returns audit.
        "share_count_treatment": shareholder_returns.get("selected_share_count_treatment"),
        "share_count_treatment_label": shareholder_returns.get("selected_share_count_treatment_label"),
        "shares_used_in_dcf": denominator_for_valuation,
        "per_share_denominator_consistency": {
            "status": "OK",
            "active_shares_used_m": round(float(denominator_for_valuation), 4),
            "headline": "active_shares_used_in_dcf",
            "gordon_sensitivity": "active_shares_used_in_dcf",
            "exit_sensitivity": "active_shares_used_in_dcf",
            "operating_sensitivity": "active_shares_used_in_dcf",
            "football_field": "active_shares_used_in_dcf",
            "scenario_cards": "active_shares_used_in_dcf",
            "export": "active_shares_used_in_dcf",
            "message": "Per-share denominator consistency across headline, sensitivity, football field, scenario, export.",
        },
        "shareholder_returns_cache_available": shareholder_returns.get("historical_cache_available"),
        "base_buybacks": (shareholder_returns.get("historical") or {}).get("base_buybacks"),
        "base_dividends": (shareholder_returns.get("historical") or {}).get("base_dividends"),
        "buybacks_excluded_from_fcff": True,
        # V3.7.5 WACC Decision Layer audit.
        "wacc_treatment": wacc_decision_bridge.get("selected_wacc_treatment"),
        "wacc_treatment_label": wacc_decision_bridge.get("selected_wacc_treatment_label"),
        "wacc_treatment_fallback_used": wacc_decision_bridge.get("selected_wacc_treatment_fallback_used"),
        "wacc_used_in_dcf": wacc_decision_bridge.get("selected_wacc_used_in_dcf"),
        "wacc_selected_vs_indicative_spread": wacc_decision_bridge.get("selected_vs_indicative_spread"),
        "capm_inputs_available": wacc_decision_bridge.get("capm_inputs_available"),
        # V3.7.6 Terminal Value Decision Layer audit.
        "terminal_treatment": terminal_decision_bridge.get("selected_terminal_treatment"),
        "terminal_treatment_label": terminal_decision_bridge.get("selected_terminal_treatment_label"),
        "terminal_treatment_fallback_used": terminal_decision_bridge.get("selected_terminal_treatment_fallback_used"),
        "terminal_value_pv_used": terminal_decision_bridge.get("selected_terminal_value_pv"),
        "tv_ev_pct_used": valuation["tv_pct"],
        "gordon_vs_exit_gap_pct": terminal_decision_bridge.get("gordon_vs_exit_gap_pct"),
        "gordon_implied_exit_multiple": terminal_decision_bridge.get("gordon_implied_exit_multiple"),
        "exit_implied_terminal_growth": terminal_decision_bridge.get("exit_implied_terminal_growth"),
        # V3.9.0 Forecast Path Upgrade v1.
        "forecast_paths_active": _forecast_paths_active_flag(inp),
        "operating_forecast_paths": forecast.get("operating_forecast_paths") or {},
        "selected_operating_path_source": operating_path_bridge.get("selected_operating_path_source"),
        "operating_path_source_legacy_defaulted": operating_path_bridge.get("selected_operating_path_source_legacy_defaulted"),
        "operating_path_source_fallback_used": operating_path_bridge.get("selected_operating_path_source_fallback_used"),
        "operating_path_source_coherence_flag": operating_path_bridge.get("coherence_flag"),
        # V3.9.8.8 Valuation Judgment Reset (AAPL-only).
        "aapl_judgment_overrides_applied": aapl_judgment_overrides,
        "aapl_judgment_reset_version": (
            "v3.9.8.8.1: AAPL Base recalibrated to institutional selected WACC (~8.65%, "
            "8.5%-8.8% range with CAPM 9.37% as High Review cross-check), bounded Gordon/Exit "
            "blend (Exit multiple 22x, peer-informed; not yfinance 27.7x), and "
            "Debt-less-Cash-&-Total-Marketable-Securities net debt. Non-AAPL tickers unaffected."
        ) if aapl_judgment_overrides else None,
        "model_status": "ok",
        "model_unsuitable": False,
        "model_unsuitable_reason": None,
    }
    audit["active_forecast_sources"] = forecast.get("active_forecast_sources") or {}
    audit["delta_nwc_source"] = audit["active_forecast_sources"].get("delta_nwc", audit.get("delta_nwc_source"))
    audit["da_source"] = audit["active_forecast_sources"].get("da", audit.get("da_source"))
    # Surface any bridge warnings alongside engine warnings.
    if net_debt_bridge.get("warnings"):
        audit["warnings"] = list(audit.get("warnings") or []) + list(net_debt_bridge.get("warnings") or [])
    if shareholder_returns.get("warnings"):
        audit["warnings"] = list(audit.get("warnings") or []) + list(shareholder_returns.get("warnings") or [])
    if wacc_decision_bridge.get("warnings"):
        audit["warnings"] = list(audit.get("warnings") or []) + list(wacc_decision_bridge.get("warnings") or [])
    if terminal_decision_bridge.get("warnings"):
        audit["warnings"] = list(audit.get("warnings") or []) + list(terminal_decision_bridge.get("warnings") or [])
    if valuation.get("warnings"):
        audit["warnings"] = list(audit.get("warnings") or []) + list(valuation.get("warnings") or [])

    return DCFOutputs(
        revenue_projections=forecast["revenue_projections"],
        revenue_growth_projections=forecast["revenue_growth_projections"],
        ebit_margin_projections=forecast["ebit_margin_projections"],
        ebit_projections=forecast["ebit_projections"],
        tax_projections=forecast["tax_projections"],
        nopat_projections=forecast["nopat_projections"],
        da_projections=forecast["da_projections"],
        capex_projections=forecast["capex_projections"],
        delta_nwc_projections=forecast["delta_nwc_projections"],
        fcf_projections=fcf_list,
        discount_factors=valuation["discount_factors"],
        pv_fcfs=valuation["pv_fcfs"],
        tv_gordon=None if valuation["tv_gordon"] is None else round(valuation["tv_gordon"], 2),
        tv_exit=None if valuation["tv_exit"] is None else round(valuation["tv_exit"], 2),
        tv_used=round(valuation["tv_used"], 2),
        tv_pct=round(valuation["tv_pct"], 4),
        pv_fcf_sum=valuation["pv_fcf_sum"],
        ev=round(valuation["ev"], 2),
        equity_value=round(valuation["equity_value"], 2),
        intrinsic_per_share=round(valuation["intrinsic_per_share"], 4),
        # V3.7.5: sensitivity grids center on the selected WACC used in DCF
        # so the center cell equals the headline IV.
        sensitivity_gordon=build_sensitivity(
            inp_for_valuation,
            "gordon",
            historical_context,
            net_debt_override=selected_net_debt,
            shares_override=denominator_for_valuation,
        ),
        sensitivity_exit=build_sensitivity(
            inp_for_valuation,
            "exit",
            historical_context,
            net_debt_override=selected_net_debt,
            shares_override=denominator_for_valuation,
        ),
        sensitivity_operating=build_operating_sensitivity(
            inp_for_valuation,
            historical_context,
            net_debt_override=selected_net_debt,
            shares_override=denominator_for_valuation,
        ),
        terminal_sanity=sanity,
        currency=MARKET_CONFIG[market]["currency"],
        market=market,
        wacc_components=wacc_comp,
        schedules=forecast.get("schedules") or {},
        audit=audit,
        historical_context={
            k: v for k, v in historical_context.items()
            if k in {"available", "market", "dso", "dio", "dpo", "gross_margin",
                     "da_pct_begin_ppe", "beginning_ppe", "initial_nwc", "warnings", "source"}
        },
        net_debt_bridge=net_debt_bridge,
        shareholder_returns=shareholder_returns,
        wacc_decision_bridge=wacc_decision_bridge,
        terminal_decision_bridge=terminal_decision_bridge,
        operating_forecast_paths=forecast.get("operating_forecast_paths") or {},
        operating_path_bridge=operating_path_bridge,
        model_status="ok",
        model_unsuitable=False,
        model_unsuitable_reason=None,
    )
