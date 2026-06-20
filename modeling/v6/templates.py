"""V6 template-based explanation generator (Chinese, no LLM).

Every user-facing sentence the engine emits is produced here from fixed
templates and structured inputs. There is NO model-based text generation -- the
output is deterministic Chinese assembled from dictionaries and the event's
structured fields.

A hard rule: generated conclusions never contain trading instructions.
:func:`contains_banned_phrase` checks generated strings against
:data:`BANNED_PHRASES` (English + Chinese instruction terms). Source headlines
we echo verbatim (inside straight double quotes) are data, not generated
advice, and are excluded via ``ignore_quoted``.
"""

from __future__ import annotations

import re

from modeling.v6.schemas import (
    DIRECTION_BULLISH,
    DIRECTION_BEARISH,
)

# Instruction phrases that must never appear in *generated* advice. Descriptive
# market vocabulary ("price target", "sell-off", "目标价" inside a quoted source
# headline) is fine; these are explicit *instructions* in either language.
BANNED_PHRASES = (
    # English
    "you should buy", "you should sell", "we recommend", "recommend buying",
    "recommend selling", "enter now", "exit now", "stop loss", "stop-loss",
    "increase position", "reduce position", "add to position", "trim position",
    "trade signal", "buy signal", "sell signal", "take profit",
    "go long", "go short",
    # Chinese
    "建议买入", "建议卖出", "建议加仓", "建议减仓", "应该买入", "应该卖出",
    "立即买入", "立即卖出", "马上买入", "马上卖出", "止损位", "止盈位",
    "目标价位", "买入信号", "卖出信号", "现在抄底", "清仓", "满仓买入",
)

_QUOTED = re.compile(r'"[^"]*"')


def contains_banned_phrase(text: str, *, ignore_quoted: bool = False) -> str | None:
    """Return the first banned instruction phrase in ``text``, else None.

    With ``ignore_quoted=True``, text inside straight double quotes (echoed
    source headlines) is removed first, so only *generated* advice is scanned.
    """
    raw = text or ""
    if ignore_quoted:
        raw = _QUOTED.sub(" ", raw)
    low = raw.lower()
    for phrase in BANNED_PHRASES:
        # English phrases compared lower-cased; Chinese phrases are case-stable.
        needle = phrase.lower() if phrase.isascii() else phrase
        hay = low if phrase.isascii() else raw
        if needle in hay:
            return phrase
    return None


# --- Chinese label dictionaries ------------------------------------------

STATUS_CN = {
    "bullish": "偏利好",
    "bearish": "偏利空",
    "neutral": "中性",
    "mixed": "多空分歧",
    "uncertain": "不确定",
}

CHANNEL_CN = {
    "direct": "直接影响",
    "second_order": "二次传导",
    "reflexivity": "反身性 / 情绪",
}

MATCH_KIND_CN = {
    "ticker": "个股代码直接命中",
    "alias": "公司别名 / 名称命中",
    "macro_factor": "宏观因子敏感度",
    "factor_tag": "主题因子标签",
    "second_order": "二次传导链",
    "sector_transmission": "行业 / ETF 保守传导",
    "reflexivity": "情绪 / 反身性敞口",
}

