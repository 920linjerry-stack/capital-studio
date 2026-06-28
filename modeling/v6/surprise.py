"""Pillar 5: structured surprise and honestly labelled proxy surprise.

The engine only treats ``actual - expected`` as consensus surprise when the
event carries traceable structured fields:

``actual`` / ``expected`` / ``surprise_std`` / ``surprise_source``.

When those fields are absent, ``surprise_score(event)`` returns ``None`` and
the V6 1-3 headline/classifier behavior is unchanged. A separate
``proxy_surprise`` field may be shown and used as a price proxy, but it is never
called consensus surprise.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from modeling.v6.schemas import MarketEvent, DIRECTION_BULLISH, DIRECTION_BEARISH, DIRECTION_NEUTRAL

_DATA_DIR = Path(__file__).with_name("data")
_OBS_JSON = _DATA_DIR / "surprise_observations.json"
_EPS = 1e-9
_CLAMP_SIGMA = 3.0


class ConsensusProvider(Protocol):
    """Future structured-data interface for EPS/macro consensus providers."""

    def lookup(self, event: MarketEvent) -> dict[str, Any] | None:
        """Return actual/expected/std/source fields, or None when unavailable."""


def _clamp_sigma(value: float) -> float:
    return max(-_CLAMP_SIGMA, min(_CLAMP_SIGMA, value))


def load_surprise_observations() -> dict[str, Any]:
    """Load committed structured surprise observations for replay fixtures."""
    if not _OBS_JSON.exists():
        return {}
    try:
        data = json.loads(_OBS_JSON.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def observation_for(event_id: str) -> dict[str, Any] | None:
    row = (load_surprise_observations().get("events") or {}).get(event_id)
    return row if isinstance(row, dict) else None


def surprise_score(event: MarketEvent) -> float | None:
    """Return standardized true surprise, or None when not traceable."""
    if event.actual is None or event.expected is None or event.surprise_std is None:
        return None
    if not event.surprise_source:
        return None
    if abs(event.surprise_std) <= _EPS:
        return None
    return round(_clamp_sigma((event.actual - event.expected) / event.surprise_std), 4)


def proxy_surprise_score(event: MarketEvent) -> float | None:
    """Return honestly labelled proxy surprise, never consensus surprise."""
    if event.proxy_surprise is None:
        return None
    return round(_clamp_sigma(float(event.proxy_surprise)), 4)


def has_structured_surprise(event: MarketEvent) -> bool:
    return surprise_score(event) is not None


def effective_direction(event: MarketEvent) -> int | None:
    """Direction implied by structured surprise, or None to keep existing logic.

    When a whisper baseline exists for the name (the stock's own historical bar),
    the direction is driven by the *excess* surprise vs that bar rather than the
    raw consensus surprise -- a serial beater beating by less than usual reads
    bearish (the AVGO effect). Validated on the replay benchmark.
    """
    score = surprise_score(event)
    if score is None:
        score = proxy_surprise_score(event)
    elif abs(score) <= _EPS:
        proxy = proxy_surprise_score(event)
        score = proxy if proxy is not None else score
    if score is None:
        return None
    from modeling.v6 import whisper
    exc = whisper.excess_surprise(event)
    if exc is not None:
        score = exc   # surprise relative to the stock's own bar (whisper proxy)
    if abs(score) <= _EPS:
        return DIRECTION_NEUTRAL
    higher_good = event.higher_is_bullish
    if higher_good is None:
        # EPS/revenue-like company surprise convention: higher is better. Macro
        # events must set ``higher_is_bullish`` explicitly to be used.
        if event.source_type != "company":
            return None
        higher_good = True
    sign = DIRECTION_BULLISH if score > 0 else DIRECTION_BEARISH
    return sign if higher_good else -sign


def magnitude_multiplier(event: MarketEvent) -> float:
    """Magnitude scales with |standardized surprise| when true surprise exists."""
    score = surprise_score(event)
    if score is None:
        score = proxy_surprise_score(event)
    elif abs(score) <= _EPS:
        proxy = proxy_surprise_score(event)
        score = proxy if proxy is not None else score
    if score is None:
        return 1.0
    if abs(score) <= _EPS:
        return 0.0
    return round(max(0.25, min(1.75, abs(score))), 4)


def surprise_payload(event: MarketEvent) -> dict[str, Any] | None:
    score = surprise_score(event)
    proxy = proxy_surprise_score(event)
    if score is None and proxy is None:
        return None
    payload: dict[str, Any] = {}
    if score is not None:
        payload.update({
            "kind": "consensus_surprise",
            "score": score,
            "actual": event.actual,
            "expected": event.expected,
            "surprise_std": event.surprise_std,
            "unit": event.surprise_unit,
            "source": event.surprise_source,
            "label": event.surprise_label,
            "higher_is_bullish": event.higher_is_bullish,
        })
    if proxy is not None:
        payload["proxy_surprise"] = proxy
        payload["proxy_surprise_source"] = event.proxy_surprise_source
    return payload
