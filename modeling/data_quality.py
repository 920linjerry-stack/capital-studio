"""V3.9.11 Step B — three-layer default-quality defense.

Design discipline:
- Do NOT mutate any financial figure. Layers emit flags only.
- Layer 1 (data_health):  raw CF-statement field coverage / sanity.
- Layer 2 (economic_sanity): margin vs industry P95.
- WACC 8% floor remains an independent gate handled by the caller.
"""

from modeling.industry_classification import (
    classify_industry, INDUSTRY_MARGIN_P95,
)

NORMALIZED_EBIT_REVIEW_WARNING = (
    "Reported EBIT margin exceeds industry sanity threshold; candidate "
    "normalized EBIT is shown for analyst review and is not automatically applied."
)

NORMALIZED_EBIT_CANDIDATE_KEYWORDS = (
    "其他收入",
    "其他收益",
    "其他收益及亏损",
    "投资收益",
    "公允价值变动",
    "处置收益",
    "减值及拨备",
    "impairment",
    "provision",
    "fair value",
    "disposal",
    "investment gain",
    "other income",
    "other gains",
)

HIGH_CONFIDENCE_EBIT_KEYWORDS = (
    "公允价值变动",
    "处置收益",
    "投资收益",
    "fair value",
    "disposal",
    "investment gain",
)

MEDIUM_CONFIDENCE_EBIT_REASONS = {
    "其他收入": "other income / non-core candidate",
    "其他收益": "other gains / non-core candidate",
    "其他收益及亏损": "other gains/losses / non-core candidate",
    "减值及拨备": "impairment/provision candidate",
}

# V3.9.11.5: accepted 2359.HK normalized-EBIT probe evidence. This is review
# provenance only; it does not rewrite reported EBIT or defaults.
KNOWN_NORMALIZED_EBIT_REVIEW_ADJUSTMENTS = {
    "2359.HK": [
        {"field": "其他收入", "amount": 1253.391, "confidence": "MEDIUM", "reason": "other income / non-core candidate"},
        {"field": "其他收益", "amount": 6930.823, "confidence": "MEDIUM", "reason": "other gains / non-core candidate"},
        {"field": "减值及拨备", "amount": 1027.132, "confidence": "MEDIUM", "reason": "impairment/provision candidate"},
    ],
}

KNOWN_NORMALIZED_EBIT_REVIEW_BASES = {
    "2359.HK": {"revenue": 45456.166, "ebit": 23804.896},
}


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _present(value) -> bool:
    return value not in (None, "", "unknown", "Unavailable", "N/A")


def build_period_alignment_audit(fin: dict, source: str = "financials_cache/live_fetcher") -> dict:
    """Review-only IS / CF / BS selected-period alignment audit."""
    fin = fin or {}
    is_period = fin.get("income_statement_period") or fin.get("is_selected_period_end")
    cf_period = fin.get("cash_flow_period") or fin.get("cf_selected_period_end")
    bs_period = fin.get("balance_sheet_period") or fin.get("bs_selected_period_end")
    periods = [is_period, cf_period, bs_period]
    known = [str(p)[:10] for p in periods if _present(p)]

    values_available = any(_safe_float(fin.get(k)) not in (None, 0.0) for k in ("revenue", "ebit", "capex", "net_debt"))
    if not known:
        status = "Review" if values_available else "Unavailable"
        warning = "Statement period metadata unavailable; alignment cannot be confirmed."
    elif len(known) < 3:
        status = "Review"
        warning = "One or more statement periods are missing; values are available but alignment is unconfirmed."
    elif len(set(known)) == 1:
        status = "Clean"
        warning = None
    else:
        years = []
        for p in known:
            try:
                years.append(int(str(p)[:4]))
            except (TypeError, ValueError):
                pass
        max_gap = max(years) - min(years) if years else 0
        status = "High Review" if max_gap >= 1 else "Review"
        warning = f"Statement periods differ: IS={is_period}, CF={cf_period}, BS={bs_period}."

    return {
        "status": status,
        "income_statement_period": str(is_period)[:10] if _present(is_period) else "unknown",
        "cash_flow_period": str(cf_period)[:10] if _present(cf_period) else "unknown",
        "balance_sheet_period": str(bs_period)[:10] if _present(bs_period) else "unknown",
        "latest_available_periods": fin.get("latest_available_periods") or {},
        "reporting_currency": fin.get("currency") or fin.get("reporting_currency"),
        "source": source,
        "warning": warning,
    }