EVENT_TYPE_CN = {
    "analyst_upgrade": "卖方上调评级",
    "analyst_downgrade": "卖方下调评级",
    "price_target_raise": "上调目标价",
    "price_target_cut": "下调目标价",
    "earnings_beat": "业绩超预期",
    "earnings_miss": "业绩不及预期",
    "guidance_raise": "上调业绩指引",
    "guidance_cut": "下调业绩指引",
    "macro_inflation_hot": "通胀超预期走高",
    "macro_inflation_cool": "通胀降温",
    "rate_cut": "降息",
    "rate_hike": "加息",
    "yields_up": "国债收益率上行",
    "yields_down": "国债收益率下行",
    "regulatory_risk": "监管 / 政策风险",
    "lawsuit_investigation": "诉讼 / 调查",
    "ai_capex_semis": "AI 资本开支 / 半导体需求",
    "risk_on": "风险偏好回升",
    "risk_off": "风险规避",
    "margin_warning": "利润率 / 利差压力",
    "revenue_acceleration": "收入增长加速",
    "revenue_slowdown": "收入增长放缓",
    "estimate_raise": "上调盈利预测",
    "estimate_cut": "下调盈利预测",
    "fda_approval": "FDA 批准",
    "fda_rejection": "FDA 拒绝 / 未批准",
    "trial_success": "临床试验达到终点",
    "trial_failure": "临床试验未达终点",
    "regulatory_approval": "监管批准",
    "regulatory_rejection": "监管否决",
    "regulatory_tightening": "监管要求收紧",
    "product_recall": "产品召回",
    "outage": "系统服务中断",
    "cybersecurity_breach": "网络安全事件",
    "jobs_hot": "就业数据偏强",
    "jobs_weak": "就业数据偏弱",
    "dollar_up": "美元走强",
    "dollar_down": "美元走弱",
    "oil_up": "油价上行",
    "oil_down": "油价下行",
    "credit_stress": "信用压力",
    "bank_stress": "银行体系压力",
    "fomc_decision": "FOMC 利率决议",
    "cpi_release": "CPI 通胀数据",
    "jobs_report": "非农就业数据",
    "earnings_date": "财报披露",
    "product_launch": "新品发布",
    "policy_announcement": "官方政策公告",
    "uncategorized": "未分类事件",
}

PHASE_CN = {
    "upcoming": "待公布",
    "anticipation": "预期升温",
    "live": "即将公布 / 进行中",
    "post_event": "影响衰减",
    "expired": "事件已兑现",
}


def direction_cn(direction: int) -> str:
    if direction == DIRECTION_BULLISH:
        return "利好"
    if direction == DIRECTION_BEARISH:
        return "利空"
    return "中性"


def confidence_cn(confidence: float) -> str:
    if confidence >= 0.66:
        return "较高"
    if confidence >= 0.4:
        return "中等"
    return "较低"


def event_type_cn(event_type: str) -> str:
    return EVENT_TYPE_CN.get(event_type, event_type.replace("_", " "))


# --- deterministic bands (severity / confidence / disagreement / freshness) ---

def severity_band(magnitude: float) -> str:
    """Map event magnitude (0..5) to a severity band id."""
    if magnitude >= 4.5:
        return "extreme"
    if magnitude >= 3.5:
        return "high"
    if magnitude >= 2.0:
        return "medium"
    return "low"


SEVERITY_CN = {"low": "低", "medium": "中", "high": "高", "extreme": "极高"}


def severity_cn(magnitude: float) -> str:
    return SEVERITY_CN[severity_band(magnitude)]


def confidence_band(confidence: float) -> str:
    if confidence >= 0.66:
        return "high"
    if confidence >= 0.4:
        return "medium"
    return "low"


_LMH_CN = {"low": "低", "medium": "中", "high": "高"}


def confidence_band_cn(confidence: float) -> str:
    return _LMH_CN[confidence_band(confidence)]


def disagreement_band(disagreement: float) -> str:
    if disagreement >= 0.6:
        return "high"
    if disagreement >= 0.25:
        return "medium"
    return "low"


def disagreement_band_cn(disagreement: float) -> str:
    return _LMH_CN[disagreement_band(disagreement)]


# Data-freshness bands keyed by source data_mode; the UI shows these plainly.
FRESHNESS_CN = {
    "live": "新鲜",
    "live-partial": "部分实时（可能滞后）",
    "fixture": "示例回退",
    "unavailable": "数据不可用",
    "error": "获取出错",
}


def freshness_cn(data_mode: str) -> str:
    return FRESHNESS_CN.get(data_mode, data_mode)


