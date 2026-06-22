"""V6 data-freshness layer: deterministic staleness grading + honest metadata.

Turns a batch of :class:`~modeling.v6.schemas.MarketEvent` records (plus the
per-source status rows from the registry) into an explicit freshness report so
the cockpit can never silently present yesterday's data as "today's latest".

Pure and deterministic: equal ``(events, statuses, now)`` inputs always produce
equal output. No network, no LLM, no file I/O.

Grading rules (age measured from the event's published / effective time):

* ``<= 6h``                       -> ``fresh``
* ``> 6h`` and ``<= 24h``         -> ``delayed``
* ``> 24h``                       -> ``stale``
* ``data_mode == "fixture"``      -> ``fixture``  (sample / fallback data)
* future-dated scheduled catalyst -> ``scheduled_event`` (NOT stale)
* future-dated non-scheduled      -> ``future_event_active`` (NOT stale)
* missing / unparseable timestamp -> ``unknown``

The top-level ``freshness_status`` reflects how trustworthy the *latest* real
datapoint is: it is graded from the freshest non-fixture, timestamped, realized
event. If there is no such event, the status falls back to ``fixture`` (when
fixture data is present) or ``unknown`` (no usable data at all).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from modeling.v6.schemas import MarketEvent
from modeling.v6.timing import parse_dt, now_utc

# --- age thresholds (seconds) --------------------------------------------
FRESH_MAX_S = 6 * 3600        # <= 6h  -> fresh
DELAYED_MAX_S = 24 * 3600     # <= 24h -> delayed; older -> stale

# --- top-level / per-event freshness vocabulary --------------------------
FRESH = "fresh"
DELAYED = "delayed"
STALE = "stale"
FIXTURE = "fixture"
UNKNOWN = "unknown"
# per-event only: future catalysts are graded separately, never "stale"
FUTURE_ACTIVE = "future_event_active"
SCHEDULED = "scheduled_event"

# Freshness ranked best -> worst, used to roll a set of per-event states up to
# a single "freshest wins" cluster label. Future/fixture sit out of the band.
_FRESHNESS_RANK = {FRESH: 0, DELAYED: 1, STALE: 2, FIXTURE: 3, UNKNOWN: 4}

_LABEL_ZH = {
    FRESH: "新鲜",
    DELAYED: "存在延迟",
    STALE: "陈旧",
    FIXTURE: "示例回退",
    UNKNOWN: "时间未知",
    FUTURE_ACTIVE: "未来事件",
    SCHEDULED: "已排期事件",
}

# --- source_mode vocabulary (honest provenance for the page badge) -------
SOURCE_MODE_ZH = {
    "live": "实时",
    "partial_live": "部分实时",
    "fixture_fallback": "示例回退",
    "offline": "离线 / 未接实时源",
    "error": "获取错误",
}


def _published_dt(event: MarketEvent) -> datetime | None:
    """The instant this event carries information for (effective > ts > sched)."""
    return (parse_dt(event.effective_at)
            or parse_dt(event.timestamp)
            or parse_dt(event.scheduled_at))


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def event_freshness(event: MarketEvent, now: datetime | None = None) -> str:
    """Deterministic freshness state for a single event.

    Future-dated catalysts are reported as ``scheduled_event`` /
    ``future_event_active`` and never as ``stale``. Fixture-mode events are
    honestly labelled ``fixture`` regardless of their (synthetic) timestamp.
    """
    if now is None:
        now = now_utc()
    dt = _published_dt(event)
    if dt is not None and (dt - now).total_seconds() > 0:
        # not yet realized -> a forward catalyst, graded by the timeline, not here
        return SCHEDULED if event.is_scheduled else FUTURE_ACTIVE
    if event.data_mode == "fixture":
        return FIXTURE
    if dt is None:
        return UNKNOWN
    delta = (now - dt).total_seconds()
    if delta <= FRESH_MAX_S:
        return FRESH
    if delta <= DELAYED_MAX_S:
        return DELAYED
    return STALE


def freshness_label_zh(status: str) -> str:
    return _LABEL_ZH.get(status, status)


def rollup_freshness(states: list[str]) -> str:
    """Collapse per-event freshness states to one cluster label (freshest wins).

    Only the in-band states (fresh/delayed/stale/fixture/unknown) participate;
    future/scheduled states are ignored. Empty / future-only -> ``unknown``.
    """
    ranked = [s for s in states if s in _FRESHNESS_RANK]
    if not ranked:
        return UNKNOWN
    return min(ranked, key=lambda s: _FRESHNESS_RANK[s])


def derive_source_mode(statuses: list[dict[str, Any]] | None) -> str:
    """Map per-source registry modes to a single public ``source_mode``.

    Returns one of ``live`` / ``partial_live`` / ``fixture_fallback`` /
    ``offline`` / ``error``. ``live`` only when *every* source is live-like.
    """
    if not statuses:
        return "offline"
    modes = [s.get("mode") for s in statuses]
    live_like = [m for m in modes if m in ("live", "live-partial")]
    if live_like:
        return "live" if all(m in ("live", "live-partial") for m in modes) else "partial_live"
    if any(m == "error" for m in modes):
        return "error"
    if any(m == "unavailable" for m in modes):
        return "offline"
    if any(m == "fixture" for m in modes):
        return "fixture_fallback"
    return "offline"


def _aggregate_source_times(statuses: list[dict[str, Any]] | None) -> tuple[str | None, str | None]:
    """Most-recent success / error wall-clock across all sources (ISO or None)."""
    if not statuses:
        return None, None
    successes = [s.get("last_success") for s in statuses if s.get("last_success")]
    errors = [s.get("last_error") for s in statuses if s.get("last_error")]
    return (max(successes) if successes else None,
            max(errors) if errors else None)


def _warning_zh(status: str, source_mode: str) -> str:
    """Build a visible Chinese warning, or '' when data is trustworthy.

    Non-empty whenever the top-level status is stale/fixture/unknown or the
    source layer is degraded (error/offline/fixture fallback).
    """
    parts: list[str] = []
    if status == STALE:
        parts.append("最新事件已超过 24 小时，可能未反映最新动态，请谨慎参考。")
    elif status == UNKNOWN:
        parts.append("无法确认事件时间戳，数据新鲜度未知，请谨慎参考。")

    if source_mode in ("fixture_fallback",) or status == FIXTURE:
        parts.append("当前为示例回退数据，未接入实时公开新闻流，并非实时行情。")
    elif source_mode == "error":
        parts.append("部分公开数据源返回错误，可能未能获取最新公共新闻流。")
    elif source_mode == "offline":
        parts.append("未接入实时公开新闻流，展示内容可能存在延迟。")

    # de-duplicate while keeping order
    seen: list[str] = []
    for p in parts:
        if p not in seen:
            seen.append(p)
    return "".join(seen)


def compute_freshness(
    events: list[MarketEvent],
    source_statuses: list[dict[str, Any]] | None = None,
    *,
    now: datetime | None = None,
    source_mode: str | None = None,
    fetch_started_at: str | None = None,
    fetch_finished_at: str | None = None,
) -> dict[str, Any]:
    """Assemble the full freshness metadata block for the API response.

    ``source_mode`` is derived from ``source_statuses`` when not supplied. The
    returned dict is JSON-serializable and additive to the existing payload.
    """
    if now is None:
        now = now_utc()
    if source_mode is None:
        source_mode = derive_source_mode(source_statuses)

    counts: dict[str, int] = {}
    live_event_count = 0      # non-fixture, timestamped, realized (gradeable)
    fixture_event_count = 0
    stale_event_count = 0
    realized: list[tuple[float, datetime]] = []   # (age_seconds, published_dt)

    for e in events:
        fs = event_freshness(e, now)
        counts[fs] = counts.get(fs, 0) + 1
        if fs == FIXTURE:
            fixture_event_count += 1
        elif fs in (FRESH, DELAYED, STALE):
            live_event_count += 1
            if fs == STALE:
                stale_event_count += 1
        # track realized (past, timestamped) events for the age window,
        # regardless of data_mode so the demo still reports a real age span
        dt = _published_dt(e)
        if dt is not None:
            age = (now - dt).total_seconds()
            if age >= 0:
                realized.append((age, dt))

    # top-level status: grade the freshest gradeable (non-fixture) event
    if live_event_count > 0:
        freshest_age = min(
            (now - _published_dt(e)).total_seconds()
            for e in events
            if event_freshness(e, now) in (FRESH, DELAYED, STALE)
        )
        if freshest_age <= FRESH_MAX_S:
            status = FRESH
        elif freshest_age <= DELAYED_MAX_S:
            status = DELAYED
        else:
            status = STALE
    elif counts.get(UNKNOWN):
        status = UNKNOWN
    elif fixture_event_count > 0:
        status = FIXTURE
    else:
        status = UNKNOWN

    newest_at = oldest_at = None
    max_age_minutes = None
    if realized:
        newest_age, newest_dt = min(realized, key=lambda t: t[0])
        oldest_age, oldest_dt = max(realized, key=lambda t: t[0])
        newest_at = _iso(newest_dt)
        oldest_at = _iso(oldest_dt)
        max_age_minutes = round(oldest_age / 60.0, 1)

    last_success, last_error = _aggregate_source_times(source_statuses)

    return {
        "freshness_status": status,
        "freshness_label_zh": freshness_label_zh(status),
        "freshness_warning_zh": _warning_zh(status, source_mode),
        "source_mode": source_mode,
        "source_mode_zh": SOURCE_MODE_ZH.get(source_mode, source_mode),
        "newest_event_published_at": newest_at,
        "oldest_event_published_at": oldest_at,
        "max_event_age_minutes": max_age_minutes,
        "event_count_by_freshness": counts,
        "live_event_count": live_event_count,
        "fixture_event_count": fixture_event_count,
        "stale_event_count": stale_event_count,
        "source_last_success_at": last_success,
        "source_last_error_at": last_error,
        "source_fetch_started_at": fetch_started_at,
        "source_fetch_finished_at": fetch_finished_at,
    }
