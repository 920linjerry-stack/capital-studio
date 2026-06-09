"""Compatibility wrappers for the V5.1 company-card seed deck.

The public endpoint remains `/api/modeling/ma/samples` for V5.0 API contract
compatibility, but the data now comes from the unified V5.1 company card loader.
"""

from __future__ import annotations

from typing import Any

from modeling.ma.company_deck import get_sample_company as _get_sample_company
from modeling.ma.company_deck import list_sample_companies as _list_sample_companies

def list_sample_companies() -> list[dict[str, Any]]:
    """Return seed company cards for the existing samples endpoint."""
    return _list_sample_companies()


def get_sample_company(company_id: str) -> dict[str, Any] | None:
    """Return one seed company projected into the A/D engine input shape."""
    return _get_sample_company(company_id)
