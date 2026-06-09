"""V3.7.7 Trading Comps v1 / Real Football Field & Valuation Pack.

Pulls peer market data from yfinance, computes EV/Revenue, EV/EBITDA, P/E
multiples, applies outlier handling, and produces implied valuation ranges for
the target ticker that respect the V3.7.3 net-debt and V3.7.4 share-count
selections from the decision layers.

Design rules (per V3.7.7 spec):
- Default peer list is a v1 reference set, not a recommendation. Peer sets are
  configurable via API ``peer_tickers``.
- Missing / negative metric rows are flagged Excluded with reason; not deleted.
- Outliers are flagged with a reason; not removed silently.
- Data quality block + warnings surface to the workbook / API.
- Graceful fallback: never raises; partial data still produces partial output.
"""
from __future__ import annotations

import json
import math
import statistics
from datetime import date, datetime
from pathlib import Path
from typing import Optional


# ── Module constants ─────────────────────────────────────────────────────────

COMPS_VERSION = "v3997_trading_comps_multisource_fallback"

# V3.7.7 default peer set. AAPL-anchored mega-cap tech / platform set; not a
# recommendation. Reviewers should treat this as a reference baseline.
DEFAULT_PEER_SETS: dict[str, list[str]] = {
    "AAPL": ["MSFT", "GOOGL", "META", "AMZN", "NVDA", "ORCL", "ADBE", "QCOM", "AVGO"],
    # MSFT default peer set mirrors AAPL with AAPL substituted in.
    "MSFT": ["AAPL", "GOOGL", "META", "AMZN", "NVDA", "ORCL", "ADBE", "CRM", "AVGO"],
    "GOOGL": ["AAPL", "MSFT", "META", "AMZN", "NFLX", "ADBE", "BIDU"],
    "META": ["AAPL", "MSFT", "GOOGL", "AMZN", "NFLX", "SNAP", "PINS"],
    "AMZN": ["AAPL", "MSFT", "GOOGL", "META", "WMT", "COST", "BABA"],
    "NVDA": ["AAPL", "MSFT", "AMD", "AVGO", "QCOM", "TSM", "ASML"],
}

AAPL_DIAGNOSTIC_ONLY_PEERS = {"NVDA", "AVGO", "QCOM"}


def _peer_role(symbol: str, ticker: str) -> str:
    if symbol.upper() == "AAPL":
        return "Diagnostic" if ticker.upper() in AAPL_DIAGNOSTIC_ONLY_PEERS else "Core"
    return "Core"

# V3.9.3 Peer rationale / category catalog. Drives the new Trading Comps v2
# Peer Set table columns and Football Field interpretation. Categories are
# deliberately coarse so the reference set stays auditable.
PEER_CATEGORY_DEFAULT = "Diagnostic / Other"
PEER_CATEGORIES: dict[str, str] = {
    "AAPL": "Hardware + Platform / Ecosystem",
    "MSFT": "Platform / Cloud",
    "GOOGL": "Platform / Digital Ads",
    "META": "Platform / Digital Ads",
    "AMZN": "Platform / Commerce + Cloud",
    "NFLX": "Platform / Streaming",
    "ORCL": "Platform / Enterprise Software",
    "ADBE": "Platform / Enterprise Software",
    "CRM": "Platform / Enterprise Software",
    "NVDA": "Semis / AI Compute",
    "AMD": "Semis / AI Compute",
    "AVGO": "Semis / Connectivity",
    "QCOM": "Semis / Connectivity",
    "TSM": "Semis / Foundry",
    "ASML": "Semis / Capital Equipment",
    "BIDU": "Platform / Digital Ads (CN)",
    "BABA": "Platform / Commerce (CN)",
    "WMT": "Diagnostic / Retail",
    "COST": "Diagnostic / Retail",
    "SNAP": "Platform / Digital Ads",
    "PINS": "Platform / Digital Ads",
}

PEER_RATIONALE: dict[str, str] = {
    "MSFT": "Mega-cap platform peer; recurring software / cloud mix anchors the platform multiple range.",
    "GOOGL": "Mega-cap platform peer; advertising-led services profile relevant for Services-mix discussions.",
    "META": "Mega-cap platform peer; advertising-led with consumer engagement model.",
    "AMZN": "Mega-cap platform peer; mixed retail + cloud distorts gross margin but useful for scale.",
    "NVDA": "Semis peer; AI-cycle multiple expansion - reviewer should expect outlier behavior.",
    "ORCL": "Enterprise software peer; mature platform multiple anchor.",
    "ADBE": "Enterprise software peer; subscription-led margin profile.",
    "QCOM": "Semis peer; smartphone-connectivity exposure - product cycle sensitive.",
    "AVGO": "Semis peer; AI/networking exposure - often EV/EBITDA outlier.",
    "AAPL": "Anchor / target self-comparable when used as a peer.",
    "AMD": "Semis peer; AI/PC GPU exposure.",
    "TSM": "Semis foundry peer; supply-chain critical, multiples vary with cycle.",
    "ASML": "Semis capital equipment peer; backlog-driven multiple cycle.",
    "NFLX": "Streaming peer; subscriber-led platform multiple.",
    "CRM": "Enterprise SaaS peer; subscription model.",
    "BIDU": "CN digital advertising peer; regional regulatory overlay.",
    "BABA": "CN commerce peer; regional regulatory overlay.",
    "SNAP": "Digital ads peer; smaller scale and higher volatility.",
    "PINS": "Digital ads peer; smaller scale and higher volatility.",
    "WMT": "Retail benchmark; comparability is diagnostic only.",
    "COST": "Retail benchmark; comparability is diagnostic only.",
}

# V3.9.3: stricter inclusion threshold. With fewer than this many peers
# remaining after exclusion + outlier filtering for a multiple, the implied
# range is suppressed entirely rather than computed off a noisy 1-2 sample.
INSUFFICIENT_PEER_THRESHOLD = 3

# Generic tech-platform fallback when symbol not in DEFAULT_PEER_SETS.
GENERIC_TECH_FALLBACK = ["AAPL", "MSFT", "GOOGL", "META", "AMZN", "NVDA"]

UNSUPPORTED_PEER_PROFILES: dict[str, tuple[str, str]] = {
    "2359.HK": (
        "cro_cdmo_peer_mapping_required",
        "CRO/CDMO peer set not yet mapped; generic tech fallback suppressed.",
    ),
    "600519.SS": (
        "premium_consumer_peer_mapping_required",
        "Premium consumer peer set not yet mapped; generic tech fallback suppressed.",
    ),
    "0700.HK": (
        "internet_platform_peer_mapping_required",
        "Internet platform peer set not yet mapped; generic tech fallback suppressed pending explicit peer policy.",
    ),
}


