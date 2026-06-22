"""V6 breaking-news / sudden-sentiment detector (deterministic, non-LLM).

Scans recent structured events and surfaces public-safe, higher-urgency ALERT
cards when headlines cluster around a ticker, a sector/macro theme, or a sudden
sentiment swing -- or when a public data source fails (so the cockpit can admit
it may be blind to fresh data).

Hard boundaries:

* It describes **news-flow / headline sentiment** only. It never scrapes social
  media and never claims real-time when only keyless public RSS/EDGAR feeds are
  used (wording stays "公共新闻流 / 近实时 / 可能存在延迟").
* It emits read-only attention signals. It never produces buy/sell instructions,
  target prices, stop-losses, position sizing, or trading signals.

Pure and deterministic: equal ``(events, statuses, now)`` inputs always produce
equal output. No network, no LLM, no I/O.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from modeling.v6.schemas import MarketEvent
from modeling.v6.timing import parse_dt, now_utc
from modeling.v6 import freshness as fr
from modeling.v6.templates import event_type_cn

# Clustering windows (hours). Velocity is measured in the 2h window; events
# older than the recency window are not considered "breaking".
_VELOCITY_WINDOW_H = 2.0
_FAST_WINDOW_H = 0.5
_RECENCY_WINDOW_H = 24.0
_URGENT_RECENT_H = 6.0

# Inherently urgent event types: a single fresh one already warrants attention.
_URGENT_TYPES = {
    "sanctions", "export_controls", "tariffs",
    "bank_stress", "credit_stress",
    "cybersecurity_breach", "outage", "product_recall",
    "enforcement_action", "lawsuit", "investigation", "antitrust_probe",
    "lawsuit_investigation", "regulatory_rejection", "regulatory_tightening",
    "fda_rejection", "trial_failure",
    "guidance_cut", "guidance_raise", "earnings_miss", "earnings_beat",
    "cpi_hot", "jobs_weak", "jobs_hot", "fomc_hawkish", "rate_hike",
    "oil_up", "macro_inflation_hot",
    "risk_off", "risk_on",
}

# Tag / event_type -> normalized theme key.
_THEME_OF_TAG = {
    "rates": "macro_rates", "yields": "macro_rates",
    "inflation": "macro_inflation", "cpi": "macro_inflation",
    "ai_capex": "ai_semis", "semiconductors": "ai_semis",
    "risk_sentiment": "risk_sentiment",
    "china_demand": "china",
    "regulatory": "regulatory", "us_regulation": "regulatory",
    "oil": "energy_oil",
    "earnings": "earnings", "guidance": "earnings",
    "analyst_action": "analyst",
}
_THEME_OF_TYPE = {
    "rate_cut": "macro_rates", "rate_hike": "macro_rates",
    "yields_up": "macro_rates", "yields_down": "macro_rates",
    "cpi_hot": "macro_inflation", "cpi_cool": "macro_inflation",
    "macro_inflation_hot": "macro_inflation", "macro_inflation_cool": "macro_inflation",
    "oil_up": "energy_oil", "oil_down": "energy_oil",
    "bank_stress": "credit", "credit_stress": "credit",
    "sanctions": "geopolitics", "export_controls": "geopolitics", "tariffs": "geopolitics",
    "risk_on": "risk_sentiment", "risk_off": "risk_sentiment",
    "ai_capex_semis": "ai_semis",
    "regulatory_risk": "regulatory", "regulatory_tightening": "regulatory",
    "cybersecurity_breach": "cyber", "outage": "cyber",
}

_MACRO_THEMES = {"macro_rates", "macro_inflation", "credit", "geopolitics", "energy_oil"}
_SENTIMENT_THEMES = {"risk_sentiment"}

_THEME_ZH = {
    "macro_rates": "利率 / 国债收益率",
    "macro_inflation": "通胀 / CPI",
    "credit": "银行 / 信用压力",
    "geopolitics": "地缘 / 制裁 / 出口管制",
    "energy_oil": "能源 / 油价",
    "ai_semis": "AI 资本开支 / 半导体",
    "risk_sentiment": "市场风险偏好",
    "china": "中国需求 / 政策",
    "regulatory": "监管 / 政策",
    "earnings": "业绩 / 指引",
    "analyst": "卖方观点",
    "cyber": "网络安全 / 服务中断",
}

_DIR_ZH = {"bullish": "偏利好", "bearish": "偏利空", "mixed": "多空分歧", "neutral": "中性", "unknown": "方向待定"}

# Urgency thresholds over a 0..100 score.
_BREAKING_SCORE = 70
_ELEVATED_SCORE = 40


def _age_hours(event: MarketEvent, now: datetime) -> float | None:
    dt = (parse_dt(event.effective_at) or parse_dt(event.timestamp)
          or parse_dt(event.scheduled_at))
    if dt is None:
        return None
    return (now - dt).total_seconds() / 3600.0


def _themes_of(event: MarketEvent) -> set[str]:
    themes: set[str] = set()
    t = _THEME_OF_TYPE.get(event.event_type)
    if t:
        themes.add(t)
    for tag in event.affected_tags:
        th = _THEME_OF_TAG.get(tag)
        if th:
            themes.add(th)
    return themes


def _dominant_direction(events: list[MarketEvent]) -> str:
    bull = sum(1 for e in events if e.direction > 0)
    bear = sum(1 for e in events if e.direction < 0)
    if bull and bear:
        return "mixed"
    if bull:
        return "bullish"
    if bear:
        return "bearish"
    if events:
        return "neutral"
    return "unknown"


def _distinct_sources(events: list[MarketEvent]) -> list[str]:
    out: list[str] = []
    for e in events:
        for s in (e.source_list or ([e.source] if e.source else [])):
            if s and s not in out:
                out.append(s)
    return out


def _score_cluster(events: list[MarketEvent], now: datetime) -> dict[str, Any]:
    """Deterministic 0..100 urgency score + supporting metrics for a cluster."""
    evidence = len(events)
    ages = [a for a in (_age_hours(e, now) for e in events) if a is not None]
    n_2h = sum(1 for a in ages if a <= _VELOCITY_WINDOW_H)
    n_30m = sum(1 for a in ages if a <= _FAST_WINDOW_H)
    n_6h = sum(1 for a in ages if a <= _URGENT_RECENT_H)
    sources = _distinct_sources(events)
    source_count = len(sources)
    has_urgent = any(e.event_type in _URGENT_TYPES for e in events)
    max_mag = max((e.magnitude for e in events), default=0.0)

    score = 0.0
    if evidence >= 3:
        score += 25
    elif evidence == 2:
        score += 15
    if n_2h >= 3:
        score += 20
    elif n_2h == 2:
        score += 10
    if n_30m >= 2:
        score += 10
    if source_count >= 2:
        score += 15
    if has_urgent:
        score += 25
    score += min(20.0, max_mag / 5.0 * 20.0)
    score = max(0.0, min(100.0, score))

    if score >= _BREAKING_SCORE:
        urgency = "breaking"
    elif score >= _ELEVATED_SCORE:
        urgency = "elevated"
    else:
        urgency = "normal"

    confs = [round(e.confidence * e.classification_confidence, 4) for e in events]
    return {
        "urgency": urgency,
        "urgency_score": int(round(score)),
        "evidence_count": evidence,
        "source_count": source_count,
        "n_2h": n_2h,
        "n_6h": n_6h,
        "has_urgent": has_urgent,
        "confidence": round(sum(confs) / len(confs), 4) if confs else 0.0,
        "dominant_direction": _dominant_direction(events),
    }


def _seen_window(events: list[MarketEvent], now: datetime) -> tuple[str | None, str | None]:
    dts = []
    for e in events:
        dt = parse_dt(e.effective_at) or parse_dt(e.timestamp) or parse_dt(e.scheduled_at)
        if dt is not None:
            dts.append(dt)
    if not dts:
        return None, None
    return fr._iso(min(dts)), fr._iso(max(dts))


def _alert_freshness(events: list[MarketEvent], now: datetime) -> str:
    return fr.rollup_freshness([fr.event_freshness(e, now) for e in events])


def _affected(events: list[MarketEvent]) -> tuple[list[str], list[str]]:
    tickers: set[str] = set()
    tags: set[str] = set()
    for e in events:
        tickers.update(e.related_tickers)
        tags.update(e.affected_tags)
    return sorted(tickers), sorted(tags)


def _build_alert(
    *, alert_id: str, alert_type: str, title_zh: str, summary_zh: str,
    events: list[MarketEvent], metrics: dict[str, Any], now: datetime,
) -> dict[str, Any]:
    tickers, tags = _affected(events)
    first_seen, last_seen = _seen_window(events, now)
    return {
        "alert_id": alert_id,
        "urgency": metrics["urgency"],
        "urgency_score": metrics["urgency_score"],
        "alert_type": alert_type,
        "title_zh": title_zh,
        "summary_zh": summary_zh,
        "affected_tickers": tickers,
        "affected_tags": tags,
        "dominant_direction": metrics["dominant_direction"],
        "confidence": metrics["confidence"],
        "evidence_count": metrics["evidence_count"],
        "source_count": metrics["source_count"],
        "first_seen_at": first_seen,
        "last_seen_at": last_seen,
        "freshness_status": _alert_freshness(events, now),
        "event_ids": [e.event_id for e in events],
    }


def _qualifies(metrics: dict[str, Any]) -> bool:
    """A cluster is a candidate alert when it clusters or carries an urgent type."""
    if metrics["evidence_count"] >= 2:
        return True
    return metrics["has_urgent"] and metrics["n_6h"] >= 1


def detect_breaking(
    events: list[MarketEvent],
    *,
    now: datetime | None = None,
    source_statuses: list[dict[str, Any]] | None = None,
    max_alerts: int = 6,
) -> dict[str, Any]:
    """Surface deterministic breaking / sudden-sentiment alerts.

    Returns ``{"alerts": [...], "summary": {...}}``. Alerts are sorted by
    urgency score (desc) and de-duplicated by event-id overlap so a ticker and
    its theme do not both fire for the same headlines.
    """
    if now is None:
        now = now_utc()

    # Only past (realized), recent events feed the clustering. Future catalysts
    # belong to the countdown timeline, not the breaking layer.
    recent: list[MarketEvent] = []
    for e in events:
        age = _age_hours(e, now)
        if age is not None and 0 <= age <= _RECENCY_WINDOW_H:
            recent.append(e)

    candidates: list[dict[str, Any]] = []

    # --- source-failure alert (honest: V6 may be blind to fresh data) -----
    # Only when the caller actually supplied source statuses; a missing list
    # means "not measured", not "offline".
    source_mode = fr.derive_source_mode(source_statuses) if source_statuses else "live"
    if source_statuses and source_mode in ("error", "offline"):
        failed = [s for s in (source_statuses or []) if s.get("mode") in ("error", "unavailable")]
        names = "、".join(s.get("source_name", "") for s in failed[:4]) or "部分公开数据源"
        candidates.append({
            "alert_id": "src-failure",
            "urgency": "elevated",
            "urgency_score": 55,
            "alert_type": "source_failure",
            "title_zh": "数据源可用性告警",
            "summary_zh": (
                f"{names} 当前返回错误或不可用，系统可能未能获取最新公共新闻流，"
                f"新鲜度存在不确定性，请谨慎判断。"
            ),
            "affected_tickers": [],
            "affected_tags": [],
            "dominant_direction": "unknown",
            "confidence": 0.0,
            "evidence_count": len(failed),
            "source_count": len(failed),
            "first_seen_at": None,
            "last_seen_at": None,
            "freshness_status": fr.UNKNOWN,
            "event_ids": [],
        })

    # --- ticker clusters (company-level shocks) ---------------------------
    by_ticker: dict[str, list[MarketEvent]] = {}
    for e in recent:
        for tk in e.related_tickers:
            by_ticker.setdefault(tk, []).append(e)
    for ticker, evs in sorted(by_ticker.items()):
        metrics = _score_cluster(evs, now)
        if not _qualifies(metrics) or metrics["urgency"] == "normal":
            continue
        dirw = _DIR_ZH[metrics["dominant_direction"]]
        if metrics["evidence_count"] == 1 and metrics["has_urgent"]:
            atype = "breaking_news"
            title = f"突发：{ticker} · {event_type_cn(evs[0].event_type)}"
        elif metrics["n_2h"] >= 3 and not metrics["has_urgent"]:
            atype = "headline_velocity"
            title = f"{ticker} 标题密集度异常升高"
        else:
            atype = "company_shock"
            title = f"{ticker} 出现密集{dirw}新闻流"
        summary = (
            f"近 {int(_RECENCY_WINDOW_H)} 小时内检测到 {metrics['evidence_count']} 条与 "
            f"{ticker} 相关的事件（其中 {metrics['n_2h']} 条集中在 2 小时内），来自 "
            f"{metrics['source_count']} 个公开来源，整体{dirw}。此为公共新闻流聚类提示（近实时，"
            f"可能存在延迟），非投资建议。"
        )
        candidates.append(_build_alert(
            alert_id=f"tk-{ticker}", alert_type=atype, title_zh=title,
            summary_zh=summary, events=evs, metrics=metrics, now=now,
        ))

    # --- theme clusters (macro / sector / sentiment shocks) ---------------
    by_theme: dict[str, list[MarketEvent]] = {}
    for e in recent:
        for th in _themes_of(e):
            by_theme.setdefault(th, []).append(e)
    for theme, evs in sorted(by_theme.items()):
        metrics = _score_cluster(evs, now)
        if not _qualifies(metrics) or metrics["urgency"] == "normal":
            continue
        theme_zh = _THEME_ZH.get(theme, theme)
        dirw = _DIR_ZH[metrics["dominant_direction"]]
        if theme in _SENTIMENT_THEMES:
            atype = "sentiment_shock"
            title = f"市场情绪快速切换：{theme_zh}（{dirw}）"
        elif theme in _MACRO_THEMES:
            atype = "macro_shock"
            title = f"宏观风险信号聚集：{theme_zh}"
        elif metrics["n_2h"] >= 3 and not metrics["has_urgent"]:
            atype = "headline_velocity"
            title = f"主题标题密集升温：{theme_zh}"
        else:
            atype = "sector_shock"
            title = f"板块 / 主题新闻流升温：{theme_zh}"
        summary = (
            f"「{theme_zh}」主题近 {int(_RECENCY_WINDOW_H)} 小时聚集 {metrics['evidence_count']} 条相关事件"
            f"（2 小时内 {metrics['n_2h']} 条），来自 {metrics['source_count']} 个公开来源，整体{dirw}。"
            f"此为公共新闻流聚类提示（近实时，可能存在延迟），非投资建议。"
        )
        candidates.append(_build_alert(
            alert_id=f"th-{theme}", alert_type=atype, title_zh=title,
            summary_zh=summary, events=evs, metrics=metrics, now=now,
        ))

    # --- de-duplicate by event-id overlap, keep the higher-scored alert ----
    candidates.sort(key=lambda a: a["urgency_score"], reverse=True)
    surfaced: list[dict[str, Any]] = []
    for cand in candidates:
        ids = set(cand.get("event_ids") or [])
        dup = False
        for kept in surfaced:
            kept_ids = set(kept.get("event_ids") or [])
            if ids and kept_ids and len(ids & kept_ids) / len(ids) >= 0.6:
                dup = True
                break
        if not dup:
            surfaced.append(cand)
        if len(surfaced) >= max_alerts:
            break

    breaking_n = sum(1 for a in surfaced if a["urgency"] == "breaking")
    elevated_n = sum(1 for a in surfaced if a["urgency"] == "elevated")
    max_urgency = "breaking" if breaking_n else "elevated" if elevated_n else "normal"
    return {
        "alerts": surfaced,
        "summary": {
            "total": len(surfaced),
            "breaking": breaking_n,
            "elevated": elevated_n,
            "max_urgency": max_urgency,
            "has_source_failure": any(a["alert_type"] == "source_failure" for a in surfaced),
        },
    }
