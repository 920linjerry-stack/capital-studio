"""V6 Historical Event Replay -- INTERNAL QA / calibration tool.

This is an internal engineering tool, NOT a user-facing product feature: there
is no HTTP route and no UI page. It produces NO buy/sell advice. Run it from
tests or a Python shell. It answers one engineering question: when a historical
event happened, would the current V6 engine have classified its impact on the
affected holdings as 偏利好 / 偏利空 / 中性 / 多空分歧 / 不确定 -- and did the
subsequent 1D/3D/5D/10D price reaction broadly support that directional read?
Use it to sanity-check / calibrate the event-impact engine, not to validate any
trading behaviour.

Design:

* :class:`HistoricalEvent` -- a curated past event with the information known
  at/before its timestamp, plus optional stored (fixture) post-event returns.
* :func:`to_market_event` -- converts a historical event into the existing V6
  ``MarketEvent`` using ONLY pre-event information (no look-ahead). Realized
  returns are never read during conversion.
* :func:`replay_event` / :func:`replay_all` -- run events through the live V6
  impact engine (at the event time, so temporal weight is full and undecayed)
  and pair the V6 read with realized returns from a return adapter.
* :func:`evaluate` -- deterministic validation metrics (hit rate, confusion
  matrix, calibration buckets).

No LLM, no brokerage, no network on the default path (fixture returns).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Callable

from modeling.v6.schemas import MarketEvent
from modeling.v6.classifier import classify_event
from modeling.v6.exposure import get_profile, _generic_profile
from modeling.v6.impact_engine import analyze_holding
from modeling.v6.timing import parse_dt

WINDOWS = (1, 3, 5, 10)
_DEFAULT_EVAL_WINDOW = 5
_EPS = 1e-9


@dataclass
class HistoricalEvent:
    """A curated historical event for replay validation."""

    event_id: str
    event_time: str                      # ISO-8601 when the event occurred
    event_title: str
    event_type: str = "uncategorized"
    source_type: str = "company"
    known_at: str = ""                   # when info was public (<= event_time)
    affected_tickers: list[str] = field(default_factory=list)
    affected_tags: list[str] = field(default_factory=list)
    expected_direction_if_known: int = 0  # curated reference label (-1/0/+1)
    benchmark_ticker: str = "SPY"
    category: str = ""                   # display grouping (e.g. "宏观利率")
    notes: str = ""
    no_lookahead_flag: bool = True
    magnitude: float = 0.0               # optional override (0 => classifier)
    confidence: float = 0.0              # optional override (0 => default)
    actual: float | None = None
    expected: float | None = None
    surprise_std: float | None = None
    surprise_unit: str = ""
    surprise_source: str = ""
    surprise_label: str = ""
    higher_is_bullish: bool | None = None
    proxy_surprise: float | None = None
    proxy_surprise_source: str = ""
    # Stored realized returns (decimals, e.g. 0.03 == +3%) for offline replay.
    fixture_returns: dict[str, float] = field(default_factory=dict)
    fixture_benchmark_returns: dict[str, float] = field(default_factory=dict)
    # Sector-ETF benchmark for residualized (sector-neutral) abnormal returns.
    sector_benchmark_ticker: str = ""
    fixture_sector_returns: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.known_at:
            self.known_at = self.event_time
        self.affected_tickers = [t.upper() for t in self.affected_tickers]

    def lookahead_ok(self) -> bool:
        """True when no info is dated after the event (no look-ahead)."""
        if not self.no_lookahead_flag:
            return False
        et, ka = parse_dt(self.event_time), parse_dt(self.known_at)
        if et is None or ka is None:
            return False
        return ka <= et

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def to_market_event(hist: HistoricalEvent) -> MarketEvent:
    """Convert a historical event into a V6 MarketEvent using PRE-EVENT info only.

    Realized returns (``fixture_returns``) are intentionally NOT read here -- the
    classification must be reproducible from what was knowable at event time.
    """
    if not hist.lookahead_ok():
        raise ValueError(
            f"Unsafe historical event {hist.event_id!r}: no-lookahead validation failed"
        )
    ev = MarketEvent(
        event_id=f"replay-{hist.event_id}",
        title=hist.event_title,
        source="HistoricalReplay",
        source_type=hist.source_type,
        timestamp=hist.event_time,
        effective_at=hist.event_time,
        event_type=hist.event_type,
        direction=0,                      # let the classifier decide
        magnitude=hist.magnitude or 1.0,
        confidence=hist.confidence or 0.6,
        affected_tags=list(hist.affected_tags),
        related_tickers=list(hist.affected_tickers),
        data_mode="fixture",
        actual=hist.actual,
        expected=hist.expected,
        surprise_std=hist.surprise_std,
        surprise_unit=hist.surprise_unit,
        surprise_source=hist.surprise_source,
        surprise_label=hist.surprise_label,
        higher_is_bullish=hist.higher_is_bullish,
        proxy_surprise=hist.proxy_surprise,
        proxy_surprise_source=hist.proxy_surprise_source,
    )
    classify_event(ev)                    # fills type/direction/tags from title
    return ev


# --- return adapter -------------------------------------------------------
# A ReturnAdapter is any callable (ticker, event_time, windows) -> dict|None
# returning ``{window_int: pct_decimal}`` or None when unavailable.
ReturnAdapter = Callable[[str, str, tuple[int, ...]], "dict[int, float] | None"]


def fixture_returns_adapter(returns_map: dict[str, dict[str, float]]) -> ReturnAdapter:
    """Build an adapter from a ``{ticker: {"1": pct, ...}}`` fixture table."""
    def _adapter(ticker: str, event_time: str, windows: tuple[int, ...]):
        row = returns_map.get(ticker.upper())
        if not row:
            return None
        return {w: float(row[str(w)]) for w in windows if str(w) in row}
    return _adapter


def _window_returns(hist: HistoricalEvent, ticker: str,
                    adapter: ReturnAdapter | None, windows: tuple[int, ...]):
    """Resolve stock returns for a ticker: adapter first, else the event's fixture."""
    if adapter is not None:
        got = adapter(ticker, hist.event_time, windows)
        if got:
            return {int(k): float(v) for k, v in got.items()}, "live"
    # fixture fallback: only the event's own affected ticker carries fixtures
    if ticker.upper() in hist.affected_tickers and hist.fixture_returns:
        return {w: float(hist.fixture_returns[str(w)])
                for w in windows if str(w) in hist.fixture_returns}, "fixture"
    return {}, "unavailable"


