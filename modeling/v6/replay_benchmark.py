"""Internal-only V6 historical event benchmark and diagnostics.

This module is deliberately disconnected from Flask and the normal V6 API.
It extends the small replay smoke set with provenance-rich benchmark metadata,
deterministic seed/dev/holdout partitions, optional stored return fixtures, and
diagnostic aggregation.  It does not alter classification, exposure, scoring,
or any user-facing output.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from modeling.v6.exposure import get_profile
from modeling.v6.replay import HistoricalEvent, WINDOWS, replay_event
from modeling.v6.replay_fixtures import load_historical_events


DATA_DIR = Path(__file__).with_name("data")
EVENTS_CSV = DATA_DIR / "replay_benchmark_events.csv"
RETURNS_JSON = DATA_DIR / "replay_benchmark_returns.json"
VALID_SPLITS = frozenset({"seed", "dev", "holdout"})
VALID_RETURN_STATUSES = frozenset({"fixture", "missing", "excluded"})


@dataclass
class BenchmarkEvent:
    event_id: str
    event_time: str
    known_at: str
    event_title: str
    event_type: str
    source_type: str
    source_name: str
    source_url: str = ""
    source_note: str = ""
    affected_tickers: list[str] = field(default_factory=list)
    affected_tags: list[str] = field(default_factory=list)
    benchmark_ticker: str = "SPY"
    expected_direction_if_known: int = 0
    confidence_of_event_label: float = 0.0
    category: str = ""
    subcategory: str = ""
    notes: str = ""
    no_lookahead_flag: bool = True
    split: str = "dev"
    return_status: str = "missing"
    asset_class: str = "equity"
    sector: str = ""
    price_anchor: str = "post_market"
    timestamp_precision: str = "date"
    actual: float | None = None
    expected: float | None = None
    surprise_std: float | None = None
    surprise_unit: str = ""
    surprise_source: str = ""
    surprise_label: str = ""
    higher_is_bullish: bool | None = None
    proxy_surprise: float | None = None
    proxy_surprise_source: str = ""
    fixture_returns_by_ticker: dict[str, dict[str, float]] = field(default_factory=dict)
    fixture_benchmark_returns: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.affected_tickers = [str(t).upper() for t in self.affected_tickers]
        self.affected_tags = [str(t).lower() for t in self.affected_tags]
        self.split = self.split.lower()
        self.return_status = self.return_status.lower()
        self.expected_direction_if_known = int(self.expected_direction_if_known)
        self.confidence_of_event_label = float(self.confidence_of_event_label)

    def lookahead_ok(self) -> bool:
        probe = HistoricalEvent(
            event_id=self.event_id,
            event_time=self.event_time,
            known_at=self.known_at,
            event_title=self.event_title,
            no_lookahead_flag=self.no_lookahead_flag,
        )
        return self.no_lookahead_flag and probe.lookahead_ok()

    def to_historical_event(self, ticker: str) -> HistoricalEvent:
        """Create the existing replay input for one affected ticker."""
        ticker = ticker.upper()
        return HistoricalEvent(
            event_id=self.event_id,
            event_time=self.event_time,
            known_at=self.known_at,
            event_title=self.event_title,
            event_type=self.event_type,
            source_type=self.source_type,
            affected_tickers=[ticker],
            affected_tags=list(self.affected_tags),
            expected_direction_if_known=self.expected_direction_if_known,
            benchmark_ticker=self.benchmark_ticker,
            category=self.category,
            notes=self.notes,
            no_lookahead_flag=self.no_lookahead_flag,
            confidence=self.confidence_of_event_label,
            actual=self.actual,
            expected=self.expected,
            surprise_std=self.surprise_std,
            surprise_unit=self.surprise_unit,
            surprise_source=self.surprise_source,
            surprise_label=self.surprise_label,
            higher_is_bullish=self.higher_is_bullish,
            proxy_surprise=self.proxy_surprise,
            proxy_surprise_source=self.proxy_surprise_source,
            fixture_returns=dict(self.fixture_returns_by_ticker.get(ticker, {})),
            fixture_benchmark_returns=dict(self.fixture_benchmark_returns),
        )


def _split_list(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split("|") if part.strip()]


def _bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _load_return_store(path: Path = RETURNS_JSON) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def _seed_events() -> list[BenchmarkEvent]:
    """Promote the existing ten curated smoke fixtures into the seed split."""
    out: list[BenchmarkEvent] = []
    for event in load_historical_events():
        returns = {
            ticker: dict(event.fixture_returns)
            for ticker in event.affected_tickers
            if event.fixture_returns
        }
        out.append(BenchmarkEvent(
            event_id=event.event_id,
            event_time=event.event_time,
            known_at=event.known_at,
            event_title=event.event_title,
            event_type=event.event_type,
            source_type=event.source_type,
            source_name="Existing curated replay fixture",
            source_note="Pre-existing V6 seed fixture retained unchanged.",
            affected_tickers=list(event.affected_tickers),
            affected_tags=list(event.affected_tags),
            benchmark_ticker=event.benchmark_ticker,
            expected_direction_if_known=event.expected_direction_if_known,
            confidence_of_event_label=event.confidence or 0.8,
            category=_canonical_category(event.source_type, event.event_id),
            subcategory=event.event_id,
            notes=event.notes,
            no_lookahead_flag=event.no_lookahead_flag,
            split="seed",
            return_status="fixture" if returns else "missing",
            asset_class="equity_or_etf",
            sector="seed_mixed",
            price_anchor="curated_fixture",
            timestamp_precision="timestamp",
            fixture_returns_by_ticker=returns,
            fixture_benchmark_returns=dict(event.fixture_benchmark_returns),
        ))
    return out


def _canonical_category(source_type: str, event_id: str = "") -> str:
    if "oil" in event_id or "bank-stress" in event_id:
        return "sector_specific_shock"
    return {
        "macro": "macro_rates_inflation",
        "company": "company_earnings_guidance",
        "institutional": "institutional_analyst",
        "official": "official_filing",
        "sentiment": "sentiment_reflexivity",
    }.get(source_type, "breaking_news_shock")


def load_benchmark_events(
    events_path: Path = EVENTS_CSV,
    returns_path: Path = RETURNS_JSON,
) -> list[BenchmarkEvent]:
    """Load the frozen seed plus CSV expansion rows in deterministic order."""
    events = _seed_events()
    return_store = _load_return_store(returns_path)
    from modeling.v6.surprise import load_surprise_observations
    surprise_store = load_surprise_observations().get("events") or {}
    with events_path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            event_returns = return_store.get(row["event_id"], {})
            surprise_row = surprise_store.get(row["event_id"], {})
            events.append(BenchmarkEvent(
                event_id=row["event_id"],
                event_time=row["event_time"],
                known_at=row["known_at"],
                event_title=row["event_title"],
                event_type=row["event_type"],
                source_type=row["source_type"],
                source_name=row["source_name"],
                source_url=row["source_url"],
                source_note=row["source_note"],
                affected_tickers=_split_list(row["affected_tickers"]),
                affected_tags=_split_list(row["affected_tags"]),
                benchmark_ticker=row["benchmark_ticker"],
                expected_direction_if_known=int(row["expected_direction_if_known"] or 0),
                confidence_of_event_label=float(row["confidence_of_event_label"] or 0),
                category=row["category"],
                subcategory=row["subcategory"],
                notes=row["notes"],
                no_lookahead_flag=_bool(row["no_lookahead_flag"]),
                split=row["split"],
                return_status=event_returns.get("return_status", row["return_status"]),
                asset_class=row["asset_class"],
                sector=row["sector"],
                price_anchor=row["price_anchor"],
                timestamp_precision=row["timestamp_precision"],
                actual=surprise_row.get("actual"),
                expected=surprise_row.get("expected"),
                surprise_std=surprise_row.get("surprise_std"),
                surprise_unit=surprise_row.get("surprise_unit", ""),
                surprise_source=surprise_row.get("surprise_source", ""),
                surprise_label=surprise_row.get("surprise_label", ""),
                higher_is_bullish=surprise_row.get("higher_is_bullish"),
                proxy_surprise=surprise_row.get("proxy_surprise"),
                proxy_surprise_source=surprise_row.get("proxy_surprise_source", ""),
                fixture_returns_by_ticker=event_returns.get("tickers", {}),
                fixture_benchmark_returns=event_returns.get("benchmark", {}),
            ))
    return events


def benchmark_integrity(events: Iterable[BenchmarkEvent]) -> dict[str, Any]:
    rows = list(events)
    ids = [event.event_id for event in rows]
    return {
        "event_count": len(rows),
        "duplicate_event_ids": sorted(k for k, v in Counter(ids).items() if v > 1),
        "invalid_splits": sorted({e.split for e in rows} - VALID_SPLITS),
        "invalid_return_statuses": sorted({e.return_status for e in rows} - VALID_RETURN_STATUSES),
        "lookahead_failures": sorted(e.event_id for e in rows if not e.lookahead_ok()),
        "missing_provenance": sorted(
            e.event_id for e in rows
            if not e.source_name or not (e.source_url or e.source_note)
        ),
        "missing_tickers": sorted(e.event_id for e in rows if not e.affected_tickers),
        "missing_label_confidence": sorted(
            e.event_id for e in rows
            if not 0 < e.confidence_of_event_label <= 1
        ),
        "by_split": dict(sorted(Counter(e.split for e in rows).items())),
        "by_category": dict(sorted(Counter(e.category for e in rows).items())),
    }


def run_benchmark(
    events: Iterable[BenchmarkEvent],
    *,
    splits: set[str] | None = None,
    eval_window: int = 5,
) -> list[dict[str, Any]]:
    """Run the unchanged replay/impact engine and attach benchmark metadata."""
    results: list[dict[str, Any]] = []
    for event in events:
        if splits is not None and event.split not in splits:
            continue
        for ticker in event.affected_tickers:
            row = replay_event(event.to_historical_event(ticker), eval_window=eval_window)[0]
            row.update({
                "split": event.split,
                "subcategory": event.subcategory,
                "source_name": event.source_name,
                "source_url": event.source_url,
                "source_note": event.source_note,
                "confidence_of_event_label": event.confidence_of_event_label,
                "return_status_declared": event.return_status,
                "asset_class": event.asset_class,
                "sector": event.sector,
                "price_anchor": event.price_anchor,
                "timestamp_precision": event.timestamp_precision,
                "profile_available": get_profile(ticker) is not None,
                "declared_event_type": event.event_type,
            })
            results.append(row)
    return results


def _direction_at_window(row: dict[str, Any], window: int, *, abnormal: bool = True) -> int | None:
    payload = row["returns"].get(window, {})
    value = payload.get("abnormal") if abnormal else payload.get("stock")
    if value is None and abnormal:
        value = payload.get("stock")
    if value is None:
        return None
    return 1 if value > 1e-9 else -1 if value < -1e-9 else 0


def _rate(rows: list[dict[str, Any]], predicate) -> float | None:
    if not rows:
        return None
    return round(sum(1 for row in rows if predicate(row)) / len(rows), 4)


def _directional_metrics(rows: list[dict[str, Any]], window: int = 5) -> dict[str, Any]:
    with_data = [r for r in rows if _direction_at_window(r, window) is not None]
    decisive = [r for r in with_data if r["predicted_direction"] != 0 and _direction_at_window(r, window) != 0]
    hits = [r for r in decisive if r["predicted_direction"] == _direction_at_window(r, window)]
    weight = sum(r["v6_confidence"] for r in decisive)
    weighted_hits = sum(r["v6_confidence"] for r in hits)
    return {
        "rows": len(rows),
        "with_returns": len(with_data),
        "decisive": len(decisive),
        "hits": len(hits),
        "directional_hit_rate": round(len(hits) / len(decisive), 4) if decisive else None,
        "confidence_weighted_hit_rate": round(weighted_hits / weight, 4) if weight else None,
        "no_call_rate": _rate(rows, lambda r: r["predicted_direction"] == 0),
        "uncertain_rate": _rate(rows, lambda r: r["predicted_status"] == "uncertain"),
        "mixed_rate": _rate(rows, lambda r: r["predicted_status"] == "mixed"),
        "false_bullish": sum(1 for r in decisive if r["predicted_direction"] > 0 and _direction_at_window(r, window) < 0),
        "false_bearish": sum(1 for r in decisive if r["predicted_direction"] < 0 and _direction_at_window(r, window) > 0),
    }


def _grouped(rows: list[dict[str, Any]], key: str, window: int = 5) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(key) or "unknown")].append(row)
    return {name: _directional_metrics(group, window) for name, group in sorted(groups.items())}


def evaluate_benchmark(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Expanded internal metrics. Holdout is always reported separately."""
    by_window = {str(w): _directional_metrics(results, w) for w in WINDOWS}
    expected = [r for r in results if r["expected_direction_if_known"] in (-1, 1)]
    expected_decisive = [r for r in expected if r["predicted_direction"] in (-1, 1)]
    expected_agree = sum(
        r["predicted_direction"] == r["expected_direction_if_known"]
        for r in expected_decisive
    )
    return {
        "benchmark_rows": len(results),
        "event_count": len({r["event_id"] for r in results}),
        "missing_return_rows": sum(r["return_mode"] == "unavailable" for r in results),
        "overall": _directional_metrics(results),
        "by_split": _grouped(results, "split"),
        "holdout": _directional_metrics([r for r in results if r["split"] == "holdout"]),
        "by_category": _grouped(results, "category"),
        "by_asset_class": _grouped(results, "asset_class"),
        "by_sector": _grouped(results, "sector"),
        "by_event_type": _grouped(results, "event_type"),
        "by_source_type": _grouped(results, "source_type"),
        "by_timestamp_precision": _grouped(results, "timestamp_precision"),
        "by_window": by_window,
        "abnormal_return_hit_rate": by_window["5"]["directional_hit_rate"],
        "expected_label_diagnostic": {
            "labelled_rows": len(expected),
            "decisive_rows": len(expected_decisive),
            "agreement_rate": round(expected_agree / len(expected_decisive), 4)
            if expected_decisive else None,
            "warning": "Diagnostic label agreement is not realized-return accuracy.",
        },
        "impact_score_calibration": _calibration(results, "impact"),
        "confidence_calibration": _calibration(results, "confidence"),
    }


