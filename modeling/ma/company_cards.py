"""V5.1 company card schema and deterministic seed-deck loader helpers.

Company cards are the frozen local data shape that feeds Deal Studio selectors
and rule-based synergy helpers. Runtime remains offline and deterministic:
there is no file I/O, network fetch, LLM, or plugin dependency here.
"""

from __future__ import annotations

import copy
import math
from typing import Any


COMPANY_CARD_SCHEMA_VERSION = "v5.1_company_card"

ARENA_TIER_VALUES = frozenset({"gold", "red", "blue", "green", "white"})
ARENA_TIER_FIELDS = (
    "arena_tier",
    "arena_tier_label",
    "arena_tier_name_cn",
    "arena_tier_reason",
)

REQUIRED_TOP_LEVEL_FIELDS = (
    "id",
    "ticker",
    "name",
    "market",
    "currency",
    "sector",
    "industry",
    "revenue",
    "ebitda",
    "net_income",
    "cash",
    "debt",
    "shares",
    "share_price",
    "tags",
    "source_meta",
)

REQUIRED_NUMERIC_FIELDS = (
    "revenue",
    "ebitda",
    "net_income",
    "cash",
    "debt",
    "shares",
    "share_price",
)

REQUIRED_TAG_FIELDS = (
    "industry_group",
    "strategic_tags",
    "sensitive_sectors",
    "jurisdiction",
    "market_position",
    "state_linked",
)

REQUIRED_SOURCE_META_FIELDS = (
    "source",
    "source_document_or_provider",
    "fiscal_period_or_as_of_date",
    "as_of_date",
    "notes",
    "confidence",
)


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)


def _flag(code: str, message: str) -> dict[str, str]:
    return {"severity": "error", "code": code, "message": message}


def validate_company_card(card: Any) -> list[dict[str, str]]:
    """Return structured validation flags for one company card."""
    flags: list[dict[str, str]] = []
    if not isinstance(card, dict):
        return [_flag("COMPANY_CARD_INVALID", "Company card must be an object.")]

    for field in REQUIRED_TOP_LEVEL_FIELDS:
        if field not in card:
            flags.append(_flag("COMPANY_CARD_FIELD_REQUIRED", f"{field} is required."))

    for field in REQUIRED_NUMERIC_FIELDS:
        if field in card and not _is_finite_number(card.get(field)):
            flags.append(_flag("COMPANY_CARD_NUMERIC_INVALID", f"{field} must be a finite number."))

    if _is_finite_number(card.get("revenue")) and float(card["revenue"]) <= 0:
        flags.append(_flag("COMPANY_CARD_REVENUE_INVALID", "revenue must be greater than zero."))
    for field in ("shares", "share_price"):
        if _is_finite_number(card.get(field)) and float(card[field]) <= 0:
            flags.append(_flag("COMPANY_CARD_NUMERIC_INVALID", f"{field} must be greater than zero."))

    tags = card.get("tags")
    if not isinstance(tags, dict):
        flags.append(_flag("COMPANY_CARD_TAGS_INVALID", "tags must be an object."))
    else:
        for field in REQUIRED_TAG_FIELDS:
            if field not in tags:
                flags.append(_flag("COMPANY_CARD_TAG_REQUIRED", f"tags.{field} is required."))
        if "strategic_tags" in tags and not isinstance(tags.get("strategic_tags"), list):
            flags.append(_flag("COMPANY_CARD_TAG_INVALID", "tags.strategic_tags must be a list."))
        if "sensitive_sectors" in tags and not isinstance(tags.get("sensitive_sectors"), list):
            flags.append(_flag("COMPANY_CARD_TAG_INVALID", "tags.sensitive_sectors must be a list."))
        if "state_linked" in tags and not isinstance(tags.get("state_linked"), bool):
            flags.append(_flag("COMPANY_CARD_TAG_INVALID", "tags.state_linked must be a boolean."))

    source_meta = card.get("source_meta")
    if not isinstance(source_meta, dict):
        flags.append(_flag("COMPANY_CARD_SOURCE_META_INVALID", "source_meta must be an object."))
    else:
        for field in REQUIRED_SOURCE_META_FIELDS:
            if field not in source_meta:
                flags.append(_flag("COMPANY_CARD_SOURCE_META_REQUIRED", f"source_meta.{field} is required."))

    present_tier_fields = [field for field in ARENA_TIER_FIELDS if field in card]
    if present_tier_fields:
        for field in ARENA_TIER_FIELDS:
            if field not in card:
                flags.append(_flag("COMPANY_CARD_ARENA_TIER_REQUIRED", f"{field} is required when arena tier metadata is present."))
        if card.get("arena_tier") not in ARENA_TIER_VALUES:
            flags.append(_flag(
                "COMPANY_CARD_ARENA_TIER_INVALID",
                "arena_tier must be one of gold, red, blue, green, or white.",
            ))
        for field in ("arena_tier_label", "arena_tier_name_cn", "arena_tier_reason"):
            if field in card and not str(card.get(field) or "").strip():
                flags.append(_flag("COMPANY_CARD_ARENA_TIER_INVALID", f"{field} must be non-empty."))

    return flags


def normalize_company_card(card: dict[str, Any]) -> dict[str, Any]:
    """Return a normalized copy after validation."""
    flags = validate_company_card(card)
    if flags:
        codes = ", ".join(flag["code"] for flag in flags)
        raise ValueError(f"Invalid company card: {codes}")

    normalized = dict(card)
    for field in REQUIRED_NUMERIC_FIELDS:
        normalized[field] = float(normalized[field])
    normalized["tags"] = dict(normalized["tags"])
    normalized["tags"]["strategic_tags"] = list(normalized["tags"]["strategic_tags"])
    normalized["tags"]["sensitive_sectors"] = list(normalized["tags"]["sensitive_sectors"])
    # V5.7.1.1 defensive deep copy: a shallow dict() left nested mappings such as
    # source_meta.field_sources sharing references with the frozen seed object,
    # so mutating one getter result polluted every later read. deepcopy isolates
    # the whole source_meta subtree (a 45-card deep copy is acceptable here).
    normalized["source_meta"] = copy.deepcopy(normalized["source_meta"])
    normalized["schema_version"] = COMPANY_CARD_SCHEMA_VERSION
    return normalized


def card_to_engine_company(card: dict[str, Any]) -> dict[str, Any]:
    """Project a company card into the strict V5.0 A/D engine schema."""
    normalized = normalize_company_card(card)
    return {
        "id": normalized["id"],
        "ticker": normalized["ticker"],
        "name": normalized["name"],
        "market": normalized["market"],
        "currency": normalized["currency"],
        "sector": normalized["sector"],
        "industry": normalized["industry"],
        "revenue": normalized["revenue"],
        "ebitda": normalized["ebitda"],
        "net_income": normalized["net_income"],
        "cash": normalized["cash"],
        "debt": normalized["debt"],
        "shares": normalized["shares"],
        "share_price": normalized["share_price"],
        "tags": dict(normalized["tags"]),
        "source_meta": copy.deepcopy(normalized["source_meta"]),
    }


def public_company_card(card: dict[str, Any]) -> dict[str, Any]:
    """Return the API-facing card shape for selectors and Deal Studio hints."""
    return normalize_company_card(card)
