"""Opt-in keyless price fixture builder for the internal V6 benchmark.

Not imported by the product or normal replay path. Run manually from the repo
root to refresh stored adjusted-close return fixtures. Missing downloads remain
explicitly marked; the script never invents prices or forward-fills gaps.
"""

from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from modeling.v6.replay import WINDOWS
from modeling.v6.replay_benchmark import EVENTS_CSV, RETURNS_JSON, load_benchmark_events


def _download_adjusted_closes(tickers: list[str], start: str, end: str, cache_dir: Path):
    import yfinance as yf

    cache_dir.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(cache_dir))
    out = {}
    for ticker in tickers:
        try:
            frame = yf.download(
                ticker,
                start=start,
                end=end,
                auto_adjust=True,
                progress=False,
                threads=False,
            )
            if frame.empty:
                continue
            close = frame["Close"]
            if getattr(close, "ndim", 1) > 1:
                close = close.iloc[:, 0]
            close = close.dropna()
            if not close.empty:
                out[ticker] = close
        except Exception:
            # The output records missing status per event; one failed symbol
            # must not abort the deterministic expansion path.
            continue
    return out


def _returns_for_event(series, event_date, anchor: str) -> dict[str, float]:
    dates = [stamp.date() for stamp in series.index]
    if anchor in {"pre_market", "intraday"}:
        baseline_candidates = [i for i, date in enumerate(dates) if date < event_date]
        target_candidates = [i for i, date in enumerate(dates) if date >= event_date]
    else:
        baseline_candidates = [i for i, date in enumerate(dates) if date <= event_date]
        target_candidates = [i for i, date in enumerate(dates) if date > event_date]
    if not baseline_candidates or not target_candidates:
        return {}
    base_i = baseline_candidates[-1]
    base = float(series.iloc[base_i])
    if base <= 0:
        return {}
    returns = {}
    for window in WINDOWS:
        if len(target_candidates) < window:
            continue
        target = float(series.iloc[target_candidates[window - 1]])
        returns[str(window)] = round(target / base - 1.0, 8)
    return returns


def build_return_store(
    *,
    events_path: Path = EVENTS_CSV,
    output_path: Path = RETURNS_JSON,
    cache_dir: Path,
) -> dict[str, Any]:
    events = [event for event in load_benchmark_events(events_path, Path("__missing__"))
              if event.split != "seed"]
    all_tickers = sorted({
        ticker
        for event in events
        for ticker in [*event.affected_tickers, event.benchmark_ticker]
        if ticker
    })
    dates = [__import__("datetime").datetime.fromisoformat(
        event.event_time.replace("Z", "+00:00")
    ).date() for event in events]
    start = str(min(dates) - timedelta(days=20))
    end = str(max(dates) + timedelta(days=max(WINDOWS) * 3 + 10))
    prices = _download_adjusted_closes(all_tickers, start, end, cache_dir)

    store: dict[str, Any] = {
        "_meta": {
            "source": "yfinance adjusted close (keyless public feed)",
            "method": "close-to-close windows using declared price_anchor",
            "windows": list(WINDOWS),
            "missing_is_not_filled": True,
        }
    }
    for event in events:
        event_date = __import__("datetime").datetime.fromisoformat(
            event.event_time.replace("Z", "+00:00")
        ).date()
        ticker_returns = {}
        for ticker in event.affected_tickers:
            if ticker in prices:
                values = _returns_for_event(prices[ticker], event_date, event.price_anchor)
                if values:
                    ticker_returns[ticker] = values
        benchmark = {}
        if event.benchmark_ticker in prices:
            benchmark = _returns_for_event(
                prices[event.benchmark_ticker], event_date, event.price_anchor
            )
        complete = bool(ticker_returns) and all(
            ticker in ticker_returns for ticker in event.affected_tickers
        )
        store[event.event_id] = {
            "return_status": "fixture" if complete else "missing",
            "tickers": ticker_returns,
            "benchmark": benchmark,
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(store, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return store


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=EVENTS_CSV)
    parser.add_argument("--output", type=Path, default=RETURNS_JSON)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("tmp") / "v6-benchmark-yfinance",
    )
    args = parser.parse_args()
    store = build_return_store(
        events_path=args.events,
        output_path=args.output,
        cache_dir=args.cache_dir,
    )
    rows = [value for key, value in store.items() if key != "_meta"]
    complete = sum(value["return_status"] == "fixture" for value in rows)
    print(f"events={len(rows)} complete={complete} missing={len(rows) - complete}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

