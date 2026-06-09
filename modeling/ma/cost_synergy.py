"""V5.1 deterministic default cost synergy rules.

This is a transparent upstream helper. It does not call the A/D engine, does not
write files, does not fetch data, and does not estimate revenue synergy.
"""

from __future__ import annotations

import math
from typing import Any


COST_SYNERGY_CONFIG = {
    "calibration": "heuristic_v0_unvalidated",
    "synergy_type": "cost_only",
    "tiers": {
        "high": 0.035,
        "medium": 0.015,
        "low": 0.005,
        "none": 0.0,
    },
}


def _flag(code: str, message: str) -> dict[str, str]:
    return {"severity": "error", "code": code, "message": message}


def _finite_positive(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0


def _tags(card: dict[str, Any]) -> dict[str, Any]:
    tags = card.get("tags")
    return tags if isinstance(tags, dict) else {}


def _strategic_set(card: dict[str, Any]) -> set[str]:
    raw = _tags(card).get("strategic_tags") or []
    if not isinstance(raw, list):
        return set()
    return {str(tag).strip().lower() for tag in raw if str(tag).strip()}


def estimate_default_cost_synergy(acquirer: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    """Estimate illustrative default cost synergy from company-card tags.

    Rules:
    * same industry_group -> high
    * otherwise two or more overlapping strategic tags -> medium
    * otherwise one overlap, shared sector, or adjacent industry-group pair -> medium
    * otherwise -> low
    """
    flags: list[dict[str, str]] = []
    if not isinstance(acquirer, dict) or not isinstance(target, dict):
        flags.append(_flag("COMPANY_CARD_REQUIRED", "Acquirer and target company cards are required."))
    elif not _finite_positive(target.get("revenue")):
        flags.append(_flag("TARGET_REVENUE_REQUIRED", "Target revenue is required for default cost synergy."))

    if flags:
        return {
            "status": "error",
            "result": None,
            "flags": flags,
        }

    acq_group = str(_tags(acquirer).get("industry_group") or "").strip().lower()
    tgt_group = str(_tags(target).get("industry_group") or "").strip().lower()
    acq_sector = str(acquirer.get("sector") or "").strip().lower()
    tgt_sector = str(target.get("sector") or "").strip().lower()
    shared_tags = sorted(_strategic_set(acquirer) & _strategic_set(target))
    matched_rules: list[str] = []

    adjacent_pairs = {
        frozenset(("software", "fintech_payments")),
        frozenset(("software", "cloud_infrastructure")),
        frozenset(("cloud_infrastructure", "semiconductors")),
        frozenset(("hardware_devices", "semiconductors")),
        frozenset(("logistics", "retail")),
        frozenset(("logistics", "energy_infrastructure")),
        frozenset(("retail", "media")),
    }

    if acq_group and acq_group == tgt_group:
        tier = "high"
        matched_rules.append("same_industry_group")
    elif len(shared_tags) >= 2:
        tier = "medium"
        matched_rules.append("two_or_more_shared_strategic_tags")
    elif shared_tags:
        tier = "medium"
        matched_rules.append("shared_strategic_tag")
    elif acq_sector and acq_sector == tgt_sector:
        tier = "medium"
        matched_rules.append("shared_sector")
    elif frozenset((acq_group, tgt_group)) in adjacent_pairs:
        tier = "medium"
        matched_rules.append("adjacent_industry_group")
    else:
        tier = "low"
        matched_rules.append("cross_industry_low_overlap")

    pct = COST_SYNERGY_CONFIG["tiers"][tier]
    target_revenue = float(target["revenue"])
    amount = target_revenue * pct
    return {
        "status": "ok",
        "result": {
            "synergy_tier": tier,
            "synergy_amount": amount,
            "synergy_pct_of_target_revenue": pct,
            "basis": "target_revenue",
            "matched_rules": matched_rules,
            "shared_strategic_tags": shared_tags,
            "synergy_type": COST_SYNERGY_CONFIG["synergy_type"],
            "calibration": COST_SYNERGY_CONFIG["calibration"],
            "illustrative": True,
            "note": "Rule-based illustrative default cost synergy only; not calibrated to transaction evidence.",
        },
        "flags": [],
    }