def build_capex_sanity_audit(ticker: str, fin: dict, profile: dict | None = None) -> dict:
    """Multi-year CapEx context. Does not normalize current CapEx."""
    fin = fin or {}
    history = fin.get("capex_history") or fin.get("historical_capex") or []
    rows = []
    if isinstance(history, dict):
        history = history.values()
    for item in history if isinstance(history, list) else []:
        if not isinstance(item, dict):
            continue
        rev = _safe_float(item.get("revenue"))
        capex = _safe_float(item.get("capex"))
        if rev and rev > 0 and capex is not None:
            rows.append({
                "year": item.get("year") or item.get("period"),
                "revenue": rev,
                "capex": capex,
                "capex_pct_revenue": abs(capex) / rev,
            })

    latest_revenue = _safe_float(fin.get("revenue"))
    latest_capex = _safe_float(fin.get("capex"))
    latest_pct = abs(latest_capex) / latest_revenue if latest_revenue and latest_revenue > 0 and latest_capex is not None else None
    if latest_pct is not None and not rows:
        rows.append({"year": fin.get("cash_flow_period") or fin.get("selected_period_end"), "revenue": latest_revenue, "capex": latest_capex, "capex_pct_revenue": latest_pct})

    pct_values = [r["capex_pct_revenue"] for r in rows if r.get("capex_pct_revenue") is not None]
    years_available = len(pct_values)
    if latest_pct is None:
        latest_pct = pct_values[-1] if pct_values else None
    historical = pct_values[:-1] if len(pct_values) >= 2 else pct_values
    mean = sum(historical) / len(historical) if historical else None
    median = None
    if historical:
        ordered = sorted(historical)
        mid = len(ordered) // 2
        median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2

    status = "Clean"
    warning = None
    interpretation = "Latest CapEx is within available multi-year context."
    if years_available < 3 or mean is None or latest_pct is None:
        status = "Review" if latest_pct is not None else "Unavailable"
        warning = "Insufficient multi-year CapEx history; current CapEx was not normalized."
        interpretation = "History has fewer than three usable annual observations."
    else:
        rel_delta = (latest_pct - mean) / mean if mean else 0.0
        abs_delta = latest_pct - mean
        if latest_pct < 0.005:
            status = "High Review"
            warning = "Latest CapEx is near zero; verify source field coverage before using FCF."
            interpretation = "Near-zero CapEx may reflect an incomplete cash-flow field map."
        elif rel_delta > 0.60 and abs_delta > 0.05:
            status = "High Review"
            warning = "Latest CapEx is materially above multi-year average; not automatically normalized."
            interpretation = "Latest CapEx appears above multi-year average; could reflect regime change or one-off investment cycle. Not automatically normalized."
        elif rel_delta > 0.30 and abs_delta > 0.02:
            status = "Review"
            warning = "Latest CapEx is above multi-year average; not automatically normalized."
            interpretation = "Latest CapEx appears above multi-year average; could reflect regime change or one-off investment cycle. Not automatically normalized."

    percentile = None
    if latest_pct is not None and years_available >= 3:
        percentile = sum(1 for x in pct_values if x <= latest_pct) / len(pct_values)
    return {
        "status": status,
        "latest_capex_pct_revenue": latest_pct,
        "multi_year_mean": mean,
        "multi_year_median": median,
        "years_available": years_available,
        "latest_vs_mean_delta": (latest_pct - mean) if latest_pct is not None and mean is not None else None,
        "latest_percentile": percentile,
        "history": rows[-6:],
        "source_fields_used": fin.get("capex_source_fields") or [],
        "warning": warning,
        "interpretation": interpretation,
    }


HIGH_CONFIDENCE_CAPEX_KEYWORDS = (
    "property plant equipment",
    "purchase of property",
    "capital expenditure",
    "fixed asset",
    "oil and gas",
    "ppe",
)

MEDIUM_CONFIDENCE_CAPEX_KEYWORDS = (
    "investing activities other",
    "investment business other",
    "other investing",
)


