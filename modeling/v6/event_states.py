"""Two-stage deterministic event recognition and direction assignment."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from modeling.v6.schemas import (
    MarketEvent, DIRECTION_BULLISH, DIRECTION_BEARISH, DIRECTION_NEUTRAL,
)


@dataclass(frozen=True)
class StateRule:
    state: str
    magnitude: float
    patterns: tuple[str, ...]
    tags: tuple[str, ...] = ()


def _r(state: str, magnitude: float, patterns: tuple[str, ...], *tags: str) -> StateRule:
    return StateRule(state, magnitude, patterns, tags)


# Priority chooses the display event type only. All matches are retained.
STATE_RULES: tuple[StateRule, ...] = (
    _r("fda_approval", 4.5, (
        r"\bfda\b.{0,35}\bapprov(?:e|es|ed|al)\b",
        r"\bapprov(?:e|es|ed|al)\b.{0,35}\b(?:drug|therapy|treatment|label|indication)\b",
        r"\b(?:clears?|cleared|clearance)\b.{0,30}\b(?:drug|therapy|treatment|device)\b",
    ), "drug_approval", "healthcare_sector", "pharma"),
    _r("fda_rejection", 4.5, (
        r"\bfda\b.{0,35}\b(?:rejects?|rejected|declines?|denies?|refuses?)\b",
        r"\b(?:complete response letter|fails? to (?:win|get|secure) approval|not approved)\b",
    ), "drug_rejection", "healthcare_sector", "pharma"),
    _r("trial_failure", 4.5, (
        r"\btrial\b.{0,35}\b(?:fails?|failed|miss(?:es|ed)? (?:the )?(?:primary )?endpoint)\b",
        r"\bmiss(?:es|ed)? (?:the )?(?:primary )?endpoint\b",
        r"\b(?:study|trial)\b.{0,30}\bhalted\b",
    ), "trial_failure", "healthcare_sector", "pharma"),
    _r("trial_success", 4.5, (
        r"\btrial\b.{0,35}\b(?:succeeds?|succeeded|meets?|met)\b.{0,20}\bendpoint\b",
        r"\bmeets? (?:the )?(?:primary )?endpoint\b",
        r"\bpositive (?:phase [123] )?(?:trial|study)\b",
    ), "trial_success", "healthcare_sector", "pharma"),
    _r("guidance_cut", 4.0, (
        r"\b(?:cut|cuts|cutting|lower|lowers|lowered|lowering|slash|slashes|slashed|trim|trims|trimmed)\b.{0,24}\b(?:guidance|outlook|forecast|full[- ]year view)\b",
        r"\b(?:guidance|outlook|forecast)\b.{0,20}\b(?:lowered|cut|reduced|weak|soft)\b",
        r"\b(?:guides?|guided) lower\b", r"\bweak outlook\b",
    ), "earnings", "guidance"),
    _r("guidance_raise", 4.0, (
        r"\b(?:raise|raises|raised|raising|lift|lifts|lifted|boost|boosts|boosted|increase|increases|increased)\b.{0,28}\b(?:guidance|outlook|forecast|full[- ]year view|growth outlook)\b",
        r"\b(?:guidance|outlook|forecast)\b.{0,20}\b(?:raised|lifted|increased|higher)\b",
        r"\b(?:guides?|guided) higher\b",
    ), "earnings", "guidance"),
    _r("margin_warning", 3.8, (
        r"\b(?:margin|margins)\b.{0,28}\b(?:pressure|pressured|compress|compression|weaken|decline|warning)\b",
        r"\b(?:net interest income|nim)\b.{0,28}\b(?:pressure|pressured|decline|weaken|lower)\b",
        r"\bprofit warning\b",
    ), "earnings", "margin_pressure"),
    _r("revenue_slowdown", 3.2, (
        r"\b(?:revenue|sales|advertising growth)\b.{0,25}\b(?:slows?|slowed|slowdown|decelerates?|deceleration|weakens?|falls?)\b",
        r"\bweak (?:revenue|sales|demand)\b",
    ), "earnings", "revenue_slowdown"),
    _r("revenue_acceleration", 3.2, (
        r"\b(?:revenue|sales|cloud revenue)\b.{0,25}\b(?:accelerates?|accelerated|surges?|surged|growth strengthens?)\b",
        r"\bstrong (?:revenue|sales|demand)\b",
    ), "earnings", "revenue_acceleration"),
    _r("earnings_miss", 3.5, (
        r"\b(?:earnings|profit|results?)\b.{0,18}\bmiss(?:es|ed)?\b",
        r"\bmiss(?:es|ed)? (?:analyst |adjusted )?(?:estimates|expectations|forecasts?)\b",
        r"\b(?:below|falls? short of) (?:analyst )?(?:estimates|expectations|forecasts?)\b",
    ), "earnings"),
    _r("earnings_beat", 3.5, (
        r"\b(?:earnings|profit|results?)\b.{0,18}\bbeat(?:s|en)?\b",
        r"\b(?:beat|beats|beating|top|tops|topped|above) (?:analyst |adjusted )?(?:estimates|expectations|forecasts?)\b",
        r"\bbeats? on (?:revenue|sales|profit)\b",
    ), "earnings"),
    _r("price_target_cut", 2.5, (
        r"\b(?:cut|cuts|cutting|lower|lowers|lowered|slash|slashes|slashed|trim|trims|trimmed|reduce|reduces|reduced)\b.{0,15}\b(?:price target|target price|target)\b",
        r"\b(?:price target|target price)\b.{0,12}\b(?:cut|lowered|reduced|trimmed)\b",
    ), "analyst_action"),
    _r("price_target_raise", 2.5, (
        r"\b(?:raise|raises|raised|raising|lift|lifts|lifted|boost|boosts|boosted|hike|hikes|hiked)\b.{0,15}\b(?:price target|target price|target)\b",
        r"\b(?:price target|target price)\b.{0,12}\b(?:raised|lifted|increased)\b",
    ), "analyst_action"),
    _r("estimate_cut", 2.5, (
        r"\b(?:cut|cuts|lower|lowers|lowered|reduce|reduces|reduced)\b.{0,18}\b(?:estimate|estimates|eps forecast|revenue forecast)\b",
    ), "analyst_action", "estimate_revision"),
    _r("estimate_raise", 2.5, (
        r"\b(?:raise|raises|raised|lift|lifts|lifted|increase|increases|increased)\b.{0,18}\b(?:estimate|estimates|eps forecast|revenue forecast)\b",
    ), "analyst_action", "estimate_revision"),
    _r("analyst_downgrade", 3.0, (
        r"\b(?:downgrade|downgrades|downgraded)\b",
        r"\b(?:cut|cuts|cutting) to (?:sell|underweight|underperform)\b",
        r"\binitiates? (?:coverage )?(?:at|with) (?:sell|underweight|underperform)\b",
    ), "analyst_action"),
    _r("analyst_upgrade", 3.0, (
        r"\b(?:upgrade|upgrades|upgraded)\b",
        r"\b(?:raise|raises|raised) to (?:buy|overweight|outperform)\b",
        r"\binitiates? (?:coverage )?(?:at|with) (?:buy|overweight|outperform)\b",
    ), "analyst_action"),
    _r("product_recall", 4.0, (
        r"\b(?:recall|recalls|recalled|recalling)\b.{0,30}\b(?:product|vehicle|device|drug|units?)\b",
        r"\bproduct recall\b",
    ), "product_recall", "company_risk"),
    _r("cybersecurity_breach", 4.2, (
        r"\b(?:cybersecurity|cyber|data)\b.{0,20}\b(?:breach|incident|attack)\b",
        r"\b(?:hacked|hackers?|ransomware|data breach|cyberattack|cyber attack)\b",
    ), "cybersecurity", "software_sector", "technology_sector"),
    _r("outage", 3.8, (
        r"\b(?:outage|service disruption|systems? down|offline)\b",
        r"\bdisrupts? global systems\b",
    ), "outage", "software_sector", "technology_sector"),
    _r("product_launch", 2.5, (
        r"\b(?:launch|launches|launched|unveils?|unveiled|introduces?|introduced)\b.{0,30}\b(?:product|device|service|platform|model)\b",
    ), "product_launch"),
    _r("antitrust_probe", 3.5, (
        r"\bantitrust\b.{0,25}\b(?:probe|investigation|case|complaint|scrutiny)\b",
        r"\b(?:probe|investigation)\b.{0,20}\bantitrust\b",
    ), "legal_risk", "regulatory"),
    _r("enforcement_action", 4.0, (
        r"\b(?:enforcement action|charges?|charged|fine|fines|fined|penalty|penalties|indicted|subpoena)\b",
        r"\b(?:sec|doj|ftc)\b.{0,25}\b(?:charges?|sues?|files?|enforcement)\b",
    ), "legal_risk", "regulatory"),
    _r("lawsuit", 3.5, (r"\b(?:lawsuit|lawsuits|sued|sues|class action|files? suit)\b",), "legal_risk"),
    _r("investigation", 3.4, (r"\b(?:probe|probes|investigation|investigations|investigates?|investigated|scrutiny)\b",), "legal_risk"),
    _r("regulatory_rejection", 4.0, (r"\b(?:regulator|regulators|agency)\b.{0,25}\b(?:rejects?|rejected|blocks?|blocked|denies?|denied)\b",), "regulatory"),
    _r("regulatory_approval", 4.0, (r"\b(?:regulator|regulators|agency)\b.{0,25}\b(?:approves?|approved|clears?|cleared)\b",), "regulatory"),
    _r("regulatory_tightening", 3.8, (
        r"\b(?:regulator|regulators|agencies|agency)\b.{0,30}\b(?:propose|proposes|proposed|impose|imposes|tighten|tightens|strengthen|strengthens|stronger)\b.{0,30}\b(?:requirements?|rules?|standards?|capital)\b",
        r"\b(?:court|judge)\b.{0,24}\b(?:rules?|ruled|finds?|found)\b.{0,24}\b(?:illegal|unlawful|monopoly)\b",
    ), "regulatory", "financial_conditions_tightening"),
    _r("export_controls", 4.0, (
        r"\bexport[- ]controls?\b", r"\bexport (?:restrictions?|curbs?|bans?)\b",
        r"\b(?:restricts?|curbs?|bans?)\b.{0,20}\bexports?\b",
    ), "regulatory", "export_controls"),
    _r("sanctions", 3.8, (r"\b(?:sanction|sanctions|sanctioned|sanctioning)\b",), "regulatory", "sanctions"),
    _r("tariffs", 3.5, (r"\b(?:tariff|tariffs|tariffed)\b",), "regulatory", "tariffs"),
    _r("cpi_hot", 4.0, (
        r"\b(?:hot|hotter|hotter[- ]than[- ]expected)\b.{0,15}\b(?:cpi|inflation|ppi)\b",
        r"\b(?:cpi|inflation|ppi)\b.{0,20}\b(?:hot|hotter|accelerates?|accelerated|above expectations?)\b",
    ), "cpi_hot", "inflation", "inflation_fear", "rates_up", "yields_up", "financial_conditions_tightening"),
    _r("cpi_cool", 4.0, (
        r"\b(?:cool|cooler|cooler[- ]than[- ]expected)\b.{0,15}\b(?:cpi|inflation|ppi)\b",
        r"\b(?:cpi|inflation|ppi)\b.{0,20}\b(?:cools?|cooled|eases?|eased|slows?|slowed|below expectations?|disinflation)\b",
        r"\bdisinflation\b",
    ), "cpi_cool", "inflation", "inflation_fear_down", "rates_down", "yields_down"),
    _r("fomc_hawkish", 4.0, (
        r"\b(?:hawkish|higher for longer|rate cuts? priced out|tightening)\b",
        r"\b(?:fed|fomc|central bank)\b.{0,25}\b(?:hikes?|hiked|raises?|raised)\b.{0,12}\brates?\b",
        r"\brate hikes?\b",
    ), "fomc_hawkish", "rates_up", "yields_up"),
    _r("fomc_dovish", 4.0, (
        r"\b(?:dovish|easing cycle|rate cuts? priced in)\b",
        r"\b(?:fed|fomc|central bank)\b.{0,25}\b(?:cuts?|cut|lowers?|lowered)\b.{0,12}\brates?\b",
        r"\brate cuts?\b",
    ), "fomc_dovish", "rates_down", "yields_down"),
    _r("jobs_hot", 3.8, (
        r"\b(?:payrolls?|jobs?|employment)\b.{0,25}\b(?:stronger|strong|surges?|beats?|above expectations?)\b",
        r"\bunemployment\b.{0,15}\b(?:falls?|declines?|drops?)\b",
        r"\blabor market\b.{0,15}\b(?:tight|strengthens?)\b",
    ), "jobs_hot", "rates_up", "cyclical_strength", "financial_conditions_tightening"),
    _r("jobs_weak", 3.8, (
        r"\b(?:payrolls?|jobs?|employment|job growth)\b.{0,28}\b(?:weak|weaker|slows?|slowed|miss(?:es|ed)?|below expectations?|declines?)\b",
        r"\bunemployment\b.{0,15}\b(?:rises?|rose|increases?|increased|jumps?)\b",
        r"\blabor market\b.{0,15}\b(?:weakens?|softens?|cools?)\b",
    ), "jobs_weak", "rates_down", "recession_risk"),
    _r("yields_up", 3.2, (r"\b(?:treasury|bond|real)? ?yields?\b.{0,16}\b(?:rise|rises|rose|jump|jumps|surge|surges|climb|climbs|spike|spikes|up)\b",), "yields_up"),
    _r("yields_down", 3.2, (r"\b(?:treasury|bond|real)? ?yields?\b.{0,16}\b(?:fall|falls|fell|drop|drops|ease|eases|decline|declines|down)\b",), "yields_down"),
    _r("dollar_up", 3.0, (
        r"\b(?:dollar|dxy)\b.{0,15}\b(?:rises?|rose|jumps?|surges?|strengthens?|stronger|up)\b", r"\bstronger dollar\b",
    ), "dollar_up"),
    _r("dollar_down", 3.0, (
        r"\b(?:dollar|dxy)\b.{0,15}\b(?:falls?|fell|drops?|weakens?|weaker|down)\b", r"\bweaker dollar\b",
    ), "dollar_down"),
    _r("bank_stress", 4.2, (
        r"\b(?:bank|banking|lender|regional lender)\b.{0,22}\b(?:stress|crisis|failure|failures|run|runs|sell[- ]off)\b", r"\bdeposit (?:flight|outflows?)\b",
    ), "bank_stress", "credit_stress", "risk_off", "risk_sentiment", "financials_sector"),
    _r("credit_stress", 4.0, (r"\b(?:credit stress|credit crunch|defaults? (?:rise|rises|surge|surges)|financial conditions tighten)\b",), "credit_stress", "risk_off", "risk_sentiment", "financials_sector"),
    _r("oil_up", 4.0, (
        r"\b(?:crude|oil|oil prices?)\b.{0,18}\b(?:rises?|rose|jumps?|surges?|higher|up)\b",
        r"\b(?:opec|opec\+)\b.{0,28}\b(?:cuts?|cut|reduces?|reduced)\b.{0,18}\b(?:supply|output|production)\b",
        r"\b(?:supply|output|production) cut\b.{0,20}\b(?:crude|oil)\b",
    ), "oil_up", "commodity_inflation", "energy_sector"),
    _r("oil_down", 4.0, (r"\b(?:crude|oil|oil prices?)\b.{0,18}\b(?:falls?|fell|drops?|slumps?|lower|down)\b",), "oil_down", "energy_sector"),
    _r("risk_off", 3.2, (r"\b(?:risk[- ]off|sell[- ]off|flight to safety|panic|rout|deleveraging|de[- ]risking|vix spikes?)\b",), "risk_off", "risk_sentiment"),
    _r("risk_on", 3.0, (r"\b(?:risk[- ]on|relief rally|rally|rebound|melt[- ]up|appetite for risk)\b",), "risk_on", "risk_sentiment", "market_turnover"),
    _r("ai_capex_semis", 4.0, (
        r"\b(?:ai capex|capex on ai|ai spending|hyperscaler capex|data cent(?:er|re) buildout)\b", r"\b(?:chip|gpu|semiconductor|accelerator) demand\b",
    ), "ai_capex", "semiconductors", "technology_sector"),
)


STATE_DIRECTION = {
    "earnings_beat": 1, "guidance_raise": 1, "revenue_acceleration": 1,
    "analyst_upgrade": 1, "price_target_raise": 1, "estimate_raise": 1,
    "fda_approval": 1, "trial_success": 1, "regulatory_approval": 1,
    "product_launch": 1, "fomc_dovish": 1, "cpi_cool": 1,
    "yields_down": 1, "dollar_down": 1, "oil_up": 1, "risk_on": 1,
    "ai_capex_semis": 1, "market_reaction_positive": 1,
    "headline_negative_but_priced_in": 1,
    "earnings_miss": -1, "guidance_cut": -1, "margin_warning": -1,
    "revenue_slowdown": -1, "analyst_downgrade": -1,
    "price_target_cut": -1, "estimate_cut": -1, "fda_rejection": -1,
    "trial_failure": -1, "regulatory_rejection": -1,
    "regulatory_tightening": -1,
    "antitrust_probe": -1, "lawsuit": -1, "investigation": -1,
    "enforcement_action": -1, "product_recall": -1, "outage": -1,
    "cybersecurity_breach": -1, "export_controls": -1, "sanctions": -1,
    "tariffs": -1, "fomc_hawkish": -1, "cpi_hot": -1,
    "yields_up": -1, "dollar_up": -1, "oil_down": -1,
    "credit_stress": -1, "bank_stress": -1, "risk_off": -1,
    "sell_the_news": -1, "market_reaction_negative": -1,
    "headline_positive_but_priced_in": -1,
    "jobs_hot": 0, "jobs_weak": 0, "ambiguous_surprise": 0,
}

EVENT_TYPE_ALIAS = {
    "cpi_hot": "macro_inflation_hot", "cpi_cool": "macro_inflation_cool",
    "fomc_hawkish": "rate_hike", "fomc_dovish": "rate_cut",
    "antitrust_probe": "lawsuit_investigation", "lawsuit": "lawsuit_investigation",
    "investigation": "lawsuit_investigation", "enforcement_action": "lawsuit_investigation",
    "export_controls": "regulatory_risk", "sanctions": "regulatory_risk",
    "tariffs": "regulatory_risk",
}

EVENT_TYPE_DIRECTION = {
    "macro_inflation_hot": -1, "macro_inflation_cool": 1,
    "rate_hike": -1, "rate_cut": 1, "regulatory_risk": -1,
    "lawsuit_investigation": -1,
    **{state: direction for state, direction in STATE_DIRECTION.items() if direction},
}

PRIMARY_ORDER = (
    "fda_approval", "fda_rejection", "trial_failure", "trial_success",
    "guidance_cut", "guidance_raise", "earnings_miss", "earnings_beat",
    "margin_warning", "revenue_slowdown", "revenue_acceleration",
)

TAG_HINTS = (
    (r"\b(?:semiconductor|semiconductors|chip|chips|gpu|gpus|nvidia|tsmc)\b", ("semiconductors", "technology_sector")),
    (r"\b(?:ai|artificial intelligence|data cent(?:er|re))\b", ("ai_capex", "technology_sector")),
    (r"\b(?:cloud|software|cybersecurity)\b", ("software_sector", "technology_sector")),
    (r"\b(?:china|chinese|beijing|prc|a[- ]share|hsi)\b", ("china_demand",)),
    (r"\b(?:ev|electric vehicle|battery|lithium)\b", ("auto_demand", "commodities")),
    (r"\b(?:biotech|pharma|cro|drug|therapy|trial|fda|wegovy|zepbound)\b", ("biotech_funding", "healthcare_sector")),
    (r"\b(?:bank|banks|banking|lender|lenders|net interest income|net interest margin|nim)\b", ("credit_cycle", "financials_sector")),
    (r"\b(?:broker|brokers|securities firm|turnover|trading volume)\b", ("market_turnover", "financials_sector")),
    (r"\b(?:opec|crude|oil|energy)\b", ("oil", "commodities", "energy_sector")),
    (r"\binflation (?:fear|scare|expectations? (?:rise|rises|jump|jumps|surge|surges))\b", ("inflation_fear",)),
    (r"\breal yields?\b.{0,14}\b(?:rise|rises|jump|jumps|surge|surges|climb|climbs|up)\b", ("real_yields_up",)),
    (r"\breal yields?\b.{0,14}\b(?:fall|falls|drop|drops|decline|declines|down)\b", ("real_yields_down",)),
    (r"\byield curve\b.{0,14}\b(?:steepens?|steepening|steeper)\b", ("yield_curve_steepening",)),
    (r"\bweak (?:global )?demand|demand concerns?|recession fears?\b", ("recession_risk", "recession_demand")),
)

REACTION_NEGATIVE = re.compile(r"\b(?:shares?|stock)\b.{0,18}\b(?:falls?|fell|drops?|dropped|slumps?|sell[- ]off)\b")
REACTION_POSITIVE = re.compile(r"\b(?:shares?|stock)\b.{0,18}\b(?:rises?|rose|jumps?|jumped|rallies|surges?)\b")
PRICED_IN = re.compile(r"\b(?:sell the news|sell[- ]the[- ]news|good news (?:is |was )?priced in|already priced in|fully priced in|priced[- ]in risk)\b")
VAGUE_HEADLINE = re.compile(r"\b(?:files? (?:quarterly|annual) report|form (?:10[- ]?[qk]|8[- ]?k)|reports? results?)\b")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().replace("–", "-").replace("—", "-")).strip()


def state_direction(state: str) -> int:
    return STATE_DIRECTION.get(state, 0)


def direction_for_event_type(event_type: str) -> int:
    return EVENT_TYPE_DIRECTION.get(event_type, 0)


def recognize_text(title: str, body: str = "") -> dict[str, Any]:
    haystack = _norm(f"{title} {body}")
    states: list[str] = []
    tags: list[str] = []
    patterns: list[str] = []
    magnitudes: dict[str, float] = {}
    for rule in STATE_RULES:
        pattern = next((p for p in rule.patterns if re.search(p, haystack)), None)
        if pattern is None:
            continue
        states.append(rule.state)
        magnitudes[rule.state] = rule.magnitude
        patterns.append(pattern)
        tags.extend(tag for tag in rule.tags if tag not in tags)
    for pattern, hint_tags in TAG_HINTS:
        if re.search(pattern, haystack):
            tags.extend(tag for tag in hint_tags if tag not in tags)

    flags: list[str] = []
    if REACTION_NEGATIVE.search(haystack):
        states.append("market_reaction_negative")
        flags.append("headline_reaction_conflict")
    if REACTION_POSITIVE.search(haystack):
        states.append("market_reaction_positive")
        flags.append("headline_reaction_conflict")
    if PRICED_IN.search(haystack):
        states.append("sell_the_news")
        flags.append("priced_in_risk")
        prior = {state_direction(state) for state in states[:-1]}
        states.append("headline_positive_but_priced_in" if 1 in prior else "headline_negative_but_priced_in")

    directions = {state_direction(state) for state in states} - {0}
    if len(directions) > 1:
        states.append("ambiguous_surprise")
        flags.append("ambiguous_surprise")
    if not directions and (VAGUE_HEADLINE.search(haystack) or not states):
        flags.extend(("surprise_unknown", "headline_only_low_confidence"))
    if re.search(r"\b(?:despite|but|while|even as|although)\b", haystack) and len(states) > 1:
        flags.append("conflicting_phrases")
    if re.search(r"\b(?:global risk[- ]off|broad market|marketwide|recession fears?)\b", haystack):
        flags.append("confounded_market_context")
    return {
        "states": list(dict.fromkeys(states)), "tags": tags,
        "flags": list(dict.fromkeys(flags)), "matched_patterns": patterns,
        "magnitude_by_state": magnitudes,
    }


def assign_direction(recognition: dict[str, Any]) -> dict[str, Any]:
    states = recognition.get("states", [])
    directions = {state_direction(state) for state in states} - {0}
    direction = next(iter(directions)) if len(directions) == 1 else DIRECTION_NEUTRAL
    flags = list(recognition.get("flags", []))
    confidence = 0.6 if len(directions) > 1 else 0.7 if "priced_in_risk" in flags else 0.6 if "headline_only_low_confidence" in flags else 0.75 if "confounded_market_context" in flags else 1.0
    magnitudes = recognition.get("magnitude_by_state", {})
    primary = next((state for state in PRIMARY_ORDER if state in magnitudes), None)
    if primary is None:
        primary = next((state for state in states if state in magnitudes), "uncategorized")
    return {
        "event_type": EVENT_TYPE_ALIAS.get(primary, primary), "direction": direction,
        "magnitude": max((magnitudes.get(s, 1.0) for s in states), default=1.0),
        "confidence_multiplier": confidence, "flags": flags,
    }


def classify_text(title: str, body: str = "") -> dict[str, Any]:
    recognition = recognize_text(title, body)
    assigned = assign_direction(recognition)
    return {
        **assigned, "tags": recognition["tags"], "states": recognition["states"],
        "matched_phrase": recognition["matched_patterns"][0] if recognition["matched_patterns"] else None,
        "matched_patterns": recognition["matched_patterns"],
    }


def classify_event(event: MarketEvent, *, overwrite: bool = False) -> MarketEvent:
    result = classify_text(event.title, event.summary)
    original_type = event.event_type
    if overwrite or event.event_type == "uncategorized":
        event.event_type = result["event_type"]
    if overwrite or event.direction == DIRECTION_NEUTRAL:
        event.direction = result["direction"] if result["states"] else direction_for_event_type(original_type)
    if overwrite or event.magnitude <= 1.0:
        event.magnitude = max(event.magnitude, float(result["magnitude"]))
    event.affected_tags = list(dict.fromkeys([*event.affected_tags, *result["tags"]]))
    event.recognized_states = list(dict.fromkeys([*event.recognized_states, *result["states"]]))
    event.classification_flags = list(dict.fromkeys([*event.classification_flags, *result["flags"]]))
    event.classification_confidence = min(event.classification_confidence, float(result["confidence_multiplier"]))
    event.__post_init__()
    return event
