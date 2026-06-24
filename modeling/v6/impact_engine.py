"""V6 deterministic portfolio impact engine.

Pure functions that take a set of :class:`MarketEvent`s and a normalized
portfolio (from :mod:`modeling.v6.exposure`) and produce:

* per-event/per-holding *contributions*, each tagged with a transmission
  channel (direct / second-order / reflexivity), an effective direction, a
  relevance, and a signed impact;
* per-holding aggregation (net impact, status, key drivers, conclusion);
* portfolio-level aggregation (net score, status, top contributors, drivers).

Scoring formula (transparent, documented in modeling/v6/README.md)::

    impact = position_weight * effective_direction * magnitude
             * relevance * confidence * decay_factor

``effective_direction`` is +1/-1/0. For macro-sensitivity channels it is the
sign of ``event.direction * holding_sensitivity`` (a bullish-for-growth rate
cut flips bearish for a bank with negative rate sensitivity). ``magnitude`` is
the raw 1..5 event magnitude. ``decay_factor`` is 1.0 for fixtures
(``decay_hours == 0``); a half-life hook is provided for future live data.

No LLM, no network, no I/O. Deterministic and order-stable.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from modeling.v6.schemas import (
    MarketEvent,
    HoldingExposure,
    DIRECTION_BULLISH,
    DIRECTION_BEARISH,
    DIRECTION_NEUTRAL,
)
from modeling.v6 import templates
from modeling.v6 import timing
from modeling.v6 import calibration
from modeling.v6 import contagion
from modeling.v6 import crowding
from modeling.v6 import surprise
from modeling.v6.classifier import state_direction

# Tag reserved for the reflexivity channel; it is NOT counted as second-order
# even if it appears in a holding's second_order_exposure list.
_REFLEXIVITY_TAG = "risk_sentiment"

# Relevance weights per channel (how strongly a match transmits). Direct
# company news is strongest; transmission chains are damped.
_REL_COMPANY_DIRECT = 1.0
_REL_FACTOR_DIRECT = 0.8
_REL_SECOND_ORDER = 0.5
# Broad macro prints are damped vs. company-specific news so a single CPI/Fed
# headline does not swamp direct earnings/guidance events on a holding.
_REL_MACRO_SCALE = 0.75
_REL_CONFLICT_DIRECT = 0.70
_REL_SECTOR_TRANSMISSION = 0.35
_REL_PEER_TRANSMISSION = 0.35
_REL_MACRO_EVENT_CAP = 1.0

# These tags describe the direction of the underlying factor itself, rather
# than the broad market reaction to an event.  Their sensitivity is therefore
# an asset-specific signed exposure: +1 benefits from the stated factor move,
# -1 is hurt by it.  Keeping this vocabulary explicit prevents a bearish broad
# event direction (for example an oil-driven inflation shock) from being
# mechanically imposed on assets that are beneficiaries of that same shock.
_SIGNED_FACTOR_STATES = frozenset({
    "oil_up",
    "commodity_inflation",
    "inflation_fear",
    "risk_off",
    "real_yields_up",
    "dollar_up",
    "credit_stress",
    "yield_curve_steepening",
    "rates_up",
    "rates_down",
    "yields_up",
    "yields_down",
    "dollar_down",
    "oil_down",
    "real_yields_down",
    "recession_risk",
    "recession_demand",
    "cyclical_strength",
    "bank_stress",
    "financial_conditions_tightening",
    "inflation_fear_down",
})

# Conservative ETF-only propagation. Company/official events reach a sector
# fund only through an explicit sector term, at lower relevance than issuer
# news. Macro factor tags are normally consumed by signed sensitivities first.
_SECTOR_ETF_TRANSMISSION: dict[str, frozenset[str]] = {
    "QQQ": frozenset({"megacap_tech", "technology_sector", "ai_capex"}),
    "TQQQ": frozenset({"megacap_tech", "technology_sector", "ai_capex"}),
    "XLK": frozenset({"technology_sector", "software_sector", "semiconductors", "ai_capex"}),
    "XLE": frozenset({"energy_sector", "oil_up", "oil_down"}),
    "USO": frozenset({"energy_sector", "oil_up", "oil_down"}),
    "XLF": frozenset({"financials_sector", "credit_stress", "bank_stress", "yield_curve_steepening"}),
    "XLV": frozenset({"healthcare_sector", "drug_approval", "drug_rejection", "healthcare_policy"}),
}

# Correlated tags are alternative descriptions of one underlying factor move,
# not independent evidence.  The matcher selects one representative per family
# for each event/holding/channel, preferring explicit signed states over legacy
# generic tags.  Cross-family conflicts (inflation fear vs. real yields, rate
# benefit vs. credit stress) remain visible because they are genuinely distinct
# transmission mechanisms.
_MACRO_FACTOR_FAMILIES: tuple[tuple[str, ...], ...] = (
    (
        "real_yields_up", "real_yields_down",
        "rates_up", "rates_down", "yields_up", "yields_down",
        "rates", "yields",
    ),
    ("inflation_fear", "inflation_fear_down", "inflation"),
    ("oil_up", "oil_down", "commodity_inflation"),
    ("bank_stress", "credit_stress", "financial_conditions_tightening"),
    ("risk_on", "risk_off"),
    ("dollar_up", "dollar_down"),
    ("recession_demand", "recession_risk"),
)

_EXPLICIT_CONFLICT_FLAGS = frozenset({
    "ambiguous_surprise", "conflicting_phrases", "headline_reaction_conflict",
})

# Aggregation thresholds.
_EPS = 1e-9
_MIXED_MIN_SHARE = 0.30      # both sides >= 30% of gross -> "mixed"
_UNCERTAIN_CONF = 0.40       # avg contributing confidence below this -> "uncertain"


def _sign(x: float) -> int:
    if x > _EPS:
        return DIRECTION_BULLISH
    if x < -_EPS:
        return DIRECTION_BEARISH
    return DIRECTION_NEUTRAL


def _decay_factor(event: MarketEvent, elapsed_hours: float | None = None) -> float:
    """Half-life decay. 1.0 when no decay configured (fixtures)."""
    if event.decay_hours <= 0 or elapsed_hours is None or elapsed_hours <= 0:
        return 1.0
    return 0.5 ** (elapsed_hours / event.decay_hours)


def _explicitly_mixed(event: MarketEvent) -> bool:
    return (
        event.direction == DIRECTION_NEUTRAL
        and bool(set(event.classification_flags) & _EXPLICIT_CONFLICT_FLAGS)
    )


def _normalized_event_tags(event: MarketEvent) -> set[str]:
    """Normalize mutually exclusive event states before exposure matching."""
    tags = set(event.affected_tags)
    if not _explicitly_mixed(event):
        states = set(event.recognized_states)
        if event.event_type == "risk_on":
            tags.discard("risk_off")
            tags.add("risk_on")
        elif event.event_type == "risk_off":
            tags.discard("risk_on")
            tags.add("risk_off")
        elif {"risk_on", "risk_off"} <= tags and "risk_on" in states and event.direction > 0:
            tags.discard("risk_off")
        elif {"risk_on", "risk_off"} <= tags and "risk_off" in states and event.direction < 0:
            tags.discard("risk_on")
    return tags


def _normalize_macro_hits(
    event: MarketEvent,
    hits: set[str],
    exposure: HoldingExposure,
) -> tuple[list[str], set[str]]:
    """Return one exposure tag per correlated macro family.

    The second return value contains every family candidate that was consumed,
    including discarded generic aliases, so those aliases cannot reappear in a
    thematic or second-order channel.
    """
    remaining = set(hits)
    selected: list[str] = []
    consumed: set[str] = set()
    recognized = set(event.recognized_states)

    for family in _MACRO_FACTOR_FAMILIES:
        candidates = remaining & set(family)
        if not candidates:
            continue
        consumed.update(candidates)
        remaining.difference_update(candidates)

        # Explicitly mixed risk-regime text is the sole case where both sides
        # may survive. Most profiles only expose risk_off, but the contract is
        # deterministic for profiles that define both sensitivities.
        if set(family) == {"risk_on", "risk_off"} and _explicitly_mixed(event):
            selected.extend(tag for tag in family if tag in candidates)
            continue

        exact = [
            tag for tag in family
            if tag in candidates and (tag == event.event_type or tag in recognized)
        ]
        pool = exact or [tag for tag in family if tag in candidates]
        chosen = max(
            pool,
            key=lambda tag: (
                abs(exposure.macro_sensitivity.get(tag, 0.0)),
                -family.index(tag),
            ),
        )
        selected.append(chosen)

    selected.extend(sorted(remaining))
    consumed.update(remaining)
    return selected, consumed


def match_event_to_holding(
    event: MarketEvent,
    exposure: HoldingExposure,
) -> list[dict[str, Any]]:
    """Return the channel contributions of one event on one holding.

    Each contribution dict carries: channel, effective_direction, relevance,
    matched_terms. A single event can hit a holding through up to three
    channels, but any given matched tag is attributed to exactly one channel
    (direct > second-order) so impact is never double-counted.
    """
    contributions: list[dict[str, Any]] = []
    event_tags = _normalized_event_tags(event)
    consumed: set[str] = set()  # tags already attributed to a channel

    # --- DIRECT: company-specific (ticker / alias / name) ----------------
    match_kind = None
    matched_term = exposure.ticker
    # For macro events, related_tickers describe the affected universe rather
    # than company-specific news. Their direction must come from the holding's
    # factor exposures below, not from an unconditional ticker hit.
    if event.source_type != "macro" and exposure.ticker in event.related_tickers:
        match_kind = "ticker"
    else:
        title_low = f"{event.title} {event.summary}".lower()
        for term in exposure.all_match_terms if event.source_type != "macro" else ():
            # alias/name match requires a non-trivial term to avoid noise
            if len(term) >= 4 and term in title_low:
                match_kind = "ticker" if term == exposure.ticker.lower() else "alias"
                matched_term = term
                break
    if match_kind:
        state_dirs = {
            state_direction(state) for state in event.recognized_states
            if state_direction(state) != DIRECTION_NEUTRAL
        }
        if len(state_dirs) > 1:
            # Preserve conflicting headline evidence instead of letting the
            # first phrase win (beat + weak outlook / priced-in / shares fall).
            for direction in sorted(state_dirs):
                contributions.append({
                    "channel": "direct",
                    "match_kind": match_kind,
                    "effective_direction": direction,
                    "relevance": _REL_CONFLICT_DIRECT,
                    "matched_terms": [matched_term],
                })
        else:
            contributions.append({
                "channel": "direct",
                "match_kind": match_kind,
                "effective_direction": event.direction,
                "relevance": _REL_COMPANY_DIRECT,
                "matched_terms": [matched_term],
            })

    # --- DIRECT: macro sensitivity (signed own-factor reaction) ----------
    # Macro relevance is damped so a broad macro print does not overwhelm a
    # direct, company-specific event unless its own magnitude is high.
    macro_hit_set = (event_tags & set(exposure.macro_sensitivity)) - consumed
    macro_hits, macro_consumed = _normalize_macro_hits(event, macro_hit_set, exposure)
    consumed.update(macro_consumed)
    macro_contributions: list[dict[str, Any]] = []
    for tag in macro_hits:
        sens = exposure.macro_sensitivity[tag]
        # Factor-state tags already carry the shock direction in their name;
        # legacy macro tags retain the broad-direction convention for backward
        # compatibility (e.g. a rate cut helps growth but can squeeze banks).
        raw_effect = sens if tag in _SIGNED_FACTOR_STATES else event.direction * sens
        eff = _sign(raw_effect)
        matched_terms = [tag]
        if tag in {"bank_stress", "credit_stress", "financial_conditions_tightening"}:
            # Preserve the recognized credit-condition aliases for explanation
            # while scoring the family only once through its most specific tag.
            matched_terms = sorted(
                macro_hit_set
                & {"bank_stress", "credit_stress", "financial_conditions_tightening"}
            )
        macro_contributions.append({
            "channel": "direct",
            "match_kind": "macro_factor",
            "effective_direction": eff,
            "relevance": round(min(1.0, abs(sens)) * _REL_MACRO_SCALE, 4),
            "matched_terms": matched_terms,
        })

    macro_relevance = sum(row["relevance"] for row in macro_contributions)
    if macro_relevance > _REL_MACRO_EVENT_CAP:
        scale = _REL_MACRO_EVENT_CAP / macro_relevance
        for row in macro_contributions:
            row["relevance"] = round(row["relevance"] * scale, 4)
    contributions.extend(macro_contributions)

    # --- DIRECT: thematic factor overlap (unsigned, uses event direction) -
    # Once a macro event has an explicit signed exposure, unsigned thematic
    # overlap must not re-apply the event's one-size-fits-all broad direction.
    factor_hits = [] if match_kind or (event.source_type == "macro" and macro_hits) else sorted(
        (event_tags & set(exposure.factor_tags)) - consumed
    )
    peer_factor_hits: list[str] = []
    if factor_hits and event.source_type in {"company", "institutional"}:
        peer_factor_hits = factor_hits
        factor_hits = []
    if factor_hits:
        consumed.update(factor_hits)
        contributions.append({
            "channel": "direct",
            "match_kind": "factor_tag",
            "effective_direction": event.direction,
            "relevance": _REL_FACTOR_DIRECT,
            "matched_terms": factor_hits,
        })

    # --- SECOND-ORDER: transmission chain (excludes reflexivity tag) ------
    so_candidates = set(exposure.second_order_exposure) - {_REFLEXIVITY_TAG}
    so_hits = sorted((event_tags & so_candidates) - consumed)
    if match_kind and event.source_type in {"company", "institutional"}:
        so_hits = []

    # --- CONSERVATIVE SECTOR / ETF TRANSMISSION -------------------------
    sector_terms = _SECTOR_ETF_TRANSMISSION.get(exposure.ticker, frozenset())
    sector_hits = sorted((event_tags & sector_terms) - consumed)
    if exposure.ticker in event.related_tickers:
        sector_hits = []

    transmission_hits = sorted(set(peer_factor_hits) | set(so_hits) | set(sector_hits))
    if transmission_hits:
        consumed.update(transmission_hits)
        is_sector_etf = bool(sector_terms)
        if is_sector_etf:
            match_kind_transmission = "sector_transmission"
            relevance = _REL_SECTOR_TRANSMISSION
        elif peer_factor_hits and not so_hits:
            match_kind_transmission = "peer_transmission"
            relevance = _REL_PEER_TRANSMISSION
        else:
            match_kind_transmission = "second_order"
            relevance = _REL_SECOND_ORDER
        contributions.append({
            "channel": "second_order",
            "match_kind": match_kind_transmission,
            "effective_direction": event.direction,
            "relevance": relevance,
            "matched_terms": transmission_hits,
        })

    # --- REFLEXIVITY / sentiment -----------------------------------------
    is_sentiment = (_REFLEXIVITY_TAG in event_tags) or (event.source_type == "sentiment")
    if is_sentiment and exposure.reflexivity_exposure > 0:
        contributions.append({
            "channel": "reflexivity",
            "match_kind": "reflexivity",
            "effective_direction": event.direction,
            "relevance": exposure.reflexivity_exposure,
            "matched_terms": [_REFLEXIVITY_TAG],
        })

    # --- CONTAGION: a bellwether single-name event reaches a sector peer ---
    # Learned *fallback* read-through: only when the holding has no other
    # transmission for this event (the existing factor/sector paths already
    # handle headlines that carry explicit sector tags). This fills the gap for
    # pure earnings/guidance bellwether prints -- e.g. "MU reports earnings" or
    # the AVGO effect -- whose headline has no semis tag to propagate.
    already_transmitted = any(c["channel"] == "second_order" for c in contributions)
    if (not match_kind and not already_transmitted and event.related_tickers
            and event.source_type in {"company", "institutional", "official"}):
        best_rt, primary_hit = 0.0, None
        for rel_t in event.related_tickers:
            rt = contagion.read_through(rel_t, exposure.ticker)
            if rt > best_rt:
                best_rt, primary_hit = rt, rel_t
        if best_rt > 0:
            contributions.append({
                "channel": "second_order",
                "match_kind": "contagion",
                "effective_direction": event.direction,
                "relevance": round(best_rt, 4),
                "matched_terms": [f"{primary_hit}→{exposure.ticker}"],
            })

    return contributions


def score_contribution(
    event: MarketEvent,
    weight: float,
    contribution: dict[str, Any],
    elapsed_hours: float | None = None,
    *,
    effective_direction: int | None = None,
    magnitude_multiplier: float = 1.0,
    reaction_multiplier: float = 1.0,
) -> float:
    """Signed impact for a single channel contribution (the V6 formula)."""
    decay = _decay_factor(event, elapsed_hours)
    direction = contribution["effective_direction"] if effective_direction is None else effective_direction
    return (
        weight
        * direction
        * event.magnitude
        * magnitude_multiplier
        * contribution["relevance"]
        * event.confidence
        * event.classification_confidence
        * decay
        * reaction_multiplier
    )


def _surprise_direction_for_contribution(event: MarketEvent, contribution: dict[str, Any]) -> int | None:
    """Map event-level surprise direction onto a holding/channel contribution."""
    sdir = surprise.effective_direction(event)
    if sdir is None:
        return None
    if sdir == DIRECTION_NEUTRAL:
        return DIRECTION_NEUTRAL
    if contribution.get("match_kind") == "macro_factor" and event.direction in (DIRECTION_BULLISH, DIRECTION_BEARISH):
        return contribution["effective_direction"] * sdir * event.direction
    return sdir


def _crowding_applies(event: MarketEvent) -> bool:
    if event.source_type != "company":
        return False
    if event.event_type in {"earnings_beat", "earnings_miss", "guidance_raise", "guidance_cut", "earnings_date"}:
        return True
    return bool({"earnings", "guidance"} & set(event.affected_tags))


def _aggregate_status(pos: float, neg_abs: float, avg_conf: float) -> str:
    """Map (positive sum, |negative sum|, avg confidence) -> status word."""
    gross = pos + neg_abs
    if gross <= _EPS:
        return "neutral"
    minside = min(pos, neg_abs)
    if minside >= _MIXED_MIN_SHARE * gross:
        return "mixed"
    net = pos - neg_abs
    directional = _sign(net)
    if directional == DIRECTION_BULLISH:
        status = "bullish"
    elif directional == DIRECTION_BEARISH:
        status = "bearish"
    else:
        status = "neutral"
    # Weak-signal override: a non-mixed read dominated by low-confidence
    # evidence is reported as uncertain.
    if status != "neutral" and avg_conf < _UNCERTAIN_CONF:
        return "uncertain"
    return status


def analyze_holding(
    exposure: HoldingExposure,
    weight: float,
    events: list[MarketEvent],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Full per-holding analysis: contributions, channels, net, status, text.

    Each event's signed impact is multiplied by its temporal multiplier (see
    :mod:`modeling.v6.timing`): anticipation ramp-up before a scheduled release,
    decay afterwards, and a possible sell-the-news direction flip. Events whose
    current temporal weight is ~0 are not scored, but *future* catalysts are
    still surfaced in an ``upcoming`` bucket so the holding detail can show them.
    """
    rows: list[dict[str, Any]] = []
    upcoming: list[dict[str, Any]] = []
    matched_event_ids: set[str] = set()
    pos = 0.0
    neg_abs = 0.0
    bull = 0
    bear = 0
    conf_sum = 0.0
    conf_n = 0
    exp_bp = 0.0       # signed expected abnormal move (calibrated, bp)
    exp_abs_bp = 0.0   # gross expected abnormal move (bp)
    crowd_state = crowding.crowding_state(exposure.ticker)

    for ev in events:
        contribs = match_event_to_holding(ev, exposure)
        if not contribs:
            continue
        tp = timing.temporal_profile(ev, now)
        mult = tp["temporal_multiplier"]
        for c in contribs:
            surprise_dir = _surprise_direction_for_contribution(ev, c)
            scoring_dir = c["effective_direction"] if surprise_dir is None else surprise_dir
            surprise_mult = surprise.magnitude_multiplier(ev)
            crowd_mult = (
                crowding.reaction_multiplier(scoring_dir, crowd_state)
                if _crowding_applies(ev) else 1.0
            )
            base = score_contribution(
                ev, weight, c,
                effective_direction=scoring_dir,
                magnitude_multiplier=surprise_mult,
                reaction_multiplier=crowd_mult,
            )
            impact = base * mult
            # effective direction the reader sees (after sell-the-news flip)
            eff_dir = _sign(impact) if abs(impact) > _EPS else scoring_dir
            ev_conf = round(ev.confidence * ev.classification_confidence, 4)
            # Calibrated parallel to ``impact``: same shape, real unit (bp). The
            # learned per-type move is scaled by weight, channel relevance,
            # confidence and the temporal weight (magnitude only -> abs(mult)).
            bp = weight * calibration.contribution_bp(
                event_type=ev.event_type, effective_direction=eff_dir,
                relevance=c["relevance"], confidence=ev_conf,
                temporal_multiplier=abs(mult),
            ) * surprise_mult * crowd_mult
            s_payload = surprise.surprise_payload(ev)
            row = {
                "event_id": ev.event_id,
                "title": ev.title,
                "event_type": ev.event_type,
                "source": ev.source,
                "source_type": ev.source_type,
                "timestamp": ev.timestamp,
                "data_mode": ev.data_mode,
                "source_count": ev.source_count,
                "channel": c["channel"],
                "match_kind": c.get("match_kind", c["channel"]),
                "effective_direction": eff_dir,
                "base_direction": c["effective_direction"],
                "relevance": round(c["relevance"], 4),
                "confidence": round(ev.confidence * ev.classification_confidence, 4),
                "magnitude": ev.magnitude,
                "matched_terms": c["matched_terms"],
                "recognized_states": list(ev.recognized_states),
                "classification_flags": list(ev.classification_flags),
                "impact": round(impact, 6),
                "expected_bp": round(bp, 1),
                "surprise": s_payload,
                "crowding_adjust": round(crowd_mult, 4),
                "surprise_magnitude_multiplier": round(surprise_mult, 4),
                "phase": tp["phase"],
                "is_future": tp["is_future"],
                "countdown_days": tp["countdown_days"],
                "time_weight": tp["time_weight"],
                "temporal_label": tp["label"],
                "explanation": templates.explain_contribution(
                    title=ev.title,
                    event_type=ev.event_type,
                    ticker=exposure.ticker,
                    effective_direction=eff_dir,
                    matched_terms=c["matched_terms"],
                    channel=c["channel"],
                    confidence=ev.confidence * ev.classification_confidence,
                    temporal=tp,
                    match_kind=c.get("match_kind"),
                ),
            }
            if abs(impact) <= _EPS:
                # no current weight: surface future catalysts, drop expired ones
                if tp["is_future"]:
                    upcoming.append(row)
                continue
            rows.append(row)
            matched_event_ids.add(ev.event_id)
            if impact > _EPS:
                pos += impact
                bull += 1
            else:
                neg_abs += -impact
                bear += 1
            exp_bp += bp
            exp_abs_bp += abs(bp)
            conf_sum += ev.confidence * ev.classification_confidence
            conf_n += 1

    avg_conf = (conf_sum / conf_n) if conf_n else 0.0
    net = round(pos - neg_abs, 6)
    status = _aggregate_status(pos, neg_abs, avg_conf)
    event_count = len(matched_event_ids)

    # Group rows by channel for the detail view.
    by_channel: dict[str, list[dict[str, Any]]] = {
        "direct": [], "second_order": [], "reflexivity": [],
    }
    for r in rows:
        by_channel.setdefault(r["channel"], []).append(r)
    for ch in by_channel:
        by_channel[ch].sort(key=lambda r: r["impact"])

    pos_rows = [r for r in rows if r["impact"] > _EPS]
    neg_rows = [r for r in rows if r["impact"] < -_EPS]
    key_positive = max(pos_rows, key=lambda r: r["impact"], default=None)
    key_negative = min(neg_rows, key=lambda r: r["impact"], default=None)

    # Per-channel signed score breakdown (transparency): how much of the net
    # impact comes from each transmission channel, plus a "future" bucket for
    # anticipated catalysts already pre-pricing in. ``future`` overlaps the
    # channel buckets (it is orthogonal: a future event is also direct/etc.).
    channel_scores = {
        "direct": round(sum(r["impact"] for r in rows if r["channel"] == "direct"), 6),
        "second_order": round(sum(r["impact"] for r in rows if r["channel"] == "second_order"), 6),
        "reflexivity": round(sum(r["impact"] for r in rows if r["channel"] == "reflexivity"), 6),
        "future": round(sum(r["impact"] for r in rows if r.get("is_future")), 6),
    }
    matched_tags = sorted({t for r in rows for t in r["matched_terms"]})
    # disagreement: 0 = one-sided, 1 = perfectly balanced bull/bear gross.
    gross = pos + neg_abs
    disagreement = round((2.0 * min(pos, neg_abs) / gross) if gross > _EPS else 0.0, 4)

    return {
        "ticker": exposure.ticker,
        "name": exposure.name,
        "sector": exposure.sector,
        "asset_type": exposure.asset_type,
        "weight": round(weight, 6),
        "net_impact": net,
        "positive_impact": round(pos, 6),
        "negative_impact": round(-neg_abs, 6),
        "expected_abnormal_bp": round(exp_bp, 1),
        "expected_abs_bp": round(exp_abs_bp, 1),
        "crowding_state": crowd_state,
        "status": status,
        "event_count": event_count,
        "bullish_count": bull,
        "bearish_count": bear,
        "avg_confidence": round(avg_conf, 4),
        "disagreement": disagreement,
        "channel_scores": channel_scores,
        "matched_tags": matched_tags,
        "key_positive_driver": _driver_brief(key_positive),
        "key_negative_driver": _driver_brief(key_negative),
        "channels": by_channel,
        "contributions": sorted(rows, key=lambda r: r["impact"]),
        "upcoming": sorted(upcoming, key=lambda r: r["countdown_days"]),
        "conclusion": templates.holding_conclusion(
            ticker=exposure.ticker,
            status=status,
            bullish_count=bull,
            bearish_count=bear,
            event_count=event_count,
        ),
    }