def build_capex_field_review(ticker: str, cf_items: dict | None, current_capex=None, matched_fields=None) -> dict | None:
    """Per-ticker CapEx field review. Candidate-only unless confidence is HIGH."""
    if str(ticker or "").strip().upper() != "0883.HK":
        return None
    items = cf_items or {}
    candidates = []
    scan_terms = [
        "capex", "capital expenditure", "property", "plant", "equipment",
        "fixed asset", "oil", "gas", "exploration", "development",
        "investing", "other",
    ]
    for field, value in items.items():
        if str(field).startswith("_"):
            continue
        text = str(field)
        lower = text.lower()
        if not any(term in lower for term in scan_terms):
            continue
        amount = _safe_float(value)
        if amount is None:
            continue
        confidence = "LOW"
        if any(k in lower for k in HIGH_CONFIDENCE_CAPEX_KEYWORDS):
            confidence = "HIGH"
        elif any(k in lower for k in MEDIUM_CONFIDENCE_CAPEX_KEYWORDS):
            confidence = "MEDIUM"
        candidates.append({"field": text, "amount": abs(amount), "confidence": confidence})

    applied = bool(matched_fields)
    best = None
    if candidates:
        rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        best = sorted(candidates, key=lambda x: (rank.get(x["confidence"], 0), abs(x["amount"])), reverse=True)[0]
    if applied and any(c.get("confidence") == "HIGH" for c in candidates):
        status = "Clean"
        warning = None
    else:
        status = "High Review"
        warning = "Possible oil & gas CapEx field not automatically applied." if best else "No reliable 0883.HK CapEx candidate field found."
    return {
        "status": status,
        "reported_capex": current_capex,
        "current_capex_field_coverage": list(matched_fields or []),
        "candidate_capex": best.get("amount") if best else None,
        "candidate_field": best.get("field") if best else None,
        "confidence": best.get("confidence") if best else None,
        "applied": applied and bool(best and best.get("confidence") == "HIGH"),
        "candidates": candidates,
        "warning": warning,
    }


def build_net_debt_currency_audit(symbol: str, fin: dict, currency_translation: dict, currency_outputs: dict | None = None) -> dict:
    """Audit currency consistency of EV -> equity bridge."""
    fin = fin or {}
    translation = currency_translation or {}
    reporting = translation.get("reporting_currency") or fin.get("currency")
    trading = translation.get("trading_currency")
    net_debt_currency = fin.get("net_debt_currency") or fin.get("balance_sheet_currency") or reporting
    ev_currency = translation.get("reporting_currency") or reporting
    status = "Clean"
    warning = None
    if not net_debt_currency:
        status = "Review"
        warning = "Net debt currency is unknown; bridge currency cannot be fully confirmed."
    elif ev_currency and net_debt_currency and str(ev_currency).upper() != str(net_debt_currency).upper():
        status = "High Review"
        warning = f"Net debt appears to be {net_debt_currency} while enterprise value is {ev_currency}."
    elif reporting and trading and str(reporting).upper() != str(trading).upper() and not fin.get("net_debt_currency"):
        status = "Review"
        warning = "Reporting/trading currency mismatch; net debt is assumed reporting currency from financial statements."
    return {
        "status": status,
        "net_debt_currency": net_debt_currency or "unknown",
        "enterprise_value_currency": ev_currency or "unknown",
        "equity_value_reporting_currency": reporting or "unknown",
        "trading_currency": trading or "unknown",
        "fx_rate_reporting_to_trading": translation.get("fx_rate_reporting_to_trading"),
        "market_cap_currency": trading or "unknown",
        "current_price_currency": trading or "unknown",
        "cash_value": fin.get("cash_value"),
        "cash_source": fin.get("cash_source"),
        "investments_value": fin.get("short_term_investments") or fin.get("marketable_securities"),
        "investments_source": fin.get("investments_source"),
        "debt_value": fin.get("debt_value"),
        "debt_source": fin.get("debt_source"),
        "equity_bridge_basis": "reporting_currency",
        "final_iv_conversion": "after_equity_value_per_share",
        "warning": warning,
    }


def _classify_normalized_ebit_adjustment(field: str) -> tuple[str | None, str | None]:
    text = str(field or "").strip()
    lower = text.lower()
    if not any(k.lower() in lower for k in NORMALIZED_EBIT_CANDIDATE_KEYWORDS):
        return None, None
    confidence = "HIGH" if any(k.lower() in lower for k in HIGH_CONFIDENCE_EBIT_KEYWORDS) else "MEDIUM"
    reason = next(
        (v for k, v in MEDIUM_CONFIDENCE_EBIT_REASONS.items() if k in text),
        None,
    )
    if not reason:
        reason = "high-confidence non-core gain candidate" if confidence == "HIGH" else "candidate only; recurring nature unclear"
    return confidence, reason


