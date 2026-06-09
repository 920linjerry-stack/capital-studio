"""V5 Deal Studio API helpers.

Thin, pure glue between the Flask route and the deterministic engine. It:

* resolves acquirer / target either from inline financials or from a built-in
  sample company id (smoke data only -- not the full curated deck). Each side
  must provide net_income + shares + share_price; V5.0 does NOT accept a
  market-cap-only input and never back-derives share_price from market_cap,
* runs the engine,
* normalizes the result into a UI-facing shape that does NOT leak internal
  field names (e.g. ``ppa_amortization_modeled``); the Pre-PPA boundary is
  surfaced as a single light chip instead.

No Flask import, no file I/O, no network. Safe to call from a precompute job.
"""

from __future__ import annotations

from typing import Any

from modeling.ma.ad_engine import run_accretion_dilution
from modeling.ma.cost_synergy import estimate_default_cost_synergy
from modeling.ma.sample_companies import get_sample_company
from modeling.ma.viability import assess_viability


# Fields that exist for the engine's internal boundary bookkeeping and must not
# be handed to the UI as raw field names. ``pre_ppa*`` are replaced by
# ``pre_ppa_chip``; the engine's legacy ``viability`` placeholder is dropped
# here so ``viability_context`` (added below) is the single outward viability
# field. The A/D engine formula itself is left untouched.
_INTERNAL_FIELDS = ("pre_ppa", "ppa_amortization_modeled", "pre_ppa_detail", "viability")
_COMPANY_OVERRIDE_FIELDS = (
    "id",
    "name",
    "ticker",
    "market",
    "currency",
    "sector",
    "industry",
    "revenue",
    "ebitda",
    "net_income",
    "cash",
    "debt",
    "shares",
    "share_price",
    "tags",
    "source_meta",
)


def _resolve_company(block: Any) -> dict[str, Any] | None:
    """Resolve one side of the deal.

    Accepts either an inline financials object, or ``{"sample_id": "..."}`` to
    pull a built-in sample company. Inline keys override sample values, so a
    user can start from a sample and tweak a field.
    """
    if not isinstance(block, dict):
        return None
    sample_id = block.get("sample_id")
    if sample_id:
        sample = get_sample_company(sample_id)
        if sample is None:
            return None
        merged = dict(sample)
        for key in _COMPANY_OVERRIDE_FIELDS:
            if block.get(key) not in (None, ""):
                merged[key] = block[key]
        return merged
    return dict(block)


def _normalize_synergy_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in {"default", "manual", "zero"} else "manual"