def _driver_brief(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "event_id": row["event_id"],
        "title": row["title"],
        "channel": row["channel"],
        "impact": row["impact"],
        "direction": row["effective_direction"],
    }


def analyze_portfolio(
    portfolio: dict[str, Any],
    events: list[MarketEvent],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Top-level orchestration: analyze every holding, then aggregate.

    ``portfolio`` is the dict returned by :func:`modeling.v6.exposure.build_portfolio`.
    ``now`` is the reference time for all countdown/decay math (defaults to
    current UTC); pass a fixed value for deterministic tests.
    """
    if now is None:
        now = timing.now_utc()
    positions = portfolio.get("positions", [])
    holdings = [
        analyze_holding(p["exposure"], p["weight"], events, now)
        for p in positions
    ]
    # carry weighting metadata onto each holding row
    for h, p in zip(holdings, positions):
        h["weight_basis"] = p.get("weight_basis")
        h["matched_profile"] = p.get("matched_profile", True)

    pos = sum(h["positive_impact"] for h in holdings)
    neg_abs = -sum(h["negative_impact"] for h in holdings)
    net_score = round(pos - neg_abs, 6)

    # Portfolio confidence = impact-weighted avg of holding confidences.
    gross_by_h = [(abs(h["positive_impact"]) + abs(h["negative_impact"])) for h in holdings]
    tot_gross = sum(gross_by_h) or 1.0
    avg_conf = sum(h["avg_confidence"] * g for h, g in zip(holdings, gross_by_h)) / tot_gross
    status = _aggregate_status(pos, neg_abs, avg_conf)

    contributors = sorted(holdings, key=lambda h: h["net_impact"])
    top_negative = [_contrib_brief(h) for h in contributors if h["net_impact"] < -_EPS][:5]
    top_positive = [_contrib_brief(h) for h in reversed(contributors) if h["net_impact"] > _EPS][:5]

    drivers = _aggregate_drivers(holdings)
    future_timeline = build_future_timeline(events, positions, now)

    # Portfolio-level transparency.
    channel_scores = {
        ch: round(sum(h["channel_scores"].get(ch, 0.0) for h in holdings), 6)
        for ch in ("direct", "second_order", "reflexivity", "future")
    }
    gross = pos + neg_abs
    disagreement = round((2.0 * min(pos, neg_abs) / gross) if gross > _EPS else 0.0, 4)
    covered = sum(1 for h in holdings if h["event_count"] > 0)
    coverage = round(covered / len(holdings), 4) if holdings else 0.0

    # Calibrated bp readout: holding bp is already position-weighted, so the
    # portfolio expected abnormal move is their sum.
    exp_bp = round(sum(h.get("expected_abnormal_bp", 0.0) for h in holdings), 1)
    exp_abs_bp = round(sum(h.get("expected_abs_bp", 0.0) for h in holdings), 1)

    return {
        "net_impact_score": net_score,
        "positive_impact": round(pos, 6),
        "negative_impact": round(-neg_abs, 6),
        "expected_abnormal_bp": exp_bp,
        "expected_abs_bp": exp_abs_bp,
        "status": status,
        "avg_confidence": round(avg_conf, 4),
        "disagreement": disagreement,
        "coverage": coverage,
        "channel_scores": channel_scores,
        "holdings_count": len(holdings),
        "covered_holdings": covered,
        "weighting": portfolio.get("weighting"),
        "weight_is_fallback": portfolio.get("weight_is_fallback", False),
        "is_sample_portfolio": portfolio.get("is_sample", False),
        "top_positive_contributors": top_positive,
        "top_negative_contributors": top_negative,
        "main_drivers": drivers,
        "future_timeline": future_timeline,
        "holdings": holdings,
        "conclusion": templates.portfolio_conclusion(
            status=status, net_score=net_score, holdings_count=len(holdings),
        ),
    }


def build_future_timeline(
    events: list[MarketEvent],
    positions: list[dict[str, Any]],
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Upcoming scheduled catalysts, sorted by countdown, with affected holdings.

    Returns one row per future event (phase upcoming/anticipation/live) listing
    its countdown, phase label, expected direction, anticipation factor, and
    which portfolio holdings it touches.
    """
    if now is None:
        now = timing.now_utc()
    exposures = [p["exposure"] for p in positions]
    out: list[dict[str, Any]] = []
    for ev in events:
        tp = timing.temporal_profile(ev, now)
        if not tp["is_future"]:
            continue
        # Which holdings it touches -- directly OR via learned contagion (so a
        # bellwether earnings print lists the sector peers it reads through to).
        direct_hits, readthrough_hits = [], []
        for e in exposures:
            cs = match_event_to_holding(ev, e)
            if not cs:
                continue
            if any(c.get("match_kind") == "contagion" for c in cs) and all(
                    c.get("match_kind") == "contagion" for c in cs):
                readthrough_hits.append(e.ticker)
            else:
                direct_hits.append(e.ticker)
        # Drop scheduled catalysts that touch nothing in this portfolio (e.g. a
        # bank bellwether's earnings for an all-tech book).
        if not (direct_hits or readthrough_hits):
            continue
        out.append({
            "event_id": ev.event_id,
            "title": ev.title,
            "event_type": ev.event_type,
            "source": ev.source,
            "source_type": ev.source_type,
            "data_mode": ev.data_mode,
            "scheduled_at": ev.scheduled_at or ev.effective_at,
            "phase": tp["phase"],
            "temporal_label": tp["label"],
            "countdown_days": tp["countdown_days"],
            "countdown_seconds": tp["countdown_seconds"],
            "expected_direction": ev.direction,
            "anticipation_factor": tp["anticipation_factor"],
            "time_weight": tp["time_weight"],
            "sell_the_news_risk": round(ev.sell_the_news_risk, 4),
            "priced_in_score": round(ev.priced_in_score, 4),
            "potential_abs_bp": calibration.scheduled_potential_bp(ev.event_type),
            "hit_rate": calibration.type_hit_rate(ev.event_type),
            "surprise": surprise.surprise_payload(ev),
            "affected_tickers": sorted(direct_hits),
            "readthrough_tickers": sorted(readthrough_hits),
            "summary": ev.summary,
        })
    out.sort(key=lambda r: r["countdown_days"])
    return out


def _contrib_brief(h: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticker": h["ticker"],
        "name": h["name"],
        "net_impact": h["net_impact"],
        "status": h["status"],
        "weight": h["weight"],
    }


def _aggregate_drivers(holdings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank the events driving the portfolio by total absolute impact."""
    agg: dict[str, dict[str, Any]] = {}
    for h in holdings:
        for r in h["contributions"]:
            d = agg.setdefault(r["event_id"], {
                "event_id": r["event_id"],
                "title": r["title"],
                "event_type": r["event_type"],
                "source_type": r["source_type"],
                "data_mode": r.get("data_mode", "fixture"),
                "phase": r.get("phase", "live"),
                "temporal_label": r.get("temporal_label", ""),
                "is_future": r.get("is_future", False),
                "source_count": r.get("source_count", 1),
                "net_impact": 0.0,
                "abs_impact": 0.0,
                "holdings_hit": set(),
            })
            d["net_impact"] += r["impact"]
            d["abs_impact"] += abs(r["impact"])
            d["holdings_hit"].add(h["ticker"])
    out = []
    for d in agg.values():
        out.append({
            "event_id": d["event_id"],
            "title": d["title"],
            "event_type": d["event_type"],
            "source_type": d["source_type"],
            "data_mode": d["data_mode"],
            "phase": d["phase"],
            "temporal_label": d["temporal_label"],
            "is_future": d["is_future"],
            "source_count": d["source_count"],
            "net_impact": round(d["net_impact"], 6),
            "abs_impact": round(d["abs_impact"], 6),
            "direction": _sign(d["net_impact"]),
            "holdings_hit": sorted(d["holdings_hit"]),
        })
    out.sort(key=lambda d: d["abs_impact"], reverse=True)
    return out