def get_trading_comps_profile(
    ticker: str,
    industry_profile: Optional[dict] = None,
    peer_tickers: Optional[list[str]] = None,
) -> dict:
    """Resolve whether Trading Comps may produce a formal peer valuation.

    V3.9.12.2 gates the old generic US tech fallback. A curated/default peer
    set or explicit user override may still run; unsupported/unknown symbols
    return an unavailable profile so API and Excel can show a review-required
    state instead of misleading AAPL-style implied IV ranges.
    """
    sym = (ticker or "").strip().upper()
    if peer_tickers:
        cleaned = [t.strip().upper() for t in peer_tickers if t and t.strip()]
        return {
            "supported": True,
            "profile_id": "user_override_peer_set",
            "peer_set_source": "user_override",
            "reason": "User-supplied peer set; generic tech fallback not used.",
            "peers": cleaned,
        }
    if sym == "AAPL":
        return {
            "supported": True,
            "profile_id": "us_mega_cap_tech",
            "peer_set_source": "curated_aapl_mega_cap_tech",
            "reason": "Curated AAPL mega-cap technology / platform peer set.",
            "peers": list(DEFAULT_PEER_SETS["AAPL"]),
        }
    if sym in DEFAULT_PEER_SETS:
        return {
            "supported": True,
            "profile_id": "curated_us_mega_cap_tech",
            "peer_set_source": f"default_v1_for_{sym}",
            "reason": "Curated US mega-cap technology peer set; generic fallback not used.",
            "peers": list(DEFAULT_PEER_SETS[sym]),
        }
    if sym in UNSUPPORTED_PEER_PROFILES:
        profile_id, reason = UNSUPPORTED_PEER_PROFILES[sym]
        return {
            "supported": False,
            "profile_id": profile_id,
            "peer_set_source": "suppressed_generic_tech_fallback",
            "reason": reason,
            "peers": [],
        }
    return {
        "supported": False,
        "profile_id": "no_curated_peer_set_available",
        "peer_set_source": "unavailable",
        "reason": "No curated peer set available; generic tech fallback suppressed.",
        "peers": [],
    }


def _unavailable_trading_comps_payload(symbol: str, profile: dict) -> dict:
    reason = profile.get("reason") or "Industry peer set requires review; generic tech fallback suppressed."
    return {
        "version": COMPS_VERSION,
        "status": "unavailable",
        "symbol": (symbol or "").strip().upper(),
        "profile": profile,
        "profile_id": profile.get("profile_id"),
        "peer_source": profile.get("peer_set_source") or "unavailable",
        "peer_set_source": profile.get("peer_set_source") or "unavailable",
        "peer_set_requested": [],
        "peers": [],
        "peer_rows": [],
        "valuation_ranges": [],
        "summary_stats": {},
        "implied_valuation": {},
        "reason": reason,
        "unavailable_reason": reason,
        "methodology_note": (
            "Trading Comps unavailable. Industry peer set requires review. "
            "Generic technology fallback has been suppressed for this ticker."
        ),
        "data_quality": {
            "overall_comps_usability_tier": "Unavailable",
            "football_field_comps_status": "Trading Comps unavailable",
            "peer_count_total": 0,
            "core_peer_count": 0,
            "suppressed_generic_tech_fallback": True,
            "profile_id": profile.get("profile_id"),
            "peer_set_source": profile.get("peer_set_source") or "unavailable",
            "reason": reason,
        },
        "warnings": [reason],
        "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }

# Outlier policy.
OUTLIER_ABS_CAP = {
    "ev_revenue": 30.0,   # > 30x EV/Revenue flagged as outlier
    "ev_ebitda": 60.0,    # > 60x EV/EBITDA flagged as outlier
    "pe": 80.0,           # > 80x P/E flagged as outlier
}
OUTLIER_IQR_K = 3.0       # rows beyond Q3+3*IQR or Q1-3*IQR flagged outlier

# Daily cache for peer market snapshots.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CACHE_DIR = _PROJECT_ROOT / "data" / "cache"

FIELD_KEYS = (
    "price",
    "market_cap",
    "enterprise_value",
    "revenue",
    "ebitda",
    "net_income",
    "trailing_pe",
    "forward_pe",
    "forward_eps",
    "fifty_two_week_high",
    "fifty_two_week_low",
)

PEER_COMPANY_NAMES = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "GOOGL": "Alphabet Inc.",
    "META": "Meta Platforms, Inc.",
    "AMZN": "Amazon.com, Inc.",
    "ORCL": "Oracle Corporation",
    "ADBE": "Adobe Inc.",
    "NVDA": "NVIDIA Corporation",
    "AVGO": "Broadcom Inc.",
    "QCOM": "QUALCOMM Incorporated",
}


def _comps_cache_path(ticker: str, day: Optional[date] = None) -> Path:
    d = (day or date.today()).isoformat()
    return _CACHE_DIR / f"comps_peer_{ticker.upper().replace('.', '_')}_{d}.json"


def _cache_glob(ticker: str) -> list[Path]:
    stem = ticker.upper().replace(".", "_")
    return sorted(_CACHE_DIR.glob(f"comps_peer_{stem}_*.json"), reverse=True)


def _stamp_payload(payload: dict, source: str, source_detail: str, cache_file: Optional[Path] = None) -> dict:
    field_sources = payload.setdefault("field_sources", {})
    for key in FIELD_KEYS:
        if _safe_float(payload.get(key)) is not None and not field_sources.get(key):
            field_sources[key] = source
    payload["source"] = source_detail
    payload["fallback_source"] = source
    if cache_file:
        payload["cache_file"] = str(cache_file)
        payload["cache_date"] = cache_file.stem.split("_")[-1]
        payload["cache_stale"] = cache_file != _comps_cache_path(payload.get("ticker") or "")
    return payload


def _payload_has_main_data(payload: dict) -> bool:
    return any(_safe_float(payload.get(k)) is not None for k in ("market_cap", "enterprise_value", "revenue", "ebitda", "net_income", "trailing_pe"))


def _load_existing_comps_cache(ticker: str) -> Optional[dict]:
    """Return the newest usable comps cache, including stale files.

    A failed same-day yfinance.info payload should not erase a usable prior
    daily cache. Stale caches are retained and surfaced as Review quality.
    """
    for path in _cache_glob(ticker):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not _payload_has_main_data(payload):
            continue
        payload.setdefault("ticker", ticker.upper())
        payload.setdefault("name", PEER_COMPANY_NAMES.get(ticker.upper()) or ticker.upper())
        return _stamp_payload(payload, "cache", f"existing comps cache ({path.name})", path)
    return None


def _quote_cache_paths(ticker: str) -> list[Path]:
    stem = ticker.upper().replace(".", "_")
    dotted = ticker.upper()
    return [
        _CACHE_DIR / f"quote_{dotted}.json",
        _CACHE_DIR / f"quote_{dotted}_v320.json",
        _CACHE_DIR / f"quote_{stem}.json",
        _CACHE_DIR / f"quote_{stem}_v320.json",
    ]


