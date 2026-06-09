"""Deterministic local loader for V5.1 company cards."""

from __future__ import annotations

from typing import Any

from modeling.ma.company_cards import card_to_engine_company, public_company_card
from modeling.ma.real_seed_deck import REAL_SEED_COMPANY_CARDS
from modeling.ma.seed_deck import SEED_COMPANY_CARDS


_REAL_DECK_BY_ID = {str(card["id"]): card for card in REAL_SEED_COMPANY_CARDS}
_FICTIONAL_DECK_BY_ID = {str(card["id"]): card for card in SEED_COMPANY_CARDS}

# V5.11.2: Marsh & McLennan moved from the legacy ticker MMC to MRSH (effective
# 2026-01-14). The production card is canonical id `mrsh` / ticker `MRSH`; this
# alias map keeps any legacy `MMC` reference (deep link ?acq=/?tgt=, Deal Review
# Queue key, board row, cached pair lookup, or old review URL) resolving to the
# same single economic entity. It never creates a second card. Keys are matched
# case-insensitively against the lowercase card-id space.
_ID_ALIASES = {"mmc": "mrsh"}


def resolve_company_id(company_id: str) -> str:
    """Normalize a (possibly legacy) company id/ticker to its canonical card id.

    Deterministic and side-effect free: lowercases/trims the input and applies
    the legacy-ticker alias map (e.g. MMC -> mrsh). Unknown ids pass through
    unchanged so the caller's normal missing-card fallback still applies.
    """
    key = str(company_id or "").strip().lower()
    return _ID_ALIASES.get(key, key)


def _find_card(company_id: str) -> dict[str, Any] | None:
    raw = str(company_id or "").strip()
    canonical = resolve_company_id(raw)
    # Try the raw key first (deck ids are lowercase, but be tolerant of an exact
    # legacy/uppercase key), then the alias-resolved canonical id.
    return (
        _REAL_DECK_BY_ID.get(raw)
        or _FICTIONAL_DECK_BY_ID.get(raw)
        or _REAL_DECK_BY_ID.get(canonical)
        or _FICTIONAL_DECK_BY_ID.get(canonical)
    )


def list_company_cards() -> list[dict[str, Any]]:
    """Return normalized real seed company cards as API-facing copies."""
    return [public_company_card(card) for card in REAL_SEED_COMPANY_CARDS]


def list_fictional_company_cards() -> list[dict[str, Any]]:
    """Return the fictional dev/test fallback deck as API-facing copies."""
    return [public_company_card(card) for card in SEED_COMPANY_CARDS]


def get_company_card(company_id: str) -> dict[str, Any] | None:
    """Return one normalized company card by id, or None if missing."""
    card = _find_card(company_id)
    return public_company_card(card) if card else None


def get_engine_company(company_id: str) -> dict[str, Any] | None:
    """Return one card projected into the strict A/D engine input shape."""
    card = _find_card(company_id)
    return card_to_engine_company(card) if card else None


def list_sample_companies() -> list[dict[str, Any]]:
    """Compatibility wrapper for the existing /samples endpoint contract."""
    return list_company_cards()


def get_sample_company(company_id: str) -> dict[str, Any] | None:
    """Compatibility wrapper for existing sample_id payloads."""
    return get_engine_company(company_id)
