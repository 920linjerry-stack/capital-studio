# modeling/v6/sources -- public, keyless market-event source adapters.
#
# Each adapter fetches structured raw items from a public source (or returns
# bundled sample items when network is disabled / a source is unavailable) and
# is honest about its data_mode (live / live-partial / fixture / unavailable /
# error). Adapters are isolated from the scoring engine: they only produce
# MarketEvents (via the deterministic classifier). No API keys, no paid sources,
# no login/paywall scraping, no LLM.

from modeling.v6.sources.base import RawItem, FetchResult, raw_to_event  # noqa: F401
from modeling.v6.sources.registry import (  # noqa: F401
    SOURCE_REGISTRY,
    get_source_status,
    ingest_events,
)
