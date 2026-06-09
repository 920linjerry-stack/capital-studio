"""V5.2.2 Precompute & Runtime Scalability Guardrail.

Build-time / immutable in-memory precompute of every *directed* Arena pair over
the frozen real seed deck. The Arena default card-table combinations can then
follow a deterministic, cacheable lookup path instead of every user re-running
the full calculate path on every click.

This is NOT production infrastructure. There is no database, no Redis, no
microservice, no runtime file write, no network, no LLM, no plugin. It is a
pure function over the local deck plus an optional immutable module-level cache
that the runtime only reads -- never mutates and never persists to disk.

Scale note
----------
* Current deck = 45 companies  -> 45 * 44 = 1980 directed pairs.
* A future 50-company deck      -> 50 * 49 = 2450 directed pairs.

Both are tiny and remain comfortably suited to a build-time / precomputed
lookup map held immutably in memory. When the deck grows, this map can be built
once at process start (or at build time) and shared read-only across all
concurrent requests, which is the guardrail this module establishes for a
future 10,000-concurrent-user Arena -- without committing to any specific
caching backend today.

Source of truth
---------------
The A/D engine and V5.1 default cost synergy are unchanged. This module reuses
``build_ma_response`` (the same helper behind ``/api/modeling/ma/calculate``),
so a precomputed pair is identical to the live calculate result for the same
two companies and the same Arena terms. There is no second Arena engine.
"""

from __future__ import annotations

import copy
import gzip
import json
import math
from typing import Any

from modeling.ma.api import build_ma_response
from modeling.ma.company_deck import list_company_cards
from modeling.ma.viability import compact_viability


# Mirrors arena.js ARENA_DEAL_TERMS exactly. Keeping these identical is what
# guarantees a precomputed pair equals the /api/modeling/ma/calculate result
# for the same acquirer/target. The A/D engine formula and the default synergy
# constants are NOT redefined here -- only the fixed light-table deal terms.
ARENA_DEAL_TERMS: dict[str, Any] = {
    "deal_type": "full_acquisition",
    "premium": 0.30,
    "cash_pct": 0.5,
    "stock_pct": 0.5,
    "financing_cost": 0.05,
    "tax_rate": 0.25,
    "synergy_mode": "default",  # V5.1 default cost synergy, upstream of engine
}


def pair_key(acquirer_id: Any, target_id: Any) -> str:
    """Stable lookup key for a directed (acquirer -> target) pair."""
    return f"{acquirer_id}__{target_id}"


def build_pair_payload(acquirer_id: Any, target_id: Any) -> dict[str, Any]:
    """Build the exact calculate-API payload for one directed Arena pair."""
    return {
        "acquirer": {"sample_id": acquirer_id},
        "target": {"sample_id": target_id},
        "deal": dict(ARENA_DEAL_TERMS),
        "currency": "USD",
    }


def _light_result(result: dict[str, Any]) -> dict[str, Any]:
    """Project a full engine result into the compact Arena light shape.

    Deliberately omits source_meta, the full economics table, and audit notes;
    those stay in Deal Studio / a future Audit layer.
    """
    acquirer = result.get("acquirer") or {}
    target = result.get("target") or {}
    ctx = result.get("synergy_context") or {}
    default_synergy = ctx.get("default_cost_synergy") or {}
    pre_ppa = result.get("pre_ppa_chip") or {}
    is_accretive = bool(result.get("is_accretive"))
    light = {
        "acquirer_id": acquirer.get("id"),
        "target_id": target.get("id"),
        "acquirer_ticker": acquirer.get("ticker"),
        "target_ticker": target.get("ticker"),
        "accretion_dilution_pct": result.get("accretion_dilution"),
        "is_accretive": is_accretive,
        "direction": "accretive" if is_accretive else "dilutive",
        "synergy_status": result.get("synergy_status"),
        "synergy_status_label": result.get("synergy_status_label"),
        "default_synergy_tier": default_synergy.get("synergy_tier"),
        "pre_ppa_chip": {
            "label": pre_ppa.get("label", "Pre-PPA"),
            "detail": pre_ppa.get("detail", ""),
        },
        # Optional light economic chip (derived view only -- NOT an overall
        # score, and kept physically separate from the viability fields below).
        "economic_chip": "增厚" if is_accretive else "摊薄",
    }
    # V5.3 compact viability light fields (level + label + top 1-2 flags). This
    # is an independent axis from the economic fields above; it is never merged
    # with accretion_dilution_pct / synergy_status / economic_chip.
    light.update(compact_viability(result.get("viability_context") or {}))
    return light


