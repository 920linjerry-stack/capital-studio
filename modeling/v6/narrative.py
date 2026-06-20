"""V6 deterministic event grouping + portfolio narrative (no LLM).

Groups scored events into product themes and assembles a template-based Chinese
narrative of what is driving the portfolio. Pure string assembly from the
engine's structured output — no model-generated text, no advice.
"""

from __future__ import annotations

from typing import Any

from modeling.v6 import templates

# event_type -> theme id. Future/scheduled events are re-routed to "future".
_THEME_OF_TYPE = {
    "rate_cut": "macro_rates", "rate_hike": "macro_rates",
    "yields_up": "macro_rates", "yields_down": "macro_rates",
    "macro_inflation_hot": "macro_rates", "macro_inflation_cool": "macro_rates",
    "fomc_decision": "macro_rates", "cpi_release": "macro_rates", "jobs_report": "macro_rates",
    "ai_capex_semis": "semis",
    "earnings_beat": "company", "earnings_miss": "company",
    "guidance_raise": "company", "guidance_cut": "company",
    "earnings_date": "company", "product_launch": "tech_ai",
    "analyst_upgrade": "institutional", "analyst_downgrade": "institutional",
    "price_target_raise": "institutional", "price_target_cut": "institutional",
    "regulatory_risk": "regulatory", "lawsuit_investigation": "regulatory",
    "policy_announcement": "regulatory",
    "risk_on": "sentiment", "risk_off": "sentiment",
}

THEME_CN = {
    "macro_rates": "宏观利率 / 通胀",
    "tech_ai": "科技与 AI",
    "semis": "半导体供应链",
    "company": "公司公告",
    "institutional": "机构观点",
    "regulatory": "监管与政策",
    "future": "未来事件",
    "sentiment": "情绪与反身性",
    "other": "其他",
}
# Stable display order.
_THEME_ORDER = ["macro_rates", "tech_ai", "semis", "company", "institutional",
                "regulatory", "sentiment", "future", "other"]


def _theme_of(driver: dict[str, Any]) -> str:
    if driver.get("is_future"):
        return "future"
    return _THEME_OF_TYPE.get(driver.get("event_type", ""), "other")


def group_events(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    """Bucket the portfolio's scored drivers into themes, ranked by impact."""
    buckets: dict[str, dict[str, Any]] = {}
    for d in analysis.get("main_drivers", []):
        theme = _theme_of(d)
        b = buckets.setdefault(theme, {
            "theme": theme, "theme_cn": THEME_CN[theme],
            "event_count": 0, "net_impact": 0.0, "abs_impact": 0.0, "titles": [],
        })
        b["event_count"] += 1
        b["net_impact"] += d["net_impact"]
        b["abs_impact"] += d["abs_impact"]
        if len(b["titles"]) < 3:
            b["titles"].append(d["title"])
    out = []
    for theme in _THEME_ORDER:
        if theme in buckets:
            b = buckets[theme]
            b["net_impact"] = round(b["net_impact"], 6)
            b["abs_impact"] = round(b["abs_impact"], 6)
            b["direction"] = 1 if b["net_impact"] > 1e-9 else -1 if b["net_impact"] < -1e-9 else 0
            out.append(b)
    out.sort(key=lambda b: b["abs_impact"], reverse=True)
    return out


def portfolio_narrative(analysis: dict[str, Any]) -> str:
    """A deterministic Chinese narrative of the portfolio's event read.

    Template-based; describes drivers/利好/利空/分歧/未来 without any instruction.
    """
    status = analysis.get("status", "neutral")
    parts = [f"当前组合事件净读数为{templates.status_cn(status)}。"]

    themes = group_events(analysis)
    if themes:
        lead = "、".join(t["theme_cn"] for t in themes[:2])
        parts.append(f"主要驱动来自{lead}。")

    top_pos = analysis.get("top_positive_contributors", [])
    top_neg = analysis.get("top_negative_contributors", [])
    if top_pos:
        parts.append("利好主要来自 " + "、".join(c["ticker"] for c in top_pos[:3]) + "。")
    if top_neg:
        parts.append("利空主要来自 " + "、".join(c["ticker"] for c in top_neg[:3]) + "。")

    dis = analysis.get("disagreement", 0.0)
    if dis >= 0.25:
        parts.append(f"多空分歧度{templates.disagreement_band_cn(dis)}，正负事件存在相互对冲。")

    timeline = analysis.get("future_timeline", [])
    if timeline:
        nxt = timeline[0]
        days = abs(nxt.get("countdown_days", 0))
        parts.append(
            f"未来 {days:.0f} 天内的{templates.event_type_cn(nxt['event_type'])}"
            f"（{nxt.get('temporal_label', '')}）可能改变后续读数。"
        )

    # 多空对冲后组合结论: net read after positive/negative offset.
    pos = analysis.get("positive_impact", 0.0)
    neg = analysis.get("negative_impact", 0.0)
    net = analysis.get("net_impact_score", 0.0)
    parts.append(
        f"多空对冲后，组合整体{templates.status_cn(status)}"
        f"（利好合计 {pos:+.3f}，利空合计 {neg:+.3f}，净 {net:+.3f}）。"
    )

    parts.append("以上为事件影响解读，非投资建议。")
    return "".join(parts)
