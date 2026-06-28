"""C1 shadow model layer -- SHADOW MODE ONLY.

A real, fitted model that combines V6's rule-layer features into a calibrated
probability. It NEVER replaces the live rule + selective-prediction output; it
only emits ``shadow_*`` fields and a scorecard for review.

Design choices (per the C1 brief):
* Simple, interpretable, stable: an L2-regularised logistic combiner fit with
  numpy gradient descent (sklearn is absent; no heavy black box).
* Time-based split only -- rows are sorted by ``event_time`` and the later slice
  is the out-of-sample test. No random shuffle (no time leakage).
* Two variants with explicit data boundaries:
    - ``preprint``  : only features knowable before the print (crowding, etc.).
    - ``postprint`` : may use realized surprise / whisper excess (labelled
      post-print; not a pre-print predictor).
* Output is calibrated (the logistic is its own Platt scaler) and reliability /
  Brier checked. If the shadow model does not beat the rule layer OOS it is
  reported as ``shadow under review`` and not promoted.

No LLM. Deterministic given the committed benchmark + snapshots.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from modeling.v6 import crowding, whisper
from modeling.v6.schemas import MarketEvent

_DATA_DIR = Path(__file__).with_name("data")
_MODEL_JSON = _DATA_DIR / "c1_shadow_model.json"
SHADOW_MODEL_VERSION = "c1.shadow.logistic.v1"
_EVAL_WINDOW = 5
_TEST_FRACTION = 0.30
_L2 = 1.0
_ITERS = 4000
_LR = 0.1

# Feature definitions, with data-boundary tags (the C1 brief requires these).
FEATURE_BOUNDARY = {
    "std_surprise": "post-print only (realized actual vs consensus)",
    "whisper_excess": "post-print only (realized surprise vs own bar)",
    "crowding_dev": "pre-print available (price-proxy snapshot; look-ahead risk if latest snapshot reused for old events)",
}
PREPRINT_FEATURES = ["crowding_dev"]
POSTPRINT_FEATURES = ["std_surprise", "whisper_excess", "crowding_dev"]


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def _std_surprise(ev: MarketEvent) -> float | None:
    if ev.actual is None or ev.expected is None or not ev.surprise_std:
        return None
    if abs(ev.surprise_std) < 1e-9:
        return None
    return max(-3.0, min(3.0, (ev.actual - ev.expected) / ev.surprise_std))


def _feature_value(name: str, ev: MarketEvent, ticker: str) -> tuple[float | None, bool]:
    """Return (value, available). Missing -> (0.0, False) so callers can record coverage."""
    if name == "std_surprise":
        v = _std_surprise(ev)
    elif name == "whisper_excess":
        v = whisper.excess_surprise(ev)
    elif name == "crowding_dev":
        state = crowding.crowding_state(ticker)
        score = state.get("priced_for_perfection")
        v = (float(score) - 0.5) if score is not None and state.get("data_mode") != "unavailable" else None
    else:
        v = None
    return (float(v), True) if v is not None else (0.0, False)


def _realized_dir(row: dict[str, Any]) -> int | None:
    pay = row.get("returns", {}).get(_EVAL_WINDOW, {})
    val = pay.get("abnormal")
    if val is None:
        val = pay.get("stock")
    if val is None:
        return None
    return 1 if val > 1e-9 else -1 if val < -1e-9 else 0


def build_dataset(mode: str = "postprint") -> dict[str, Any]:
    """Build a time-ordered feature dataset from the replay benchmark."""
    from modeling.v6.replay_benchmark import load_benchmark_events, run_benchmark
    from modeling.v6.replay import to_market_event

    events = {e.event_id: e for e in load_benchmark_events()}
    rows = run_benchmark(load_benchmark_events(), eval_window=_EVAL_WINDOW)
    feats = PREPRINT_FEATURES if mode == "preprint" else POSTPRINT_FEATURES

    samples: list[dict[str, Any]] = []
    miss_counts = {f: 0 for f in feats}
    for r in rows:
        rd = _realized_dir(r)
        if rd in (None, 0):
            continue
        bev = events.get(r["event_id"])
        if bev is None:
            continue
        me = to_market_event(bev.to_historical_event(r["ticker"]))
        x, avail = [], []
        for f in feats:
            val, ok = _feature_value(f, me, r["ticker"])
            x.append(val)
            avail.append(ok)
            if not ok:
                miss_counts[f] += 1
        # The post-print model's domain is events that actually carry a realized
        # surprise; scoring it on macro/control rows (no features) is meaningless.
        if mode == "postprint" and not avail[feats.index("std_surprise")]:
            continue
        samples.append({
            "event_id": r["event_id"], "ticker": r["ticker"], "event_time": r["event_time"],
            "event_type": r.get("event_type"), "x": x, "avail": avail,
            "y": 1 if rd > 0 else 0, "rule_dir": r["predicted_direction"], "realized_dir": rd,
        })
    samples.sort(key=lambda s: s["event_time"])
    return {"mode": mode, "features": feats, "samples": samples, "missing": miss_counts}


def _fit_logistic(X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float, np.ndarray, np.ndarray]:
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std[std < 1e-9] = 1.0
    Xs = (X - mean) / std
    n, d = Xs.shape
    w = np.zeros(d)
    b = 0.0
    for _ in range(_ITERS):
        p = _sigmoid(Xs @ w + b)
        grad_w = Xs.T @ (p - y) / n + _L2 * w / n
        grad_b = float(np.sum(p - y) / n)
        w -= _LR * grad_w
        b -= _LR * grad_b
    return w, b, mean, std


def _metrics(y: np.ndarray, p: np.ndarray) -> dict[str, Any]:
    pred = (p >= 0.5).astype(int)
    acc = float((pred == y).mean()) if len(y) else None
    brier = float(np.mean((p - y) ** 2)) if len(y) else None
    bins = []
    for lo, hi in [(0.0, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 1.01)]:
        m = (p >= lo) & (p < hi)
        if m.sum():
            bins.append({"range": f"{lo:.1f}-{min(hi,1.0):.1f}", "n": int(m.sum()),
                         "mean_pred": round(float(p[m].mean()), 3), "empirical": round(float(y[m].mean()), 3)})
    return {"n": int(len(y)), "accuracy": round(acc, 4) if acc is not None else None,
            "brier": round(brier, 4) if brier is not None else None, "reliability_bins": bins}


def train(mode: str = "postprint", *, write: bool = False) -> dict[str, Any]:
    ds = build_dataset(mode)
    samples = ds["samples"]
    if len(samples) < 30:
        return {"status": "insufficient_sample", "mode": mode, "n": len(samples),
                "reason": "fewer than 30 decisive samples"}
    split = int(len(samples) * (1 - _TEST_FRACTION))
    train_s, test_s = samples[:split], samples[split:]
    Xtr = np.array([s["x"] for s in train_s], float)
    ytr = np.array([s["y"] for s in train_s], float)
    Xte = np.array([s["x"] for s in test_s], float)
    yte = np.array([s["y"] for s in test_s], float)
    w, b, mean, std = _fit_logistic(Xtr, ytr)
    pte = _sigmoid(((Xte - mean) / std) @ w + b)
    shadow = _metrics(yte, pte)

    # rule-layer OOS on the SAME test rows (apples-to-apples)
    rule_correct = [1 if s["rule_dir"] == s["realized_dir"] else 0 for s in test_s if s["rule_dir"] != 0]
    rule_acc = round(sum(rule_correct) / len(rule_correct), 4) if rule_correct else None

    # selective on shadow probabilities (confidence = max(p,1-p))
    conf = np.maximum(pte, 1 - pte)
    pred = (pte >= 0.5).astype(int)
    strong_mask = conf >= 0.62
    sel = {
        "strong_coverage": round(float(strong_mask.mean()), 3) if len(conf) else None,
        "strong_acted_accuracy": round(float((pred[strong_mask] == yte[strong_mask]).mean()), 3)
        if strong_mask.sum() else None,
        "weak_no_edge_coverage": round(float((conf < 0.62).mean()), 3) if len(conf) else None,
    }
    coef = {f: round(float(c), 4) for f, c in zip(ds["features"], w)}
    promoted = shadow["accuracy"] is not None and rule_acc is not None and shadow["accuracy"] > rule_acc + 0.01

    result = {
        "status": "ok" if promoted else "shadow_under_review",
        "shadow_model_version": SHADOW_MODEL_VERSION,
        "mode": mode,
        "features": ds["features"],
        "feature_boundary": {f: FEATURE_BOUNDARY[f] for f in ds["features"]},
        "n_train": len(train_s), "n_test": len(test_s),
        "split": "time-based (sorted by event_time; later slice = OOS); no shuffle",
        "rule_baseline_oos_accuracy": rule_acc,
        "shadow_oos": shadow,
        "selective_on_shadow": sel,
        "feature_missingness": {f: ds["missing"][f] for f in ds["features"]},
        "coefficients_standardized": coef,
        "reason_codes": _reason_codes(coef),
        "weights": {"w": list(map(float, w)), "b": float(b),
                    "mean": list(map(float, mean)), "std": list(map(float, std))},
    }
    if write and mode == "postprint":
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        _MODEL_JSON.write_text(json.dumps(_model_blob(result), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
    return result


def _reason_codes(coef: dict[str, float]) -> list[str]:
    return [f"{f}:{'+' if c >= 0 else '-'}{abs(c):.2f}"
            for f, c in sorted(coef.items(), key=lambda kv: -abs(kv[1]))]


def _model_blob(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "shadow_model_version": result["shadow_model_version"],
        "mode": result["mode"], "features": result["features"],
        "feature_boundary": result["feature_boundary"],
        "weights": result["weights"], "status": result["status"],
        "note": "C1 shadow model -- shadow output only, never replaces live V6 selective prediction.",
    }


_MODEL_CACHE: dict[str, Any] | None = None


def _load_model() -> dict[str, Any]:
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        if _MODEL_JSON.exists():
            try:
                _MODEL_CACHE = json.loads(_MODEL_JSON.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                _MODEL_CACHE = {}
        else:
            _MODEL_CACHE = {}
    return _MODEL_CACHE


def shadow_for_event(event: MarketEvent, ticker: str | None = None) -> dict[str, Any]:
    """Read-only shadow_* fields for one event. Never affects live scoring."""
    model = _load_model()
    base = {
        "shadow_model_version": SHADOW_MODEL_VERSION,
        "shadow_model_status": "shadow_only",
        "shadow_probability": None,
        "shadow_direction": None,
        "shadow_signal_tier": "no_edge",
        "shadow_feature_coverage": 0.0,
        "shadow_missing_features": [],
        "shadow_reason_codes": [],
    }
    if not model or "weights" not in model:
        base["shadow_missing_features"] = ["model_unavailable"]
        return base
    tkr = (ticker or (event.related_tickers[0] if event.related_tickers else "")).upper()
    feats = model.get("features", [])
    x, missing, n_ok = [], [], 0
    for f in feats:
        val, ok = _feature_value(f, event, tkr)
        x.append(val)
        if ok:
            n_ok += 1
        else:
            missing.append(f)
    w = np.array(model["weights"]["w"], float)
    mean = np.array(model["weights"]["mean"], float)
    std = np.array(model["weights"]["std"], float)
    b = float(model["weights"]["b"])
    p_up = float(_sigmoid(((np.array(x, float) - mean) / std) @ w + b))
    direction = 1 if p_up >= 0.5 else -1
    conf = max(p_up, 1 - p_up)
    from modeling.v6.selective import signal_tier
    base.update({
        "shadow_probability": round(conf, 3),
        "shadow_direction": direction,
        "shadow_signal_tier": signal_tier(conf),
        "shadow_feature_coverage": round(n_ok / len(feats), 3) if feats else 0.0,
        "shadow_missing_features": missing,
        "shadow_reason_codes": model.get("reason_codes", []) if isinstance(model.get("reason_codes"), list) else [],
        "shadow_p_up": round(p_up, 3),
    })
    return base