def _merge_quote_cache(payload: dict) -> None:
    ticker = (payload.get("ticker") or "").upper()
    field_sources = payload.setdefault("field_sources", {})
    for path in _quote_cache_paths(ticker):
        if not path.exists():
            continue
        try:
            q = json.loads(path.read_text(encoding="utf-8")).get("data") or {}
        except Exception:
            continue
        mapping = {
            "price": q.get("current_price"),
            "market_cap": (_safe_float(q.get("market_cap")) * 1_000_000.0 if _safe_float(q.get("market_cap")) is not None else None),
            "fifty_two_week_high": q.get("week52_high"),
            "fifty_two_week_low": q.get("week52_low"),
            "trailing_pe": q.get("pe_ratio"),
        }
        if q.get("name") and not payload.get("name"):
            payload["name"] = q.get("name")
        if q.get("currency") and not payload.get("currency"):
            payload["currency"] = q.get("currency")
        for key, value in mapping.items():
            value = _safe_float(value)
            if _safe_float(payload.get(key)) is None and value is not None:
                payload[key] = value
                field_sources[key] = "cache"
        payload.setdefault("quote_cache_file", str(path))
        return


def _financials_cache_path(ticker: str) -> Optional[Path]:
    candidates = [
        _CACHE_DIR / f"financials_{ticker.upper()}_v327.json",
        _CACHE_DIR / f"financials_{ticker.upper().replace('.', '_')}_v327.json",
        _CACHE_DIR / f"financials_{ticker}_v327.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _merge_financials_cache(payload: dict) -> None:
    ticker = (payload.get("ticker") or "").upper()
    path = _financials_cache_path(ticker)
    if not path:
        return
    try:
        fc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    data = fc.get("data") or {}
    field_sources = payload.setdefault("field_sources", {})

    def _actual(key: str) -> Optional[float]:
        v = _safe_float(data.get(key))
        return v * 1_000_000.0 if v is not None else None

    for target_key, source_key in (("revenue", "revenue"), ("net_income", "net_income")):
        if _safe_float(payload.get(target_key)) is None:
            v = _actual(source_key)
            if v is not None:
                payload[target_key] = v
                field_sources[target_key] = "cache"
    if _safe_float(payload.get("ebitda")) is None:
        ebit = _actual("ebit")
        da = _actual("da")
        if ebit is not None and da is not None:
            payload["ebitda"] = ebit + da
            payload["ebitda_methodology"] = "EBIT + D&A approximation"
            field_sources["ebitda"] = "derived"
    if _safe_float(payload.get("enterprise_value")) is None and _safe_float(payload.get("market_cap")) is not None:
        net_debt = _actual("net_debt")
        if net_debt is not None:
            payload["enterprise_value"] = _safe_float(payload.get("market_cap")) + net_debt
            field_sources["enterprise_value"] = "derived"
    if _safe_float(payload.get("price")) is None:
        shares = _actual("shares")
        mc = _safe_float(payload.get("market_cap"))
        if shares and mc:
            payload["price"] = mc / shares
            field_sources["price"] = "derived"
    payload["financials_cache_file"] = str(path)


def _merge_history_context(payload: dict) -> None:
    ticker = (payload.get("ticker") or "").upper()
    path = _CACHE_DIR / f"history_{ticker}_1y.json"
    if not path.exists():
        path = _CACHE_DIR / f"history_{ticker.replace('.', '_')}_1y.json"
    if not path.exists():
        return
    try:
        hist = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    rows = hist.get("data") or []
    highs = [_safe_float(r.get("high")) for r in rows if _safe_float(r.get("high")) is not None]
    lows = [_safe_float(r.get("low")) for r in rows if _safe_float(r.get("low")) is not None]
    closes = [_safe_float(r.get("close")) for r in rows if _safe_float(r.get("close")) is not None]
    field_sources = payload.setdefault("field_sources", {})
    if _safe_float(payload.get("fifty_two_week_high")) is None and highs:
        payload["fifty_two_week_high"] = max(highs)
        field_sources["fifty_two_week_high"] = "cache"
    if _safe_float(payload.get("fifty_two_week_low")) is None and lows:
        payload["fifty_two_week_low"] = min(lows)
        field_sources["fifty_two_week_low"] = "cache"
    if _safe_float(payload.get("price")) is None and closes:
        payload["price"] = closes[-1]
        field_sources["price"] = "cache"
    payload["history_cache_file"] = str(path)


# ── Peer data fetch ─────────────────────────────────────────────────────────


def _safe_float(value):
    if value is None:
        return None
    try:
        v = float(value)
        if v != v or v in (float("inf"), float("-inf")):
            return None
        return v
    except (TypeError, ValueError):
        return None


def fetch_peer_market_data(ticker: str, use_cache: bool = True) -> dict:
    """Pull one peer's market data with cache-first multisource fallback.

    Never raises - failures degrade to ``status='unavailable'`` with the
    exception message captured for audit.
    """
    ticker_norm = ticker.strip().upper()
    cache_path = _comps_cache_path(ticker_norm)
    if use_cache:
        cached = _load_existing_comps_cache(ticker_norm)
        if cached:
            _merge_quote_cache(cached)
            _merge_financials_cache(cached)
            _merge_history_context(cached)
            cached["status"] = "ok"
            cached["name"] = cached.get("name") or PEER_COMPANY_NAMES.get(ticker_norm) or ticker_norm
            cached["fallback_hierarchy"] = [
                "existing comps cache",
                "quote cache / fast quote fields",
                "normalized financials cache",
                "manual peer metadata",
            ]
            for key in FIELD_KEYS:
                cached.setdefault("field_sources", {}).setdefault(key, "unavailable")
            return cached

    payload: dict = {
        "ticker": ticker_norm,
        "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "ok",
        "field_sources": {},
    }
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker_norm)
        info = tk.info or {}
        fast = {}
        try:
            fast = dict(getattr(tk, "fast_info", {}) or {})
        except Exception:
            fast = {}
        payload.update({
            "name": info.get("longName") or info.get("shortName") or ticker_norm,
            "currency": info.get("financialCurrency") or info.get("currency") or "USD",
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "price": _safe_float(
                info.get("currentPrice")
                or info.get("regularMarketPrice")
                or info.get("previousClose")
                or fast.get("lastPrice")
                or fast.get("last_price")
            ),
            "fifty_two_week_high": _safe_float(info.get("fiftyTwoWeekHigh")),
            "fifty_two_week_low": _safe_float(info.get("fiftyTwoWeekLow")),
            "market_cap": _safe_float(info.get("marketCap") or fast.get("marketCap") or fast.get("market_cap")),
            "enterprise_value": _safe_float(info.get("enterpriseValue")),
            "revenue": _safe_float(info.get("totalRevenue")),
            "ebitda": _safe_float(info.get("ebitda")),
            "net_income": _safe_float(info.get("netIncomeToCommon")),
            "trailing_pe": _safe_float(info.get("trailingPE")),
            "forward_pe": _safe_float(info.get("forwardPE")),
            "forward_eps": _safe_float(info.get("forwardEps")),
            "source": "yfinance.info",
        })
        for key in FIELD_KEYS:
            if _safe_float(payload.get(key)) is not None:
                payload["field_sources"][key] = "live"
    except Exception as e:  # noqa: BLE001 - graceful
        payload.update({
            "status": "unavailable",
            "error": repr(e),
            "name": PEER_COMPANY_NAMES.get(ticker_norm) or ticker_norm,
            "currency": None,
            "sector": None,
            "industry": None,
            "price": None,
            "fifty_two_week_high": None,
            "fifty_two_week_low": None,
            "market_cap": None,
            "enterprise_value": None,
            "revenue": None,
            "ebitda": None,
            "net_income": None,
            "trailing_pe": None,
            "forward_pe": None,
            "forward_eps": None,
            "source": "yfinance.info (failed)",
        })

    _merge_quote_cache(payload)
    _merge_financials_cache(payload)
    _merge_history_context(payload)
    payload["name"] = payload.get("name") or PEER_COMPANY_NAMES.get(ticker_norm) or ticker_norm
    if _payload_has_main_data(payload):
        payload["status"] = "ok"
        if payload.get("source") == "yfinance.info (failed)":
            payload["source"] = "fallback stack after yfinance.info failure"
    payload["fallback_hierarchy"] = [
        "existing comps cache",
        "yfinance.info / fast_info",
        "quote cache / history cache",
        "normalized financials cache",
        "manual peer metadata",
    ]
    for key in FIELD_KEYS:
        payload.setdefault("field_sources", {}).setdefault(key, "unavailable")

    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return payload