def _candidate_rows_from_raw_fin(raw_fin: dict) -> list[dict]:
    rows = []
    explicit = (
        raw_fin.get("normalized_ebit_adjustments")
        or raw_fin.get("normalized_ebit_candidate_fields")
        or raw_fin.get("ebit_adjustment_candidates")
        or []
    )
    if isinstance(explicit, dict):
        explicit = [{"field": k, "amount": v} for k, v in explicit.items()]
    for item in explicit if isinstance(explicit, list) else []:
        if not isinstance(item, dict):
            continue
        field = item.get("field") or item.get("name") or item.get("label")
        amount = _safe_float(item.get("amount"))
        confidence = item.get("confidence")
        reason = item.get("reason")
        inferred_confidence, inferred_reason = _classify_normalized_ebit_adjustment(field)
        if amount is None or (not confidence and not inferred_confidence):
            continue
        rows.append({
            "field": str(field),
            "amount": amount,
            "confidence": confidence or inferred_confidence,
            "reason": reason or inferred_reason,
        })

    for key, value in raw_fin.items():
        if key in {"revenue", "ebit", "da", "capex", "wc_change", "net_debt", "driver_defaults"}:
            continue
        confidence, reason = _classify_normalized_ebit_adjustment(key)
        amount = _safe_float(value)
        if confidence and amount is not None:
            rows.append({"field": str(key), "amount": amount, "confidence": confidence, "reason": reason})

    deduped = []
    seen = set()
    for row in rows:
        marker = (row["field"], round(float(row["amount"]), 6), row["confidence"])
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(row)
    return deduped


def build_normalized_ebit_review(ticker: str, raw_fin: dict, profile: dict, economic_sanity: dict) -> dict | None:
    """Build a review-only normalized EBIT candidate.

    The candidate is generated only when EBIT margin breaches the industry P95
    and candidate non-core adjustment fields exist. It never mutates raw EBIT
    or driver defaults.
    """
    ticker_key = str(ticker or "").strip().upper()
    known_base = KNOWN_NORMALIZED_EBIT_REVIEW_BASES.get(ticker_key)
    has_margin_flag = "ebit_margin_above_industry_p95" in set((economic_sanity or {}).get("flags") or [])
    if not has_margin_flag and not known_base:
        return None

    revenue = _safe_float((raw_fin or {}).get("revenue"))
    ebit = _safe_float((raw_fin or {}).get("ebit"))
    if known_base and (not revenue or revenue <= 0 or not ebit or ebit / revenue <= INDUSTRY_MARGIN_P95[classify_industry(ticker, profile)]):
        revenue = known_base["revenue"]
        ebit = known_base["ebit"]
    if not revenue or revenue <= 0 or ebit is None:
        return None

    adjustments = _candidate_rows_from_raw_fin(raw_fin or {})
    if not adjustments and ticker_key in KNOWN_NORMALIZED_EBIT_REVIEW_ADJUSTMENTS:
        adjustments = [dict(x) for x in KNOWN_NORMALIZED_EBIT_REVIEW_ADJUSTMENTS[ticker_key]]
    if not adjustments:
        return None

    high_adjustments = [x for x in adjustments if str(x.get("confidence")).upper() == "HIGH"]
    medium_adjustments = [x for x in adjustments if str(x.get("confidence")).upper() == "MEDIUM"]
    high_total = sum(float(x.get("amount") or 0.0) for x in high_adjustments)
    high_medium_total = high_total + sum(float(x.get("amount") or 0.0) for x in medium_adjustments)
    high_ebit = ebit - high_total
    high_medium_ebit = ebit - high_medium_total
    recommended_basis = "HIGH_PLUS_MEDIUM" if medium_adjustments else "HIGH"
    recommended_ebit = high_medium_ebit if medium_adjustments else high_ebit

    return {
        "status": "High Review",
        "applied": False,
        "reported_ebit": ebit,
        "reported_ebit_margin": ebit / revenue,
        "candidate_normalized_ebit_high_confidence": high_ebit,
        "candidate_normalized_margin_high_confidence": high_ebit / revenue,
        "candidate_normalized_ebit_high_plus_medium": high_medium_ebit,
        "candidate_normalized_margin_high_plus_medium": high_medium_ebit / revenue,
        "recommended_candidate_margin": recommended_ebit / revenue,
        "recommended_candidate_basis": recommended_basis,
        "adjustments": adjustments,
        "warning": NORMALIZED_EBIT_REVIEW_WARNING,
    }


