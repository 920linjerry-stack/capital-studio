"""V6 learned calibration: turn the unitless impact score into basis points.

The hand-typed magnitudes (earnings_beat = 3.5, rate_cut = 4.0 ...) make the
engine's ``net_impact_score`` a dimensionless index -- it ranks, but ``+0.04``
has no referent. This module fits, from the **real-return replay benchmark**, a
per-event-type expected absolute abnormal move (in basis points) plus a realized
directional hit rate, so a contribution can be expressed as an *expected
abnormal move* with a unit and an empirical confidence.

It is the feedback loop the benchmark was missing: measurement -> coefficients.

Pipeline
--------
``build_calibration()`` runs the unchanged replay/impact engine over the benchmark
events, pairs each read with its realized benchmark-relative (abnormal) return,
and aggregates per classified ``event_type`` with empirical-Bayes shrinkage
toward the global mean (so a type seen 3 times is pulled toward the pooled
estimate). The result is written to ``data/calibration.json`` and loaded
deterministically by the engine. No network on the load path; no LLM.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).with_name("data")
_CALIBRATION_JSON = _DATA_DIR / "calibration.json"

# Eval window (trading days) the coefficients are fit on.
EVAL_WINDOW = 5
# Shrinkage strength: a type's estimate is pulled toward the global mean as if
# it had this many pseudo-observations of the global mean added.
_SHRINK_K = 4.0
# Hard fallback when no calibration file is present (keeps the engine working).
_FALLBACK_BP = 180.0


def _abnormal_bp(row: dict[str, Any], window: int) -> float | None:
    payload = row.get("returns", {}).get(window, {})
    val = payload.get("abnormal")
    if val is None:
        val = payload.get("stock")
    return None if val is None else abs(float(val)) * 10000.0


def _signed_abnormal(row: dict[str, Any], window: int) -> float | None:
    payload = row.get("returns", {}).get(window, {})
    val = payload.get("abnormal")
    if val is None:
        val = payload.get("stock")
    return None if val is None else float(val)


def fit_calibration(results: list[dict[str, Any]], *, window: int = EVAL_WINDOW) -> dict[str, Any]:
    """Aggregate replay rows into per-event-type calibration coefficients."""
    moves = [m for r in results if (m := _abnormal_bp(r, window)) is not None]
    global_mean = round(sum(moves) / len(moves), 2) if moves else _FALLBACK_BP

    by_type: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        by_type.setdefault(r.get("event_type", "uncategorized"), []).append(r)

    types: dict[str, Any] = {}
    for etype, rows in sorted(by_type.items()):
        bps = [m for r in rows if (m := _abnormal_bp(r, window)) is not None]
        if not bps:
            continue
        raw_mean = sum(bps) / len(bps)
        n = len(bps)
        # Empirical-Bayes shrinkage toward the global mean.
        shrunk = (n * raw_mean + _SHRINK_K * global_mean) / (n + _SHRINK_K)
        # Realized directional consistency: did the move sign match V6's call?
        decisive = [r for r in rows if r.get("predicted_direction", 0) != 0
                    and (s := _signed_abnormal(r, window)) is not None and abs(s) > 1e-9]
        hits = sum(1 for r in decisive
                   if (r["predicted_direction"] > 0) == (_signed_abnormal(r, window) > 0))
        types[etype] = {
            "n": n,
            "expected_abs_bp": round(shrunk, 1),
            "raw_mean_bp": round(raw_mean, 1),
            "hit_rate": round(hits / len(decisive), 3) if decisive else None,
            "decisive_n": len(decisive),
        }

    return {
        "_meta": {
            "window_days": window,
            "global_mean_bp": global_mean,
            "shrink_k": _SHRINK_K,
            "n_rows": len(results),
            "source": "replay benchmark (real yfinance abnormal returns) -> empirical-Bayes per event_type",
            "note": "expected_abs_bp is the historical mean |benchmark-relative move|; not a forecast of profit.",
        },
        "types": types,
    }


def build_calibration(write: bool = True) -> dict[str, Any]:
    """Run the benchmark and fit calibration; optionally persist to data/."""
    from modeling.v6.replay_benchmark import load_benchmark_events, run_benchmark
    results = run_benchmark(load_benchmark_events(), eval_window=EVAL_WINDOW)
    calib = fit_calibration(results)
    if write:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        _CALIBRATION_JSON.write_text(
            json.dumps(calib, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return calib


_CACHE: dict[str, Any] | None = None


def load_calibration() -> dict[str, Any]:
    """Load committed calibration coefficients (cached). Offline, deterministic."""
    global _CACHE
    if _CACHE is None:
        if _CALIBRATION_JSON.exists():
            try:
                _CACHE = json.loads(_CALIBRATION_JSON.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                _CACHE = {}
        else:
            _CACHE = {}
    return _CACHE


def global_mean_bp() -> float:
    return float(load_calibration().get("_meta", {}).get("global_mean_bp", _FALLBACK_BP))


def expected_move_bp(event_type: str) -> float:
    """Historical mean |abnormal move| (bp) for an event type, shrunk; fallback global."""
    calib = load_calibration()
    row = (calib.get("types") or {}).get(event_type)
    if row and isinstance(row.get("expected_abs_bp"), (int, float)):
        return float(row["expected_abs_bp"])
    return global_mean_bp()


def type_hit_rate(event_type: str) -> float | None:
    row = (load_calibration().get("types") or {}).get(event_type)
    return row.get("hit_rate") if row else None


# Scheduled catalysts have no realized type yet; map them to the realized
# counterpart(s) whose historical move best represents their potential.
_SCHEDULED_PROXY: dict[str, tuple[str, ...]] = {
    "cpi_release": ("macro_inflation_hot", "macro_inflation_cool"),
    "fomc_decision": ("rate_cut", "rate_hike"),
    "jobs_report": ("jobs_report",),
    "earnings_date": ("earnings_beat", "earnings_miss"),
    "product_launch": ("ai_capex_semis",),
    "policy_announcement": ("regulatory_risk",),
}


def scheduled_potential_bp(event_type: str) -> float:
    """Potential |abnormal move| (bp) for an as-yet-unrealized scheduled catalyst."""
    proxies = _SCHEDULED_PROXY.get(event_type)
    if not proxies:
        return expected_move_bp(event_type)
    vals = [expected_move_bp(p) for p in proxies]
    return round(sum(vals) / len(vals), 1)


def contribution_bp(
    *, event_type: str, effective_direction: int, relevance: float,
    confidence: float, temporal_multiplier: float = 1.0,
) -> float:
    """Signed expected abnormal move (bp) for one scored contribution.

    The learned per-type move is scaled by how strongly the event transmits to
    this holding (relevance), the read's confidence, and the temporal weight.
    This is a calibrated parallel to the unitless ``impact`` -- same shape, real
    unit -- so the engine can report "≈ ±N bp" alongside the index.
    """
    base = expected_move_bp(event_type)
    return effective_direction * base * relevance * confidence * temporal_multiplier
