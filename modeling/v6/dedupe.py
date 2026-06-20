"""V6 deterministic event de-duplication.

The same story often arrives from several feeds (Yahoo, Google News, a wire).
Without dedupe the engine would over-count its impact. This module collapses
duplicates into a single representative event while preserving provenance.

Strategy (dependency-free, deterministic):

1. Build a coarse **signature** per event:
   ``(event_type, entity_key, time_bucket)`` where ``entity_key`` is the sorted
   related tickers when present, else a small set of salient title tokens.
2. Within a signature group, merge events whose normalized titles are
   sufficiently similar (token Jaccard >= threshold) -- this catches near-dupes
   with different punctuation/wording from different sources.
3. The representative is the highest (confidence, magnitude) member. Merged
   events contribute ``source_count`` and ``source_list``; confidence gets a
   small, capped boost (more independent sources => slightly higher confidence)
   but impact is NOT multiplied by source count.
"""

from __future__ import annotations

import re
from typing import Any

from modeling.v6.schemas import MarketEvent
from modeling.v6.timing import parse_dt

# Tokenization: alphanumeric words of length >= 3, lower-cased. Cheap stopword
# trim keeps signatures stable across wording variants.
_STOP = {
    "the", "and", "for", "with", "from", "after", "amid", "its", "into", "out",
    "on", "in", "to", "of", "as", "at", "by", "is", "are", "be", "will", "new",
    "says", "say", "report", "reports", "reported", "update",
}
_WORD = re.compile(r"[a-z0-9]+")

_TIME_BUCKET_HOURS = 24.0          # same-day grouping
_TITLE_TOKENS_FOR_KEY = 5          # salient tokens used when no tickers
_JACCARD_THRESHOLD = 0.6           # near-duplicate title similarity
_CONF_BOOST_PER_EXTRA = 0.03
_CONF_BOOST_CAP = 0.10


def _tokens(title: str) -> set[str]:
    return {w for w in _WORD.findall((title or "").lower()) if len(w) >= 3 and w not in _STOP}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _time_bucket(event: MarketEvent) -> int:
    dt = parse_dt(event.effective_at) or parse_dt(event.timestamp) or parse_dt(event.scheduled_at)
    if dt is None:
        return 0
    return int(dt.timestamp() // (_TIME_BUCKET_HOURS * 3600))


def _entity_key(event: MarketEvent, toks: set[str]) -> tuple:
    if event.related_tickers:
        return tuple(sorted(event.related_tickers))
    return tuple(sorted(toks)[:_TITLE_TOKENS_FOR_KEY])


def event_signature(event: MarketEvent) -> tuple:
    """Coarse dedupe signature for ``event`` (deterministic)."""
    toks = _tokens(event.title)
    return (event.event_type, _entity_key(event, toks), _time_bucket(event))


def dedupe_events(events: list[MarketEvent]) -> tuple[list[MarketEvent], dict[str, Any]]:
    """Collapse duplicate events. Returns (deduped_events, report).

    Order-stable: groups are processed in first-seen order, and the kept event
    keeps the earliest position. The input events are not mutated.
    """
    groups: list[dict[str, Any]] = []   # each: {sig, toks, members:[event]}
    index: dict[tuple, list[int]] = {}

    for ev in events:
        sig = event_signature(ev)
        toks = _tokens(ev.title)
        placed = False
        for gi in index.get(sig, []):
            g = groups[gi]
            if _jaccard(toks, g["toks"]) >= _JACCARD_THRESHOLD or ev.related_tickers and (
                set(ev.related_tickers) & set(g["members"][0].related_tickers)
            ):
                g["members"].append(ev)
                g["toks"] |= toks
                placed = True
                break
        if not placed:
            groups.append({"sig": sig, "toks": set(toks), "members": [ev]})
            index.setdefault(sig, []).append(len(groups) - 1)

    deduped: list[MarketEvent] = []
    merged_count = 0
    for g in groups:
        members = g["members"]
        rep = max(members, key=lambda e: (e.confidence, e.magnitude))
        if len(members) == 1:
            deduped.append(rep)
            continue
        merged_count += len(members) - 1
        sources: list[str] = []
        for m in members:
            for s in (m.source_list or ([m.source] if m.source else [])):
                if s and s not in sources:
                    sources.append(s)
        boost = min(_CONF_BOOST_CAP, _CONF_BOOST_PER_EXTRA * (len(members) - 1))
        # Build a merged copy so the input list is untouched.
        merged = MarketEvent.from_dict(rep.to_dict())
        merged.confidence = min(1.0, rep.confidence + boost)
        merged.source_count = len(members)
        merged.source_list = sources
        merged.__post_init__()
        deduped.append(merged)

    report = {
        "input_count": len(events),
        "output_count": len(deduped),
        "merged_count": merged_count,
        "duplicate_groups": sum(1 for g in groups if len(g["members"]) > 1),
    }
    return deduped, report
