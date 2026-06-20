"""V6 source registry: orchestrate adapters, isolate failures, report status.

One adapter failing never aborts the page: each adapter runs in a try/except,
its outcome (mode + count + error) is collected, and its items are converted to
events via the deterministic classifier. A tiny in-process TTL cache avoids
hammering live sources on rapid reloads.
"""

from __future__ import annotations

import time
from typing import Any

from modeling.v6.schemas import MarketEvent
from modeling.v6.sources.base import raw_to_event, FetchResult, DEFAULT_TIMEOUT
from modeling.v6.sources.adapters import ALL_ADAPTERS
from modeling.v6.dedupe import dedupe_events

SOURCE_REGISTRY = ALL_ADAPTERS

# Default tickers/keywords used when the caller passes none (keeps the demo
# meaningful). Real callers should pass their holdings' tickers.
_DEFAULT_TICKERS = ["AAPL", "NVDA", "MSFT"]
_DEFAULT_KEYWORDS = ["inflation", "rate decision", "AI capex", "semiconductor"]

# Simple TTL cache: key -> (expires_at, (events, statuses))
_CACHE: dict[tuple, tuple[float, Any]] = {}
_CACHE_TTL_S = 120.0

# Per-source reliability stats, accumulated across this process's fetches.
# source_id -> {last_attempt, last_success, last_error, success_count,
#               error_count, last_mode}. Wall-clock ISO strings; reset on restart.
_SOURCE_STATS: dict[str, dict[str, Any]] = {}


def _iso(ts: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record_stats(result: FetchResult, ts: float) -> dict[str, Any]:
    """Update and return the rolling reliability stats for one source."""
    s = _SOURCE_STATS.setdefault(result.source_id, {
        "last_attempt": None, "last_success": None, "last_error": None,
        "success_count": 0, "error_count": 0, "last_mode": None,
    })
    s["last_attempt"] = _iso(ts)
    s["last_mode"] = result.mode
    ok = result.mode in ("live", "live-partial", "fixture")
    if ok:
        s["success_count"] += 1
        s["last_success"] = _iso(ts)
    else:
        s["error_count"] += 1
        s["last_error"] = _iso(ts)
    return s


def _reliability(stats: dict[str, Any], mode: str) -> str:
    """Coarse reliability label from current mode + history."""
    if mode == "error":
        return "错误"
    if mode == "unavailable":
        return "未接实时源"
    if mode == "fixture":
        return "示例回退"
    if mode == "live-partial":
        return "部分实时"
    if stats.get("error_count", 0) > 0:
        return "部分实时"
    return "实时正常"


def _run_adapters(tickers, keywords, allow_network, timeout) -> list[FetchResult]:
    results: list[FetchResult] = []
    for adapter in SOURCE_REGISTRY:
        try:
            results.append(adapter.fetch(
                tickers=tickers, keywords=keywords,
                timeout=timeout, allow_network=allow_network,
            ))
        except Exception as e:  # noqa: BLE001 - registry must never raise
            results.append(FetchResult(
                getattr(adapter, "id", "unknown"),
                getattr(adapter, "name", "unknown"),
                "error", [], error=str(e),
            ))
    return results


def ingest_events(
    tickers: list[str] | None = None,
    keywords: list[str] | None = None,
    *,
    allow_network: bool = False,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[list[MarketEvent], list[dict[str, Any]]]:
    """Fetch + classify + dedupe events from all registered sources.

    Returns ``(events, source_statuses)``. ``source_statuses`` is one dict per
    adapter (source_id, source_name, mode, item_count, error). Network is OFF by
    default (fixture mode); pass ``allow_network=True`` to attempt live fetches.
    """
    tickers = tickers or _DEFAULT_TICKERS
    keywords = keywords or _DEFAULT_KEYWORDS
    cache_key = (tuple(tickers), tuple(keywords), allow_network)
    now = time.time()
    hit = _CACHE.get(cache_key)
    if hit and hit[0] > now:
        return hit[1]

    results = _run_adapters(tickers, keywords, allow_network, timeout)

    events: list[MarketEvent] = []
    idx = 0
    for r in results:
        for item in r.items:
            events.append(raw_to_event(item, idx, data_mode=r.mode))
            idx += 1
    events, _ = dedupe_events(events)
    statuses = []
    for r in results:
        st = r.to_status()
        stats = _record_stats(r, now)
        st["last_success"] = stats["last_success"]
        st["last_error"] = stats["last_error"]
        st["success_count"] = stats["success_count"]
        st["error_count"] = stats["error_count"]
        st["reliability"] = _reliability(stats, r.mode)
        statuses.append(st)

    _CACHE[cache_key] = (now + _CACHE_TTL_S, (events, statuses))
    return events, statuses


def get_source_status(allow_network: bool = False) -> list[dict[str, Any]]:
    """Lightweight per-source status for UI badges (uses the same fetch path)."""
    _, statuses = ingest_events(allow_network=allow_network)
    return statuses


def source_health(statuses: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll per-source statuses into a health summary for the UI.

    Reports counts by mode, whether any source errored / is unavailable / is
    fixture-only, and a single ``overall`` mode. Deterministic; no network.
    """
    by_mode: dict[str, int] = {}
    for s in statuses:
        by_mode[s["mode"]] = by_mode.get(s["mode"], 0) + 1
    total = len(statuses) or 1
    live_like = by_mode.get("live", 0) + by_mode.get("live-partial", 0)
    return {
        "by_mode": by_mode,
        "total": len(statuses),
        "ok_count": by_mode.get("live", 0) + by_mode.get("live-partial", 0) + by_mode.get("fixture", 0),
        "live_count": live_like,
        "any_error": (by_mode.get("error", 0) + by_mode.get("unavailable", 0)) > 0,
        "any_fixture": by_mode.get("fixture", 0) > 0,
        "all_fixture": by_mode.get("fixture", 0) == total,
        "overall": overall_data_mode(statuses),
    }


def overall_data_mode(statuses: list[dict[str, Any]]) -> str:
    """Roll per-source modes up into one label for the page badge."""
    modes = {s["mode"] for s in statuses}
    if "live" in modes and modes <= {"live", "live-partial"}:
        return "live"
    if "live" in modes or "live-partial" in modes:
        return "live-partial"
    if modes <= {"fixture"}:
        return "fixture"
    if "fixture" in modes:
        return "live-partial" if (modes & {"live", "live-partial"}) else "fixture"
    return "unavailable"