def _benchmark_returns(hist: HistoricalEvent, adapter: ReturnAdapter | None,
                       windows: tuple[int, ...]):
    bt = hist.benchmark_ticker
    if not bt:
        return {}, "none"
    if adapter is not None:
        got = adapter(bt, hist.event_time, windows)
        if got:
            return {int(k): float(v) for k, v in got.items()}, "live"
    if hist.fixture_benchmark_returns:
        return {w: float(hist.fixture_benchmark_returns[str(w)])
                for w in windows if str(w) in hist.fixture_benchmark_returns}, "fixture"
    return {}, "unavailable"


# --- direction helpers ----------------------------------------------------
_STATUS_TO_DIR = {"bullish": 1, "bearish": -1, "neutral": 0, "mixed": 0, "uncertain": 0}


def _sign(x: float) -> int:
    return 1 if x > _EPS else -1 if x < -_EPS else 0


def replay_event(
    hist: HistoricalEvent,
    *,
    adapter: ReturnAdapter | None = None,
    windows: tuple[int, ...] = WINDOWS,
    eval_window: int = _DEFAULT_EVAL_WINDOW,
) -> list[dict[str, Any]]:
    """Replay one historical event; return one result row per affected ticker."""
    me = to_market_event(hist)
    now = parse_dt(hist.event_time)
    rows: list[dict[str, Any]] = []
    bench, bench_mode = _benchmark_returns(hist, adapter, windows)
    # Sector-ETF returns for residualized (sector-neutral) abnormal returns.
    sector = {int(k): float(v) for k, v in (hist.fixture_sector_returns or {}).items()
              if str(k).isdigit() or isinstance(k, int)} if hist.fixture_sector_returns else {}
    if hist.fixture_sector_returns and not sector:
        sector = {int(k): float(v) for k, v in hist.fixture_sector_returns.items()}

    for ticker in (hist.affected_tickers or []):
        exposure = get_profile(ticker) or _generic_profile(ticker)
        h = analyze_holding(exposure, 1.0, [me], now)
        pred_dir = _STATUS_TO_DIR.get(h["status"], 0)

        stock, ret_mode = _window_returns(hist, ticker, adapter, windows)
        ret_by_window = {}
        for w in windows:
            s = stock.get(w)
            b = bench.get(w)
            sec = sector.get(w)
            # Residualize against the sector ETF when available (removes sector +
            # market beta in one step); else fall back to SPY-relative abnormal.
            if s is not None and sec is not None:
                abn = s - sec
            elif s is not None and b is not None:
                abn = s - b
            else:
                abn = None
            ret_by_window[w] = {"stock": s, "benchmark": b, "sector_benchmark": sec, "abnormal": abn}

        ew = ret_by_window.get(eval_window, {})
        realized_val = ew.get("abnormal")
        if realized_val is None:
            realized_val = ew.get("stock")
        realized_dir = _sign(realized_val) if realized_val is not None else None

        decisive = pred_dir != 0 and realized_dir is not None and realized_dir != 0
        result = "uncertain"
        if pred_dir == 0:
            result = "no_call"          # V6 did not take a side (中性/分歧/不确定)
        elif realized_dir is None:
            result = "no_data"
        elif realized_dir == 0:
            result = "flat"
        else:
            result = "hit" if pred_dir == realized_dir else "miss"

        rows.append({
            "event_id": hist.event_id,
            "category": hist.category,
            "event_title": hist.event_title,
            "event_type": me.event_type,
            "source_type": hist.source_type,
            "event_time": hist.event_time,
            "ticker": ticker,
            "predicted_status": h["status"],
            "predicted_direction": pred_dir,
            "v6_net_impact": h["net_impact"],
            "v6_confidence": h["avg_confidence"],
            "matched_tags": h["matched_tags"],
            "channels_hit": [k for k, v in h["channel_scores"].items()
                             if abs(v) > _EPS and k != "future"],
            "conclusion": h["conclusion"],
            "returns": ret_by_window,
            "return_mode": ret_mode,
            "benchmark_ticker": hist.benchmark_ticker,
            "benchmark_mode": bench_mode,
            "realized_direction": realized_dir,
            "eval_window": eval_window,
            "decisive": decisive,
            "result": result,
            "expected_direction_if_known": hist.expected_direction_if_known,
            "lookahead_ok": hist.lookahead_ok(),
            "notes": hist.notes,
        })
    return rows


