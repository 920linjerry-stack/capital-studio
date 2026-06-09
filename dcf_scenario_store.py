# dcf_scenario_store.py
# v3.4.5: scenario DCF persistence. Bull / Bear only. Base never persisted here.
#
# Hard boundaries:
#   - Do not import dcf_calculator / thesis_store / yfinance
#   - Whole-file overwrite, no merge
#   - Local single-user storage, no concurrency lock
#
# File structure (data/dcf_scenarios/{filename_key}_scenarios.json):
#   {
#     "symbol": "AAPL",
#     "schema_version": "scenario_v1",
#     "scenarios": {
#       "bull": { params, valuation, saved_at, updated_at, origin } | null,
#       "bear": { ... } | null
#     }
#   }

import json
from datetime import datetime, timezone
from pathlib import Path

from thesis_utils import canonical_ticker, filename_key


_PROJECT_ROOT = Path(__file__).parent.resolve()
_SCENARIO_DIR = _PROJECT_ROOT / "data" / "dcf_scenarios"

SCENARIO_SCHEMA_VERSION = "scenario_v1"
SCENARIO_TYPES = {"bull", "bear"}


def _scenario_path(ticker: str) -> Path:
    key = filename_key(ticker)
    return _SCENARIO_DIR / f"{key}_scenarios.json"


def _empty_doc(symbol: str) -> dict:
    return {
        "symbol": canonical_ticker(symbol),
        "schema_version": SCENARIO_SCHEMA_VERSION,
        "scenarios": {"bull": None, "bear": None},
    }


def read_scenarios(symbol: str) -> dict:
    """
    Return the full scenario document. Missing files return an empty document
    without writing to disk.
    """
    path = _scenario_path(symbol)
    if not path.exists():
        return _empty_doc(symbol)

    with open(path, "r", encoding="utf-8") as f:
        doc = json.load(f)

    doc.setdefault("symbol", canonical_ticker(symbol))
    doc.setdefault("schema_version", SCENARIO_SCHEMA_VERSION)
    doc.setdefault("scenarios", {})
    doc["scenarios"].setdefault("bull", None)
    doc["scenarios"].setdefault("bear", None)
    return doc


def write_scenario(symbol: str, scenario_type: str, entry: dict) -> dict:
    """
    Overwrite one Bull/Bear scenario and write the whole document back.
    entry must contain params / valuation / origin.
    """
    if scenario_type not in SCENARIO_TYPES:
        raise ValueError(f"invalid scenario_type: {scenario_type}")

    doc = read_scenarios(symbol)

    now = datetime.now(timezone.utc).isoformat()
    existing = doc["scenarios"].get(scenario_type)
    saved_at = entry.get("saved_at") or (existing["saved_at"] if existing else now)

    doc["scenarios"][scenario_type] = {
        "params": entry["params"],
        "valuation": entry["valuation"],
        "origin": entry.get("origin", {}),
        "saved_at": saved_at,
        "updated_at": now,
    }

    _SCENARIO_DIR.mkdir(parents=True, exist_ok=True)
    path = _scenario_path(symbol)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    return doc


def delete_scenario(symbol: str, scenario_type: str) -> dict:
    """
    Set the requested scenario entry to null while preserving the document shape.
    Missing files and already-null entries are treated as successful no-ops.
    """
    if scenario_type not in SCENARIO_TYPES:
        raise ValueError(f"invalid scenario_type: {scenario_type}")

    doc = read_scenarios(symbol)
    doc["scenarios"][scenario_type] = None

    _SCENARIO_DIR.mkdir(parents=True, exist_ok=True)
    path = _scenario_path(symbol)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    return doc
