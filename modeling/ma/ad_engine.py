"""V5.0 simplified pre-PPA M&A Accretion / Dilution engine.

This module is the deterministic calculation core for the Deal Studio /
A&D Engine. It is intentionally pure:

* no Flask dependency
* no file I/O
* no network / external API / web scraping
* no LLM call, no runtime plugin
* no global mutable state, no randomness

Same input -> same output. ``run_accretion_dilution()`` is the single source
of truth for the Deal Studio UI and for any future precompute / batch
regression layer. The function takes a plain dict and returns a plain dict so
that 10,000 concurrent users can be served from cached / precomputed pairwise
results without touching this engine per request.

V5.0 scope and explicit boundaries
----------------------------------
* full-control acquisition only (full_acquisition). Minority stake, JV and
  strategic alliance are different future engines and are NOT modeled here.
* simplified *pre-PPA* view. Purchase Price Allocation is not modeled: no
  acquired-intangible amortization, no PP&E step-up D&A, no deferred tax from
  the step-up. See ``PRE_PPA_DETAIL``. Because of this, an intangible-heavy
  target can look more accretive here than it would post-PPA.
* synergy is *manual input or 0*. Rule-based default synergy is V5.1.
* economic result only. Real-world / regulatory viability is deliberately kept
  out of the EPS chain and surfaced as a separate, clearly-labelled
  placeholder block (``viability``).
"""

from __future__ import annotations

import math
from typing import Any


# Internal pre-PPA boundary markers. The API/UI never render these field names
# directly; they map them to a single light "Pre-PPA" chip + short explanation.
PRE_PPA = True
PPA_AMORTIZATION_MODELED = False
PRE_PPA_DETAIL = (
    "未计入收购价格分摊（PPA）：无 acquired intangibles 摊销，无 PP&E step-up "
    "折旧。无形资产占比高的标的，增厚可能偏乐观。"
)

# Three synergy states. Codes are stable for tests / precompute; the cn label is
# what the UI shows. accretion direction and break-even synergy must agree with
# whichever state is returned.
SYNERGY_STATUS = {
    "self_accretive": "自带增厚",
    "synergy_supported": "协同支撑",
    "synergy_short": "协同不足",
}

# Tolerance used when comparing the consideration mix sum to 1.0.
_MIX_TOL = 1e-6


def _flag(code: str, message: str, severity: str = "error") -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message}


def _error(flags: list[dict[str, str]]) -> dict[str, Any]:
    return {"status": "error", "result": None, "flags": flags}


def _opt_float(value: Any) -> float | None:
    """Parse a value to a finite float, or None when absent / unparseable."""
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _require_positive(
    raw: dict[str, Any],
    key: str,
    code: str,
    label: str,
    flags: list[dict[str, str]],
) -> float | None:
    value = _opt_float(raw.get(key))
    if value is None:
        flags.append(_flag(code, f"{label} is required and must be a finite number."))
        return None
    if value <= 0:
        flags.append(_flag(code, f"{label} must be greater than zero."))
        return None
    return value


def _resolve_mix(deal: dict[str, Any], flags: list[dict[str, str]]) -> tuple[float, float] | None:
    """Resolve the cash / stock consideration split.

    Accepts ``cash_pct`` and ``stock_pct`` (each 0..1). If only one is given the
    other is derived. They must sum to 1.0 within tolerance. Missing both is an
    error rather than a silent 0/100 default.
    """
    cash = _opt_float(deal.get("cash_pct"))
    stock = _opt_float(deal.get("stock_pct"))

    if cash is None and stock is None:
        flags.append(_flag(
            "CONSIDERATION_MIX_REQUIRED",
            "Consideration mix is required: provide cash_pct and/or stock_pct.",
        ))
        return None
    if cash is None:
        cash = 1.0 - stock  # type: ignore[operator]
    if stock is None:
        stock = 1.0 - cash

    if cash < -_MIX_TOL or stock < -_MIX_TOL or cash > 1.0 + _MIX_TOL or stock > 1.0 + _MIX_TOL:
        flags.append(_flag(
            "CONSIDERATION_MIX_INVALID",
            "cash_pct and stock_pct must each be between 0 and 1.",
        ))
        return None
    if abs((cash + stock) - 1.0) > _MIX_TOL:
        flags.append(_flag(
            "CONSIDERATION_MIX_INVALID",
            "cash_pct and stock_pct must sum to 1.0.",
        ))
        return None
    # Clamp tiny floating dust so downstream splits stay exact.
    cash = min(1.0, max(0.0, cash))
    return cash, 1.0 - cash


