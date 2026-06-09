"""Workbook display unit helpers.

Raw historical caches keep actual local currency. The DCF model inputs in this
repo are already in the model base unit, so these helpers are intentionally
used only at export/display boundaries. The legacy data-fetcher helpers below
remain API-compatible because data_fetcher.py and data_fetcher_akshare.py import
them directly.
"""

from __future__ import annotations


UNIT_MULTIPLIERS = {
    "actual": 1e-6,
    "thousands": 1e-3,
    "millions": 1.0,
    "yi": 100.0,
    "billions": 1000.0,
}

MODEL_UNIT_SCALE_FACTORS = {
    "US": 1_000_000.0,
}

MODEL_UNIT_NAMES = {
    "US": "millions",
}


def model_unit_scale_factor(market: str) -> float | None:
    return MODEL_UNIT_SCALE_FACTORS.get((market or "").upper())


def model_unit_name(market: str) -> str:
    return MODEL_UNIT_NAMES.get((market or "").upper(), "local currency")


def model_unit_label(currency: str, market: str) -> str:
    unit = model_unit_name(market)
    if unit == "millions":
        return f"{currency} millions"
    return f"{currency} {unit}".strip()


def normalize_raw_actual_to_model_unit(value, market: str):
    """Convert raw actual local-currency amounts to workbook model unit."""
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric != numeric:
        return None
    scale = model_unit_scale_factor(market)
    if not scale:
        return None
    return numeric / scale


def model_value_for_workbook(value):
    """Return DCF model values unchanged; they are already in model base unit."""
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric != numeric:
        return None
    return numeric


def normalize_to_millions(raw_value, source_unit: str = "actual", currency: str = "USD") -> tuple[float, str]:
    """Normalize source values to millions of local currency.

    This is the legacy data-layer helper used by financial defaults fetchers.
    For example, actual USD 416,161,000,000 becomes 416,161.0 USD millions.
    """
    if raw_value is None:
        return 0.0, currency
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return 0.0, currency
    if value != value or value == float("inf") or value == float("-inf"):
        return 0.0, currency

    multiplier = UNIT_MULTIPLIERS.get(source_unit, 1e-6)
    return round(value * multiplier, 4), currency


def detect_source_unit(value, expected_magnitude_hint: str = "revenue") -> str:
    """Heuristically detect source unit for AKShare-style inputs."""
    if value is None:
        return "actual"
    try:
        magnitude = abs(float(value))
    except (TypeError, ValueError):
        return "actual"

    if magnitude == 0:
        return "actual"

    if expected_magnitude_hint == "shares":
        if magnitude >= 1e9:
            return "actual"
        if magnitude >= 1e6:
            return "actual"
        return "millions"

    if expected_magnitude_hint == "price":
        return "actual"

    if magnitude >= 1e9:
        return "actual"
    if magnitude >= 1e6:
        return "thousands"
    if magnitude >= 1e3:
        return "millions"
    return "yi"


def convert_unit(value_in_millions: float, target_unit: str = "millions") -> float:
    """Convert a value already in millions into a target display unit."""
    if value_in_millions is None:
        return 0.0
    multiplier = UNIT_MULTIPLIERS.get(target_unit, 1.0)
    return round(float(value_in_millions) / multiplier, 4)


def format_unit_label(currency: str, unit: str) -> str:
    labels = {
        "actual": "",
        "thousands": "thousands",
        "millions": "millions",
        "yi": "yi",
        "billions": "billions",
    }
    unit_label = labels.get(unit, "")
    return f"{currency} {unit_label}".strip()
