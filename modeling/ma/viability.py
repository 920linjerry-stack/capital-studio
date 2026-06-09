"""V5.3 Real-World Viability Rule Layer v1.

A deterministic, rule-based layer that sits ENTIRELY beside the economic /
accretion-dilution result. It reads only the static company-card tags (and, for
the capacity placeholder, the deck's share/price fields) and emits red / yellow
/ green flags describing how plausibly a deal could clear real-world hurdles
(antitrust, national security, sensitive sectors, deal capacity).

Hard boundaries (V5.3):
* This NEVER feeds the A/D engine. It does not touch pro-forma EPS,
  accretion/dilution, break-even synergy, or the synergy status. It is computed
  separately and only attached to the API response as ``viability_context``.
* No LLM, no plugin, no network, no file I/O. Pure function of the two cards.
* These are illustrative rule flags, NOT a legal/regulatory conclusion, and NOT
  an overall score, win-rate, or merged economic+viability number.

Every flag is transparent: it carries the ``rule_id`` that fired and the
``triggered_tags`` that caused it.
"""

from __future__ import annotations

import math
from typing import Any


# ── Severity / level vocabulary ─────────────────────────────────────────────
_SEVERITY_ORDER = {"green": 0, "yellow": 1, "red": 2}

_LEVEL_LABEL = {
    "green": "现实可行性：较高",
    "yellow": "现实可行性：需审查",
    "red": "现实可行性：高风险",
}

DISCLAIMER_LEVEL = "light"  # rule inference only, not a legal opinion

# Coarse industry families used only by the antitrust-concentration rule. This
# is a transparent grouping of the frozen deck's industry_group values; it is
# NOT a synergy input and never affects EPS.
_INDUSTRY_FAMILY = {
    "consumer_electronics_ecosystem": "big_tech_platform",
    "enterprise_software_cloud": "big_tech_platform",
    "search_ads_cloud": "big_tech_platform",
    "ecommerce_cloud_logistics": "big_tech_platform",
    "social_ads_platform": "big_tech_platform",
    "database_enterprise_cloud_infrastructure": "big_tech_platform",
    "enterprise_saas_customer_platform": "big_tech_platform",
    "semiconductors_ai_accelerators": "semiconductors",
    "semiconductor_networking_infrastructure": "semiconductors",
    "media_entertainment_content": "media",
    "home_improvement_retail": "retail",
    "membership_warehouse_retail": "retail",
    "industrial_machinery_equipment": "industrial",
    "integrated_oil_gas_energy": "energy",
}


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _tags(card: Any) -> dict[str, Any]:
    tags = card.get("tags") if isinstance(card, dict) else None
    return tags if isinstance(tags, dict) else {}


def _strategic(card: Any) -> set[str]:
    raw = _tags(card).get("strategic_tags") or []
    return {_norm(t) for t in raw if _norm(t)} if isinstance(raw, list) else set()


def _sensitive(card: Any) -> set[str]:
    raw = _tags(card).get("sensitive_sectors") or []
    return {_norm(t) for t in raw if _norm(t)} if isinstance(raw, list) else set()


def _combined(card: Any) -> set[str]:
    return _strategic(card) | _sensitive(card)


def _industry_group(card: Any) -> str:
    return _norm(_tags(card).get("industry_group"))


def _market_position(card: Any) -> str:
    return _norm(_tags(card).get("market_position"))


def _is_leader(position: str) -> bool:
    return "leader" in position or "major" in position


def _is_global_tier(position: str) -> bool:
    return "global" in position or "mega" in position


