"""V3.9.11 — industry classification for default-quality + DCF-suitability banners.

V3.9.11 base layer defined:
  - INDUSTRY_MARGIN_P95 — economic_sanity threshold per industry
  - TICKER_TO_INDUSTRY — explicit whitelist
  - classify_industry()

V3.9.11 Batch 2A extension:
  - MODEL_UNSUITABLE_INDUSTRIES — DCF FCFF assumptions break (bank/insurance/REIT/...)
  - DCF_CAUTION_INDUSTRIES — DCF usable but warrants a soft caveat (fintech/clinical biotech)
  - Expanded TICKER_TO_INDUSTRY with ~30 financial / REIT / fintech / biotech tickers
  - Expanded INDUSTRY_MARGIN_P95 to cover the new buckets (banks won't actually fire
    economic_sanity because hard banner pre-empts; entries kept for completeness)

Discipline: only add tickers we have a concrete need for. Do not preemptively expand.
"""

INDUSTRY_MARGIN_P95 = {
    "consumer_staples_premium": 0.70,
    "luxury": 0.45,
    "tobacco": 0.50,
    "tech_software": 0.50,
    "tech_internet_platform": 0.40,
    "exchange_financial_infra": 0.80,
    "energy_upstream": 0.50,
    "biotech_mature": 0.40,
    "cro_cdmo_pharma": 0.30,
    "manufacturing_general": 0.25,
    "_default_unknown": 0.40,
    # Batch 2A — financial / REIT / fintech / clinical biotech
    "bank": 0.50,                  # DCF unsuitable; hard banner pre-empts
    "insurance_life": 0.30,
    "insurance_property": 0.20,
    "broker_dealer": 0.35,
    "asset_manager": 0.50,
    "reit": 0.55,                  # REIT 高 margin 是常态 (rental income)
    "mortgage_lender": 0.40,
    "fintech_payment": 0.50,       # V/MA/PYPL high margin is normal
    "biotech_clinical_stage": 0.0, # negative margin is normal; P95 set to 0
}

MODEL_UNSUITABLE_INDUSTRIES = {
    "exchange_financial_infra",
    "bank",
    "insurance_life",
    "insurance_property",
    "broker_dealer",
    "asset_manager",
    "reit",
    "mortgage_lender",
}

DCF_CAUTION_INDUSTRIES = {
    "fintech_payment",
    "biotech_clinical_stage",
}

# ── V3.9.11 Batch 2B F014 — sector-differentiated SBC dilution floor ─────────
# Used by dcf_calculator.py as the fallback default when historical SBC data
# is unavailable for a ticker (the data-driven SBC / market-cap path always
# takes precedence when present). Pre-F014 this was a flat 0.25% across all
# industries, materially under-diluting SaaS/biotech and slightly over-
# diluting consumer staples / energy. Values calibrated against US 10-K
# medians; _default_unknown kept at 0.25% for backward compatibility.
INDUSTRY_SBC_FLOOR = {
    "tech_software": 0.020,              # 2.0% — SaaS SBC is the comp model
    "tech_internet_platform": 0.015,     # 1.5% — large platforms slightly lower
    "fintech_payment": 0.015,            # 1.5% — software-like
    "biotech_clinical_stage": 0.030,     # 3.0% — SBC is primary compensation
    "biotech_mature": 0.010,             # 1.0%
    "consumer_staples_premium": 0.0010,  # 0.1% — Maotai/tobacco essentially none
    "luxury": 0.0010,                    # 0.1%
    "tobacco": 0.0010,                   # 0.1%
    "energy_upstream": 0.0020,           # 0.2%
    "manufacturing_general": 0.0020,
    "cro_cdmo_pharma": 0.0030,
    "exchange_financial_infra": 0.0020,
    "bank": 0.0020,
    "insurance_life": 0.0020,
    "insurance_property": 0.0020,
    "broker_dealer": 0.0050,
    "asset_manager": 0.0050,
    "reit": 0.0010,
    "mortgage_lender": 0.0020,
    "_default_unknown": 0.0025,          # legacy 0.25% backstop
}