def resolve_peer_tickers(symbol: str, override: Optional[list[str]] = None) -> tuple[list[str], str]:
    """Return (peer_list, source_label).

    V3.9.12.2 no longer returns GENERIC_TECH_FALLBACK for unsupported
    symbols; callers receive an empty set plus a suppressed source label.
    """
    profile = get_trading_comps_profile(symbol, peer_tickers=override)
    return list(profile.get("peers") or []), profile.get("peer_set_source") or "unavailable"


# ── Multiples computation ──────────────────────────────────────────────────


def _compute_peer_multiples(raw: dict) -> dict:
    """Per-peer multiple dict. Adds Included flag + exclusion reasons per multiple."""
    rev = raw.get("revenue")
    ebitda = raw.get("ebitda")
    ni = raw.get("net_income")
    mc = raw.get("market_cap")
    ev = raw.get("enterprise_value")

    multiples: dict[str, Optional[float]] = {
        "ev_revenue": None,
        "ev_ebitda": None,
        "pe": raw.get("trailing_pe"),
    }
    exclusions: dict[str, Optional[str]] = {
        "ev_revenue": None,
        "ev_ebitda": None,
        "pe": None,
    }

    # EV / Revenue
    if ev is not None and rev and rev > 0:
        multiples["ev_revenue"] = ev / rev
    elif ev is None or rev is None:
        exclusions["ev_revenue"] = "missing EV or Revenue"
    else:
        exclusions["ev_revenue"] = "Revenue <= 0"

    # EV / EBITDA
    if ev is not None and ebitda and ebitda > 0:
        multiples["ev_ebitda"] = ev / ebitda
    elif ev is None or ebitda is None:
        exclusions["ev_ebitda"] = "missing EV or EBITDA"
    else:
        exclusions["ev_ebitda"] = "EBITDA <= 0"

    # P/E (use trailing_pe from info; fall back to MC/NI when missing/negative).
    if multiples["pe"] is None and mc is not None and ni and ni > 0:
        multiples["pe"] = mc / ni
    elif multiples["pe"] is not None and multiples["pe"] <= 0:
        exclusions["pe"] = "trailing P/E <= 0 (negative earnings)"
        multiples["pe"] = None
    if multiples["pe"] is None and exclusions["pe"] is None:
        exclusions["pe"] = "trailing P/E unavailable"

    return {"multiples": multiples, "exclusions": exclusions}


def _flag_outliers(rows: list[dict]) -> None:
    """Mutate rows in place: add per-multiple `outlier` + `outlier_reason` flags.

    Uses both absolute caps (per OUTLIER_ABS_CAP) and Tukey 3x IQR on the
    currently-included values.
    """
    for key, cap in OUTLIER_ABS_CAP.items():
        # Collect non-null, non-excluded values for IQR.
        values = [
            r["multiples"][key]
            for r in rows
            if r["multiples"].get(key) is not None and r["exclusions"].get(key) is None
        ]
        if len(values) >= 4:
            q1, q3 = statistics.quantiles(values, n=4)[0], statistics.quantiles(values, n=4)[2]
            iqr = q3 - q1
            lo = q1 - OUTLIER_IQR_K * iqr
            hi = q3 + OUTLIER_IQR_K * iqr
        else:
            lo, hi = -math.inf, math.inf
        for r in rows:
            v = r["multiples"].get(key)
            outliers = r.setdefault("outliers", {})
            reasons = r.setdefault("outlier_reasons", {})
            if v is None:
                outliers[key] = False
                reasons[key] = None
                continue
            if v > cap:
                outliers[key] = True
                reasons[key] = f"> {cap:g}x absolute cap"
            elif v < 0:
                outliers[key] = True
                reasons[key] = "negative multiple"
            elif v > hi or v < lo:
                outliers[key] = True
                reasons[key] = f"IQR outlier (Q1={q1:.1f}, Q3={q3:.1f}, k={OUTLIER_IQR_K})"
            else:
                outliers[key] = False
                reasons[key] = None


def _summary_stats(rows: list[dict], key: str) -> dict:
    """Min / 25 / median / mean / 75 / max for a multiple, computed only on
    peers whose ``included_in_stats[key]`` flag is True (not excluded, not
    outlier, value present and positive). V3.9.3 also returns the included
    peer ticker list and an ``insufficient_data`` flag so the workbook can
    refuse to print an implied range from <3 peers."""
    contributors = []
    values = []
    for r in rows:
        per_mult = r.get("included_in_stats") or {}
        if not per_mult.get(key):
            continue
        v = (r.get("multiples") or {}).get(key)
        if v is None:
            continue
        values.append(v)
        contributors.append(r.get("ticker"))
    if not values:
        return {
            "count": 0,
            "min": None, "p25": None, "median": None, "mean": None, "p75": None, "max": None,
            "contributors": [],
            "insufficient_data": True,
            "insufficient_reason": "no peers included after exclusion + outlier filters",
        }
    values_sorted = sorted(values)
    n = len(values_sorted)
    if n >= 4:
        q = statistics.quantiles(values_sorted, n=4)
        p25, median, p75 = q[0], q[1], q[2]
    else:
        p25 = values_sorted[0]
        median = statistics.median(values_sorted)
        p75 = values_sorted[-1]
    insufficient = n < INSUFFICIENT_PEER_THRESHOLD
    return {
        "count": n,
        "min": round(values_sorted[0], 4),
        "p25": round(p25, 4),
        "median": round(median, 4),
        "mean": round(statistics.fmean(values_sorted), 4),
        "p75": round(p75, 4),
        "max": round(values_sorted[-1], 4),
        "contributors": contributors,
        "insufficient_data": insufficient,
        "insufficient_reason": (
            f"only {n} included peer(s); minimum {INSUFFICIENT_PEER_THRESHOLD} required for a credible range"
            if insufficient else None
        ),
    }


