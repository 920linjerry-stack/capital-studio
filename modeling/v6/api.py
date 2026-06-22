"""V6 API glue: thin, pure bridge between the Flask route and the engine.

It assembles a portfolio from caller-supplied holdings (or falls back to the
sample portfolio), runs the deterministic engine over the bundled sample event
feed (or a caller-supplied event list), and returns a single UI-facing dict.

No Flask import, no file I/O, no network, no LLM. Safe to unit-test directly.

The response always carries an explicit ``data_mode`` and a ``boundaries``
block so the UI can render the "mock data" and "not investment advice" notices
without guessing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from modeling.v6.exposure import build_portfolio
from modeling.v6.fixtures import load_fixture_events
from modeling.v6.impact_engine import analyze_portfolio
from modeling.v6.dedupe import dedupe_events
from modeling.v6.schemas import MarketEvent
from modeling.v6 import templates
from modeling.v6 import timing
from modeling.v6 import freshness as freshness_mod
from modeling.v6.breaking import detect_breaking
from modeling.v6.narrative import group_events, portfolio_narrative

# Single source of truth for the non-advice boundary, surfaced to the UI.
# Keeps the English "does not provide buy/sell" phrase for the guard test and
# adds the Chinese notice the UI renders.
BOUNDARIES = {
    "not_investment_advice": True,
    "no_buy_sell_signal": True,
    "no_target_price": True,
    "no_stop_loss": True,
    "engine": "deterministic rule-based (non-LLM)",
    "notice": (
        "V6 Market Intelligence maps events to holdings to explain potential "
        "impact direction. It does not provide buy/sell instructions, target "
        "prices, stop-losses, or automated trading recommendations."
    ),
    "notice_cn": (
        "V6 市场情报雷达仅将事件映射到持仓以解读潜在影响方向，"
        "不提供买入/卖出指令、目标价、止损位或任何自动交易建议。"
    ),
}


def build_intelligence_response(
    holdings: list[dict[str, Any]] | None = None,
    events: list[MarketEvent] | None = None,
    *,
    event_source: str = "sample",
    now: datetime | None = None,
    portfolio_is_demo: bool = False,
    allow_network: bool = False,
    include_source_feed: bool = False,
) -> dict[str, Any]:
    """Assemble the full V6 intelligence payload for the UI.

    Args:
        holdings: application portfolio rows (or synthetic sample rows). When
            falsy, the engine uses the bundled sample portfolio.
        events: Pre-built events. When ``None``, the bundled sample feed is used.
        event_source: Label for where events came from ("sample" | "live" | ...).
        now: Reference time for countdown/decay (defaults to current UTC).
        portfolio_is_demo: True when ``holdings`` is a built-in demo portfolio
            (not the user's real holdings) so the UI labels it as sample.

    Returns a JSON-serializable dict (see modeling/v6/README.md for the schema).
    """
    portfolio = build_portfolio(holdings)
    if events is None:
        events = load_fixture_events(now=now)

    # --- public source adapters: status badges + optional live ingestion --
    from modeling.v6.sources.registry import ingest_events, overall_data_mode, source_health
    from modeling.v6.sources.base import sanitize_source_status
    tickers = [p["exposure"].ticker for p in portfolio.get("positions", [])]
    fetch_started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    source_events, source_statuses = ingest_events(tickers=tickers, allow_network=allow_network)
    fetch_finished_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Defense-in-depth: re-scrub every source status at the V6 API boundary so a
    # raw adapter exception can never reach the client via ``sources[].error``,
    # even if a future adapter forgets to sanitize.
    source_statuses = [sanitize_source_status(s) for s in source_statuses]
    sources_overall = overall_data_mode(source_statuses)
    sources_health = source_health(source_statuses)
    if include_source_feed:
        # Merge ingested headlines with the curated set (which carries the
        # scheduled future catalysts) so the countdown still works.
        events = events + source_events
        if allow_network and sources_overall in ("live", "live-partial"):
            event_source = sources_overall

    # De-duplicate before scoring so multi-feed repeats do not over-count.
    events, dedupe_report = dedupe_events(events)

    analysis = analyze_portfolio(portfolio, events, now=now)
    # deterministic theme grouping + narrative (template-based, no LLM)
    analysis["themes"] = group_events(analysis)
    analysis["narrative"] = portfolio_narrative(analysis)

    # data_mode reflects the weakest "realness" link: a demo/sample portfolio
    # => "sample"; real holdings + sample events => "sample-events"; real +
    # live feed => "live".
    if portfolio.get("is_sample") or portfolio_is_demo:
        data_mode = "sample"
        analysis["is_sample_portfolio"] = True
    elif event_source == "sample":
        data_mode = "sample-events"
    else:
        data_mode = "live"

    ref_now = now or datetime.now(timezone.utc)
    generated_at = ref_now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Server-local rendering (uses the host timezone; falls back to UTC offset).
    generated_at_local = ref_now.astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")

    # --- freshness + breaking layers (deterministic, additive) ------------
    freshness = freshness_mod.compute_freshness(
        events, source_statuses, now=now,
        fetch_started_at=fetch_started_at, fetch_finished_at=fetch_finished_at,
    )
    breaking = detect_breaking(events, now=now, source_statuses=source_statuses)

    # Per-event portfolio relevance, from the driver aggregation, so the UI feed
    # can rank by how much each event actually moves THIS portfolio.
    relevance = {d["event_id"]: d for d in analysis.get("main_drivers", [])}
    ui_events = []
    for e in events:
        row = _event_for_ui(e)
        d = relevance.get(e.event_id)
        row["portfolio_abs_impact"] = d["abs_impact"] if d else 0.0
        row["portfolio_net_impact"] = d["net_impact"] if d else 0.0
        row["holdings_hit"] = d["holdings_hit"] if d else []
        age = timing.age_info(e, now)
        row["age_label"] = age["label"]
        row["age_band"] = age["band"]
        row["freshness_status"] = freshness_mod.event_freshness(e, now)
        ui_events.append(row)
    return {
        "version": "v6.4",
        "product": "V6 Market Intelligence",
        "generated_at": generated_at,
        "generated_at_local": generated_at_local,
        "data_mode": data_mode,
        "event_source": event_source,
        "event_count": len(events),
        "bands": _portfolio_bands(analysis, sources_overall),
        "summary": _event_summary(events),
        "risks": _risk_summary(analysis),
        "dedupe": dedupe_report,
        "sources": source_statuses,
        "sources_overall_mode": sources_overall,
        "source_health": sources_health,
        "source_feed_merged": include_source_feed,
        # freshness guard rails: never present stale data as "today's latest"
        "freshness": freshness,
        "source_mode": freshness["source_mode"],
        "source_health_summary": sources_health,
        "freshness_status": freshness["freshness_status"],
        "freshness_warning_zh": freshness["freshness_warning_zh"],
        # breaking-news / sudden-sentiment alert layer
        "alerts": breaking["alerts"],
        "alert_summary": breaking["summary"],
        "boundaries": BOUNDARIES,
        "portfolio": _strip_portfolio_internal(analysis),
        "events": ui_events,
    }


def _portfolio_bands(analysis: dict[str, Any], sources_overall: str) -> dict[str, Any]:
    """Deterministic portfolio-level bands for professional badges."""
    dis = analysis.get("disagreement", 0.0)
    conf = analysis.get("avg_confidence", 0.0)
    return {
        "disagreement": templates.disagreement_band(dis),
        "disagreement_cn": templates.disagreement_band_cn(dis),
        "confidence": templates.confidence_band(conf),
        "confidence_cn": templates.confidence_band_cn(conf),
        "freshness": sources_overall,
        "freshness_cn": templates.freshness_cn(sources_overall),
    }


def _event_summary(events: list[MarketEvent]) -> dict[str, Any]:
    """Counts by event_type, direction, source_type, and data_mode."""
    by_type: dict[str, int] = {}
    by_dir = {"bullish": 0, "bearish": 0, "neutral": 0}
    by_src: dict[str, int] = {}
    by_mode: dict[str, int] = {}
    scheduled = 0
    for e in events:
        by_type[e.event_type] = by_type.get(e.event_type, 0) + 1
        by_dir["bullish" if e.direction > 0 else "bearish" if e.direction < 0 else "neutral"] += 1
        by_src[e.source_type] = by_src.get(e.source_type, 0) + 1
        by_mode[e.data_mode] = by_mode.get(e.data_mode, 0) + 1
        if e.is_scheduled:
            scheduled += 1
    return {
        "by_event_type": by_type,
        "by_direction": by_dir,
        "by_source_type": by_src,
        "by_data_mode": by_mode,
        "scheduled_count": scheduled,
    }


def _risk_summary(analysis: dict[str, Any]) -> dict[str, Any]:
    """Surface the portfolio's main downside drivers and priced-in catalysts.

    Read-only attention items -- never an instruction. ``top_negative_drivers``
    are realized bearish events; ``priced_in_catalysts`` are upcoming events with
    elevated sell-the-news / 利好出尽 risk.
    """
    drivers = analysis.get("main_drivers", [])
    top_neg = [d for d in drivers if d["net_impact"] < 0][:3]
    priced_in = [
        {
            "event_id": f["event_id"], "title": f["title"], "event_type": f["event_type"],
            "countdown_days": f["countdown_days"], "phase": f["phase"],
            "sell_the_news_risk": f["sell_the_news_risk"], "priced_in_score": f["priced_in_score"],
            "affected_tickers": f["affected_tickers"],
        }
        for f in analysis.get("future_timeline", []) if f.get("sell_the_news_risk", 0) >= 0.4
    ]
    return {
        "top_negative_drivers": top_neg,
        "priced_in_catalysts": priced_in,
        "disagreement": analysis.get("disagreement", 0.0),
        "coverage": analysis.get("coverage", 0.0),
    }


def _event_for_ui(e: MarketEvent) -> dict[str, Any]:
    return {
        "event_id": e.event_id,
        "title": e.title,
        "source": e.source,
        "source_type": e.source_type,
        "timestamp": e.timestamp,
        "event_type": e.event_type,
        "direction": e.direction,
        "magnitude": e.magnitude,
        "confidence": round(e.confidence * e.classification_confidence, 4),
        "source_confidence": e.confidence,
        "classification_confidence": e.classification_confidence,
        "recognized_states": e.recognized_states,
        "classification_flags": e.classification_flags,
        "affected_tags": e.affected_tags,
        "related_tickers": e.related_tickers,
        "summary": e.summary,
        "data_mode": e.data_mode,
        "source_count": e.source_count,
        "source_list": e.source_list,
        "is_scheduled": e.is_scheduled,
        "scheduled_at": e.scheduled_at,
        "severity": templates.severity_band(e.magnitude),
        "severity_cn": templates.severity_cn(e.magnitude),
        "confidence_band": templates.confidence_band(e.confidence),
        "confidence_band_cn": templates.confidence_band_cn(e.confidence),
    }


def _strip_portfolio_internal(analysis: dict[str, Any]) -> dict[str, Any]:
    """Pass the engine output through unchanged for now.

    Kept as a seam: if internal-only fields are added to the engine later, they
    can be dropped here before reaching the UI (mirrors the ma/api.py pattern).
    """
    return analysis