def _finite_positive(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _equity_value(card: Any) -> float | None:
    if not isinstance(card, dict):
        return None
    price = _finite_positive(card.get("share_price"))
    shares = _finite_positive(card.get("shares"))
    if price is None or shares is None:
        return None
    return price * shares


# ── Tag detectors (transparent, deterministic) ──────────────────────────────
def _data_ai_tokens(card: Any) -> set[str]:
    found: set[str] = set()
    for t in _combined(card):
        if t == "data" or t == "data platform":
            found.add("data")
        if t == "ai" or t.startswith("ai "):
            found.add("ai")
        if t == "platform" or t.endswith(" platform"):
            found.add("platform")
        if t in {"social", "social_media", "social media"}:
            found.add("social")
    return found


def _semiconductor_tokens(card: Any) -> set[str]:
    """Detect *semiconductor* exposure only.

    AI / cloud infrastructure is intentionally NOT folded in here: an
    "AI infrastructure" tag (e.g. ORCL) is data/AI sensitivity, not a
    semiconductor signal, and must not be caught by the semiconductor rule.
    """
    return {"semiconductors" for t in _combined(card) if "semiconductor" in t}


def _energy_tokens(card: Any) -> set[str]:
    combined = _combined(card)
    found = {t for t in combined if t in {"energy", "climate"}}
    if any("oil" in t for t in combined):
        found.add("energy")
    return found


def _flag(severity: str, category: str, title: str, message: str,
          rule_id: str, triggered_tags: list[str]) -> dict[str, Any]:
    return {
        "severity": severity,
        "category": category,
        "title": title,
        "message": message,
        "rule_id": rule_id,
        "triggered_tags": sorted(triggered_tags),
    }


# ── Individual rules ────────────────────────────────────────────────────────
def _rule_antitrust(acquirer: Any, target: Any) -> dict[str, Any] | None:
    acq_family = _INDUSTRY_FAMILY.get(_industry_group(acquirer))
    tgt_family = _INDUSTRY_FAMILY.get(_industry_group(target))
    if not acq_family or acq_family != tgt_family:
        return None
    acq_pos = _market_position(acquirer)
    tgt_pos = _market_position(target)
    if not (_is_leader(acq_pos) and _is_leader(tgt_pos)):
        return None
    triggered = sorted({acq_family, acq_pos, tgt_pos})
    if _is_global_tier(acq_pos) and _is_global_tier(tgt_pos):
        return _flag(
            "red", "antitrust", "同业集中度高",
            "两家均为同一行业的头部企业，合并后市场集中度高，反垄断审查风险较大。",
            "antitrust_same_industry_global_leaders", triggered,
        )
    return _flag(
        "yellow", "antitrust", "同业集中度",
        "双方处于同一行业且均为行业领导者，存在反垄断关注。",
        "antitrust_same_industry_leaders", triggered,
    )


def _rule_data_ai(acquirer: Any, target: Any) -> dict[str, Any] | None:
    acq = _data_ai_tokens(acquirer)
    tgt = _data_ai_tokens(target)
    if not (acq and tgt):
        return None
    return _flag(
        "yellow", "sensitive_sector", "数据/AI 敏感",
        "双方均涉及数据 / AI / 平台属性，可能触发数据与平台监管审查。",
        "data_ai_platform_sensitivity", sorted(acq | tgt),
    )


def _rule_semiconductors(acquirer: Any, target: Any) -> dict[str, Any] | None:
    acq = _semiconductor_tokens(acquirer)
    tgt = _semiconductor_tokens(target)
    if not (acq or tgt):
        return None
    if acq and tgt:
        return _flag(
            "red", "sensitive_sector", "半导体敏感",
            "双方均涉及半导体，属于高度敏感领域，出口管制与审查风险较高。",
            "semiconductors_both", sorted(acq | tgt),
        )
    return _flag(
        "yellow", "sensitive_sector", "半导体敏感",
        "其中一方涉及半导体，可能触发敏感行业与出口管制审查。",
        "semiconductors_one", sorted(acq | tgt),
    )


def _rule_energy(acquirer: Any, target: Any) -> dict[str, Any] | None:
    acq = _energy_tokens(acquirer)
    tgt = _energy_tokens(target)
    if not (acq or tgt):
        return None
    return _flag(
        "yellow", "sensitive_sector", "能源/气候行业审查",
        "交易涉及能源 / 气候相关行业，可能受到行业与环境监管关注。",
        "energy_climate_sector", sorted(acq | tgt),
    )


def _rule_capacity(acquirer: Any, target: Any) -> dict[str, Any] | None:
    """Light deal-capacity placeholder. NOT a hard gate and NOT a financing
    model: if the acquirer is markedly smaller than the target by equity value,
    surface a yellow capacity flag only."""
    acq_value = _equity_value(acquirer)
    tgt_value = _equity_value(target)
    if acq_value is None or tgt_value is None:
        return None
    if acq_value >= 0.5 * tgt_value:
        return None
    return _flag(
        "yellow", "capacity", "买方体量偏小",
        "买方股权体量明显小于标的，交易承接与融资能力存疑（仅提示，非硬性限制）。",
        "acquirer_smaller_than_target", ["acquirer_equity_below_half_target"],
    )


_RULES = (
    _rule_antitrust,
    _rule_data_ai,
    _rule_semiconductors,
    _rule_energy,
    _rule_capacity,
)


def _summary(level: str, flags: list[dict[str, Any]]) -> str:
    non_green = [f for f in flags if f["severity"] != "green"]
    if not non_green:
        return "跨行业且未命中主要敏感规则，现实可行性较高（仅规则推演）。"
    top_titles = []
    for f in non_green:
        if f["title"] not in top_titles:
            top_titles.append(f["title"])
    head = "高风险" if level == "red" else "需审查"
    return f"{head}：{'、'.join(top_titles[:3])}（仅规则推演，非法律意见）。"


def assess_viability(acquirer: Any, target: Any) -> dict[str, Any]:
    """Return the deterministic viability result for one directed deal.

    Pure function of the two company cards. Never mutates inputs, never touches
    the economic result, never calls the engine.
    """
    flags: list[dict[str, Any]] = []
    for rule in _RULES:
        flag = rule(acquirer, target)
        if flag is not None:
            flags.append(flag)

    # Stable order: highest severity first, then by rule_id for determinism.
    flags.sort(key=lambda f: (-_SEVERITY_ORDER.get(f["severity"], 0), f["rule_id"]))

    if flags:
        level = max(flags, key=lambda f: _SEVERITY_ORDER.get(f["severity"], 0))["severity"]
    else:
        level = "green"
        flags = [_flag(
            "green", "other", "无明显现实可行性风险",
            "未命中同业集中、数据/AI、半导体或能源等敏感规则。",
            "cross_industry_clean", [],
        )]

    return {
        "viability_level": level,
        "viability_label": _LEVEL_LABEL[level],
        "flags": flags,
        "summary": _summary(level, flags),
        "disclaimer_level": DISCLAIMER_LEVEL,
        "disclaimer": "规则推演，非法律意见；不进入 EPS / 增厚摊薄计算。",
    }


def compact_viability(viability: dict[str, Any]) -> dict[str, Any]:
    """Project a full viability result into the compact Arena light shape.

    Keeps level + label + the top 1-2 flags (severity / category / title /
    rule_id only), plus the short one-line summary and a count of real
    risk flags (severity != green) used to rank the Viability board. No long
    per-flag messages, no triggered_tags, no audit, no source_meta.

    This is a pure PROJECTION of the already-computed viability result. It does
    not add, remove, or re-order any rule, and never touches the economic
    numbers.
    """
    flags = viability.get("flags") or []
    top = [
        {
            "severity": f.get("severity"),
            "category": f.get("category"),
            "title": f.get("title"),
            "rule_id": f.get("rule_id"),
        }
        for f in flags[:2]
    ]
    # Count only genuine concern flags. A clean cross-industry deal carries a
    # single synthetic green flag and so reports a risk count of 0.
    risk_count = sum(1 for f in flags if f.get("severity") != "green")
    return {
        "viability_level": viability.get("viability_level"),
        "viability_label": viability.get("viability_label"),
        "viability_summary": viability.get("summary"),
        "viability_flags_count": risk_count,
        "viability_flags_top": top,
    }