def _synergy_status(break_even_synergy: float, synergy: float) -> str:
    """Deterministic three-state classification.

    * break_even <= 0  -> deal is accretive on its own economics (自带增厚).
    * break_even > 0 and synergy >= break_even -> synergy carries it (协同支撑).
    * break_even > 0 and synergy < break_even -> still dilutive (协同不足).

    This is by construction consistent with the accretion sign: at synergy ==
    break_even the pro forma EPS equals the standalone EPS.
    """
    if break_even_synergy <= 0.0:
        return "self_accretive"
    if synergy >= break_even_synergy:
        return "synergy_supported"
    return "synergy_short"


def run_accretion_dilution(inputs: dict[str, Any]) -> dict[str, Any]:
    """Run a simplified pre-PPA accretion / dilution analysis.

    ``inputs`` schema::

        {
          "acquirer": {"name", "ticker", "net_income", "shares", "share_price"},
          "target":   {"name", "ticker", "net_income", "shares", "share_price"},
          "deal": {
            "deal_type": "full_acquisition",   # only supported value
            "premium": 0.30,                   # fraction, e.g. 0.30 = +30%
            "cash_pct": 0.5, "stock_pct": 0.5, # mix; sum to 1
            "financing_cost": 0.05,            # pre-tax annual rate on cash
            "tax_rate": 0.25,                  # 0 <= t < 1
            "synergy": 0.0                     # pre-tax annual synergy (manual or 0)
          },
          "currency": "USD"
        }

    Amounts (net_income, synergy) are in the same currency unit (e.g. millions);
    share_price is per share; shares are in the matching unit (e.g. millions) so
    that net_income / shares yields a per-share EPS. Returns a dict with
    ``status == "ok"`` and a ``result`` block, or ``status == "error"`` with a
    structured ``flags`` list. No core field is ever silently defaulted to 0.

    V5.0 input schema is deliberately strict: each side must carry
    ``net_income``, ``shares`` and ``share_price``. A market-cap-only input is
    NOT supported -- the A/D chain needs ``shares`` (standalone EPS) and the
    acquirer ``share_price`` (new shares issued), so ``market_cap`` cannot
    stand in for them and is never used to back-derive a share price.
    """
    flags: list[dict[str, str]] = []
    acquirer = inputs.get("acquirer") or {}
    target = inputs.get("target") or {}
    deal = inputs.get("deal") or {}

    if not isinstance(acquirer, dict) or not isinstance(target, dict) or not isinstance(deal, dict):
        return _error([_flag("INPUT_SCHEMA_INVALID", "acquirer, target and deal must each be objects.")])

    deal_type = str(deal.get("deal_type") or "full_acquisition").strip().lower()
    if deal_type != "full_acquisition":
        return _error([_flag(
            "DEAL_TYPE_UNSUPPORTED",
            "V5.0 only supports full_acquisition. Minority stake / JV / strategic "
            "alliance are separate future engines.",
        )])

    # ---- Core required fields (structured errors, never silent 0) ----------
    acq_ni = _require_positive(acquirer, "net_income", "ACQUIRER_NET_INCOME_REQUIRED", "Acquirer net income", flags)
    acq_shares = _require_positive(acquirer, "shares", "ACQUIRER_SHARES_REQUIRED", "Acquirer shares", flags)
    acq_price = _require_positive(acquirer, "share_price", "ACQUIRER_PRICE_REQUIRED", "Acquirer share price", flags)

    tgt_shares = _require_positive(target, "shares", "TARGET_SHARES_REQUIRED", "Target shares", flags)
    tgt_price = _require_positive(target, "share_price", "TARGET_PRICE_REQUIRED", "Target share price", flags)
    # Target net income may be zero or negative (acquiring a loss-maker is valid),
    # but it must be supplied as a finite number rather than silently defaulted.
    tgt_ni = _opt_float(target.get("net_income"))
    if tgt_ni is None:
        flags.append(_flag("TARGET_NET_INCOME_REQUIRED", "Target net income is required and must be a finite number."))

    premium = _opt_float(deal.get("premium"))
    if premium is None:
        flags.append(_flag("PREMIUM_REQUIRED", "Deal premium is required (use 0 for no premium)."))
    elif premium < -1.0:
        flags.append(_flag("PREMIUM_INVALID", "Deal premium cannot be below -100%."))

    tax_rate = _opt_float(deal.get("tax_rate"))
    if tax_rate is None:
        flags.append(_flag("TAX_RATE_REQUIRED", "Tax rate is required (0 <= tax_rate < 1)."))
    elif tax_rate < 0.0 or tax_rate >= 1.0:
        flags.append(_flag("TAX_RATE_INVALID", "Tax rate must satisfy 0 <= tax_rate < 1."))

    # financing_cost only affects the cash portion. It must be supplied
    # EXPLICITLY whenever the deal carries any cash -- a missing value is never
    # silently treated as 0 (that could make a cash deal look falsely accretive).
    # For a stock-only deal (cash_pct == 0) it may be absent and is ignored.
    financing_cost = _opt_float(deal.get("financing_cost"))
    if financing_cost is not None and financing_cost < 0.0:
        flags.append(_flag("FINANCING_COST_INVALID", "Financing cost cannot be negative."))

    synergy = _opt_float(deal.get("synergy"))
    if synergy is None:
        synergy = 0.0  # V5.0 default: no AI synergy, manual or 0 only
    elif synergy < 0.0:
        flags.append(_flag("SYNERGY_INVALID", "Manual synergy cannot be negative."))

    mix = _resolve_mix(deal, flags)

    # Conditional financing-cost requirement, evaluated once the cash share is
    # known. Missing OR unparseable counts as "not supplied".
    if mix is not None and mix[0] > 0.0 and financing_cost is None:
        flags.append(_flag(
            "FINANCING_COST_REQUIRED",
            "Financing cost is required when the deal includes a cash portion "
            "(set it explicitly to 0 for cost-free cash).",
        ))

    if flags:
        return _error(flags)

    # Stock-only deal: cash consideration is zero, so financing cost is moot.
    if financing_cost is None:
        financing_cost = 0.0

    # All core fields validated past this point.
    assert acq_ni is not None and acq_shares is not None and acq_price is not None
    assert tgt_shares is not None and tgt_price is not None and tgt_ni is not None
    assert premium is not None and tax_rate is not None and mix is not None
    cash_pct, stock_pct = mix

    # ---- Pre-PPA accretion / dilution chain --------------------------------
    target_equity_value = tgt_shares * tgt_price
    offer_value = target_equity_value * (1.0 + premium)

    cash_consideration = offer_value * cash_pct
    stock_consideration = offer_value * stock_pct

    # Cash portion is funded with debt at the pre-tax financing cost; the
    # interest is tax-deductible, so only the after-tax cost hits net income.
    after_tax_financing_cost = cash_consideration * financing_cost * (1.0 - tax_rate)

    # Stock portion issues new acquirer shares at the acquirer's own share
    # price. Because offer_value already embeds the premium, new shares are sized
    # off the acquisition value -- never off the target's unaffected P/E.
    new_shares_issued = stock_consideration / acq_price

    after_tax_synergy = synergy * (1.0 - tax_rate)

    pro_forma_net_income = acq_ni + tgt_ni + after_tax_synergy - after_tax_financing_cost
    pro_forma_shares = acq_shares + new_shares_issued
    pro_forma_eps = pro_forma_net_income / pro_forma_shares
    acquirer_standalone_eps = acq_ni / acq_shares

    accretion_dilution = pro_forma_eps / acquirer_standalone_eps - 1.0
    accretion_dilution_per_share = pro_forma_eps - acquirer_standalone_eps
    is_accretive = pro_forma_eps >= acquirer_standalone_eps

    # ---- Break-even synergy -------------------------------------------------
    # Pro forma shares do not depend on synergy, so EPS is linear in synergy and
    # the break-even solve is exact:
    #   acquirer_standalone_eps * pro_forma_shares = required pro forma NI
    #   required_after_tax_synergy = required_NI - (acq_ni + tgt_ni - financing)
    #   break_even_synergy (pre-tax) = required_after_tax_synergy / (1 - tax_rate)
    required_pro_forma_ni = acquirer_standalone_eps * pro_forma_shares
    required_after_tax_synergy = required_pro_forma_ni - (acq_ni + tgt_ni - after_tax_financing_cost)
    break_even_synergy = required_after_tax_synergy / (1.0 - tax_rate)

    status_code = _synergy_status(break_even_synergy, synergy)

    # P/E context. acquisition_pe is the P/E *paid* including the premium; it is
    # the correct comparison for an all-stock deal (acquirer P/E vs acquisition
    # P/E), and is what proves we are not sneaking in the target's raw P/E.
    acquirer_pe = (acq_shares * acq_price) / acq_ni
    acquisition_pe = (offer_value / tgt_ni) if tgt_ni > 0 else None
    target_unaffected_pe = (target_equity_value / tgt_ni) if tgt_ni > 0 else None

    result = {
        "deal_type": "full_acquisition",
        "currency": (inputs.get("currency") or "USD"),
        # offer / consideration
        "target_equity_value": target_equity_value,
        "premium": premium,
        "offer_value": offer_value,
        "consideration_mix": {"cash_pct": cash_pct, "stock_pct": stock_pct},
        "cash_consideration": cash_consideration,
        "stock_consideration": stock_consideration,
        "new_shares_issued": new_shares_issued,
        # income bridge
        "after_tax_financing_cost": after_tax_financing_cost,
        "synergy": synergy,
        "after_tax_synergy": after_tax_synergy,
        "acquirer_net_income": acq_ni,
        "target_net_income": tgt_ni,
        "pro_forma_net_income": pro_forma_net_income,
        # per-share
        "acquirer_shares": acq_shares,
        "pro_forma_shares": pro_forma_shares,
        "acquirer_standalone_eps": acquirer_standalone_eps,
        "pro_forma_eps": pro_forma_eps,
        "accretion_dilution": accretion_dilution,
        "accretion_dilution_per_share": accretion_dilution_per_share,
        "is_accretive": is_accretive,
        # synergy economics
        "break_even_synergy": break_even_synergy,
        "synergy_status": status_code,
        "synergy_status_label": SYNERGY_STATUS[status_code],
        # P/E context
        "acquirer_pe": acquirer_pe,
        "acquisition_pe": acquisition_pe,
        "target_unaffected_pe": target_unaffected_pe,
        # pre-PPA boundary (internal field names; surfaced as a light chip only)
        "pre_ppa": PRE_PPA,
        "ppa_amortization_modeled": PPA_AMORTIZATION_MODELED,
        "pre_ppa_detail": PRE_PPA_DETAIL,
        # Real-world viability is intentionally kept OUT of the EPS chain. V5.0
        # ships only a neutral placeholder; rule-based viability is deferred.
        "viability": {
            "status": "not_assessed",
            "note": "Real-world / regulatory viability not assessed in V5.0 (economic view only).",
        },
    }
    return {"status": "ok", "result": result, "flags": []}