def build_arena_pairs() -> dict[str, Any]:
    """Pure deterministic build of all directed Arena pairs.

    Returns ``{"pairs": [...], "index": {key: light_result}, "deck_size": N,
    "pair_count": N*(N-1)}``. No file write, no network, no mutation of shared
    state. Safe to call from a precompute job or a test rebuild.
    """
    cards = list_company_cards()
    ids = [card["id"] for card in cards]

    pairs: list[dict[str, Any]] = []
    for acquirer_id in ids:
        for target_id in ids:
            if acquirer_id == target_id:
                continue  # never a self-deal
            body, code = build_ma_response(build_pair_payload(acquirer_id, target_id))
            if code != 200 or body.get("status") != "ok":
                # The deck is QA'd, so a default-synergy build should always
                # succeed. If it ever does not, fail loudly here at build time
                # rather than silently dropping a pair at runtime.
                raise RuntimeError(
                    f"Arena precompute failed for {acquirer_id} -> {target_id}: {body.get('flags')}"
                )
            pairs.append(_light_result(body["result"]))

    index = {pair_key(p["acquirer_id"], p["target_id"]): p for p in pairs}
    return {
        "pairs": pairs,
        "index": index,
        "deck_size": len(ids),
        "pair_count": len(pairs),
    }


# ── Immutable, read-only module-level cache ────────────────────────────────
# Built lazily on first read and shared across all requests. The runtime only
# reads from it; it is never mutated per request and never written to disk.
_CACHE: dict[str, Any] | None = None


def _get_cache(rebuild: bool = False) -> dict[str, Any]:
    """Internal: return the shared, mutable precompute cache (built once).

    This is NOT a public accessor. Callers outside this module must go through
    the defensive-copy helpers below (``get_arena_pairs`` / ``list_arena_pairs``
    / ``get_arena_pair``) so the shared cache can never be mutated by a request
    handler or any other caller. ``rebuild=True`` forces a fresh deterministic
    build (used by tests).
    """
    global _CACHE
    if _CACHE is None or rebuild:
        _CACHE = build_arena_pairs()
    return _CACHE


def get_arena_pairs(rebuild: bool = False) -> dict[str, Any]:
    """Return a defensive deep copy of the precomputed pair bundle.

    The returned object is fully detached from the internal cache: callers may
    read or even mutate it freely without affecting subsequent precomputed
    results. ``rebuild=True`` forces a fresh deterministic build (used by tests).
    """
    return copy.deepcopy(_get_cache(rebuild))


def list_arena_pairs() -> list[dict[str, Any]]:
    """Return a defensive copy of all precomputed light pair results."""
    return copy.deepcopy(_get_cache()["pairs"])


def get_arena_pair(acquirer_id: Any, target_id: Any) -> dict[str, Any] | None:
    """Return a defensive copy of one directed pair, or None if absent."""
    found = _get_cache()["index"].get(pair_key(acquirer_id, target_id))
    return copy.deepcopy(found) if found is not None else None


# ── V5.5 Settlement Board · dual deterministic result layer ─────────────────
# Two INDEPENDENT light rankings over the same precomputed directed pairs:
#   * Economic board  -> ranked by EPS accretion/dilution (most accretive first)
#   * Viability board -> ranked by real-world plausibility (green > yellow > red)
# These are never merged into one "overall score". Both are pure, deterministic
# functions of the frozen deck's precomputed pairs; they re-use the existing
# light pair shape and add no new economics. No LLM, no network, no randomness.

_DEFAULT_TOP_N = 10
_TENSION_N = 3
_VIABILITY_LEVEL_ORDER = {"green": 0, "yellow": 1, "red": 2}


def _finite_pct(pair: dict[str, Any]) -> float | None:
    """Return the pair's accretion/dilution % if it is a finite number, else
    None. A non-numeric / NaN / inf value must never crash the ranking; such a
    pair is pushed to the tail instead."""
    value = pair.get("accretion_dilution_pct")
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def _ticker_tiebreak(pair: dict[str, Any]) -> tuple[str, str]:
    return (str(pair.get("acquirer_ticker") or ""), str(pair.get("target_ticker") or ""))


def _economic_sort_key(pair: dict[str, Any]) -> tuple[Any, ...]:
    """Most accretive first. Finite values lead; unparseable values fall to the
    tail. Final ticker tie-break makes repeated builds byte-for-byte stable."""
    pct = _finite_pct(pair)
    has_value = pct is not None
    acq, tgt = _ticker_tiebreak(pair)
    return (0 if has_value else 1, -(pct if has_value else 0.0), acq, tgt)


def _viability_sort_key(pair: dict[str, Any]) -> tuple[Any, ...]:
    """Steadiest first: green > yellow > red, then fewer risk flags, then higher
    EPS accretion, then a stable ticker tie-break."""
    level = _VIABILITY_LEVEL_ORDER.get(pair.get("viability_level"), 3)
    count = pair.get("viability_flags_count")
    count = count if isinstance(count, int) and not isinstance(count, bool) else 99
    pct = _finite_pct(pair)
    eps_rank = -pct if pct is not None else math.inf  # higher EPS first; missing last
    acq, tgt = _ticker_tiebreak(pair)
    return (level, count, eps_rank, acq, tgt)


