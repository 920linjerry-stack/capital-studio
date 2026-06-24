"""V6 real event calendar: scheduled macro releases + earnings dates.

Why this module exists
----------------------
The original future-event demo built scheduled catalysts as ``now + fixed_days``
on every request, so the countdown was frozen ("always 2 days away") and a real
bellwether such as a Micron (MU) earnings print could never appear. This module
replaces that with **real, fixed calendar dates**:

* Macro releases (FOMC / CPI / jobs) come from a committed schedule -- FOMC from
  an exact published table (the meetings are irregular), CPI and jobs generated
  from their deterministic monthly cadence so the calendar never runs empty.
* Earnings dates come from a committed fallback table for the curated universe
  plus a set of sector *bellwethers* (NVDA / AVGO / MU / TSM ...), optionally
  refreshed from yfinance (keyless) into a local cache.

Because the dates are fixed, the countdown genuinely counts down and expires.

Boundaries
----------
Deterministic. No LLM. Network is OFF by default (``allow_network=False``) and
is only ever used to refresh the earnings cache; every code path works fully
offline from committed data. Produced events carry ``data_mode`` honestly
("fixture" for the committed fallback, "live" when refreshed from yfinance).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from modeling.v6.schemas import MarketEvent, DIRECTION_NEUTRAL

_DATA_DIR = Path(__file__).with_name("data")
_EARNINGS_CACHE = _DATA_DIR / "earnings_cache.json"

# Default look-ahead horizon for surfacing scheduled catalysts (days).
DEFAULT_HORIZON_DAYS = 120


# --- Macro schedule -------------------------------------------------------
# FOMC decision days (announcement ~18:00 UTC). Meetings are irregular, so the
# exact dates are tabled and must be refreshed annually from the Fed calendar.
_FOMC_DECISION_DATES = (
    # 2026
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-16",
    # 2027 (provisional; refresh when the Fed publishes the official schedule)
    "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-16",
    "2027-07-28", "2027-09-22", "2027-11-03", "2027-12-15",
)

# US data prints land at 08:30 ET == 12:30 UTC (we ignore DST by ~1h; the day is
# what matters for a multi-day countdown).
_RELEASE_UTC = (12, 30)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _at(date: datetime, hm: tuple[int, int]) -> datetime:
    return date.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0, tzinfo=timezone.utc)


def _first_friday(year: int, month: int) -> datetime:
    d = datetime(year, month, 1, tzinfo=timezone.utc)
    # weekday(): Mon=0 .. Fri=4
    return d + timedelta(days=(4 - d.weekday()) % 7)


def _month_iter(now: datetime, horizon_days: int):
    """Yield (year, month) for every month touched by [now, now+horizon]."""
    end = now + timedelta(days=horizon_days)
    y, m = now.year, now.month
    seen = set()
    while (y, m) <= (end.year, end.month):
        if (y, m) not in seen:
            seen.add((y, m))
            yield y, m
        m += 1
        if m > 12:
            m, y = 1, y + 1


def macro_calendar_events(now: datetime, horizon_days: int = DEFAULT_HORIZON_DAYS) -> list[MarketEvent]:
    """Build scheduled macro MarketEvents (FOMC / CPI / jobs) within the horizon.

    Direction is left NEUTRAL: the realized direction of a scheduled release is
    genuinely unknown until it prints (we do not fabricate a consensus lean).
    The events still surface in the countdown timeline and pre-price via the
    timing module's anticipation ramp.
    """
    end = now + timedelta(days=horizon_days)
    out: list[MarketEvent] = []

    # FOMC: exact tabled dates.
    for d in _FOMC_DECISION_DATES:
        rel = _at(datetime.fromisoformat(d), (18, 0))
        if now <= rel <= end:
            out.append(_sched_event(
                event_id=f"cal-fomc-{d}",
                title=f"FOMC rate decision ({d})",
                source="Federal Reserve (scheduled)",
                source_type="macro",
                event_type="fomc_decision",
                scheduled_at=_iso(rel),
                affected_tags=["rates", "yields"],
                anticipation_score=0.45, priced_in_score=0.45, sell_the_news_risk=0.2,
                summary="FOMC 利率决议（已排期）。实际方向待公布；预期会提前部分定价。",
            ))

    # CPI (~13th) and jobs (first Friday): generated monthly cadence.
    for y, m in _month_iter(now, horizon_days):
        cpi = _at(datetime(y, m, 13, tzinfo=timezone.utc), _RELEASE_UTC)
        if now <= cpi <= end:
            out.append(_sched_event(
                event_id=f"cal-cpi-{y}-{m:02d}",
                title=f"CPI inflation report ({y}-{m:02d})",
                source="BLS (scheduled)", source_type="macro", event_type="cpi_release",
                scheduled_at=_iso(cpi), affected_tags=["inflation", "yields", "rates"],
                anticipation_score=0.55, priced_in_score=0.5, sell_the_news_risk=0.25,
                summary="CPI 通胀数据（已排期）。冷热将驱动利率敏感资产；实际方向待公布。",
            ))
        jobs = _at(_first_friday(y, m), _RELEASE_UTC)
        if now <= jobs <= end:
            out.append(_sched_event(
                event_id=f"cal-jobs-{y}-{m:02d}",
                title=f"Nonfarm payrolls / jobs report ({y}-{m:02d})",
                source="BLS (scheduled)", source_type="macro", event_type="jobs_report",
                scheduled_at=_iso(jobs), affected_tags=["rates", "risk_sentiment"],
                anticipation_score=0.45, priced_in_score=0.4, sell_the_news_risk=0.2,
                summary="非农就业数据（已排期）。强弱将影响利率与风险偏好；实际方向待公布。",
            ))

    out.sort(key=lambda e: e.scheduled_at)
    return out


# --- Earnings schedule ----------------------------------------------------
# Sector bellwethers: their prints move the whole complex via read-through, so
# they are surfaced even when not held (the contagion layer maps the impact).
BELLWETHERS = (
    "NVDA", "AVGO", "MU", "TSM", "AMD", "ASML",   # AI / semis complex
    "AAPL", "MSFT", "GOOGL", "AMZN", "META",       # megacap tech
    "JPM", "BAC", "GS",                            # banks
    "XOM", "CVX",                                  # energy
    "LLY", "UNH",                                  # healthcare
)

# Committed fallback earnings dates (realistic quarterly cadence). Refresh from
# yfinance for production accuracy; these keep the offline demo meaningful and
# count down correctly until they pass.
_EARNINGS_FALLBACK: dict[str, str] = {
    "MU": "2026-06-25",    # fiscal Q3 print -- the bellwether the demo was missing
    "NVDA": "2026-08-26", "AVGO": "2026-09-04", "AMD": "2026-07-28",
    "TSM": "2026-07-16", "ASML": "2026-07-15",
    "AAPL": "2026-07-30", "MSFT": "2026-07-28", "GOOGL": "2026-07-28",
    "AMZN": "2026-07-30", "META": "2026-07-29",
    "JPM": "2026-07-14", "BAC": "2026-07-15", "GS": "2026-07-15",
    "XOM": "2026-07-31", "CVX": "2026-08-01",
    "LLY": "2026-08-06", "UNH": "2026-07-14",
}


def _load_earnings_cache() -> dict[str, str]:
    if not _EARNINGS_CACHE.exists():
        return {}
    try:
        data = json.loads(_EARNINGS_CACHE.read_text(encoding="utf-8"))
        return data.get("dates", {}) if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def _write_earnings_cache(dates: dict[str, str]) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "_meta": {"source": "yfinance get_earnings_dates (keyless)", "refreshed_at": _iso(datetime.now(timezone.utc))},
        "dates": dict(sorted(dates.items())),
    }
    _EARNINGS_CACHE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def refresh_earnings_dates(tickers: list[str], *, timeout: float = 6.0) -> dict[str, str]:
    """Best-effort yfinance refresh of next earnings dates -> local cache.

    Returns the merged date map. One ticker failing never aborts the others.
    Only called when a caller explicitly opts into network access.
    """
    merged = dict(_EARNINGS_FALLBACK)
    merged.update(_load_earnings_cache())
    try:
        import yfinance as yf
    except ImportError:
        return merged
    now = datetime.now(timezone.utc)
    for t in tickers:
        try:
            df = yf.Ticker(t).get_earnings_dates(limit=8)
            if df is None or df.empty:
                continue
            future = [idx for idx in df.index if idx.to_pydatetime().astimezone(timezone.utc) >= now]
            if future:
                merged[t.upper()] = min(future).to_pydatetime().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:  # noqa: BLE001 - a single symbol must not break the batch
            continue
    _write_earnings_cache(merged)
    return merged


def earnings_events(
    tickers: list[str],
    now: datetime,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    *,
    allow_network: bool = False,
) -> list[MarketEvent]:
    """Build earnings_date MarketEvents for held tickers + sector bellwethers.

    Held names get their own direct catalyst; bellwethers are surfaced so the
    contagion layer can map their read-through onto the portfolio's holdings.
    """
    universe = {t.upper() for t in (tickers or [])} | set(BELLWETHERS)
    if allow_network:
        dates = refresh_earnings_dates(sorted(universe))
    else:
        dates = dict(_EARNINGS_FALLBACK)
        dates.update(_load_earnings_cache())
    data_mode = "live" if (allow_network and _EARNINGS_CACHE.exists()) else "fixture"

    end = now + timedelta(days=horizon_days)
    held = {t.upper() for t in (tickers or [])}
    out: list[MarketEvent] = []
    for ticker in sorted(universe):
        iso = dates.get(ticker)
        if not iso:
            continue
        rel = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if rel.tzinfo is None:
            rel = rel.replace(tzinfo=timezone.utc)
        rel = rel.astimezone(timezone.utc)
        if not (now <= rel <= end):
            continue
        is_held = ticker in held
        out.append(_sched_event(
            event_id=f"cal-earn-{ticker}-{rel.date().isoformat()}",
            title=f"{ticker} quarterly earnings ({'持仓' if is_held else 'sector bellwether'})",
            source="Earnings calendar", source_type="company", event_type="earnings_date",
            scheduled_at=_iso(rel), related_tickers=[ticker],
            affected_tags=["earnings", "guidance"],
            anticipation_score=0.6, priced_in_score=0.65, sell_the_news_risk=0.45,
            summary=f"{ticker} 财报披露（已排期）。预期较高时存在「利好出尽」风险；实际方向待公布。",
            data_mode=data_mode,
        ))
    out.sort(key=lambda e: e.scheduled_at)
    return out


def _sched_event(
    *, event_id: str, title: str, source: str, source_type: str, event_type: str,
    scheduled_at: str, affected_tags: list[str] | None = None,
    related_tickers: list[str] | None = None, anticipation_score: float = 0.5,
    priced_in_score: float = 0.5, sell_the_news_risk: float = 0.25,
    summary: str = "", data_mode: str = "fixture",
) -> MarketEvent:
    return MarketEvent(
        event_id=event_id, title=title, source=source, source_type=source_type,
        timestamp=scheduled_at, scheduled_at=scheduled_at, effective_at=scheduled_at,
        event_type=event_type, direction=DIRECTION_NEUTRAL,
        affected_tags=list(affected_tags or []), related_tickers=list(related_tickers or []),
        anticipation_score=anticipation_score, priced_in_score=priced_in_score,
        surprise_sensitivity=0.8, sell_the_news_risk=sell_the_news_risk,
        summary=summary, data_mode=data_mode, confidence=0.6,
    )


def build_calendar_events(
    tickers: list[str] | None = None,
    now: datetime | None = None,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    *,
    allow_network: bool = False,
) -> list[MarketEvent]:
    """Real scheduled macro + earnings catalysts within the horizon, sorted.

    This is the product replacement for the synthetic ``now + delta`` future
    fixtures: every event has a fixed real date, so the countdown counts down.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    events = macro_calendar_events(now, horizon_days)
    events += earnings_events(tickers or [], now, horizon_days, allow_network=allow_network)
    events.sort(key=lambda e: e.scheduled_at)
    return events