def replay_all(
    events: list[HistoricalEvent],
    *,
    adapter: ReturnAdapter | None = None,
    windows: tuple[int, ...] = WINDOWS,
    eval_window: int = _DEFAULT_EVAL_WINDOW,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ev in events:
        out.extend(replay_event(ev, adapter=adapter, windows=windows, eval_window=eval_window))
    return out


def evaluate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic validation metrics over replay results.

    Validates DIRECTIONAL plausibility only -- never trade profitability.
    """
    decisive = [r for r in results if r["decisive"]]
    hits = [r for r in decisive if r["result"] == "hit"]
    hit_rate = round(len(hits) / len(decisive), 4) if decisive else 0.0

    # confidence-weighted hit rate
    w_sum = sum(r["v6_confidence"] for r in decisive)
    w_hit = sum(r["v6_confidence"] for r in hits)
    weighted_hit_rate = round(w_hit / w_sum, 4) if w_sum > _EPS else 0.0

    def _eval_ret(r):
        ew = r["returns"].get(r["eval_window"], {})
        v = ew.get("abnormal")
        return ew.get("stock") if v is None else v

    bull = [_eval_ret(r) for r in results if r["predicted_direction"] > 0 and _eval_ret(r) is not None]
    bear = [_eval_ret(r) for r in results if r["predicted_direction"] < 0 and _eval_ret(r) is not None]
    avg_bull = round(sum(bull) / len(bull), 4) if bull else None
    avg_bear = round(sum(bear) / len(bear), 4) if bear else None

    # confusion matrix over decisive rows
    cm = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    for r in decisive:
        p, a = r["predicted_direction"], r["realized_direction"]
        if p > 0 and a > 0:
            cm["tp"] += 1
        elif p > 0 and a < 0:
            cm["fp"] += 1
        elif p < 0 and a < 0:
            cm["tn"] += 1
        elif p < 0 and a > 0:
            cm["fn"] += 1

    # score-magnitude calibration buckets vs realized move magnitude
    buckets = {"low": [], "medium": [], "high": []}
    for r in results:
        rv = _eval_ret(r)
        if rv is None:
            continue
        s = abs(r["v6_net_impact"])
        b = "low" if s < 0.33 else "medium" if s < 0.66 else "high"
        buckets[b].append(abs(rv))
    calibration = {
        b: {"count": len(v), "avg_abs_move": round(sum(v) / len(v), 4) if v else None}
        for b, v in buckets.items()
    }

    by_result: dict[str, int] = {}
    for r in results:
        by_result[r["result"]] = by_result.get(r["result"], 0) + 1

    return {
        "total": len(results),
        "decisive": len(decisive),
        "hits": len(hits),
        "hit_rate": hit_rate,
        "weighted_hit_rate": weighted_hit_rate,
        "avg_return_after_bullish": avg_bull,
        "avg_return_after_bearish": avg_bear,
        "confusion_matrix": cm,
        "calibration": calibration,
        "by_result": by_result,
        "eval_window": results[0]["eval_window"] if results else _DEFAULT_EVAL_WINDOW,
    }