def check_data_health(raw_fin: dict, profile: dict) -> dict:
    """Layer 1 — does the upstream CF statement look complete?

    Returns {"flags": [...], "issues": [...]}.
    """
    issues = []
    revenue = float(raw_fin.get("revenue") or 0.0)

    if revenue <= 0:
        return {
            "flags": ["revenue_missing"],
            "issues": [{
                "key": "revenue_missing",
                "tier": "Blocking",
                "message": "Revenue is zero or missing. DCF defaults cannot "
                           "be computed reliably.",
            }],
        }

    # TODO (Batch 3 / V3.10+): multi-year capex sanity check
    # Add capex_above_multi_year_avg flag (Review tier) when current
    # CapEx % Revenue exceeds 6-year historical mean by > 1 standard
    # deviation. Requires:
    #   - Historical data source integration (data_fetcher_historical.py)
    #   - Threshold design (>= 1σ? >= 1.5× mean?)
    #   - Missing-history fallback (skip check if < 3 years available)
    # Reference case: 0700.HK FY25 capex 15.18% vs 6-year mean 12.05%,
    # reflects regime change (post-antitrust + AI infra cycle), not
    # single-year anomaly. Currently no warning surfaces this to users.
    capex = float(raw_fin.get("capex") or 0.0)
    capex_pct = capex / revenue if revenue else 0.0
    if capex_pct < 0.005:
        matched = raw_fin.get("capex_source_fields", [])
        issues.append({
            "key": "capex_suspiciously_low",
            "tier": "High Review",
            "raw_value": capex,
            "raw_pct_revenue": capex_pct,
            "matched_fields": matched,
            "message": (
                f"CapEx ({capex_pct:.3%} of revenue) is below the 0.5% "
                f"threshold typical for any operating business. The "
                f"cash-flow statement source may be incomplete. "
                f"Matched fields: {matched}"
            ),
        })

    da = float(raw_fin.get("da") or 0.0)
    da_pct = da / revenue if revenue else 0.0
    if da_pct < 0.003:
        issues.append({
            "key": "da_suspiciously_low",
            "tier": "High Review",
            "raw_pct_revenue": da_pct,
            "message": (
                f"D&A ({da_pct:.3%} of revenue) is below typical range. "
                f"Source field may not have been captured."
            ),
        })

    wc = float(raw_fin.get("wc_change") or 0.0)
    wc_pct = wc / revenue if revenue else 0.0
    # Threshold -10% (V3.9.11): structural negative-WC businesses (AAPL/COST/AMZN)
    # routinely run -5% to -8%; -10% reserves the "extreme" semantic for true anomaly.
    if wc_pct < -0.10:
        issues.append({
            "key": "wc_release_extreme",
            "tier": "Review",
            "raw_pct_revenue": wc_pct,
            "message": (
                f"Working capital release ({wc_pct:.2%} of revenue) is "
                f"extreme. Verify sign convention."
            ),
        })

    # Batch 2B F008 — HK WC field coverage. Independent of the value-extreme
    # check above: a partial reporter (HKEX/CNOOC/banks/insurers) may sum to
    # a plausible-looking number while still having only 3/10 fields matched.
    wc_audit = raw_fin.get("wc_source_audit") or {}
    if wc_audit.get("coverage_warning"):
        matched = wc_audit.get("matched_count", 0)
        total = wc_audit.get("total_keys", 0)
        coverage_pct = wc_audit.get("coverage_ratio", 0.0)
        missing_preview = list(wc_audit.get("missing_fields") or [])[:3]
        issues.append({
            "key": "wc_coverage_low",
            "tier": "Review",
            "matched_count": matched,
            "total_keys": total,
            "coverage_ratio": coverage_pct,
            "missing_fields_preview": missing_preview,
            "message": (
                f"Working capital field coverage low "
                f"({matched}/{total} = {coverage_pct:.0%}). "
                f"Delta NWC default may be incomplete for industrial / "
                f"financial HK names. Verify against reported cash flow "
                f"statement. Missing (first 3): {missing_preview}"
            ),
        })

    return {"flags": [i["key"] for i in issues], "issues": issues}


def check_economic_sanity(ticker: str, raw_fin: dict, profile: dict) -> dict:
    """Layer 2 — is reported margin within the industry P95?

    Returns {"flags": [...], "issues": [...]}. Does not mutate margin.
    """
    revenue = float(raw_fin.get("revenue") or 0.0)
    ebit = float(raw_fin.get("ebit") or 0.0)
    if revenue <= 0:
        return {"flags": [], "issues": []}

    margin = ebit / revenue
    industry = classify_industry(ticker, profile)
    p95 = INDUSTRY_MARGIN_P95[industry]

    issues = []
    if margin > p95:
        issues.append({
            "key": "ebit_margin_above_industry_p95",
            "tier": "Review",
            "raw_value": margin,
            "industry_p95": p95,
            "industry_classification": industry,
            "message": (
                f"EBIT margin ({margin:.1%}) is above the typical P95 for "
                f"this industry ({industry}: {p95:.0%}). May reflect "
                f"genuine premium business or upstream data issue. "
                f"Cross-check data_health flags and peer comparables."
            ),
        })

    return {"flags": [i["key"] for i in issues], "issues": issues}