def status_cn(status: str) -> str:
    return STATUS_CN.get(status, status)


def channel_cn(channel: str) -> str:
    return CHANNEL_CN.get(channel, channel)


def _temporal_clause(temporal: dict | None) -> str:
    """Optional trailing clause describing future anticipation / decay state."""
    if not temporal:
        return ""
    phase = temporal.get("phase")
    label = temporal.get("label", "")
    days = temporal.get("countdown_days")
    if phase in ("upcoming", "anticipation"):
        d = abs(days) if isinstance(days, (int, float)) else None
        when = f"，倒计时约 {d:.0f} 天" if d is not None else ""
        return f"该事件尚未落地（{label}{when}），市场可能提前对预期部分定价。"
    if phase == "live":
        return "事件临近公布，预期影响处于高峰，实际方向需待数据 / 公告确认。"
    if phase == "post_event":
        if label in ("利好出尽风险", "利空出尽"):
            return "需留意预期兑现风险：相关预期已较充分定价，兑现后方向可能减弱甚至反转。"
        return "事件已发生，市场影响正在逐步衰减。"
    if phase == "expired":
        return "事件影响已基本兑现并消退。"
    return ""


def explain_contribution(
    *,
    title: str,
    event_type: str,
    ticker: str,
    effective_direction: int,
    matched_terms: list[str],
    channel: str,
    confidence: float,
    temporal: dict | None = None,
    match_kind: str | None = None,
) -> str:
    """Deterministic Chinese explanation of why an event hit a holding.

    Professional finance-dashboard tone; guaranteed advice-free. The echoed
    source title is wrapped in straight double quotes so the banned-phrase guard
    can exclude it.
    """
    terms = "、".join(matched_terms) if matched_terms else "大盘整体因子"
    mk = MATCH_KIND_CN.get(match_kind or channel, channel_cn(channel))
    base = (
        f'该事件 "{title}" 被识别为{event_type_cn(event_type)}。'
        f"基于{mk}（命中：{terms}），其通过「{channel_cn(channel)}」路径"
        f"对 {ticker} 形成{direction_cn(effective_direction)}影响，置信度{confidence_cn(confidence)}。"
    )
    clause = _temporal_clause(temporal)
    return base + ("" if not clause else " " + clause)


def holding_conclusion(
    *,
    ticker: str,
    status: str,
    bullish_count: int,
    bearish_count: int,
    event_count: int,
) -> str:
    """Holding-level summary sentence (Chinese). Describes balance, never action."""
    if event_count == 0:
        return f"暂无与 {ticker} 相关的事件映射。"
    if status == "mixed":
        return (
            f"{ticker} 当前多空分歧：{bullish_count} 条利好与 {bearish_count} 条利空"
            f"相互抵消（共 {event_count} 条相关事件），净影响方向不明确。"
        )
    if status == "uncertain":
        return (
            f"{ticker} 有 {event_count} 条相关事件，但信号置信度偏低，"
            f"净影响判断为不确定。"
        )
    if status == "neutral":
        return (
            f"{ticker} 的 {event_count} 条相关事件大体相互平衡，净影响中性。"
        )
    return (
        f"{ticker} 综合{status_cn(status)}：{bullish_count} 条利好对 "
        f"{bearish_count} 条利空（共 {event_count} 条相关事件）。"
        f"此为事件影响方向解读，并非交易指令。"
    )


def portfolio_conclusion(*, status: str, net_score: float, holdings_count: int) -> str:
    """Portfolio-level summary sentence (Chinese)."""
    sign = "+" if net_score >= 0 else ""
    return (
        f"当前组合共 {holdings_count} 只持仓，事件净影响为{status_cn(status)}"
        f"（净分值 {sign}{net_score:.3f}）。"
        f"本视图仅为市场影响方向解读，不构成投资建议，也不提供买卖信号。"
    )