def _peer_inclusion_flags(row: dict) -> dict[str, bool]:
    """V3.9.3: per-multiple included_in_stats. A peer multiple is included iff
    value is present, exclusion is None, and outlier is False."""
    mults = row.get("multiples") or {}
    excls = row.get("exclusions") or {}
    outliers = row.get("outliers") or {}
    flags = {}
    for key in ("ev_revenue", "ev_ebitda", "pe"):
        v = mults.get(key)
        flags[key] = bool(
            v is not None
            and v > 0
            and excls.get(key) is None
            and not outliers.get(key)
        )
    return flags


def _implied_valuation_for_multiple(
    metric_value: Optional[float],
    stats: dict,
    multiple_kind: str,
    net_debt_used: float,
    shares_used: float,
) -> dict:
    """Apply low/median/high peer multiples to the target's metric.

    For EV-based multiples the implied value is EV, converted to equity via
    selected net debt. For P/E the result is already equity value.
    """
    low_m, mid_m, hi_m = stats.get("p25"), stats.get("median"), stats.get("p75")

    def _per_share_from_ev(ev_val):
        if ev_val is None:
            return None
        eq = ev_val - float(net_debt_used or 0.0)
        return round(eq / shares_used, 4) if shares_used and shares_used > 0 else None

    def _per_share_from_equity(eq_val):
        if eq_val is None:
            return None
        return round(eq_val / shares_used, 4) if shares_used and shares_used > 0 else None

    if stats.get("insufficient_data") or metric_value is None:
        return {
            "multiple_kind": multiple_kind,
            "metric_used": round(metric_value, 4) if metric_value is not None else None,
            "multiple_low": low_m,
            "multiple_median": mid_m,
            "multiple_high": hi_m,
            "implied_value_low": None,
            "implied_value_mid": None,
            "implied_value_high": None,
            "iv_per_share_low": None,
            "iv_per_share_mid": None,
            "iv_per_share_high": None,
            "value_kind": "EV" if multiple_kind in {"ev_revenue", "ev_ebitda"} else "Equity",
            "suppressed_reason": (
                stats.get("insufficient_reason")
                if stats.get("insufficient_data")
                else "Target metric unavailable"
            ),
        }

    if multiple_kind in {"ev_revenue", "ev_ebitda"}:
        low_v = (metric_value * low_m) if low_m is not None else None
        mid_v = (metric_value * mid_m) if mid_m is not None else None
        high_v = (metric_value * hi_m) if hi_m is not None else None
        return {
            "multiple_kind": multiple_kind,
            "metric_used": round(metric_value, 4),
            "multiple_low": low_m,
            "multiple_median": mid_m,
            "multiple_high": hi_m,
            "implied_value_low": round(low_v, 4) if low_v is not None else None,
            "implied_value_mid": round(mid_v, 4) if mid_v is not None else None,
            "implied_value_high": round(high_v, 4) if high_v is not None else None,
            "iv_per_share_low": _per_share_from_ev(low_v),
            "iv_per_share_mid": _per_share_from_ev(mid_v),
            "iv_per_share_high": _per_share_from_ev(high_v),
            "value_kind": "EV",
        }

    # P/E case
    low_v = (metric_value * low_m) if low_m is not None else None
    mid_v = (metric_value * mid_m) if mid_m is not None else None
    high_v = (metric_value * hi_m) if hi_m is not None else None
    return {
        "multiple_kind": multiple_kind,
        "metric_used": round(metric_value, 4),
        "multiple_low": low_m,
        "multiple_median": mid_m,
        "multiple_high": hi_m,
        "implied_value_low": round(low_v, 4) if low_v is not None else None,
        "implied_value_mid": round(mid_v, 4) if mid_v is not None else None,
        "implied_value_high": round(high_v, 4) if high_v is not None else None,
        "iv_per_share_low": _per_share_from_equity(low_v),
        "iv_per_share_mid": _per_share_from_equity(mid_v),
        "iv_per_share_high": _per_share_from_equity(high_v),
        "value_kind": "Equity",
    }


# ── Top-level entry point ──────────────────────────────────────────────────


