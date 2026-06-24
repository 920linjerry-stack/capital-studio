"""V6 learned sector contagion: the read-through cascade (e.g. the AVGO effect).

A single bellwether print moves its whole complex: when Broadcom or Micron
reports, the AI/semis group reprices even if you only hold NVDA. The original
engine could not express this -- a single-name event only hit its own ticker.

This module learns, from the **real-return replay benchmark**, how cohesively
each sector cluster co-moves, and exposes a damped per-pair ``read_through``
coefficient. The impact engine uses it to propagate a single-name company event
onto sector peers through the second-order channel, signed by the event and
scaled by the learned coefficient.

Learning is seeded with a conservative prior per cluster and shrunk toward the
benchmark's realized co-movement, so it is meaningful with little data and
sharpens as more events are added. Deterministic, offline, no LLM.
"""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).with_name("data")
_CONTAGION_JSON = _DATA_DIR / "contagion.json"
_EVAL_WINDOW = 5
_SHRINK_K = 3.0
# Max share of a peer's relevance attributable to read-through (keeps it a
# damped second-order channel, never as strong as a direct hit).
MAX_READ_THROUGH = 0.6

# Sector clusters: the membership that co-moves on a bellwether print. Keyed by
# cluster id; tickers may belong to one cluster. Conservative seed priors encode
# how tightly each group historically trades together.
CLUSTERS: dict[str, dict[str, Any]] = {
    "ai_semis": {
        "members": ["NVDA", "AMD", "AVGO", "TSM", "ASML", "MU", "MRVL", "QCOM", "SMCI", "ARM", "SOXX", "SMH", "XLK", "QQQ", "TQQQ"],
        "prior": 0.55,
    },
    "megacap_tech": {
        "members": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "QQQ", "XLK", "SPY"],
        "prior": 0.45,
    },
    "banks": {
        "members": ["JPM", "BAC", "GS", "WFC", "C", "MS", "XLF"],
        "prior": 0.50,
    },
    "energy": {
        "members": ["XOM", "CVX", "COP", "SLB", "USO", "XLE"],
        "prior": 0.55,
    },
    "healthcare": {
        "members": ["LLY", "NVO", "UNH", "JNJ", "MRK", "PFE", "XLV"],
        "prior": 0.35,
    },
}

# A ticker can sit in more than one cluster (NVDA is semis; QQQ is both indices);
# we resolve to the *most specific* cluster a primary belongs to via this order.
_CLUSTER_PRIORITY = ("ai_semis", "energy", "banks", "healthcare", "megacap_tech")


def cluster_of(ticker: str) -> str | None:
    """Return the most-specific cluster id containing ``ticker`` (or None)."""
    t = (ticker or "").upper()
    for cid in _CLUSTER_PRIORITY:
        if t in CLUSTERS[cid]["members"]:
            return cid
    return None


def _signed(row: dict[str, Any], window: int) -> float | None:
    payload = row.get("returns", {}).get(window, {})
    val = payload.get("abnormal")
    if val is None:
        val = payload.get("stock")
    return None if val is None else float(val)


def fit_contagion(results: list[dict[str, Any]], *, window: int = _EVAL_WINDOW) -> dict[str, Any]:
    """Learn per-cluster cohesion from benchmark co-movement, shrunk to a prior.

    For every benchmark event touching >=2 members of a cluster, each member
    pair contributes a sign-agreement (do they move the same way?) and a
    magnitude ratio (how proportionally). The cluster coefficient is
    ``cohesion * transmission`` shrunk toward the seed prior.
    """
    # Group rows by event, keep cluster members with a realized move.
    by_event: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        by_event.setdefault(r["event_id"], []).append(r)

    agree: dict[str, list[float]] = {c: [] for c in CLUSTERS}
    ratio: dict[str, list[float]] = {c: [] for c in CLUSTERS}
    for rows in by_event.values():
        moves = {r["ticker"].upper(): _signed(r, window) for r in rows}
        moves = {t: v for t, v in moves.items() if v is not None and abs(v) > 1e-9}
        for cid, spec in CLUSTERS.items():
            members = [t for t in moves if t in spec["members"]]
            for a, b in combinations(sorted(members), 2):
                agree[cid].append(1.0 if (moves[a] > 0) == (moves[b] > 0) else 0.0)
                hi, lo = max(abs(moves[a]), abs(moves[b])), min(abs(moves[a]), abs(moves[b]))
                ratio[cid].append(lo / hi if hi > 1e-9 else 0.0)

    clusters: dict[str, Any] = {}
    for cid, spec in CLUSTERS.items():
        prior = float(spec["prior"])
        pairs = agree[cid]
        n = len(pairs)
        if n:
            cohesion = sum(pairs) / n
            transmission = sum(ratio[cid]) / n
            learned = cohesion * transmission
            coef = (n * learned + _SHRINK_K * prior) / (n + _SHRINK_K)
        else:
            cohesion = transmission = None
            coef = prior
        clusters[cid] = {
            "coefficient": round(min(MAX_READ_THROUGH, coef), 3),
            "prior": prior,
            "pairs_observed": n,
            "cohesion": round(cohesion, 3) if cohesion is not None else None,
            "transmission": round(transmission, 3) if transmission is not None else None,
            "members": list(spec["members"]),
        }
    return {
        "_meta": {
            "window_days": window,
            "shrink_k": _SHRINK_K,
            "max_read_through": MAX_READ_THROUGH,
            "source": "replay benchmark co-movement (real abnormal returns) shrunk to seed priors",
            "note": "coefficient = damped read-through of a single-name event onto sector peers; not a forecast.",
        },
        "clusters": clusters,
    }


def build_contagion(write: bool = True) -> dict[str, Any]:
    from modeling.v6.replay_benchmark import load_benchmark_events, run_benchmark
    results = run_benchmark(load_benchmark_events(), eval_window=_EVAL_WINDOW)
    data = fit_contagion(results)
    if write:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        _CONTAGION_JSON.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return data


_CACHE: dict[str, Any] | None = None


def load_contagion() -> dict[str, Any]:
    global _CACHE
    if _CACHE is None:
        if _CONTAGION_JSON.exists():
            try:
                _CACHE = json.loads(_CONTAGION_JSON.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                _CACHE = {}
        else:
            _CACHE = {}
    return _CACHE


def cluster_coefficient(cluster_id: str) -> float:
    spec = (load_contagion().get("clusters") or {}).get(cluster_id)
    if spec and isinstance(spec.get("coefficient"), (int, float)):
        return float(spec["coefficient"])
    seed = CLUSTERS.get(cluster_id, {}).get("prior", 0.0)
    return float(seed)


def read_through(primary: str, peer: str) -> float:
    """Damped read-through coefficient (0..MAX) of a ``primary`` single-name
    event onto a sector ``peer``. 0 when they are not in the same cluster or are
    the same ticker."""
    p, q = (primary or "").upper(), (peer or "").upper()
    if not p or not q or p == q:
        return 0.0
    cid = cluster_of(p)
    if cid is None or q not in CLUSTERS[cid]["members"]:
        return 0.0
    return cluster_coefficient(cid)
