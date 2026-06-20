"""V6 sample market-event fixtures.

These are hand-authored, deterministic sample events used for development, the
demo UI, and tests. They are *mock* data -- clearly flagged as such by the API
(``data_mode: "sample"``). They are NOT scraped from any live source and contain
no private data.

The set deliberately demonstrates every channel the engine supports (see the
V6 spec, section L):

* E1  -- bullish *direct* company event (Apple guidance raise)
* E2  -- bearish *direct* company event (WuXi AppTec regulatory / BIOSECURE)
* E3  -- *macro* event affecting growth/tech holdings (Fed rate cut)
* E4  -- *second-order* transmission event (AI capex / chip demand -> tech & CATL)
* E5  -- *reflexivity / sentiment* event (global risk-off sell-off)
* E6  -- bearish direct event that *conflicts* with E1 on Apple (PT cut)
* E7  -- bullish sentiment/macro for China financials & consumer (stimulus)
* E8  -- long-end yields climb (bullish financials, bearish growth) -- extra conflict

The fixtures set ``event_type`` / ``direction`` / ``magnitude`` / ``affected_tags``
explicitly so matching is fully controlled; running them through the classifier
(``load_fixture_events``) only merges in any additional text-derived tags and is
a no-op on the curated fields.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from modeling.v6.schemas import (
    MarketEvent,
    DIRECTION_BULLISH,
    DIRECTION_BEARISH,
)
from modeling.v6.classifier import classify_event


# Raw curated records. Timestamps are illustrative (a single trading session).
_RAW_EVENTS: list[dict] = [
    {
        "event_id": "v6-e1",
        "title": "Apple raises full-year revenue guidance on services strength",
        "source": "Fixture Filing Source",
        "source_type": "company",
        "timestamp": "2026-06-20T13:30:00Z",
        "event_type": "guidance_raise",
        "direction": DIRECTION_BULLISH,
        "magnitude": 4.0,
        "confidence": 0.8,
        "affected_tags": ["earnings", "guidance"],
        "related_tickers": ["AAPL"],
        "decay_hours": 0.0,
        "summary": "Apple lifted its full-year outlook, citing record services and resilient hardware demand.",
    },
    {
        "event_id": "v6-e2",
        "title": "US lawmakers advance BIOSECURE Act provisions targeting WuXi AppTec",
        "source": "Fixture News",
        "source_type": "official",
        "timestamp": "2026-06-20T11:00:00Z",
        "event_type": "regulatory_risk",
        "direction": DIRECTION_BEARISH,
        "magnitude": 4.0,
        "confidence": 0.7,
        "affected_tags": ["regulatory", "us_regulation"],
        "related_tickers": ["2359.HK"],
        "decay_hours": 0.0,
        "summary": "Renewed legislative momentum on BIOSECURE raises US market-access risk for named CRO providers.",
    },
    {
        "event_id": "v6-e3",
        "title": "Fed cuts rates 25bp and signals a dovish easing path as inflation cools",
        "source": "Fixture Macro Calendar",
        "source_type": "macro",
        "timestamp": "2026-06-20T18:00:00Z",
        "event_type": "rate_cut",
        "direction": DIRECTION_BULLISH,
        "magnitude": 4.0,
        "confidence": 0.75,
        # Bullish for rate-sensitive growth/tech; the engine will read each
        # holding's signed macro_sensitivity to "rates" (banks are negative).
        "affected_tags": ["rates"],
        "related_tickers": [],
        "decay_hours": 0.0,
        "summary": "A 25bp cut with dovish guidance lowers the discount rate for long-duration growth assets.",
    },
    {
        "event_id": "v6-e4",
        "title": "Hyperscaler AI capex guidance surges; chip and data-center demand to stay tight",
        "source": "Fixture Analyst Headline",
        "source_type": "institutional",
        "timestamp": "2026-06-20T09:15:00Z",
        "event_type": "ai_capex_semis",
        "direction": DIRECTION_BULLISH,
        "magnitude": 4.0,
        "confidence": 0.65,
        "affected_tags": ["ai_capex", "semiconductors"],
        "related_tickers": ["NVDA"],
        "decay_hours": 0.0,
        "summary": "Raised AI infrastructure budgets transmit to chip suppliers and battery/data-center build-outs.",
    },
    {
        "event_id": "v6-e5",
        "title": "Global markets hit by risk-off sell-off; VIX spikes on growth fears",
        "source": "Fixture News",
        "source_type": "sentiment",
        "timestamp": "2026-06-20T14:45:00Z",
        "event_type": "risk_off",
        "direction": DIRECTION_BEARISH,
        "magnitude": 3.0,
        "confidence": 0.55,
        "affected_tags": ["risk_sentiment"],
        "related_tickers": [],
        "decay_hours": 0.0,
        "summary": "A broad de-risking move pressures high-beta and high-reflexivity names first.",
    },
    {
        "event_id": "v6-e6",
        "title": "Morgan Stanley cuts Apple price target on softer iPhone unit demand",
        "source": "Fixture Analyst Headline",
        "source_type": "institutional",
        "timestamp": "2026-06-20T10:05:00Z",
        "event_type": "price_target_cut",
        "direction": DIRECTION_BEARISH,
        "magnitude": 2.5,
        "confidence": 0.6,
        "affected_tags": ["analyst_action"],
        "related_tickers": ["AAPL"],
        "decay_hours": 0.0,
        "summary": "A target reduction citing unit-demand softness partially offsets the company's raised guidance.",
    },
    {
        "event_id": "v6-e7",
        "title": "China unveils stimulus package to boost domestic demand; risk appetite rebounds",
        "source": "Fixture News",
        "source_type": "macro",
        "timestamp": "2026-06-20T02:30:00Z",
        "event_type": "risk_on",
        "direction": DIRECTION_BULLISH,
        "magnitude": 3.5,
        "confidence": 0.6,
        "affected_tags": ["china_demand", "risk_sentiment"],
        "related_tickers": [],
        "decay_hours": 0.0,
        "summary": "Fiscal support lifts domestic-demand names and broker turnover; partially offsets global risk-off.",
    },
    {
        "event_id": "v6-e8",
        "title": "Long-end Treasury yields climb after hotter-than-expected term premium repricing",
        "source": "Fixture News",
        "source_type": "macro",
        "timestamp": "2026-06-20T15:20:00Z",
        "event_type": "yields_up",
        "direction": DIRECTION_BEARISH,
        "magnitude": 3.0,
        "confidence": 0.55,
        # Signed sensitivity: bearish for growth (negative), but financials hold
        # POSITIVE yield sensitivity, so the engine flips this to bullish for them.
        "affected_tags": ["yields"],
        "related_tickers": [],
        "decay_hours": 0.0,
        "summary": "Higher long-end yields pressure long-duration growth but aid bank/insurer reinvestment.",
    },
]


# How many hours ago each recent event occurred, so its time-decay is visible
# but it still carries weight. Keyed by event_id; default 6h.
_RECENT_AGE_HOURS: dict[str, float] = {
    "v6-e1": 5, "v6-e2": 9, "v6-e3": 2, "v6-e4": 14,
    "v6-e5": 4, "v6-e6": 11, "v6-e7": 20, "v6-e8": 6,
}

# Scheduled FUTURE catalysts. ``days_ahead`` is converted to scheduled_at at
# load time relative to ``now`` so the countdown is always live in the demo.
# direction is the *expected* impact direction; it is pre-priced via the
# anticipation/priced-in fields and only fully realizes after the date.
_RAW_FUTURE: list[dict] = [
    {
        "event_id": "v6-f1", "days_ahead": 2.5,
        "title": "CPI inflation report scheduled (consensus: cooling)",
        "source": "Fixture Macro Calendar", "source_type": "macro", "event_type": "cpi_release",
        "direction": DIRECTION_BULLISH, "magnitude": 4.0, "confidence": 0.6,
        "affected_tags": ["inflation", "yields", "rates"],
        "anticipation_score": 0.55, "priced_in_score": 0.5, "surprise_sensitivity": 0.8,
        "sell_the_news_risk": 0.25,
        "summary": "A cooler CPI print would support rate-sensitive growth; a hot surprise would hurt it.",
    },
    {
        "event_id": "v6-f2", "days_ahead": 6,
        "title": "FOMC rate decision scheduled",
        "source": "Fixture Macro Calendar", "source_type": "macro", "event_type": "fomc_decision",
        "direction": DIRECTION_BULLISH, "magnitude": 4.5, "confidence": 0.55,
        "affected_tags": ["rates", "yields"],
        "anticipation_score": 0.45, "priced_in_score": 0.45, "surprise_sensitivity": 0.85,
        "sell_the_news_risk": 0.2,
        "summary": "Market leans toward a dovish hold/cut; the decision mainly realizes on announcement.",
    },
    {
        "event_id": "v6-f3", "days_ahead": 11,
        "title": "Apple quarterly earnings date scheduled",
        "source": "Fixture Event Calendar", "source_type": "company", "event_type": "earnings_date",
        "direction": DIRECTION_BULLISH, "magnitude": 4.0, "confidence": 0.6,
        "affected_tags": ["earnings", "guidance"], "related_tickers": ["AAPL"],
        "anticipation_score": 0.6, "priced_in_score": 0.7, "surprise_sensitivity": 0.85,
        "sell_the_news_risk": 0.45,
        "summary": "Expectations are elevated into the print, raising sell-the-news / 利好出尽 risk if results merely meet.",
    },
    {
        "event_id": "v6-f4", "days_ahead": 18,
        "title": "NVIDIA GTC product event scheduled (AI accelerators)",
        "source": "Fixture Event Calendar", "source_type": "company", "event_type": "product_launch",
        "direction": DIRECTION_BULLISH, "magnitude": 4.0, "confidence": 0.6,
        "affected_tags": ["ai_capex", "semiconductors"], "related_tickers": ["NVDA"],
        "anticipation_score": 0.7, "priced_in_score": 0.6, "surprise_sensitivity": 0.6,
        "sell_the_news_risk": 0.5,
        "summary": "AI accelerator roadmap event; benefits transmit to the AI-capex / semis complex pre-event.",
    },
]


def _iso(dt) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_fixture_events(now=None) -> list[MarketEvent]:
    """Return the curated sample events as classified :class:`MarketEvent`s.

    Recent events get a ``timestamp`` a few hours before ``now`` (so decay is
    visible); future catalysts get a ``scheduled_at`` a few days after ``now``
    (so the countdown is live). Each is passed through :func:`classify_event`
    to merge text-derived tags; curated fields are preserved. ``now`` defaults
    to current UTC; pass a fixed value for deterministic tests.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    events: list[MarketEvent] = []
    for raw in _RAW_EVENTS:
        raw = dict(raw)
        age_h = _RECENT_AGE_HOURS.get(raw["event_id"], 6)
        ts = _iso(now - timedelta(hours=age_h))
        raw["timestamp"] = ts
        raw["effective_at"] = ts
        raw.setdefault("data_mode", "fixture")
        ev = MarketEvent.from_dict(raw)
        classify_event(ev)  # merges extra tags only; curated fields kept
        events.append(ev)

    for raw in _RAW_FUTURE:
        raw = dict(raw)
        days = raw.pop("days_ahead", 7)
        sched = _iso(now + timedelta(days=days))
        raw["scheduled_at"] = sched
        raw["effective_at"] = sched
        raw["timestamp"] = sched
        raw.setdefault("data_mode", "fixture")
        ev = MarketEvent.from_dict(raw)
        classify_event(ev)
        events.append(ev)

    return events
