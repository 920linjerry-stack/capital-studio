"""V4.7.4 deterministic LBO sensitivity grids.

Pure helper module: no Flask dependency, no file I/O, no provider fetch. Each
cell deep-copies the input payload and reruns ``run_lbo()``; IRR / MOIC are not
calculated here.
"""

from __future__ import annotations

import copy
from typing import Any

from modeling.lbo_calculator import run_lbo


METHOD = "lbo_sensitivity_v474"
OFFSETS = [-1.0, -0.5, 0.0, 0.5, 1.0]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _grid_values(base: float, floor: float | None = None) -> list[float]:
    values = []
    for offset in OFFSETS:
        value = round(base + offset, 4)
        if floor is not None:
            value = max(floor, value)
        values.append(value)
    return values


def _base_assumptions(inputs: dict[str, Any]) -> dict[str, float]:
    transaction = inputs.get("transaction") or {}
    debt = inputs.get("debt") or {}
    entry_ebitda = _num(transaction.get("entry_ebitda"))
    debt_amount = _num(debt.get("debt_amount"), None)
    if debt_amount is None:
        debt_amount = entry_ebitda * _num(debt.get("leverage_multiple"))
    capital_structure = inputs.get("capital_structure") or {}
    if capital_structure.get("mode") == "multi_tranche":
        debt_amount = sum(_num(t.get("opening_balance")) for t in capital_structure.get("tranches") or [])
    return {
        "entry_multiple": _num(transaction.get("entry_multiple")),
        "exit_multiple": _num(transaction.get("exit_multiple"), _num(transaction.get("entry_multiple"))),
        "leverage": (debt_amount / entry_ebitda) if entry_ebitda else 0.0,
    }


def _cell(payload: dict[str, Any], row: float, col: float, base_row: float, base_col: float) -> dict[str, Any]:
    try:
        result = run_lbo(payload)
    except Exception as exc:  # pragma: no cover - defensive boundary
        return {
            "row": row,
            "col": col,
            "irr": None,
            "moic": None,
            "status": "unavailable",
            "error_code": type(exc).__name__.upper(),
            "is_base": row == base_row and col == base_col,
        }
    if result.get("status") != "ok" or not result.get("returns"):
        flags = result.get("flags") or []
        return {
            "row": row,
            "col": col,
            "irr": None,
            "moic": None,
            "status": "unavailable",
            "error_code": (flags[0].get("code") if flags else "LBO_UNAVAILABLE"),
            "is_base": row == base_row and col == base_col,
        }
    returns = result["returns"]
    return {
        "row": row,
        "col": col,
        "irr": returns.get("irr"),
        "moic": returns.get("moic"),
        "status": "ok",
        "is_base": row == base_row and col == base_col,
    }


def build_entry_exit_multiple_grid(inputs: dict[str, Any]) -> dict[str, Any]:
    base = _base_assumptions(inputs)
    rows = _grid_values(base["entry_multiple"], 0.1)
    cols = _grid_values(base["exit_multiple"], 0.1)
    cells = []
    for row in rows:
        line = []
        for col in cols:
            payload = copy.deepcopy(inputs)
            payload.setdefault("transaction", {})["entry_multiple"] = row
            payload.setdefault("transaction", {})["exit_multiple"] = col
            line.append(_cell(payload, row, col, base["entry_multiple"], base["exit_multiple"]))
        cells.append(line)
    return {
        "row_label": "Entry Multiple",
        "col_label": "Exit Multiple",
        "rows": rows,
        "cols": cols,
        "cells": cells,
    }


def _set_leverage(payload: dict[str, Any], leverage: float) -> None:
    transaction = payload.setdefault("transaction", {})
    debt = payload.setdefault("debt", {})
    entry_ebitda = _num(transaction.get("entry_ebitda"))
    target_debt = max(0.0, leverage) * entry_ebitda
    capital_structure = payload.get("capital_structure") or {}
    if capital_structure.get("mode") != "multi_tranche":
        debt["debt_amount"] = target_debt
        debt["leverage_multiple"] = max(0.0, leverage)
        return

    tranches = capital_structure.get("tranches") or []
    current_debt = sum(_num(t.get("opening_balance")) for t in tranches)
    scale = 0.0 if current_debt == 0 else target_debt / current_debt
    for tranche in tranches:
        opening = _num(tranche.get("opening_balance")) * scale
        tranche["opening_balance"] = opening
        if tranche.get("type") != "revolver" or opening > 0:
            tranche["commitment"] = max(_num(tranche.get("commitment")), opening)
    debt["debt_amount"] = target_debt
    debt["leverage_multiple"] = max(0.0, leverage)


def build_leverage_exit_multiple_grid(inputs: dict[str, Any]) -> dict[str, Any]:
    base = _base_assumptions(inputs)
    rows = _grid_values(base["leverage"], 0.0)
    cols = _grid_values(base["exit_multiple"], 0.1)
    cells = []
    for row in rows:
        line = []
        for col in cols:
            payload = copy.deepcopy(inputs)
            payload.setdefault("transaction", {})["exit_multiple"] = col
            _set_leverage(payload, row)
            line.append(_cell(payload, row, col, base["leverage"], base["exit_multiple"]))
        cells.append(line)
    return {
        "row_label": "Debt / EBITDA",
        "col_label": "Exit Multiple",
        "rows": rows,
        "cols": cols,
        "cells": cells,
    }


def build_lbo_sensitivity(inputs: dict[str, Any]) -> dict[str, Any]:
    base = _base_assumptions(inputs)
    flags: list[dict[str, str]] = []
    return {
        "status": "ok",
        "method": METHOD,
        "base": base,
        "grids": {
            "entry_exit": build_entry_exit_multiple_grid(inputs),
            "leverage_exit": build_leverage_exit_multiple_grid(inputs),
        },
        "flags": flags,
    }