# Floors above this threshold are "elevated" and trigger an audit warning so
# users see why the fallback default jumped vs the legacy 0.25%.
SBC_FLOOR_LEGACY_BASELINE = 0.0025

TICKER_TO_INDUSTRY = {
    # ── V3.9.11 base ───────────────────────────────────────────
    # A 股白酒龙头
    "600519.SS": "consumer_staples_premium",
    "000858.SZ": "consumer_staples_premium",
    "000568.SZ": "consumer_staples_premium",
    "600809.SS": "consumer_staples_premium",
    # 港股龙头
    "0388.HK": "exchange_financial_infra",
    "0883.HK": "energy_upstream",
    "0700.HK": "tech_internet_platform",
    # CRO/CDMO
    "2359.HK": "cro_cdmo_pharma",
    "3759.HK": "cro_cdmo_pharma",
    "603259.SS": "cro_cdmo_pharma",
    # 美股锚定
    "AAPL": "tech_software",

    # ── Batch 2A — US banks ────────────────────────────────────
    "JPM": "bank",
    "BAC": "bank",
    "WFC": "bank",
    "C": "bank",
    # US broker-dealers
    "GS": "broker_dealer",
    "MS": "broker_dealer",
    # US asset managers / holdco
    "BRK.A": "asset_manager",
    "BRK.B": "asset_manager",
    "BX": "asset_manager",
    "BLK": "asset_manager",
    # US REITs
    "O": "reit",
    "SPG": "reit",
    "PLD": "reit",
    "AMT": "reit",
    "EQIX": "reit",
    # US insurance
    "MET": "insurance_life",
    "PRU": "insurance_life",
    "ALL": "insurance_property",
    "PGR": "insurance_property",
    # US fintech / payments
    "V": "fintech_payment",
    "MA": "fintech_payment",
    "PYPL": "fintech_payment",
    "SQ": "fintech_payment",
    "COIN": "fintech_payment",

    # ── Batch 2A — A 股金融 ───────────────────────────────────
    "601318.SS": "insurance_life",   # 中国平安
    "601628.SS": "insurance_life",   # 中国人寿
    "600030.SS": "broker_dealer",    # 中信证券
    "601398.SS": "bank",             # 工商银行
    "601288.SS": "bank",             # 农业银行
    "601988.SS": "bank",             # 中国银行
    "601939.SS": "bank",             # 建设银行
    "000001.SZ": "bank",             # 平安银行 (V3.2.7 -261/股那只)

    # ── Batch 2A — 港股金融 ───────────────────────────────────
    "0005.HK": "bank",               # 汇丰
    "0011.HK": "bank",               # 恒生银行
    "1299.HK": "insurance_life",     # 友邦
    "1398.HK": "bank",               # 工商银行 H
    "3988.HK": "bank",               # 中国银行 H
    "2318.HK": "insurance_life",     # 中国平安 H
}


def _normalize_ticker(ticker: str) -> str:
    """Case-insensitive matching; preserve dotted forms (BRK.B, 600519.SS)."""
    if not isinstance(ticker, str):
        return ""
    return ticker.strip().upper()


def classify_industry(ticker: str, profile: dict) -> str:
    """Return industry bucket key. profile is the dict from _default_quality_profile."""
    key = _normalize_ticker(ticker)
    if key in TICKER_TO_INDUSTRY:
        return TICKER_TO_INDUSTRY[key]
    profile = profile or {}
    if profile.get("is_financial"):
        return "exchange_financial_infra"
    if profile.get("is_software_like"):
        return "tech_software"
    if profile.get("is_pharma_or_manufacturing"):
        return "cro_cdmo_pharma"
    return "_default_unknown"
