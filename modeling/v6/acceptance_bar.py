"""Pre-print acceptance-bar archive (logging only -- not live scoring).

The MU case exposed that V6 had no record of the *market's pre-print bar*
(consensus hurdle, the stock's own surprise bar, option-implied move, crowding).
This module captures that bar as a point-in-time snapshot for later C1 / PEAD /
options research. It does NOT feed scoring, thresholds, whisper, or crowding.

Everything network-touching is failure-tolerant: when yfinance, an options
chain, an expiry, usable quotes, a whisper baseline, or crowding data is missing,
the field is recorded as ``None`` with a ``reason`` and capture continues.

``option_implied_move`` is market pricing / expectation magnitude -- NOT a
directional forecast. Consensus pulled from articles must be tagged
``external_context``; we never LLM-extract numbers into engine-native fields.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from modeling.v6.postprint import (
    ACCEPTANCE_BAR_STATUSES,
    ACCEPTANCE_BAR_SCHEMA_VERSION,
    utc_timestamp,
)

ARCHIVE_DIR = Path("internal/v6_acceptance_bar")
RECORD_SCHEMA_VERSION = "v6.acceptance_bar_record.v1"


@dataclass
class AcceptanceBarRecord:
    """Full pre-print acceptance-bar capture for one ticker/event."""

    ticker: str
    event_date: str = ""
    snapshot_time: str = ""
    is_preprint_snapshot: bool = True
    # consensus hurdle (engine-native only when structured; else external_context)
    consensus_eps: float | None = None
    consensus_revenue: float | None = None
    next_quarter_consensus_eps: float | None = None
    next_quarter_consensus_revenue: float | None = None
    consensus_source_type: str = "unavailable"   # structured | external_context | unavailable
    # the stock's own bar (whisper proxy)
    own_historical_surprise_bar: float | None = None
    own_bar_n_history: int | None = None
    # option-implied move (magnitude, NOT direction)
    option_implied_move: float | None = None
    option_expiry_used: str = ""
    atm_strike_used: float | None = None
    stock_price_at_snapshot: float | None = None
    # crowding
    priced_for_perfection: float | None = None
    crowding_band: str = ""
    # status / provenance
    acceptance_bar_status: str = "unavailable"
    reason_missing: list[str] = field(default_factory=list)
    data_sources: list[str] = field(default_factory=list)
    # Boundary flags: this is a point-in-time live capture. option_implied_move
    # and upcoming consensus are live snapshots, NOT historical backtestable
    # features, and the whole record is logging-only (never enters scoring).
    live_logging_only: bool = True
    not_backtestable: bool = True
    live_only_fields: tuple[str, ...] = ("option_implied_move", "option_expiry_used",
                                         "atm_strike_used", "stock_price_at_snapshot",
                                         "consensus_eps", "consensus_revenue",
                                         "next_quarter_consensus_eps", "next_quarter_consensus_revenue")
    scoring_isolation: str = "logging_only; never enters official V6 score, verdict, or signal"
    schema_version: str = RECORD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.ticker = self.ticker.upper()
        if not self.snapshot_time:
            self.snapshot_time = utc_timestamp()
        if self.acceptance_bar_status not in ACCEPTANCE_BAR_STATUSES:
            self.acceptance_bar_status = "unavailable"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _own_bar(ticker: str, rec: AcceptanceBarRecord) -> None:
    from modeling.v6 import whisper
    base = whisper.baseline_for(ticker)
    if base is None:
        rec.reason_missing.append("own_historical_surprise_bar: no whisper baseline for ticker")
        return
    rec.own_historical_surprise_bar = round(float(base["mean_sd"]), 4)
    rec.own_bar_n_history = base.get("n")
    rec.data_sources.append("whisper baseline (historical EPS surprise)")


def _crowding(ticker: str, rec: AcceptanceBarRecord) -> None:
    from modeling.v6 import crowding
    state = crowding.crowding_state(ticker)
    score = state.get("priced_for_perfection")
    if score is None or state.get("data_mode") == "unavailable":
        rec.reason_missing.append("crowding: no ticker-specific priced_for_perfection")
        return
    rec.priced_for_perfection = round(float(score), 4)
    rec.crowding_band = state.get("band", "")
    rec.data_sources.append("crowding snapshot (price proxy)")


def _consensus_eps(ticker: str, rec: AcceptanceBarRecord, *, allow_network: bool) -> None:
    """Next (upcoming) EPS consensus from yfinance, if available. Structured only."""
    if not allow_network:
        rec.reason_missing.append("consensus_eps: network disabled")
        return
    try:
        import yfinance as yf
        ed = yf.Ticker(ticker).get_earnings_dates(limit=8)
    except Exception as exc:  # noqa: BLE001
        rec.reason_missing.append(f"consensus_eps: earnings_dates unavailable ({exc})"[:140])
        return
    if ed is None or ed.empty or "EPS Estimate" not in ed.columns:
        rec.reason_missing.append("consensus_eps: no earnings estimate rows")
        return
    # the most recent row with an estimate but no reported EPS = upcoming print
    upcoming = ed[ed["Reported EPS"].isna() & ed["EPS Estimate"].notna()] if "Reported EPS" in ed.columns else None
    if upcoming is not None and not upcoming.empty:
        row = upcoming.iloc[-1]
        rec.consensus_eps = round(float(row["EPS Estimate"]), 4)
        rec.event_date = str(upcoming.index[-1].date())
        rec.consensus_source_type = "structured"
        rec.data_sources.append("yfinance get_earnings_dates (upcoming EPS estimate)")
    else:
        rec.reason_missing.append("consensus_eps: no upcoming (unreported) estimate row")


def _option_implied_move(ticker: str, rec: AcceptanceBarRecord, *, allow_network: bool) -> None:
    if not allow_network:
        rec.reason_missing.append("option_implied_move: network disabled")
        return
    try:
        import yfinance as yf
    except Exception as exc:  # noqa: BLE001
        rec.reason_missing.append(f"option_implied_move: yfinance unavailable ({exc})"[:140])
        return
    try:
        yt = yf.Ticker(ticker)
        expiries = list(getattr(yt, "options", []) or [])
        if not expiries:
            rec.reason_missing.append("option_implied_move: no option expiries")
            return
        hist = yt.history(period="1d")
        if hist.empty:
            rec.reason_missing.append("option_implied_move: spot price unavailable")
            return
        spot = float(hist["Close"].iloc[-1])
        chain = yt.option_chain(expiries[0])
        calls, puts = chain.calls.copy(), chain.puts.copy()
        if calls.empty or puts.empty:
            rec.reason_missing.append("option_implied_move: empty call/put chain")
            return
        calls["d"] = (calls["strike"] - spot).abs()
        puts["d"] = (puts["strike"] - spot).abs()
        c = calls.sort_values("d").iloc[0]
        p = puts.sort_values("d").iloc[0]
        cm = (float(c["bid"]) + float(c["ask"])) / 2.0
        pm = (float(p["bid"]) + float(p["ask"])) / 2.0
        if spot <= 0 or cm <= 0 or pm <= 0:
            rec.reason_missing.append("option_implied_move: non-positive spot/midpoint")
            return
        rec.option_implied_move = round((cm + pm) / spot, 4)
        rec.option_expiry_used = expiries[0]
        rec.atm_strike_used = round(float(c["strike"]), 2)
        rec.stock_price_at_snapshot = round(spot, 2)
        rec.data_sources.append(f"yfinance nearest-expiry ATM straddle {expiries[0]}")
    except Exception as exc:  # noqa: BLE001
        rec.reason_missing.append(f"option_implied_move: fetch failed ({exc})"[:140])


def _status(rec: AcceptanceBarRecord) -> str:
    have = sum(v is not None for v in (
        rec.consensus_eps, rec.own_historical_surprise_bar,
        rec.option_implied_move, rec.priced_for_perfection))
    if have == 0:
        return "unavailable"
    if have == 4:
        return "available"
    return "partial"


def build_acceptance_bar(ticker: str, *, allow_network: bool = True,
                         skip_options: bool = False, event_date: str = "") -> AcceptanceBarRecord:
    """Assemble a pre-print acceptance-bar snapshot; failure-tolerant per field."""
    rec = AcceptanceBarRecord(ticker=ticker, event_date=event_date)
    _own_bar(rec.ticker, rec)
    _crowding(rec.ticker, rec)
    _consensus_eps(rec.ticker, rec, allow_network=allow_network)
    if skip_options:
        rec.reason_missing.append("option_implied_move: skipped (--skip-options)")
    else:
        _option_implied_move(rec.ticker, rec, allow_network=allow_network)
    rec.acceptance_bar_status = _status(rec)
    return rec


def archive_acceptance_bars(tickers: list[str], *, allow_network: bool = True,
                            skip_options: bool = False, out_dir: Path = ARCHIVE_DIR) -> list[dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for t in tickers:
        rec = build_acceptance_bar(t, allow_network=allow_network, skip_options=skip_options)
        path = out_dir / f"{rec.ticker}_{(rec.event_date or 'nodate')}.json"
        path.write_text(json.dumps(rec.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
        written.append({"ticker": rec.ticker, "status": rec.acceptance_bar_status, "path": str(path)})
    return written