def _build_settlement_boards_uncached(top_n: int = _DEFAULT_TOP_N) -> dict[str, Any]:
    """Pure deterministic build of both boards from the precomputed pairs.

    Works off a defensive copy of the pairs, so it never mutates the shared
    precompute cache. AAPL->MSFT and MSFT->AAPL stay distinct directed deals.
    """
    pairs = list_arena_pairs()  # already a deep copy of all directed pairs
    economic = sorted(pairs, key=_economic_sort_key)
    viability = sorted(pairs, key=_viability_sort_key)
    # Tension callout: deals that rank high economically yet flag yellow/red on
    # viability. Explanatory only -- NOT a third ranking and never fed back into
    # either board's order or any result number.
    tension = [
        p for p in economic if p.get("viability_level") in {"red", "yellow"}
    ][:_TENSION_N]
    return {
        "economic": economic[:top_n],
        "viability": viability[:top_n],
        "tension": tension,
        "pair_count": len(pairs),
        "top_n": top_n,
    }


# Immutable, read-only module-level board cache (same discipline as _CACHE).
_BOARDS_CACHE: dict[str, Any] | None = None


def _get_boards_cache(rebuild: bool = False) -> dict[str, Any]:
    global _BOARDS_CACHE
    if _BOARDS_CACHE is None or rebuild:
        _BOARDS_CACHE = _build_settlement_boards_uncached()
    return _BOARDS_CACHE


def build_settlement_boards(top_n: int = _DEFAULT_TOP_N) -> dict[str, Any]:
    """Public deterministic builder (defensive: never returns shared state).

    Always rebuilds for an explicit ``top_n`` so tests can request a different
    slice without touching the cached default-size boards.
    """
    if top_n == _DEFAULT_TOP_N:
        return copy.deepcopy(_get_boards_cache())
    return _build_settlement_boards_uncached(top_n)


def get_settlement_boards(rebuild: bool = False) -> dict[str, Any]:
    """Return a defensive deep copy of the cached default-size boards bundle.

    The returned object is fully detached from the internal cache: a request
    handler may read or even mutate it without affecting later reads.
    """
    return copy.deepcopy(_get_boards_cache(rebuild))


# ── V5.11.2 Payload strategy · cached, gzip-compressed pairs response ─────────
# A 100-card deck has 100*99 = 9,900 directed pairs. The full rich pairs+boards
# body is ~9 MB of JSON, but it is extremely repetitive (a handful of distinct
# Chinese labels, synergy / viability values, and flag titles repeated across
# every pair), so it gzips ~29x to ~0.31 MB on the wire. Every browser sends
# `Accept-Encoding: gzip`, so the transparent, content-negotiated compressed
# body is what is actually transferred — well under the 3 MB guardrail and with
# large headroom for further deck growth, with ZERO change to the pair shape or
# the front-end (fetch() decompresses Content-Encoding transparently).
#
# This is the "compressed static artifact" path: the serialized + gzipped bytes
# are built ONCE into an immutable module-level cache and served read-only to
# every request (bytes are immutable, so there is no defensive-copy concern).
# That is also strictly cheaper per request than re-serializing on every hit,
# which matters for the 10,000-concurrent target. No file write, no network, no
# DB, no LLM -- same deterministic, offline discipline as the rest of the module.
_RESPONSE_CACHE: tuple[bytes, bytes] | None = None


def _finite_scrub(obj: Any) -> Any:
    """Replace non-finite floats (NaN / inf) with None so the body is valid JSON.

    Mirrors the route's historical ``_clean_nan`` defense. The QA'd deck produces
    only finite pair numbers today, but this keeps a future deck change from ever
    emitting an invalid-JSON ``NaN`` token. Returns a new structure; never mutates
    the shared caches it reads from.
    """
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _finite_scrub(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_finite_scrub(v) for v in obj]
    return obj


def _build_response_cache() -> tuple[bytes, bytes]:
    cache = _get_cache()
    body = _finite_scrub({
        "status": "ok",
        "deck_size": cache["deck_size"],
        "pair_count": cache["pair_count"],
        "pairs": cache["pairs"],
        "boards": _get_boards_cache(),
    })
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return raw, gzip.compress(raw, 6)


def get_arena_pairs_response(accept_gzip: bool = False, rebuild: bool = False) -> tuple[bytes, bool]:
    """Return ``(body_bytes, is_gzip)`` for the ``/arena/pairs`` response.

    ``body_bytes`` is the full ``status/deck_size/pair_count/pairs/boards`` JSON,
    gzip-compressed when ``accept_gzip`` is true (the caller has negotiated
    ``Accept-Encoding: gzip``), otherwise the raw UTF-8 JSON. Both forms are
    built once and cached immutably. ``rebuild=True`` forces a fresh build (used
    by tests).
    """
    global _RESPONSE_CACHE
    if _RESPONSE_CACHE is None or rebuild:
        _RESPONSE_CACHE = _build_response_cache()
    raw, gz = _RESPONSE_CACHE
    return (gz, True) if accept_gzip else (raw, False)
