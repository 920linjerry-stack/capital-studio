"""PEAD (post-earnings-announcement drift) readiness scaffold.

PEAD is a MEDIUM-horizon (20/40/60D) drift framework -- deliberately separate
from the short reaction (AH / T+1 / T+2 / 5D). This module builds PEAD-ready
labels and a feature dataset and computes a readiness scorecard. It is a
scaffold: it does not emit trade signals and never mixes 20-60D drift into the
short-horizon prediction.

Honesty rules:
* A forward window that has not matured (event too recent) is recorded
  ``not_matured`` -- never imputed.
* If too few matured samples exist for a window, the scorecard reports
  ``insufficient_matured_windows`` rather than a pretty fabricated number.
* The unmatured MU 20/40/60D windows are NOT treated as known results.

Drift labels are residual-vs-sector (stock - sector ETF), consistent with the
rest of V6. Deterministic, offline on load (reads ``data/pead_returns.json``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).with_name("data")
_PEAD_RETURNS = _DATA_DIR / "pead_returns.json"

SHORT_WINDOWS = (1, 2, 5)          # short reaction model territory
PEAD_WINDOWS = (20, 40, 60)        # medium-horizon drift territory
ALL_WINDOWS = (5, 20, 40, 60)
MIN_MATURED = 30                   # below this -> insufficient_matured_windows


def load_pead_returns() -> dict[str, Any]:
    if not _PEAD_RETURNS.exists():
        return {}
    try:
        data = json.loads(_PEAD_RETURNS.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _sign(x: float | None) -> int | None:
    if x is None:
        return None
    return 1 if x > 1e-9 else -1 if x < -1e-9 else 0


def build_pead_dataset() -> dict[str, Any]:
    """Join harvested earnings surprises with matured 5/20/40/60D residuals."""
    from modeling.v6.replay_benchmark import load_benchmark_events
    from modeling.v6.replay import to_market_event
    from modeling.v6 import whisper

    returns = (load_pead_returns().get("events") or {})
    rows: list[dict[str, Any]] = []
    for bev in load_benchmark_events():
        if bev.event_type not in {"earnings_beat", "earnings_miss"} or not bev.affected_tickers:
            continue
        if bev.actual is None or bev.expected is None or not bev.surprise_std:
            continue
        ticker = bev.affected_tickers[0]
        me = to_market_event(bev.to_historical_event(ticker))
        std_surprise = (bev.actual - bev.expected) / bev.surprise_std
        ret = returns.get(bev.event_id, {})
        labels, matured = {}, {}
        for w in ALL_WINDOWS:
            cell = ret.get(str(w)) if isinstance(ret, dict) else None
            resid = cell.get("residual_vs_sector") if isinstance(cell, dict) else None
            labels[w] = resid
            matured[w] = resid is not None
        rows.append({
            "event_id": bev.event_id, "ticker": ticker, "event_time": bev.event_time,
            "sector": bev.sector, "split": bev.split,
            # features (post-print): surprise magnitude/sign, whisper excess
            "std_surprise": round(std_surprise, 4),
            "whisper_excess": whisper.excess_surprise(me),
            "t1_reaction": (ret.get("1") or {}).get("residual_vs_sector") if isinstance(ret.get("1"), dict) else None,
            "labels_residual": labels,
            "matured": matured,
        })
    rows.sort(key=lambda r: r["event_time"])
    return {
        "rows": rows,
        "windows": ALL_WINDOWS,
        "feature_note": (
            "FEATURES (post-print only): std_surprise, whisper_excess, and t1_reaction "
            "(the realized T+1 residual). These are valid only for the post-print drift "
            "model and MUST NOT be used in any pre-print direction model. "
            "LABELS/TARGETS: the 5/20/40/60D residual_vs_sector in labels_residual are "
            "targets, never features. No window's residual is used to predict itself."
        ),
        "feature_roles": {
            "std_surprise": "feature (post-print)",
            "whisper_excess": "feature (post-print)",
            "t1_reaction": "feature (post-print only; not for pre-print direction model)",
            "labels_residual[5/20/40/60]": "label/target (never a feature)",
        },
    }


def _spearman_ic(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 5:
        return None
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        for pos, i in enumerate(order):
            r[i] = pos
        return r
    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx) ** 0.5
    vy = sum((b - my) ** 2 for b in ry) ** 0.5
    if vx < 1e-9 or vy < 1e-9:
        return None
    return round(cov / (vx * vy), 4)


def pead_scorecard() -> dict[str, Any]:
    """Per-window PEAD readiness: drift hit rate, IC, quantile spread, coverage."""
    ds = build_pead_dataset()
    rows = ds["rows"]
    total = len(rows)
    windows: dict[str, Any] = {}
    for w in ALL_WINDOWS:
        matured = [r for r in rows if r["matured"].get(w) and r["labels_residual"].get(w) is not None]
        n = len(matured)
        if n < MIN_MATURED:
            windows[str(w)] = {"status": "insufficient_matured_windows", "matured": n,
                               "total_earnings": total, "min_required": MIN_MATURED}
            continue
        surp = [r["std_surprise"] for r in matured]
        resid = [r["labels_residual"][w] for r in matured]
        hits = sum(1 for s, d in zip(surp, resid) if _sign(s) == _sign(d) and _sign(d) != 0)
        decisive = sum(1 for s, d in zip(surp, resid) if _sign(s) != 0 and _sign(d) not in (None, 0))
        # top vs bottom surprise tercile mean drift
        order = sorted(matured, key=lambda r: r["std_surprise"])
        k = max(1, n // 3)
        bot = [r["labels_residual"][w] for r in order[:k]]
        top = [r["labels_residual"][w] for r in order[-k:]]
        windows[str(w)] = {
            "status": "ok",
            "matured": n,
            "coverage": round(n / total, 3) if total else None,
            "drift_direction_hit_rate": round(hits / decisive, 3) if decisive else None,
            "ic_spearman": _spearman_ic(surp, resid),
            "mean_drift_top_surprise_tercile": round(sum(top) / len(top), 4),
            "mean_drift_bottom_surprise_tercile": round(sum(bot) / len(bot), 4),
            "horizon_class": "short_reaction" if w in SHORT_WINDOWS else "pead",
        }
    return {
        "total_earnings_events": total,
        "min_matured_required": MIN_MATURED,
        "windows": windows,
        "note": "Drift labels are residual-vs-sector. Unmatured windows are excluded, not imputed. Scaffold only; no trade signal.",
    }