def _calibration(rows: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {"low": [], "medium": [], "high": []}
    for row in rows:
        value = abs(row["v6_net_impact"]) if kind == "impact" else row["v6_confidence"]
        bucket = "low" if value < 0.33 else "medium" if value < 0.66 else "high"
        groups[bucket].append(row)
    return {bucket: _directional_metrics(group) for bucket, group in groups.items()}


ERROR_REASONS = (
    "wrong_event_classification",
    "ticker_entity_match_failure",
    "macro_factor_sign_wrong",
    "sector_specific_contra_exposure_missing",
    "stale_or_lagging_event",
    "price_reaction_dominated_by_unrelated_event",
    "benchmark_mismatch",
    "event_label_ambiguous",
    "insufficient_exposure_profile",
    "true_market_surprise_not_captured_by_headline",
    "fixture_return_missing_or_low_confidence",
)


def classify_error(row: dict[str, Any]) -> str | None:
    if row["return_mode"] == "unavailable":
        return "fixture_return_missing_or_low_confidence"
    if not row["profile_available"]:
        return "insufficient_exposure_profile"
    if row["result"] not in {"miss", "no_call"}:
        return None
    # A deliberately neutral filing/attention label is coverage, not an error.
    if row["result"] == "no_call" and row["expected_direction_if_known"] == 0:
        return None
    if row["predicted_status"] == "mixed":
        return "event_label_ambiguous"
    if row["confidence_of_event_label"] < 0.7:
        return "event_label_ambiguous"
    # The declared type can survive conversion while its headline fails to
    # supply a direction. Treat that as classifier coverage, not entity match.
    if row["result"] == "no_call" and row["declared_event_type"] not in {"", "uncategorized"}:
        return "wrong_event_classification"
    if row["declared_event_type"] not in {"", "uncategorized", row["event_type"]}:
        return "wrong_event_classification"
    if not row["matched_tags"]:
        return "ticker_entity_match_failure"
    # When V6 and the pre-event directional label agree but the subsequent
    # return differs, the headline mapping is not itself evidence of a sign
    # error. Date-level composite events are especially confounded.
    if (
        row["result"] == "miss"
        and row["predicted_direction"] == row["expected_direction_if_known"]
        and row["timestamp_precision"] == "date"
    ):
        return "price_reaction_dominated_by_unrelated_event"
    if row["source_type"] == "macro":
        return "macro_factor_sign_wrong"
    if row["category"] == "sector_specific_shock":
        return "sector_specific_contra_exposure_missing"
    if row["benchmark_mode"] in {"none", "unavailable"}:
        return "benchmark_mismatch"
    return "true_market_surprise_not_captured_by_headline"


def error_taxonomy(results: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {reason: [] for reason in ERROR_REASONS}
    for row in results:
        reason = classify_error(row)
        if reason:
            grouped[reason].append({
                "event_id": row["event_id"],
                "ticker": row["ticker"],
                "split": row["split"],
                "result": row["result"],
            })
    return {
        "counts": {reason: len(grouped[reason]) for reason in ERROR_REASONS},
        "examples": {reason: grouped[reason][:5] for reason in ERROR_REASONS},
        "classified_rows": sum(len(rows) for rows in grouped.values()),
    }