def build_trading_comps(
    symbol: str,
    target_financials: Optional[dict] = None,
    net_debt_used: float = 0.0,
    shares_used: float = 1.0,
    peer_tickers: Optional[list[str]] = None,
    use_cache: bool = True,
    target_model_basis: Optional[dict] = None,
) -> dict:
    """Build the V3.7.7 Trading Comps payload for ``symbol``.

    ``target_financials`` is a dict providing the target's metrics in the SAME
    raw-actual scale as the peer data (yfinance reports in actual local
    currency, not millions). Expected keys: revenue, ebitda, net_income,
    market_cap. If missing, fetched live from yfinance.
    """
    sym = symbol.strip().upper()
    profile = get_trading_comps_profile(sym, peer_tickers=peer_tickers)
    if not profile.get("supported"):
        return _unavailable_trading_comps_payload(sym, profile)
    peers_resolved, peer_source = resolve_peer_tickers(sym, peer_tickers)
    warnings: list[str] = []

    # Target metrics. If caller didn't pass them, fetch live (yfinance scale).
    if target_financials is None:
        target_raw = fetch_peer_market_data(sym, use_cache=use_cache)
    else:
        target_raw = {
            "ticker": sym,
            "name": target_financials.get("name") or sym,
            "currency": target_financials.get("currency") or "USD",
            "market_cap": _safe_float(target_financials.get("market_cap")),
            "enterprise_value": _safe_float(target_financials.get("enterprise_value")),
            "revenue": _safe_float(target_financials.get("revenue")),
            "ebitda": _safe_float(target_financials.get("ebitda")),
            "net_income": _safe_float(target_financials.get("net_income")),
            "source": target_financials.get("source") or "caller_supplied",
            "status": "ok",
        }

    # Peer set fetch.
    peer_rows: list[dict] = []
    for ticker in peers_resolved:
        raw = fetch_peer_market_data(ticker, use_cache=use_cache)
        computed = _compute_peer_multiples(raw)
        peer_rows.append({
            "ticker": ticker,
            "name": raw.get("name"),
            "currency": raw.get("currency"),
            "sector": raw.get("sector"),
            "industry": raw.get("industry"),
            "raw": raw,
            "multiples": computed["multiples"],
            "exclusions": computed["exclusions"],
        })

    _flag_outliers(peer_rows)

    # V3.9.3: attach peer category + rationale and per-multiple inclusion flags.
    # included_in_stats[key] drives summary stats; the aggregated booleans
    # included_in_stats_any / included_in_stats_all describe overall posture.
    for r in peer_rows:
        ticker = (r.get("ticker") or "").upper()
        role = _peer_role(sym, ticker)
        r["peer_role"] = role
        base_category = PEER_CATEGORIES.get(ticker, PEER_CATEGORY_DEFAULT)
        r["category"] = f"{role}: {base_category}" if sym == "AAPL" else base_category
        r["rationale"] = PEER_RATIONALE.get(
            ticker, "Reference peer; review for industry alignment before drawing conclusions."
        )
        if sym == "AAPL" and role == "Diagnostic":
            diagnostic_reason = (
                "AAPL diagnostic semiconductor peer excluded from core statistics; "
                "semis / AI-cycle multiples are not direct Apple ecosystem-platform comps"
            )
            r["rationale"] = f"{r['rationale']} Diagnostic only for market context; excluded from AAPL core statistics."
            exclusions = r.setdefault("exclusions", {})
            for key in ("ev_revenue", "ev_ebitda", "pe"):
                exclusions[key] = diagnostic_reason
        per_mult = _peer_inclusion_flags(r)
        r["included_in_stats"] = per_mult
        r["included_in_stats_any"] = any(per_mult.values())
        r["included_in_stats_all"] = all(per_mult.values())
        raw = r.get("raw") or {}
        fs = raw.get("field_sources") or {}
        has_price = _safe_float(raw.get("price")) is not None
        has_market = _safe_float(raw.get("market_cap")) is not None or _safe_float(raw.get("enterprise_value")) is not None
        has_profit_metric = _safe_float(raw.get("ebitda")) is not None or _safe_float(raw.get("net_income")) is not None
        has_main = has_price and has_market and _safe_float(raw.get("revenue")) is not None and has_profit_metric
        if has_main and not raw.get("cache_stale") and "derived" not in fs.values():
            r["data_quality_tier"] = "OK"
        elif r["included_in_stats_any"] or has_market or _safe_float(raw.get("revenue")) is not None or has_profit_metric:
            r["data_quality_tier"] = "Review"
        else:
            r["data_quality_tier"] = "Insufficient"
        r["field_source_summary"] = ", ".join(
            f"{k}={fs.get(k, 'unavailable')}"
            for k in ("price", "market_cap", "enterprise_value", "revenue", "ebitda", "net_income")
        )
        # Aggregated outlier/exclusion summary for sheet display.
        outlier_reasons = r.get("outlier_reasons") or {}
        exclusions = r.get("exclusions") or {}
        any_outlier = any((r.get("outliers") or {}).get(k) for k in ("ev_revenue", "ev_ebitda", "pe"))
        r["outlier_flag"] = any_outlier
        r["outlier_reason"] = "; ".join(
            f"{k}: {outlier_reasons[k]}" for k in ("ev_revenue", "ev_ebitda", "pe")
            if outlier_reasons.get(k)
        ) or None
        r["exclusion_reason"] = "; ".join(
            f"{k}: {exclusions[k]}" for k in ("ev_revenue", "ev_ebitda", "pe")
            if exclusions.get(k)
        ) or None
        # Keep prior key for backwards compatibility.
        r["included_overall"] = r["included_in_stats_any"]

    # Summary stats per multiple.
    stats = {
        "ev_revenue": _summary_stats(peer_rows, "ev_revenue"),
        "ev_ebitda": _summary_stats(peer_rows, "ev_ebitda"),
        "pe": _summary_stats(peer_rows, "pe"),
    }
    for k, kind_label in (("ev_revenue", "EV / Revenue"), ("ev_ebitda", "EV / EBITDA"), ("pe", "P / E")):
        if stats[k]["count"] < 5:
            warnings.append(
                f"{kind_label}: only {stats[k]['count']} valid peers (<5) - confidence low."
            )
    if sym == "AAPL":
        warnings.append(
            "AAPL peer policy: MSFT/GOOGL/META/AMZN/ORCL/ADBE are core included peers; "
            "NVDA/AVGO/QCOM are diagnostic semiconductor references and excluded from summary statistics."
        )

    # AAPL implied valuation. Target metrics use the SAME scale as peer data
    # (yfinance raw actuals). EV-based valuations subtract net_debt_used and
    # divide by shares_used, both also expressed in the workbook's model units
    # (millions for US) - the caller is responsible for matching scales when
    # passing target_financials. fetch_peer_market_data returns raw actuals
    # (e.g. revenue in actual USD), so when target_financials is fetched live
    # we treat the implied EV/Equity in actual USD too.
    target_revenue = _safe_float(target_raw.get("revenue"))
    target_ebitda = _safe_float(target_raw.get("ebitda"))
    target_ni = _safe_float(target_raw.get("net_income"))
    implied = {
        "ev_revenue": _implied_valuation_for_multiple(
            target_revenue, stats["ev_revenue"], "ev_revenue", net_debt_used, shares_used
        ),
        "ev_ebitda": _implied_valuation_for_multiple(
            target_ebitda, stats["ev_ebitda"], "ev_ebitda", net_debt_used, shares_used
        ),
        "pe": _implied_valuation_for_multiple(
            target_ni, stats["pe"], "pe", 0.0, shares_used
        ),
    }

    # Data quality block. V3.9.3 uses the new per-multiple included_in_stats
    # flags so outlier peers cannot leak back into the count.
    total = len(peer_rows)
    included_ev_rev = sum(1 for r in peer_rows if (r.get("included_in_stats") or {}).get("ev_revenue"))
    included_ev_ebitda = sum(1 for r in peer_rows if (r.get("included_in_stats") or {}).get("ev_ebitda"))
    included_pe = sum(1 for r in peer_rows if (r.get("included_in_stats") or {}).get("pe"))
    failed = sum(1 for r in peer_rows if r.get("raw", {}).get("status") != "ok")
    excluded_or_outlier = sum(
        1 for r in peer_rows
        if not (r.get("included_in_stats") or {}).get("ev_revenue")
        and not (r.get("included_in_stats") or {}).get("ev_ebitda")
        and not (r.get("included_in_stats") or {}).get("pe")
    )
    core_rows = [r for r in peer_rows if r.get("peer_role") == "Core"]
    core_total = len(core_rows)
    core_ev_rev = sum(1 for r in core_rows if (r.get("included_in_stats") or {}).get("ev_revenue"))
    core_ev_ebitda = sum(1 for r in core_rows if (r.get("included_in_stats") or {}).get("ev_ebitda"))
    core_pe = sum(1 for r in core_rows if (r.get("included_in_stats") or {}).get("pe"))
    quality_counts = {"live": 0, "cache": 0, "derived": 0, "unavailable": 0}
    for r in peer_rows:
        fs = ((r.get("raw") or {}).get("field_sources") or {})
        for key in ("price", "market_cap", "enterprise_value", "revenue", "ebitda", "net_income", "trailing_pe", "forward_pe"):
            source = fs.get(key) or "unavailable"
            if source not in quality_counts:
                source = "cache" if "cache" in source else "unavailable"
            quality_counts[source] += 1
    quality_total = sum(quality_counts.values()) or 1
    quality_pct = {k: round(v / quality_total, 4) for k, v in quality_counts.items()}
    if core_ev_ebitda >= 4 or core_pe >= 4:
        usability_tier = "Review" if quality_counts.get("derived") or any((r.get("raw") or {}).get("cache_stale") for r in core_rows) else "OK"
    else:
        usability_tier = "Insufficient"

    data_quality = {
        "peer_count_total": total,
        "peer_count_failed_fetch": failed,
        "peer_count_fully_excluded": excluded_or_outlier,
        "peer_count_included_ev_revenue": included_ev_rev,
        "peer_count_included_ev_ebitda": included_ev_ebitda,
        "peer_count_included_pe": included_pe,
        "core_peer_count": core_total,
        "core_peer_ev_revenue_coverage": core_ev_rev,
        "core_peer_ev_ebitda_coverage": core_ev_ebitda,
        "core_peer_pe_coverage": core_pe,
        "source_mix_counts": quality_counts,
        "source_mix_pct": quality_pct,
        "overall_comps_usability_tier": usability_tier,
        "football_field_comps_status": (
            "Trailing comps rows restored"
            if (core_ev_ebitda >= 4 or core_pe >= 4)
            else "Insufficient core peer coverage"
        ),
        "insufficient_peer_threshold": INSUFFICIENT_PEER_THRESHOLD,
        "outlier_policy": {
            "abs_caps": OUTLIER_ABS_CAP,
            "iqr_multiplier": OUTLIER_IQR_K,
        },
    }

    # V3.9.3: target metric source trail + basis reconciliation block.
    target_cache_file = str(_comps_cache_path(sym)) if target_financials is None else "caller_supplied"
    peer_cache_files = {
        (r.get("ticker") or "").upper(): str(_comps_cache_path((r.get("ticker") or "").upper()))
        for r in peer_rows
    }

    basis_block = None
    if target_model_basis:
        model_revenue = _safe_float(target_model_basis.get("revenue"))
        model_ebit = _safe_float(target_model_basis.get("ebit"))
        model_da = _safe_float(target_model_basis.get("da"))
        model_shares = _safe_float(target_model_basis.get("shares"))
        model_net_debt = _safe_float(target_model_basis.get("net_debt"))
        model_price = _safe_float(target_model_basis.get("price"))
        model_ebitda = None
        if model_ebit is not None and model_da is not None:
            model_ebitda = model_ebit + model_da
        # Convert model-basis (millions) into yfinance actual currency scale
        # so reviewers can compare side-by-side without unit confusion.
        scale = 1_000_000.0
        model_revenue_actual = model_revenue * scale if model_revenue is not None else None
        model_ebitda_actual = model_ebitda * scale if model_ebitda is not None else None
        model_market_cap_actual = (
            model_price * model_shares * scale
            if (model_price is not None and model_shares is not None) else None
        )
        model_ev_actual = (
            model_market_cap_actual + (model_net_debt * scale)
            if (model_market_cap_actual is not None and model_net_debt is not None) else None
        )
        def _delta(model_actual, market_actual):
            if model_actual is None or market_actual is None:
                return None
            denom = abs(market_actual) if market_actual else 1.0
            return round((model_actual - market_actual) / denom, 4)
        basis_block = {
            "currency_model": target_model_basis.get("currency"),
            "currency_market": target_raw.get("currency"),
            "model_basis": "Latest available FY annual financials from normalized cache (millions of reporting currency).",
            "market_basis": "yfinance TTM market data (actual currency).",
            "revenue_model_actual": model_revenue_actual,
            "revenue_market_actual": target_revenue,
            "revenue_delta_pct": _delta(model_revenue_actual, target_revenue),
            "ebitda_model_actual": model_ebitda_actual,
            "ebitda_market_actual": target_ebitda,
            "ebitda_delta_pct": _delta(model_ebitda_actual, target_ebitda),
            "market_cap_model_actual": model_market_cap_actual,
            "market_cap_market_actual": _safe_float(target_raw.get("market_cap")),
            "market_cap_delta_pct": _delta(model_market_cap_actual, _safe_float(target_raw.get("market_cap"))),
            "ev_model_actual": model_ev_actual,
            "ev_market_actual": _safe_float(target_raw.get("enterprise_value")),
            "ev_delta_pct": _delta(model_ev_actual, _safe_float(target_raw.get("enterprise_value"))),
            "shares_model_actual": (model_shares * scale) if model_shares is not None else None,
            "net_debt_model_actual": (model_net_debt * scale) if model_net_debt is not None else None,
            "basis_note": (
                "Target Revenue / EBITDA shown in the Peer table use yfinance TTM market data so "
                "they are directly comparable to peer multiples. Model basis above shows the FY annual "
                "values used inside the workbook; differences arise from TTM vs FY cutoff and from "
                "yfinance reclassifications and are diagnostic only."
            ),
        }

    forward_consensus = {
        "ntm_ev_revenue": "N/A - consensus forecast feed not connected",
        "ntm_ev_ebitda": "N/A - consensus forecast feed not connected",
        "ntm_pe": "N/A - consensus forecast feed not connected",
        "note": (
            "Forward consensus multiples are intentionally not included. Connecting an external "
            "consensus feed is out of scope for this release; trailing peer multiples remain the "
            "only cross-check shown."
        ),
    }

    def _forward_row(raw: dict, classification: str) -> dict:
        price = _safe_float(raw.get("price"))
        f_eps = _safe_float(raw.get("forward_eps"))
        f_pe = _safe_float(raw.get("forward_pe"))
        t_pe = _safe_float(raw.get("trailing_pe"))
        if raw.get("status") != "ok":
            classification = "Excluded"
        limitation = []
        if f_eps is None:
            limitation.append("forward EPS unavailable")
        if f_pe is None:
            limitation.append("forward P/E unavailable")
        if t_pe is None:
            limitation.append("trailing P/E unavailable")
        return {
            "ticker": (raw.get("ticker") or "").upper(),
            "company": raw.get("name") or raw.get("ticker"),
            "peer_classification": classification,
            "price": price,
            "forward_eps": f_eps,
            "forward_pe": f_pe,
            "trailing_pe": t_pe,
            "forward_vs_trailing_delta": (f_pe - t_pe) if (f_pe is not None and t_pe is not None) else None,
            "source_availability": raw.get("source") or "yfinance.info",
            "data_limitation_note": "; ".join(limitation) if limitation else "forward and trailing fields available from single feed",
        }

    forward_rows = [_forward_row(target_raw, "Core")]
    for r in peer_rows:
        role = r.get("peer_role") or "Core"
        raw = r.get("raw") or {}
        classification = "Diagnostic" if role == "Diagnostic" else "Core"
        if raw.get("status") != "ok":
            classification = "Excluded"
        forward_rows.append(_forward_row(raw, classification))
    core_peer_rows = [r for r in forward_rows[1:] if r.get("peer_classification") == "Core"]
    core_available = [r for r in core_peer_rows if r.get("forward_pe") is not None and r.get("forward_pe") > 0]
    core_forward_values = [float(r["forward_pe"]) for r in core_available]
    core_trailing_values = [
        float(r["trailing_pe"]) for r in core_peer_rows
        if r.get("trailing_pe") is not None and r.get("trailing_pe") > 0
    ]
    core_forward_median = round(statistics.median(core_forward_values), 4) if core_forward_values else None
    core_trailing_median = round(statistics.median(core_trailing_values), 4) if core_trailing_values else None
    core_total = len(core_peer_rows)
    core_available_count = len(core_available)
    if core_available_count >= 4:
        forward_review_tier = "OK"
    elif core_available_count == 3:
        forward_review_tier = "Review"
    else:
        forward_review_tier = "Insufficient forward coverage"
    target_forward = forward_rows[0]
    forward_summary = {
        "target_forward_pe": target_forward.get("forward_pe"),
        "target_trailing_pe": target_forward.get("trailing_pe"),
        "core_peer_forward_pe_median": core_forward_median,
        "core_peer_trailing_pe_median": core_trailing_median,
        "core_forward_available_count": core_available_count,
        "core_peer_count": core_total,
        "review_tier": forward_review_tier,
        "interpretation": (
            "Insufficient forward coverage - trailing comps remain primary diagnostic."
            if core_available_count < 3
            else (
                f"{sym} forward P/E (one-feed diagnostic) is "
                f"{target_forward.get('forward_pe'):.1f}x vs core peer median {core_forward_median:.1f}x; "
                "spread is directional only due to single-source data limitation."
                if target_forward.get("forward_pe") is not None and core_forward_median is not None
                else "Forward P/E comparison unavailable for target or core peer median."
            )
        ),
        "disclosure": (
            "Forward P/E values are sourced from yfinance.info.forwardPE / available one-feed data. "
            "They are NOT FactSet / Refinitiv multi-analyst consensus medians. Analyst count, dispersion, "
            "and update timestamp are not available through this feed. Use as directional diagnostic only; "
            "validate against institutional consensus feed before relying in IC discussion."
        ),
    }

    high_52 = _safe_float(target_raw.get("fifty_two_week_high"))
    low_52 = _safe_float(target_raw.get("fifty_two_week_low"))
    market_price = _safe_float(target_raw.get("price"))
    percentile = None
    if market_price is not None and high_52 is not None and low_52 is not None and high_52 > low_52:
        percentile = (market_price - low_52) / (high_52 - low_52)
    market_context = {
        "current_price": market_price,
        "fifty_two_week_high": high_52,
        "fifty_two_week_low": low_52,
        "current_price_percentile": round(percentile, 6) if percentile is not None else None,
        "source": target_raw.get("source") or "yfinance.info",
        "price_source": (target_raw.get("field_sources") or {}).get("price") or "unavailable",
        "range_source": (
            (target_raw.get("field_sources") or {}).get("fifty_two_week_high")
            or (target_raw.get("field_sources") or {}).get("fifty_two_week_low")
            or "unavailable"
        ),
        "history_cache_file": target_raw.get("history_cache_file"),
        "disclosure": "52-week price range reflects market trading history, not valuation. Shown for IC context only; not a valuation reference.",
    }

    return {
        "version": COMPS_VERSION,
        "status": "ok",
        "symbol": sym,
        "profile": profile,
        "profile_id": profile.get("profile_id"),
        "peer_set_source": peer_source,
        "peer_source": peer_source,
        "peer_set_requested": peers_resolved,
        "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "target": {
            "ticker": sym,
            "name": target_raw.get("name"),
            "currency": target_raw.get("currency"),
            "revenue": target_revenue,
            "ebitda": target_ebitda,
            "net_income": target_ni,
            "market_cap": _safe_float(target_raw.get("market_cap")),
            "enterprise_value": _safe_float(target_raw.get("enterprise_value")),
            "price": _safe_float(target_raw.get("price")),
            "fifty_two_week_high": _safe_float(target_raw.get("fifty_two_week_high")),
            "fifty_two_week_low": _safe_float(target_raw.get("fifty_two_week_low")),
            "forward_eps": _safe_float(target_raw.get("forward_eps")),
            "forward_pe": _safe_float(target_raw.get("forward_pe")),
            "trailing_pe": _safe_float(target_raw.get("trailing_pe")),
            "net_debt_used_actual_currency": float(net_debt_used or 0.0),
            "shares_used": float(shares_used or 0.0),
            "source": target_raw.get("source"),
            "field_sources": target_raw.get("field_sources") or {},
            "cache_file": target_cache_file,
        },
        "target_model_basis": basis_block,
        "forward_consensus": forward_consensus,
        "forward_diagnostic": {
            "rows": forward_rows,
            "summary": forward_summary,
        },
        "market_context": market_context,
        "peer_rows": peer_rows,
        "peer_cache_files": peer_cache_files,
        "summary_stats": stats,
        "implied_valuation": implied,
        "data_quality": data_quality,
        "methodology_note": (
            "V3.9.8.6 Trading Comps v2: peer set is a configurable reference (not rating guidance). "
            "Each peer carries category, rationale, and per-multiple included_in_stats flags. "
            "Outliers (absolute cap or 3x IQR) and exclusions (missing or non-positive metric) are "
            "shown in the peer table but removed from summary statistics. Implied IV/share ranges "
            "are suppressed for any multiple with fewer than "
            f"{INSUFFICIENT_PEER_THRESHOLD} included peers."
        ),
        "peer_philosophy_note": (
            "AAPL core statistics emphasize mega-cap platform / ecosystem / consumer-tech comparables. "
            "Semiconductor peers remain visible as diagnostic context but are excluded from AAPL core multiple statistics. "
            "Samsung and Sony are not connected through the current yfinance peer feed; no substitute data is fabricated."
            if sym == "AAPL" else None
        ),
        "no_recommendation_note": (
            "Trading Comps are a diagnostic market cross-check, not the primary valuation output. "
            "Reviewers should validate the peer set, currency / basis consistency, and outlier "
            "policy before drawing conclusions. Wide ranges typically reflect dispersion across "
            "business models rather than a model reference range. Not an investment recommendation."
        ),
        "warnings": warnings,
    }
