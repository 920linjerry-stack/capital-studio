"""Post-print evidence schemas for V6 validation and future C1 work.

This module is internal evidence plumbing only. It records realized event
windows, post-print surprise facts, and acceptance-bar inputs for later C1 /
PEAD / options research. It is deliberately disconnected from the live scoring
path and must not be used to backfill pre-print predictions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


EVENT_WINDOW_SCHEMA_VERSION = "v6.event_window_residual.v1"
REALIZED_SURPRISE_SCHEMA_VERSION = "v6.realized_surprise_payload.v1"
ACCEPTANCE_BAR_SCHEMA_VERSION = "v6.acceptance_bar_snapshot.v1"

EVENT_WINDOWS = (
    "after_hours",
    "t1_regular_close",
    "t2_regular_close",
    "t2_premarket_snapshot",
    "5d_forward",
    "20d_forward",
    "40d_forward",
    "60d_forward",
)

ACCEPTANCE_BAR_STATUSES = ("unavailable", "partial", "available")


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct_surprise(actual: float | None, expected: float | None) -> float | None:
    if actual is None or expected is None or abs(expected) <= 1e-12:
        return None
    return actual / expected - 1.0


@dataclass
class EventWindowResidual:
    """One realized reaction window for a company/macro event.

    Returns are decimal returns, e.g. ``0.1574`` for +15.74%.
    """

    window: str
    stock_return: float | None = None
    sector_benchmark_return: float | None = None
    market_benchmark_return: float | None = None
    residual_vs_sector: float | None = None
    residual_vs_market: float | None = None
    primary_benchmark_used: str = ""
    data_source: str = ""
    timestamp: str = ""
    missing_data_reason: str = ""

    schema_version: str = EVENT_WINDOW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.window not in EVENT_WINDOWS:
            raise ValueError(f"Unsupported event window: {self.window!r}")
        self.stock_return = _optional_float(self.stock_return)
        self.sector_benchmark_return = _optional_float(self.sector_benchmark_return)
        self.market_benchmark_return = _optional_float(self.market_benchmark_return)
        self.residual_vs_sector = _optional_float(self.residual_vs_sector)
        self.residual_vs_market = _optional_float(self.residual_vs_market)
        if self.stock_return is not None and self.sector_benchmark_return is not None:
            self.residual_vs_sector = self.stock_return - self.sector_benchmark_return
        if self.stock_return is not None and self.market_benchmark_return is not None:
            self.residual_vs_market = self.stock_return - self.market_benchmark_return
        if not self.timestamp:
            self.timestamp = utc_timestamp()
        if self.stock_return is None and not self.missing_data_reason:
            self.missing_data_reason = "stock_return unavailable"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EventWindowResidualSet:
    """Multi-window residual evidence for one ticker/event pair."""

    event_id: str
    ticker: str
    sector_benchmark: str = ""
    market_benchmark: str = "SPY"
    windows: list[EventWindowResidual] = field(default_factory=list)
    notes: str = ""
    schema_version: str = EVENT_WINDOW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.ticker = self.ticker.upper()
        self.sector_benchmark = self.sector_benchmark.upper()
        self.market_benchmark = self.market_benchmark.upper()

    def by_window(self) -> dict[str, EventWindowResidual]:
        return {row.window: row for row in self.windows}

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "ticker": self.ticker,
            "sector_benchmark": self.sector_benchmark,
            "market_benchmark": self.market_benchmark,
            "windows": [row.to_dict() for row in self.windows],
            "notes": self.notes,
        }


@dataclass
class RealizedSurprisePayload:
    """Post-print actuals and guide facts.

    These fields are validation facts only. They are not safe pre-print
    features unless a separate pre-print source captured them before release.
    """

    actual_eps: float | None = None
    consensus_eps: float | None = None
    eps_surprise_abs: float | None = None
    eps_surprise_pct: float | None = None
    actual_revenue: float | None = None
    consensus_revenue: float | None = None
    revenue_surprise_abs: float | None = None
    revenue_surprise_pct: float | None = None
    gross_margin_actual: float | None = None
    gross_margin_consensus_or_prior: float | None = None
    next_quarter_revenue_guide: float | None = None
    next_quarter_revenue_consensus: float | None = None
    next_quarter_revenue_surprise_abs: float | None = None
    next_quarter_revenue_surprise_pct: float | None = None
    next_quarter_eps_guide: float | None = None
    next_quarter_eps_consensus: float | None = None
    next_quarter_eps_surprise_abs: float | None = None
    next_quarter_eps_surprise_pct: float | None = None
    hbm_positive: bool | None = None
    dram_pricing_positive: bool | None = None
    nand_pricing_positive: bool | None = None
    supply_tightness: bool | None = None
    customer_agreement: bool | None = None
    capex_risk: bool | None = None
    demand_positive: bool | None = None
    data_source: str = ""
    timestamp: str = ""
    notes: str = ""
    schema_version: str = REALIZED_SURPRISE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "actual_eps", "consensus_eps", "eps_surprise_abs", "eps_surprise_pct",
            "actual_revenue", "consensus_revenue", "revenue_surprise_abs",
            "revenue_surprise_pct", "gross_margin_actual",
            "gross_margin_consensus_or_prior", "next_quarter_revenue_guide",
            "next_quarter_revenue_consensus", "next_quarter_revenue_surprise_abs",
            "next_quarter_revenue_surprise_pct", "next_quarter_eps_guide",
            "next_quarter_eps_consensus", "next_quarter_eps_surprise_abs",
            "next_quarter_eps_surprise_pct",
        ):
            setattr(self, name, _optional_float(getattr(self, name)))
        if self.actual_eps is not None and self.consensus_eps is not None:
            self.eps_surprise_abs = self.actual_eps - self.consensus_eps
            self.eps_surprise_pct = _pct_surprise(self.actual_eps, self.consensus_eps)
        if self.actual_revenue is not None and self.consensus_revenue is not None:
            self.revenue_surprise_abs = self.actual_revenue - self.consensus_revenue
            self.revenue_surprise_pct = _pct_surprise(self.actual_revenue, self.consensus_revenue)
        if self.next_quarter_revenue_guide is not None and self.next_quarter_revenue_consensus is not None:
            self.next_quarter_revenue_surprise_abs = (
                self.next_quarter_revenue_guide - self.next_quarter_revenue_consensus
            )
            self.next_quarter_revenue_surprise_pct = _pct_surprise(
                self.next_quarter_revenue_guide, self.next_quarter_revenue_consensus
            )
        if self.next_quarter_eps_guide is not None and self.next_quarter_eps_consensus is not None:
            self.next_quarter_eps_surprise_abs = self.next_quarter_eps_guide - self.next_quarter_eps_consensus
            self.next_quarter_eps_surprise_pct = _pct_surprise(
                self.next_quarter_eps_guide, self.next_quarter_eps_consensus
            )
        if not self.timestamp:
            self.timestamp = utc_timestamp()

    def qualitative_tags(self) -> dict[str, bool | None]:
        return {
            "hbm_positive": self.hbm_positive,
            "dram_pricing_positive": self.dram_pricing_positive,
            "nand_pricing_positive": self.nand_pricing_positive,
            "supply_tightness": self.supply_tightness,
            "customer_agreement": self.customer_agreement,
            "capex_risk": self.capex_risk,
            "demand_positive": self.demand_positive,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AcceptanceBarSnapshot:
    """Pre-print acceptance-bar inputs captured for research, not scoring."""

    consensus_hurdle: float | None = None
    own_historical_surprise_bar: float | None = None
    option_implied_move: float | None = None
    crowding_priced_for_perfection: float | None = None
    crowding_band: str = ""
    acceptance_bar_status: str = "unavailable"
    reason_missing: str = ""
    data_source: str = ""
    timestamp: str = ""
    schema_version: str = ACCEPTANCE_BAR_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.consensus_hurdle = _optional_float(self.consensus_hurdle)
        self.own_historical_surprise_bar = _optional_float(self.own_historical_surprise_bar)
        self.option_implied_move = _optional_float(self.option_implied_move)
        self.crowding_priced_for_perfection = _optional_float(self.crowding_priced_for_perfection)
        if self.acceptance_bar_status not in ACCEPTANCE_BAR_STATUSES:
            self.acceptance_bar_status = "unavailable"
        if self.acceptance_bar_status == "unavailable" and not self.reason_missing:
            self.reason_missing = "acceptance-bar inputs unavailable"
        if not self.timestamp:
            self.timestamp = utc_timestamp()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def infer_acceptance_bar_status(snapshot: AcceptanceBarSnapshot) -> str:
    fields = [
        snapshot.consensus_hurdle,
        snapshot.own_historical_surprise_bar,
        snapshot.option_implied_move,
        snapshot.crowding_priced_for_perfection,
    ]
    available = sum(value is not None for value in fields)
    if available == 0:
        return "unavailable"
    if available == len(fields):
        return "available"
    return "partial"


def option_implied_move_snapshot(ticker: str, *, timestamp: str = "") -> AcceptanceBarSnapshot:
    """Best-effort yfinance ATM straddle implied move snapshot.

    This is intentionally optional and failure-tolerant. It returns an
    unavailable snapshot when yfinance, options chains, or usable quotes are not
    present, and it never mutates V6 scoring state.
    """

    ticker = ticker.upper()
    try:
        import yfinance as yf  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return AcceptanceBarSnapshot(
            acceptance_bar_status="unavailable",
            reason_missing=f"yfinance unavailable: {exc}",
            data_source="yfinance options chain",
            timestamp=timestamp,
        )

    try:
        yf_ticker = yf.Ticker(ticker)
        expiries = list(getattr(yf_ticker, "options", []) or [])
        if not expiries:
            return AcceptanceBarSnapshot(
                acceptance_bar_status="unavailable",
                reason_missing="options expiries unavailable",
                data_source="yfinance options chain",
                timestamp=timestamp,
            )
        hist = yf_ticker.history(period="1d")
        if hist.empty:
            return AcceptanceBarSnapshot(
                acceptance_bar_status="unavailable",
                reason_missing="spot price unavailable",
                data_source="yfinance options chain",
                timestamp=timestamp,
            )
        spot = float(hist["Close"].iloc[-1])
        chain = yf_ticker.option_chain(expiries[0])
        calls = chain.calls.copy()
        puts = chain.puts.copy()
        if calls.empty or puts.empty:
            return AcceptanceBarSnapshot(
                acceptance_bar_status="unavailable",
                reason_missing="call/put chain unavailable",
                data_source=f"yfinance options chain {expiries[0]}",
                timestamp=timestamp,
            )
        calls["distance"] = (calls["strike"] - spot).abs()
        puts["distance"] = (puts["strike"] - spot).abs()
        call = calls.sort_values("distance").iloc[0]
        put = puts.sort_values("distance").iloc[0]
        call_mid = (float(call["bid"]) + float(call["ask"])) / 2.0
        put_mid = (float(put["bid"]) + float(put["ask"])) / 2.0
        if spot <= 0 or call_mid <= 0 or put_mid <= 0:
            raise ValueError("non-positive spot or option midpoint")
        implied_move = (call_mid + put_mid) / spot
        snap = AcceptanceBarSnapshot(
            option_implied_move=implied_move,
            acceptance_bar_status="partial",
            data_source=f"yfinance nearest-expiry ATM straddle {expiries[0]}",
            timestamp=timestamp,
        )
        snap.acceptance_bar_status = infer_acceptance_bar_status(snap)
        return snap
    except Exception as exc:  # noqa: BLE001
        return AcceptanceBarSnapshot(
            acceptance_bar_status="unavailable",
            reason_missing=f"options implied move fetch failed: {exc}",
            data_source="yfinance options chain",
            timestamp=timestamp,
        )
