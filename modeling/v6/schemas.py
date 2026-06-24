"""V6 structured schemas: market events and holding exposure profiles.

These are plain ``dataclass`` records with light validation and ``from_dict`` /
``to_dict`` helpers. They are the contract shared by the classifier, the
exposure layer, the impact engine, the templates, and the API glue. No external
dependencies, no I/O.

Two record types:

* :class:`MarketEvent`  -- one structured market event (macro, sentiment,
  institutional headline, official announcement, or company event).
* :class:`HoldingExposure` -- the exposure fingerprint of one portfolio holding
  (tags, sector, macro sensitivities, second-order links, reflexivity score).

Both are deterministic: equal inputs always produce equal records.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

# --- direction vocabulary -------------------------------------------------
# Event-level direction is a sign: +1 bullish, -1 bearish, 0 neutral. The
# holding/portfolio *status* vocabulary (bullish/bearish/neutral/mixed/
# uncertain) lives in the impact engine -- it is derived, not a raw field.
DIRECTION_BULLISH = 1
DIRECTION_BEARISH = -1
DIRECTION_NEUTRAL = 0

_VALID_DIRECTIONS = (DIRECTION_BULLISH, DIRECTION_BEARISH, DIRECTION_NEUTRAL)

# --- source-type vocabulary ----------------------------------------------
SOURCE_TYPES = (
    "macro",          # macro data prints, central-bank actions
    "sentiment",      # risk-on / risk-off, positioning, flows
    "institutional",  # sell-side / analyst headlines
    "official",       # regulator / government / exchange announcements
    "company",        # company-specific news (earnings, guidance, filings)
)

# --- event-type vocabulary (what the classifier can emit) ----------------
# Each maps to a default (direction, magnitude 1..5) in the classifier. Kept
# here so schema, classifier and tests share one source of truth.
EVENT_TYPES = (
    "analyst_upgrade",
    "analyst_downgrade",
    "price_target_raise",
    "price_target_cut",
    "earnings_beat",
    "earnings_miss",
    "guidance_raise",
    "guidance_cut",
    "macro_inflation_hot",
    "macro_inflation_cool",
    "rate_cut",
    "rate_hike",
    "yields_up",
    "yields_down",
    "regulatory_risk",
    "lawsuit_investigation",
    "ai_capex_semis",
    "risk_on",
    "risk_off",
    # --- structural state vocabulary (recognition separated from direction)
    "margin_warning",
    "revenue_acceleration",
    "revenue_slowdown",
    "estimate_raise",
    "estimate_cut",
    "fda_approval",
    "fda_rejection",
    "trial_success",
    "trial_failure",
    "regulatory_approval",
    "regulatory_rejection",
    "regulatory_tightening",
    "antitrust_probe",
    "lawsuit",
    "investigation",
    "enforcement_action",
    "product_recall",
    "outage",
    "cybersecurity_breach",
    "export_controls",
    "sanctions",
    "tariffs",
    "fomc_hawkish",
    "fomc_dovish",
    "cpi_hot",
    "cpi_cool",
    "jobs_hot",
    "jobs_weak",
    "dollar_up",
    "dollar_down",
    "oil_up",
    "oil_down",
    "credit_stress",
    "bank_stress",
    "sell_the_news",
    "headline_positive_but_priced_in",
    "headline_negative_but_priced_in",
    "ambiguous_surprise",
    # --- scheduled / future catalysts (no realized direction yet) ---------
    "fomc_decision",
    "cpi_release",
    "jobs_report",
    "earnings_date",
    "product_launch",
    "policy_announcement",
    "uncategorized",
)

# Scheduled-catalyst event types: known in advance, direction unrealized until
# the release. Used by the timing module to drive anticipation / priced-in /
# sell-the-news logic.
SCHEDULED_EVENT_TYPES = (
    "fomc_decision",
    "cpi_release",
    "jobs_report",
    "earnings_date",
    "product_launch",
    "policy_announcement",
)

# data_mode vocabulary, surfaced honestly to the UI per source.
DATA_MODES = ("live", "live-partial", "fixture", "unavailable", "error")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class MarketEvent:
    """A single structured market event.

    Fields mirror the V6 spec. ``direction`` / ``magnitude`` / ``confidence``
    can be supplied directly (fixtures) or filled in by the classifier from the
    title; see :mod:`modeling.v6.classifier`.
    """

    event_id: str
    title: str
    source: str = ""                       # e.g. "Reuters", "FOMC", "GS Research"
    source_type: str = "company"           # one of SOURCE_TYPES
    timestamp: str = ""                     # ISO-8601 string; not parsed here
    event_type: str = "uncategorized"      # one of EVENT_TYPES
    direction: int = DIRECTION_NEUTRAL      # +1 / -1 / 0 (expected impact dir)
    magnitude: float = 1.0                  # 1..5 strength of the event itself
    confidence: float = 0.5                 # 0..1 how reliable the read is
    affected_tags: list[str] = field(default_factory=list)   # exposure tags hit
    related_tickers: list[str] = field(default_factory=list)  # direct tickers
    decay_hours: float = 0.0                # 0 == no decay applied (fixtures)
    summary: str = ""                       # short human note / raw headline body

    # --- future / scheduled-catalyst fields (all optional) ----------------
    scheduled_at: str = ""                  # ISO-8601 when the event is scheduled
    effective_at: str = ""                  # ISO-8601 when impact begins/realizes
    anticipation_score: float = 0.0         # 0..1 how much the market pre-prices
    priced_in_score: float = 0.0            # 0..1 how much is already in price
    surprise_sensitivity: float = 0.5       # 0..1 sensitivity to a surprise vs cons.
    post_event_decay_hours: float = 0.0     # half-life after the event realizes
    sell_the_news_risk: float = 0.0         # 0..1 "good news exhausted" / 利好出尽
    phase_override: str = ""                # optional forced event_phase

    # --- Pillar 5: structured surprise audit -----------------------------
    # ``actual`` / ``expected`` / ``surprise_std`` require a traceable
    # structured source. ``proxy_surprise`` is separate and is never presented
    # as true consensus surprise.
    actual: float | None = None
    expected: float | None = None
    surprise_std: float | None = None
    surprise_unit: str = ""
    surprise_source: str = ""
    surprise_label: str = ""
    higher_is_bullish: bool | None = None
    proxy_surprise: float | None = None
    proxy_surprise_source: str = ""

    # --- provenance / dedupe ---------------------------------------------
    data_mode: str = "fixture"              # one of DATA_MODES
    source_count: int = 1                   # how many feeds carried this event
    source_list: list[str] = field(default_factory=list)

    # --- deterministic classification audit -----------------------------
    # Recognition answers "what happened?" independently from direction.
    recognized_states: list[str] = field(default_factory=list)
    classification_flags: list[str] = field(default_factory=list)
    classification_confidence: float = 1.0

    def __post_init__(self) -> None:
        if self.direction not in _VALID_DIRECTIONS:
            self.direction = DIRECTION_NEUTRAL
        self.magnitude = _clamp(float(self.magnitude), 0.0, 5.0)
        self.confidence = _clamp(float(self.confidence), 0.0, 1.0)
        self.decay_hours = max(0.0, float(self.decay_hours))
        self.affected_tags = [t.lower() for t in _as_str_list(self.affected_tags)]
        self.related_tickers = [t.upper() for t in _as_str_list(self.related_tickers)]
        if self.source_type not in SOURCE_TYPES:
            self.source_type = "company"
        if self.event_type not in EVENT_TYPES:
            self.event_type = "uncategorized"
        # future-field normalization
        self.anticipation_score = _clamp(float(self.anticipation_score), 0.0, 1.0)
        self.priced_in_score = _clamp(float(self.priced_in_score), 0.0, 1.0)
        self.surprise_sensitivity = _clamp(float(self.surprise_sensitivity), 0.0, 1.0)
        self.sell_the_news_risk = _clamp(float(self.sell_the_news_risk), 0.0, 1.0)
        self.post_event_decay_hours = max(0.0, float(self.post_event_decay_hours))
        self.actual = _optional_float(self.actual)
        self.expected = _optional_float(self.expected)
        self.surprise_std = _optional_float(self.surprise_std)
        if self.surprise_std is not None and self.surprise_std <= 0:
            self.surprise_std = None
        self.proxy_surprise = _optional_float(self.proxy_surprise)
        self.source_count = max(1, int(self.source_count))
        self.source_list = _as_str_list(self.source_list) or ([self.source] if self.source else [])
        self.recognized_states = [
            str(s).lower() for s in _as_str_list(self.recognized_states)
        ]
        self.classification_flags = [
            str(s).lower() for s in _as_str_list(self.classification_flags)
        ]
        self.classification_confidence = _clamp(
            float(self.classification_confidence), 0.0, 1.0
        )
        if self.data_mode not in DATA_MODES:
            self.data_mode = "fixture"

    @property
    def is_scheduled(self) -> bool:
        """True when this is a known-in-advance catalyst (has a scheduled date)."""
        return bool(self.scheduled_at) or self.event_type in SCHEDULED_EVENT_TYPES

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MarketEvent":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HoldingExposure:
    """The exposure fingerprint of one holding.

    This is *not* portfolio position data (no cost, quantity, P&L). It is the
    reusable, non-private description of what the holding is sensitive to, used
    to match events. Position weight is supplied separately by the adapter so
    the same fingerprint works for any user's portfolio.
    """

    ticker: str
    name: str = ""
    aliases: list[str] = field(default_factory=list)
    sector: str = ""
    asset_type: str = "equity"             # equity / etf / adr / ...
    factor_tags: list[str] = field(default_factory=list)        # thematic exposure
    # macro_sensitivity: tag -> signed beta (-1..+1). Legacy broad tags are
    # measured against the EVENT's broad direction. Explicit factor-state tags
    # such as oil_up, real_yields_up, dollar_up, and credit_stress instead use
    # the sign directly as an asset-specific response to that stated move.
    # See modeling/v6/README.md.
    macro_sensitivity: dict[str, float] = field(default_factory=dict)
    # second_order_exposure: tags reaching this holding via a transmission chain
    # (supplier/customer/sector-beta), not direct company news.
    second_order_exposure: list[str] = field(default_factory=list)
    # reflexivity_exposure: 0..1 how strongly sentiment / positioning feedback
    # loops move this holding independent of fundamentals.
    reflexivity_exposure: float = 0.0

    def __post_init__(self) -> None:
        self.ticker = str(self.ticker).upper()
        self.aliases = [a for a in _as_str_list(self.aliases)]
        self.factor_tags = [t.lower() for t in _as_str_list(self.factor_tags)]
        self.second_order_exposure = [t.lower() for t in _as_str_list(self.second_order_exposure)]
        self.reflexivity_exposure = _clamp(float(self.reflexivity_exposure), 0.0, 1.0)
        self.macro_sensitivity = {
            str(k).lower(): _clamp(float(v), -1.0, 1.0)
            for k, v in (self.macro_sensitivity or {}).items()
        }

    @property
    def all_match_terms(self) -> list[str]:
        """Lower-cased terms usable for direct ticker/alias matching."""
        terms = [self.ticker.lower()]
        terms.extend(a.lower() for a in self.aliases)
        if self.name:
            terms.append(self.name.lower())
        return terms

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HoldingExposure":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