def _sanitize_result(result: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(result)
    for field in _INTERNAL_FIELDS:
        cleaned.pop(field, None)
    return cleaned


def _result_snapshot(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "synergy": result.get("synergy"),
        "after_tax_synergy": result.get("after_tax_synergy"),
        "pro_forma_net_income": result.get("pro_forma_net_income"),
        "pro_forma_eps": result.get("pro_forma_eps"),
        "accretion_dilution": result.get("accretion_dilution"),
        "accretion_dilution_per_share": result.get("accretion_dilution_per_share"),
        "is_accretive": result.get("is_accretive"),
        "break_even_synergy": result.get("break_even_synergy"),
        "synergy_status": result.get("synergy_status"),
        "synergy_status_label": result.get("synergy_status_label"),
    }


# V5.7.1.1 data minimization: the /calculate company echo carries only the
# display / financial fields the UI needs to label a deal. ``source_meta``
# (and its nested ``field_sources`` / filing / quote / companyfacts URLs) is a
# build-time source-trail / audit concern that belongs in the deck and the
# ``/samples`` inspection layer — it must NOT ride back on a calculate result.
def _company_echo(company: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "id",
        "name",
        "ticker",
        "market",
        "currency",
        "sector",
        "industry",
        "revenue",
        "ebitda",
        "net_income",
        "cash",
        "debt",
        "shares",
        "share_price",
        "tags",
        "schema_version",
    )
    return {k: company.get(k) for k in keys if k in company}


def _run_core_validation(
    acquirer: dict[str, Any],
    target: dict[str, Any],
    deal: dict[str, Any],
    currency: Any,
) -> dict[str, Any]:
    """Run the A/D engine first as the authoritative core-schema validator.

    V5.1 default-synergy checks sit upstream of the engine, but they must not
    mask V5.0 core input errors such as missing shares, share price, or cash
    financing cost. A zero-synergy pass is enough to validate schema without
    giving the default-synergy helper any influence over error precedence.
    """
    core_deal = dict(deal)
    core_deal["synergy"] = 0.0
    return run_accretion_dilution({
        "acquirer": acquirer,
        "target": target,
        "deal": core_deal,
        "currency": currency,
    })


def build_ma_response(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Build the normalized Deal Studio API response and HTTP status code.

    Returns ``(body, status_code)``. ``400`` is returned for structured engine
    validation errors (missing core fields, bad mix, etc.); ``200`` for a
    successful calculation.
    """
    if not isinstance(payload, dict):
        return {"status": "error", "result": None,
                "flags": [{"severity": "error", "code": "INPUT_SCHEMA_INVALID",
                           "message": "Request body must be a JSON object."}]}, 400

    acquirer = _resolve_company(payload.get("acquirer"))
    target = _resolve_company(payload.get("target"))
    flags: list[dict[str, str]] = []
    if acquirer is None:
        flags.append({"severity": "error", "code": "ACQUIRER_REQUIRED",
                      "message": "Acquirer is required (inline financials or a valid sample_id)."})
    if target is None:
        flags.append({"severity": "error", "code": "TARGET_REQUIRED",
                      "message": "Target is required (inline financials or a valid sample_id)."})
    if flags:
        return {"status": "error", "result": None, "flags": flags}, 400

    deal = dict(payload.get("deal") or {})
    synergy_mode = _normalize_synergy_mode(deal.get("synergy_mode"))

    zero_out = _run_core_validation(acquirer, target, deal, payload.get("currency") or "USD")
    if zero_out["status"] != "ok":
        return zero_out, 400

    default_synergy = estimate_default_cost_synergy(acquirer, target)

    if synergy_mode == "default":
        if default_synergy["status"] != "ok":
            flags = list(default_synergy.get("flags") or [])
            flags.append({
                "severity": "error",
                "code": "DEFAULT_COST_SYNERGY_UNAVAILABLE",
                "message": "Default cost synergy requires company cards with positive target revenue.",
            })
            return {"status": "error", "result": None, "flags": flags}, 400
        deal["synergy"] = default_synergy["result"]["synergy_amount"]
    elif synergy_mode == "zero":
        deal["synergy"] = 0.0

    engine_inputs = {
        "acquirer": acquirer,
        "target": target,
        "deal": deal,
        "currency": payload.get("currency") or "USD",
    }
    out = run_accretion_dilution(engine_inputs)
    if out["status"] != "ok":
        return out, 400

    result = _sanitize_result(out["result"])
    pre_ppa_chip = {
        "label": "Pre-PPA",
        "detail": out["result"].get("pre_ppa_detail", ""),
    }
    result["pre_ppa_chip"] = pre_ppa_chip
    # Echo back the resolved companies so the UI can label headline / reverse.
    result["acquirer"] = _company_echo(acquirer)
    result["target"] = _company_echo(target)
    result["synergy_context"] = {
        "mode": synergy_mode,
        "current_synergy": result.get("synergy"),
        "default_cost_synergy": default_synergy["result"] if default_synergy["status"] == "ok" else None,
        "default_cost_synergy_status": default_synergy["status"],
        "default_cost_synergy_flags": default_synergy.get("flags", []),
        "zero_synergy_result": _result_snapshot(zero_out["result"]),
        "current_result": _result_snapshot(out["result"]),
        "manual_override": synergy_mode == "manual",
        "zero_synergy_selected": synergy_mode == "zero",
    }

    # V5.3 Real-World Viability layer. Computed entirely separately from the
    # engine: it reads only the static company-card tags and is attached here
    # as its own context. It is NEVER passed into run_accretion_dilution and
    # never alters EPS / accretion-dilution / synergy fields above.
    result["viability_context"] = assess_viability(acquirer, target)

    return {"status": "ok", "result": result, "flags": out.get("flags", [])}, 200
