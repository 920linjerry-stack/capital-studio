"""V6 temporal engine: future-event countdown, anticipation, and decay.

Pure, deterministic time math over a `MarketEvent` and a reference ``now``.
Given an event's timing fields, it computes:

* ``phase`` -- upcoming / anticipation / live / post_event / expired
* ``countdown_seconds`` / ``countdown_days`` -- signed time to the release
* a signed **temporal multiplier** applied to the event's signed impact:
  ``temporal_multiplier = time_weight * direction_factor`` where

  - ``time_weight`` (0..1) ramps UP before a scheduled release (the market
    pre-prices expectations) and decays DOWN after it (impact fades);
  - ``direction_factor`` (-1..1) is normally 1, but goes toward 0 or flips
    negative right after a release with high *sell-the-news* / priced-in risk
    (利好出尽 / "good news exhausted").

No network, no LLM. Equal (event, now) inputs always produce equal output.

The future-event impact follows the spec's transparent shape::

    future_impact = base_impact x anticipation_factor x confidence
                    x relevance x time_weight

Here ``base_impact`` and ``confidence`` x ``relevance`` already live in the
impact engine's per-contribution score; this module supplies the
``anticipation_factor``-folded ``time_weight`` (and the post-event decay), so
the engine only multiplies the contribution by ``temporal_multiplier``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from modeling.v6.schemas import MarketEvent, SCHEDULED_EVENT_TYPES

# Per-type defaults for scheduled catalysts: how many days ahead the market
# starts pre-pricing, how much of the impact prices in pre-event, the
# sell-the-news risk, and the post-event half-life (hours).
_SCHED_DEFAULTS: dict[str, dict[str, float]] = {
    "fomc_decision":      {"antic_days": 10, "antic": 0.45, "sell_news": 0.20, "post_h": 72},
    "cpi_release":        {"antic_days": 7,  "antic": 0.55, "sell_news": 0.25, "post_h": 48},
    "jobs_report":        {"antic_days": 5,  "antic": 0.45, "sell_news": 0.20, "post_h": 36},
    "earnings_date":      {"antic_days": 14, "antic": 0.60, "sell_news": 0.40, "post_h": 72},
    "product_launch":     {"antic_days": 21, "antic": 0.70, "sell_news": 0.55, "post_h": 48},
    "policy_announcement":{"antic_days": 10, "antic": 0.50, "sell_news": 0.30, "post_h": 96},
}
_SCHED_FALLBACK = {"antic_days": 7, "antic": 0.50, "sell_news": 0.25, "post_h": 72}

# Per-type half-life (hours) for *recent past* (non-scheduled) headlines.
_RECENT_DECAY_H: dict[str, float] = {
    "analyst_upgrade": 72, "analyst_downgrade": 72,
    "price_target_raise": 72, "price_target_cut": 72,
    "earnings_beat": 120, "earnings_miss": 120,
    "guidance_raise": 168, "guidance_cut": 168,
    "macro_inflation_hot": 96, "macro_inflation_cool": 96,
    "rate_cut": 120, "rate_hike": 120,
    "yields_up": 72, "yields_down": 72,
    "regulatory_risk": 240, "lawsuit_investigation": 336,
    "ai_capex_semis": 120, "risk_on": 48, "risk_off": 48,
}
_RECENT_DECAY_FALLBACK = 96.0

# Window (hours) before the scheduled instant that counts as "live / imminent".
_LIVE_WINDOW_H = 6.0
# Multiple of half-life after which an event is considered fully expired.
_EXPIRED_HALF_LIVES = 5.0

_HOUR = 3600.0
_DAY = 86400.0


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: str) -> datetime | None:
    """Parse an ISO-8601 string (accepting a trailing 'Z') to aware UTC."""
    if not value:
        return None
    try:
        s = value.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _sched_defaults(event: MarketEvent) -> dict[str, float]:
    return _SCHED_DEFAULTS.get(event.event_type, _SCHED_FALLBACK)


def _release_time(event: MarketEvent) -> datetime | None:
    """The instant the event realizes (effective_at, else scheduled_at, else timestamp)."""
    return (parse_dt(event.effective_at)
            or parse_dt(event.scheduled_at)
            or parse_dt(event.timestamp))


def age_info(event: MarketEvent, now: datetime | None = None) -> dict[str, Any]:
    """Deterministic item-age + staleness for an event (UI labelling).

    Returns ``{age_seconds, label, band}``. ``band`` is one of: fixture (示例
    数据), future (待公布), fresh, lagging, stale, unknown. Fixture-mode events
    are honestly labelled rather than given a false "fresh" age.
    """
    if now is None:
        now = now_utc()
    if event.data_mode == "fixture":
        return {"age_seconds": None, "label": "示例数据", "band": "fixture"}
    dt = parse_dt(event.effective_at) or parse_dt(event.timestamp) or parse_dt(event.scheduled_at)
    if dt is None:
        return {"age_seconds": None, "label": "时间未知", "band": "unknown"}
    delta = (now - dt).total_seconds()
    if delta < 0:
        return {"age_seconds": round(delta, 1), "label": "待公布", "band": "future"}
    if delta < 3600:
        label = "刚刚" if delta < 600 else f"{int(delta // 60)}分钟前"
        band = "fresh"
    elif delta < _DAY:
        label = f"{int(delta // _HOUR)}小时前"
        band = "fresh"
    elif delta < 3 * _DAY:
        label = f"{int(delta // _DAY)}天前"
        band = "lagging"
    else:
        label = f"{int(delta // _DAY)}天前"
        band = "stale"
    return {"age_seconds": round(delta, 1), "label": label, "band": band}


def temporal_profile(event: MarketEvent, now: datetime | None = None) -> dict[str, Any]:
    """Compute the temporal profile of ``event`` relative to ``now``.

    Returns a dict with phase, countdowns, time_weight, direction_factor, the
    combined signed ``temporal_multiplier``, and a Chinese ``label`` for the UI.
    Events with no parseable time get a neutral, full-weight profile.
    """
    if now is None:
        now = now_utc()

    release = _release_time(event)
    scheduled = event.is_scheduled and (parse_dt(event.scheduled_at) or release) is not None

    # No usable time -> treat as a current, full-weight event.
    if release is None:
        return _profile(phase="live", countdown_s=0.0, time_weight=1.0,
                        direction_factor=1.0, label="当前事件", is_future=False)

    delta_s = (release - now).total_seconds()   # >0 future, <0 past

    # ---- scheduled catalyst, before release: anticipation ramp ----------
    if scheduled and delta_s > 0:
        d = _sched_defaults(event)
        antic = event.anticipation_score or d["antic"]
        antic_days = d["antic_days"]
        horizon_s = antic_days * _DAY
        # ramp 0..1 as now moves from (release - horizon) toward release
        if delta_s >= horizon_s:
            phase = "upcoming"
            ramp = 0.0
        else:
            phase = "anticipation"
            ramp = _clamp(1.0 - (delta_s / horizon_s), 0.0, 1.0)
        if 0 < delta_s <= _LIVE_WINDOW_H * _HOUR:
            phase = "live"
            ramp = 1.0
        time_weight = _clamp(antic * ramp, 0.0, 1.0)
        label = {"upcoming": "待公布", "anticipation": "预期升温", "live": "即将公布"}[phase]
        return _profile(phase=phase, countdown_s=delta_s, time_weight=time_weight,
                        direction_factor=1.0, label=label, is_future=True,
                        anticipation=antic, ramp=ramp)

    # ---- released: just-released (live) OR decaying post-event / recent --
    age_h = max(0.0, -delta_s / _HOUR)
    if scheduled:
        d = _sched_defaults(event)
        half_h = event.post_event_decay_hours or d["post_h"]
    else:
        half_h = event.decay_hours or _RECENT_DECAY_H.get(event.event_type, _RECENT_DECAY_FALLBACK)

    decay = 0.5 ** (age_h / half_h) if half_h > 0 else 1.0
    expired = age_h >= half_h * _EXPIRED_HALF_LIVES
    # A scheduled event within the live window just realized: it carries full
    # impact (decay has barely started) and is labelled "live".
    within_live = scheduled and age_h <= _LIVE_WINDOW_H
    if expired:
        phase, time_weight, label = "expired", 0.0, "事件已兑现"
    elif within_live:
        phase, time_weight, label = "live", 1.0, "进行中"
    else:
        phase, time_weight, label = "post_event", _clamp(decay, 0.0, 1.0), "影响衰减"

    # sell-the-news: applies as soon as a scheduled, directional event realizes
    # (including the live window); dampens or flips the realized direction the
    # more was priced in and the higher the sell-the-news risk.
    direction_factor = 1.0
    if scheduled and not expired and event.direction != 0:
        sell_news = event.sell_the_news_risk or _sched_defaults(event)["sell_news"]
        recency = _clamp(1.0 - age_h / max(half_h, 1e-6), 0.0, 1.0)
        direction_factor = _clamp(1.0 - 1.8 * sell_news * event.priced_in_score * recency, -1.0, 1.0)
        if direction_factor < 0.5:
            label = "利好出尽风险" if event.direction > 0 else "利空出尽"

    return _profile(phase=phase, countdown_s=delta_s, time_weight=time_weight,
                    direction_factor=direction_factor, label=label, is_future=False)


def _profile(*, phase: str, countdown_s: float, time_weight: float,
             direction_factor: float, label: str, is_future: bool,
             anticipation: float = 0.0, ramp: float = 0.0) -> dict[str, Any]:
    return {
        "phase": phase,
        "countdown_seconds": round(countdown_s, 1),
        "countdown_days": round(countdown_s / _DAY, 3),
        "time_weight": round(time_weight, 4),
        "direction_factor": round(direction_factor, 4),
        "temporal_multiplier": round(time_weight * direction_factor, 6),
        "anticipation_factor": round(anticipation, 4),
        "ramp": round(ramp, 4),
        "label": label,
        "is_future": is_future,
    }
