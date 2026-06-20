# modeling/v6/__init__.py
# V6 Market Intelligence -- a deterministic, non-LLM, portfolio-aware market
# event engine. It represents macro / sentiment / institutional / company
# events as structured records, maps them onto the holdings already tracked by
# the Portfolio Tracker, and explains the likely impact through three channels:
# direct, second-order transmission, and reflexivity / sentiment.
#
# Hard boundaries (enforced by design, see modeling/v6/README.md):
#   * No LLM / model-based text generation anywhere in this package.
#   * No brokerage / trading APIs, no order placement, no trade signals.
#   * No target prices, stop-losses, or buy/sell instructions in any output.
#   * Explanations are template-based and deterministic.
#
# The package is pure Python: no Flask import, no file I/O on the hot path, no
# network. It is safe to import from a Flask route, a test, or a future batch
# precompute job.

from modeling.v6.schemas import (  # noqa: F401
    MarketEvent,
    HoldingExposure,
    EVENT_TYPES,
    DIRECTION_BULLISH,
    DIRECTION_BEARISH,
    DIRECTION_NEUTRAL,
)
