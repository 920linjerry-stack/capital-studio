"""V6 exposure profiles + portfolio adapter.

Two responsibilities:

1. A built-in registry of :class:`HoldingExposure` fingerprints for the tickers
   covered by the public demo portfolios and common cross-asset examples, so
   the deterministic sample remains useful without bundling private holdings.

2. A thin adapter (:func:`build_portfolio`) that takes whatever holdings the
   caller has -- application holdings, synthetic sample rows, or nothing -- and returns a normalized list of ``(exposure, weight)`` pairs.
   Weights come from cost basis when available, else equal-weight fallback that
   is clearly flagged. Unknown tickers get a neutral generic fingerprint so the
   engine degrades gracefully instead of dropping the holding.

No network, no live quotes: weighting uses only fields already present in the
holding dict (cost_price * quantity), so the engine runs fully offline.
"""

from __future__ import annotations

from typing import Any

from modeling.v6.schemas import HoldingExposure


# --- Built-in exposure registry ------------------------------------------
# Hand-curated, deterministic fingerprints. Tags are the vocabulary the
# fixtures/classifier emit into ``affected_tags``. Keep tag names stable.
_PROFILES: dict[str, HoldingExposure] = {
    "AAPL": HoldingExposure(
        ticker="AAPL",
        name="Apple Inc.",
        aliases=["apple"],
        sector="Technology",
        asset_type="equity",
        factor_tags=["us_tech", "megacap", "consumer_hardware", "ai_device", "growth", "high_duration_growth", "dollar_sensitive"],
        # Signed beta vs. the event's broad direction: growth/tech moves WITH
        # the market reaction to rates/yields/inflation, so betas are POSITIVE.
        macro_sensitivity={"rates": 0.6, "yields": 0.6, "inflation": 0.5, "real_yields_up": -0.6, "dollar_up": -0.3, "china_demand": 0.3},
        second_order_exposure=["semiconductors", "ai_capex", "china_supply_chain"],
        reflexivity_exposure=0.8,
    ),
    "0700.HK": HoldingExposure(
        ticker="0700.HK",
        name="Tencent Holdings",
        aliases=["tencent", "腾讯"],
        sector="Communication Services",
        asset_type="equity",
        factor_tags=["china_tech", "internet", "gaming", "ai", "growth", "megacap"],
        macro_sensitivity={"rates": 0.5, "china_demand": 0.6, "china_regulation": 0.7},
        second_order_exposure=["ai_capex", "risk_sentiment"],
        reflexivity_exposure=0.75,
    ),
    "600519.SS": HoldingExposure(
        ticker="600519.SS",
        name="Kweichow Moutai",
        aliases=["moutai", "茅台", "贵州茅台"],
        sector="Consumer Staples",
        asset_type="equity",
        factor_tags=["china_consumer", "luxury", "defensive", "domestic_demand"],
        macro_sensitivity={"china_demand": 0.7, "rates": 0.1, "inflation": 0.2},
        second_order_exposure=["risk_sentiment"],
        reflexivity_exposure=0.35,
    ),
    "300750.SZ": HoldingExposure(
        ticker="300750.SZ",
        name="CATL (Contemporary Amperex)",
        aliases=["catl", "宁德时代"],
        sector="Industrials",
        asset_type="equity",
        factor_tags=["ev_battery", "china_manufacturing", "green_energy", "growth", "commodities"],
        macro_sensitivity={"china_demand": 0.6, "rates": 0.5, "commodities": 0.4},
        second_order_exposure=["semiconductors", "ai_capex", "auto_demand"],
        reflexivity_exposure=0.55,
    ),
    "000001.SZ": HoldingExposure(
        ticker="000001.SZ",
        name="Ping An Bank",
        aliases=["ping an bank", "平安银行"],
        sector="Financials",
        asset_type="equity",
        factor_tags=["china_financials", "banks", "value", "rate_sensitive"],
        # Banks are CONTRA to growth on rates: a (broadly bullish) rate cut
        # squeezes net interest margin, and (broadly bearish) rising yields help
        # them -> negative betas vs. the event's broad direction.
        macro_sensitivity={"yields": -0.6, "rates": -0.6, "china_demand": 0.4},
        second_order_exposure=["risk_sentiment", "credit_cycle"],
        reflexivity_exposure=0.4,
    ),
    "600030.SS": HoldingExposure(
        ticker="600030.SS",
        name="CITIC Securities",
        aliases=["citic securities", "中信证券"],
        sector="Financials",
        asset_type="equity",
        factor_tags=["china_financials", "brokers", "high_beta", "risk_on_proxy"],
        macro_sensitivity={"yields": 0.2, "china_demand": 0.5},
        # Brokers are the classic risk-on/turnover proxy.
        second_order_exposure=["risk_sentiment", "market_turnover"],
        reflexivity_exposure=0.7,
    ),
    "601318.SS": HoldingExposure(
        ticker="601318.SS",
        name="Ping An Insurance",
        aliases=["ping an", "ping an insurance", "中国平安"],
        sector="Financials",
        asset_type="equity",
        factor_tags=["china_financials", "insurance", "rate_sensitive", "value"],
        # Insurers benefit from higher long-end yields (reinvestment) and are
        # hurt by cuts -> contra betas vs. the event's broad direction.
        macro_sensitivity={"yields": -0.6, "rates": -0.4, "china_demand": 0.4},
        second_order_exposure=["risk_sentiment", "credit_cycle"],
        reflexivity_exposure=0.45,
    ),
    "2359.HK": HoldingExposure(
        ticker="2359.HK",
        name="WuXi AppTec",
        aliases=["wuxi apptec", "药明康德"],
        sector="Health Care",
        asset_type="equity",
        factor_tags=["china_pharma", "cro", "biotech", "growth", "us_regulatory_risk"],
        macro_sensitivity={"rates": 0.4, "china_demand": 0.3, "us_regulation": 0.8},
        second_order_exposure=["biotech_funding", "risk_sentiment"],
        reflexivity_exposure=0.6,
    ),
    # A couple of common US names so user-added tickers also resolve.
    "NVDA": HoldingExposure(
        ticker="NVDA",
        name="NVIDIA Corp.",
        aliases=["nvidia"],
        sector="Technology",
        asset_type="equity",
        factor_tags=["us_tech", "semiconductors", "ai_capex", "growth", "megacap", "high_beta", "high_duration_growth", "dollar_sensitive"],
        macro_sensitivity={"rates": 0.8, "yields": 0.8, "real_yields_up": -0.8, "dollar_up": -0.25},
        second_order_exposure=["ai_capex", "data_center_demand"],
        reflexivity_exposure=0.9,
    ),
    "MSFT": HoldingExposure(
        ticker="MSFT",
        name="Microsoft Corp.",
        aliases=["microsoft"],
        sector="Technology",
        asset_type="equity",
        factor_tags=["us_tech", "megacap", "cloud", "ai", "growth", "high_duration_growth", "dollar_sensitive"],
        macro_sensitivity={"rates": 0.6, "yields": 0.6, "real_yields_up": -0.6, "dollar_up": -0.25},
        second_order_exposure=["ai_capex", "semiconductors"],
        reflexivity_exposure=0.7,
    ),
}

# Wave-2 coverage: additional US large caps + ETF / leveraged / factor assets.
# Same signed-beta-vs-broad-direction convention (growth = +rates/+yields;
# banks = contra/negative; see schemas.py).
_PROFILES_EXTRA: dict[str, HoldingExposure] = {
    "AMD": HoldingExposure(
        ticker="AMD", name="Advanced Micro Devices", aliases=["amd"],
        sector="Technology", asset_type="equity",
        factor_tags=["us_tech", "semiconductors", "ai_capex", "growth", "high_beta", "high_duration_growth", "dollar_sensitive"],
        macro_sensitivity={"rates": 0.7, "yields": 0.7, "real_yields_up": -0.75, "dollar_up": -0.25},
        second_order_exposure=["ai_capex", "data_center_demand"],
        reflexivity_exposure=0.85,
    ),
    "TSLA": HoldingExposure(
        ticker="TSLA", name="Tesla Inc.", aliases=["tesla"],
        sector="Consumer Discretionary", asset_type="equity",
        factor_tags=["us_tech", "ev_auto", "growth", "megacap", "high_beta", "high_duration_growth"],
        macro_sensitivity={"rates": 0.7, "yields": 0.7, "real_yields_up": -0.8},
        second_order_exposure=["auto_demand", "commodities", "ai_capex"],
        reflexivity_exposure=0.95,
    ),
    "META": HoldingExposure(
        ticker="META", name="Meta Platforms", aliases=["meta", "facebook"],
        sector="Communication Services", asset_type="equity",
        factor_tags=["us_tech", "internet", "advertising", "ai", "growth", "megacap", "high_duration_growth", "dollar_sensitive"],
        macro_sensitivity={"rates": 0.55, "yields": 0.55, "real_yields_up": -0.55, "dollar_up": -0.2, "us_regulation": 0.4},
        second_order_exposure=["ai_capex", "semiconductors"],
        reflexivity_exposure=0.7,
    ),
    "GOOGL": HoldingExposure(
        ticker="GOOGL", name="Alphabet Inc.", aliases=["google", "alphabet"],
        sector="Communication Services", asset_type="equity",
        factor_tags=["us_tech", "internet", "advertising", "ai", "cloud", "growth", "megacap", "high_duration_growth", "dollar_sensitive"],
        macro_sensitivity={"rates": 0.55, "yields": 0.55, "real_yields_up": -0.55, "dollar_up": -0.2, "us_regulation": 0.45},
        second_order_exposure=["ai_capex", "semiconductors"],
        reflexivity_exposure=0.65,
    ),
    "JPM": HoldingExposure(
        ticker="JPM", name="JPMorgan Chase", aliases=["jpmorgan", "jp morgan"],
        sector="Financials", asset_type="equity",
        factor_tags=["us_financials", "banks", "value", "rate_sensitive", "credit_stress_sensitive", "yield_curve_sensitive", "bank_rate_beneficiary"],
        # Contra to growth on rates: a broadly-bullish rate cut compresses NIM.
        macro_sensitivity={"yields": -0.5, "rates": -0.5, "yield_curve_steepening": 0.7, "credit_stress": -0.9},
        second_order_exposure=["credit_cycle", "risk_sentiment"],
        reflexivity_exposure=0.4,
    ),
    "XOM": HoldingExposure(
        ticker="XOM", name="Exxon Mobil", aliases=["exxon"],
        sector="Energy", asset_type="equity",
        factor_tags=["energy", "oil", "value", "commodities", "defensive", "commodity_beneficiary", "oil_up_beneficiary", "inflation_hedge"],
        # Energy benefits from hot inflation (bearish-broad) -> contra/negative.
        macro_sensitivity={"inflation": -0.5, "rates": 0.1, "oil_up": 0.9, "commodity_inflation": 0.7, "inflation_fear": 0.4},
        second_order_exposure=["commodities", "oil_price"],
        reflexivity_exposure=0.3,
    ),
    "UNH": HoldingExposure(
        ticker="UNH", name="UnitedHealth Group", aliases=["unitedhealth"],
        sector="Health Care", asset_type="equity",
        factor_tags=["healthcare", "managed_care", "defensive"],
        macro_sensitivity={"us_regulation": 0.6, "rates": 0.2, "risk_off": 0.2},
        second_order_exposure=["risk_sentiment"],
        reflexivity_exposure=0.4,
    ),
    "TSM": HoldingExposure(
        ticker="TSM", name="Taiwan Semiconductor", aliases=["tsmc", "taiwan semi"],
        sector="Technology", asset_type="adr",
        factor_tags=["semiconductors", "ai_capex", "growth", "taiwan", "geopolitical", "high_duration_growth", "dollar_sensitive"],
        macro_sensitivity={"rates": 0.6, "yields": 0.6, "real_yields_up": -0.65, "dollar_up": -0.2, "us_regulation": 0.4},
        second_order_exposure=["ai_capex", "data_center_demand"],
        reflexivity_exposure=0.7,
    ),
    "QQQ": HoldingExposure(
        ticker="QQQ", name="Invesco QQQ (Nasdaq-100)", aliases=["nasdaq 100", "nasdaq"],
        sector="Index ETF", asset_type="etf",
        factor_tags=["us_tech", "growth", "index", "megacap", "high_duration_growth", "dollar_sensitive"],
        macro_sensitivity={"rates": 0.6, "yields": 0.6, "real_yields_up": -0.65, "dollar_up": -0.2},
        second_order_exposure=["ai_capex", "semiconductors", "risk_sentiment"],
        reflexivity_exposure=0.6,
    ),
    "TQQQ": HoldingExposure(
        ticker="TQQQ", name="ProShares UltraPro QQQ (3x)", aliases=["3x nasdaq"],
        sector="Leveraged ETF", asset_type="etf_leveraged",
        factor_tags=["us_tech", "growth", "index", "leveraged", "high_beta", "high_duration_growth", "leveraged_growth", "dollar_sensitive"],
        # 3x daily Nasdaq: extreme sensitivity to rates expectations + risk appetite.
        macro_sensitivity={"rates": 0.9, "yields": 0.9, "real_yields_up": -0.95, "dollar_up": -0.3},
        second_order_exposure=["ai_capex", "semiconductors", "risk_sentiment"],
        reflexivity_exposure=0.97,
    ),
    "SGOV": HoldingExposure(
        ticker="SGOV", name="iShares 0-3 Month Treasury (T-bills)", aliases=["t-bills", "tbill"],
        sector="Cash / Short Treasury ETF", asset_type="etf_bond",
        factor_tags=["cash", "defensive", "short_duration"],
        # Near cash: NAV ~flat; only a mild negative read on rate cuts (lower yield).
        macro_sensitivity={"rates": -0.1},
        second_order_exposure=[],
        reflexivity_exposure=0.0,
    ),
    "GLD": HoldingExposure(
        ticker="GLD", name="SPDR Gold Shares", aliases=["gold"],
        sector="Commodity ETF", asset_type="etf_commodity",
        # Gold's hedge channels are explicit and may conflict: inflation fear /
        # risk-off support versus real-yield / dollar pressure.
        factor_tags=["gold", "safe_haven", "commodities", "defensive", "commodity_beneficiary", "inflation_hedge", "real_yields_sensitive", "dollar_sensitive"],
        macro_sensitivity={"inflation": -0.4, "yields": 0.3, "rates": -0.2, "inflation_fear": 0.8, "risk_off": 0.8, "real_yields_up": -0.85, "dollar_up": -0.75},
        second_order_exposure=[],
        reflexivity_exposure=0.0,
    ),
}

# Wave-3 coverage: more megacaps, financials, energy, healthcare, and the
# common sector / index / commodity ETFs. Same signed-beta convention.
_PROFILES_WAVE3: dict[str, HoldingExposure] = {
    "AMZN": HoldingExposure(
        ticker="AMZN", name="Amazon.com", aliases=["amazon"],
        sector="Consumer Discretionary", asset_type="equity",
        factor_tags=["us_tech", "internet", "ecommerce", "cloud", "ai", "growth", "megacap", "high_duration_growth", "dollar_sensitive"],
        macro_sensitivity={"rates": 0.55, "yields": 0.55, "real_yields_up": -0.6, "dollar_up": -0.2},
        second_order_exposure=["ai_capex", "consumer_demand", "semiconductors"],
        reflexivity_exposure=0.7,
    ),
    "AVGO": HoldingExposure(
        ticker="AVGO", name="Broadcom Inc.", aliases=["broadcom"],
        sector="Technology", asset_type="equity",
        factor_tags=["us_tech", "semiconductors", "ai_capex", "growth", "megacap", "high_beta", "high_duration_growth", "dollar_sensitive"],
        macro_sensitivity={"rates": 0.7, "yields": 0.7, "real_yields_up": -0.7, "dollar_up": -0.25},
        second_order_exposure=["ai_capex", "data_center_demand"],
        reflexivity_exposure=0.8,
    ),
    "ASML": HoldingExposure(
        ticker="ASML", name="ASML Holding", aliases=["asml"],
        sector="Technology", asset_type="adr",
        factor_tags=["semiconductors", "ai_capex", "growth", "europe", "geopolitical", "high_duration_growth", "dollar_sensitive"],
        macro_sensitivity={"rates": 0.65, "yields": 0.65, "real_yields_up": -0.65, "dollar_up": -0.2, "us_regulation": 0.4},
        second_order_exposure=["ai_capex", "semiconductors", "data_center_demand"],
        reflexivity_exposure=0.75,
    ),
    "BAC": HoldingExposure(
        ticker="BAC", name="Bank of America", aliases=["bank of america"],
        sector="Financials", asset_type="equity",
        factor_tags=["us_financials", "banks", "value", "rate_sensitive", "credit_stress_sensitive", "yield_curve_sensitive", "bank_rate_beneficiary"],
        macro_sensitivity={"yields": -0.5, "rates": -0.5, "yield_curve_steepening": 0.7, "credit_stress": -0.95},
        second_order_exposure=["credit_cycle", "risk_sentiment"],
        reflexivity_exposure=0.4,
    ),
    "GS": HoldingExposure(
        ticker="GS", name="Goldman Sachs", aliases=["goldman sachs", "goldman"],
        sector="Financials", asset_type="equity",
        factor_tags=["us_financials", "brokers", "investment_bank", "high_beta", "risk_on_proxy", "credit_stress_sensitive", "yield_curve_sensitive", "bank_rate_beneficiary"],
        macro_sensitivity={"yields": -0.2, "rates": -0.2, "yield_curve_steepening": 0.4, "credit_stress": -0.75},
        second_order_exposure=["market_turnover", "credit_cycle", "risk_sentiment"],
        reflexivity_exposure=0.6,
    ),
    "CVX": HoldingExposure(
        ticker="CVX", name="Chevron Corp.", aliases=["chevron"],
        sector="Energy", asset_type="equity",
        factor_tags=["energy", "oil", "value", "commodities", "defensive", "commodity_beneficiary", "oil_up_beneficiary", "inflation_hedge"],
        macro_sensitivity={"inflation": -0.5, "rates": 0.1, "oil_up": 0.9, "commodity_inflation": 0.7, "inflation_fear": 0.4},
        second_order_exposure=["commodities", "oil_price"],
        reflexivity_exposure=0.3,
    ),
    "LLY": HoldingExposure(
        ticker="LLY", name="Eli Lilly", aliases=["eli lilly", "lilly"],
        sector="Health Care", asset_type="equity",
        factor_tags=["healthcare", "pharma", "glp1", "growth", "defensive"],
        macro_sensitivity={"rates": 0.2, "us_regulation": 0.5},
        second_order_exposure=["biotech_funding"],
        reflexivity_exposure=0.5,
    ),
    "NVO": HoldingExposure(
        ticker="NVO", name="Novo Nordisk", aliases=["novo nordisk", "novo"],
        sector="Health Care", asset_type="adr",
        factor_tags=["healthcare", "pharma", "glp1", "growth", "defensive", "europe"],
        macro_sensitivity={"rates": 0.2, "us_regulation": 0.4},
        second_order_exposure=["biotech_funding"],
        reflexivity_exposure=0.5,
    ),
    "SPY": HoldingExposure(
        ticker="SPY", name="SPDR S&P 500 ETF", aliases=["s&p 500", "sp500", "spx"],
        sector="Index ETF", asset_type="etf",
        factor_tags=["us_equity", "index", "broad_market"],
        macro_sensitivity={"rates": 0.4, "yields": 0.4},
        second_order_exposure=["ai_capex", "risk_sentiment"],
        reflexivity_exposure=0.5,
    ),
    "USO": HoldingExposure(
        ticker="USO", name="United States Oil Fund", aliases=["oil", "crude", "wti"],
        sector="Commodity ETF", asset_type="etf_commodity",
        factor_tags=["oil", "commodities", "energy", "commodity_beneficiary", "oil_up_beneficiary", "inflation_hedge"],
        macro_sensitivity={"inflation": -0.5, "oil_up": 1.0, "commodity_inflation": 0.8, "inflation_fear": 0.4},
        second_order_exposure=["oil_price", "commodities"],
        reflexivity_exposure=0.3,
    ),
    "IWM": HoldingExposure(
        ticker="IWM", name="iShares Russell 2000 ETF", aliases=["russell 2000", "small caps"],
        sector="Index ETF", asset_type="etf",
        factor_tags=["us_equity", "small_cap", "index", "high_beta"],
        # Small caps are very rate-sensitive and risk-appetite-driven.
        macro_sensitivity={"rates": 0.7, "yields": 0.7},
        second_order_exposure=["credit_cycle", "risk_sentiment"],
        reflexivity_exposure=0.7,
    ),
    "XLF": HoldingExposure(
        ticker="XLF", name="Financial Select Sector SPDR", aliases=["financials etf"],
        sector="Sector ETF", asset_type="etf",
        factor_tags=["us_financials", "banks", "value", "index", "credit_stress_sensitive", "yield_curve_sensitive", "bank_rate_beneficiary"],
        macro_sensitivity={"yields": -0.4, "rates": -0.4, "yield_curve_steepening": 0.6, "credit_stress": -0.85},
        second_order_exposure=["credit_cycle", "risk_sentiment"],
        reflexivity_exposure=0.45,
    ),
    "XLK": HoldingExposure(
        ticker="XLK", name="Technology Select Sector SPDR", aliases=["tech etf"],
        sector="Sector ETF", asset_type="etf",
        factor_tags=["us_tech", "growth", "index", "high_duration_growth", "dollar_sensitive"],
        macro_sensitivity={"rates": 0.6, "yields": 0.6, "real_yields_up": -0.65, "dollar_up": -0.2},
        second_order_exposure=["ai_capex", "semiconductors", "risk_sentiment"],
        reflexivity_exposure=0.6,
    ),
    "XLV": HoldingExposure(
        ticker="XLV", name="Health Care Select Sector SPDR", aliases=["healthcare etf"],
        sector="Sector ETF", asset_type="etf",
        factor_tags=["healthcare", "defensive", "index"],
        macro_sensitivity={"us_regulation": 0.4, "rates": 0.1, "risk_off": 0.2},
        second_order_exposure=["biotech_funding"],
        reflexivity_exposure=0.35,
    ),
    "XLE": HoldingExposure(
        ticker="XLE", name="Energy Select Sector SPDR", aliases=["energy etf"],
        sector="Sector ETF", asset_type="etf",
        factor_tags=["energy", "oil", "value", "commodities", "index", "commodity_beneficiary", "oil_up_beneficiary", "inflation_hedge"],
        macro_sensitivity={"inflation": -0.5, "rates": 0.1, "oil_up": 0.9, "commodity_inflation": 0.7, "inflation_fear": 0.4},
        second_order_exposure=["commodities", "oil_price"],
        reflexivity_exposure=0.3,
    ),
}

_PROFILES.update(_PROFILES_EXTRA)
_PROFILES.update(_PROFILES_WAVE3)


# Structural factor-state augmentations. These are explicit signed responses to
# named moves (not calibrated weights): they let one macro event create
# different or conflicting channels across duration, banks, gold, and energy.
_GROWTH_DURATION = {
    "AAPL": 0.60, "MSFT": 0.60, "NVDA": 0.80, "AMD": 0.75,
    "TSLA": 0.80, "META": 0.55, "GOOGL": 0.55, "AMZN": 0.60,
    "AVGO": 0.70, "TSM": 0.65, "ASML": 0.65, "QQQ": 0.65,
    "TQQQ": 0.95, "XLK": 0.65,
}
for _ticker, _beta in _GROWTH_DURATION.items():
    _profile = _PROFILES[_ticker]
    _profile.factor_tags = list(dict.fromkeys([
        *_profile.factor_tags, "rates_up_bad", "risk_off_bad",
    ]))
    _profile.macro_sensitivity.update({
        "rates_up": -_beta,
        "rates_down": _beta,
        "yields_up": -_beta,
        "yields_down": _beta,
        "risk_off": -min(0.9, _beta + 0.1),
        "recession_risk": -max(0.35, _beta * 0.65),
        "cyclical_strength": min(0.25, _beta * 0.25),
        "commodity_inflation": -min(0.40, _beta * 0.50),
    })

for _ticker, _rate_beta in {"JPM": 0.40, "BAC": 0.40, "GS": 0.25, "XLF": 0.35}.items():
    _profile = _PROFILES[_ticker]
    _profile.factor_tags = list(dict.fromkeys([
        *_profile.factor_tags, "financial_conditions_sensitive",
    ]))
    _profile.macro_sensitivity.update({
        "rates_up": _rate_beta,
        "rates_down": -_rate_beta,
        "yields_up": _rate_beta,
        "yields_down": -_rate_beta,
        "financial_conditions_tightening": -0.35,
        "bank_stress": -0.95,
        "risk_off": -0.55,
        "recession_risk": -0.75,
        "cyclical_strength": 0.30,
        "real_yields_up": 0.20,
    })

for _ticker, _oil_beta in {"XOM": 0.90, "CVX": 0.90, "XLE": 0.90, "USO": 1.0}.items():
    _profile = _PROFILES[_ticker]
    _profile.factor_tags = list(dict.fromkeys([
        *_profile.factor_tags, "inflation_pass_through",
        "recession_demand_sensitive",
    ]))
    _profile.macro_sensitivity.update({
        "oil_up": _oil_beta,
        "oil_down": -_oil_beta,
        "recession_demand": -0.85,
        "recession_risk": -0.60,
    })

_gld = _PROFILES["GLD"]
_gld.factor_tags = list(dict.fromkeys([
    *_gld.factor_tags, "inflation_fear_beneficiary", "risk_off_beneficiary",
]))
_gld.macro_sensitivity.update({
    "inflation_fear": 0.80,
    "inflation_fear_down": -0.55,
    "risk_off": 0.85,
    "real_yields_up": -0.85,
    "real_yields_down": 0.85,
    "yields_up": -0.45,
    "yields_down": 0.45,
    "dollar_up": -0.75,
    "dollar_down": 0.75,
    "credit_stress": 0.60,
    "bank_stress": 0.70,
})

for _ticker in ("UNH", "LLY", "NVO", "XLV"):
    _profile = _PROFILES[_ticker]
    _profile.factor_tags = list(dict.fromkeys([
        *_profile.factor_tags, "defensive_healthcare",
        "policy_regulation_sensitive", "drug_approval_sensitive",
    ]))
    _profile.macro_sensitivity.setdefault("risk_off", 0.20)

# Broad/small-cap jobs transmission: falling rates can help, while recession
# risk hurts. Keeping both produces a mixed read when the headline warrants it.
_PROFILES["SPY"].macro_sensitivity.update({
    "rates_up": -0.40, "rates_down": 0.40, "risk_off": -0.60,
    "recession_risk": -0.60, "cyclical_strength": 0.40,
})
_PROFILES["IWM"].macro_sensitivity.update({
    "rates_up": -0.70, "rates_down": 0.45, "risk_off": -0.80,
    "recession_risk": -0.80, "cyclical_strength": 0.60,
    "credit_stress": -0.70,
})
_PROFILES["SGOV"].macro_sensitivity.update({
    "rates_up": 0.10, "rates_down": -0.10,
})


def get_profile(ticker: str) -> HoldingExposure | None:
    """Return the registered exposure profile for ``ticker`` or ``None``."""
    if not ticker:
        return None
    return _PROFILES.get(str(ticker).upper())


def _generic_profile(ticker: str, name: str = "") -> HoldingExposure:
    """A neutral fingerprint for tickers without a curated profile.

    It still participates in macro/sentiment matching (broad equity beta) so the
    holding is never silently dropped, but carries no thematic tags.
    """
    return HoldingExposure(
        ticker=ticker,
        name=name or ticker,
        sector="Unclassified",
        asset_type="equity",
        factor_tags=["equity_beta"],
        macro_sensitivity={"rates": 0.3, "yields": 0.3},
        second_order_exposure=["risk_sentiment"],
        reflexivity_exposure=0.3,
    )


# --- Sample fallback portfolio -------------------------------------------
# Used when the caller has no holdings at all (e.g. first-run demo). Explicit
# weights so the overview is fully populated. Clearly flagged as sample upstream.
SAMPLE_PORTFOLIO = [
    {"symbol": "AAPL", "weight": 0.30},
    {"symbol": "0700.HK", "weight": 0.20},
    {"symbol": "300750.SZ", "weight": 0.18},
    {"symbol": "601318.SS", "weight": 0.16},
    {"symbol": "2359.HK", "weight": 0.16},
]

# Named demo portfolios for exercising the engine across very different
# exposure mixes (selectable in the UI). Weights sum to ~1.0.
DEMO_PORTFOLIOS: dict[str, dict[str, Any]] = {
    "sample": {
        "label": "示例混合组合 (中港美)",
        "holdings": SAMPLE_PORTFOLIO,
    },
    "us_megacap_tech": {
        "label": "美股大型科技 US Megacap Tech",
        "holdings": [
            {"symbol": "AAPL", "weight": 0.20}, {"symbol": "MSFT", "weight": 0.20},
            {"symbol": "NVDA", "weight": 0.20}, {"symbol": "GOOGL", "weight": 0.15},
            {"symbol": "META", "weight": 0.15}, {"symbol": "AMD", "weight": 0.10},
        ],
    },
    "leveraged_growth": {
        "label": "杠杆成长 Leveraged Growth",
        "holdings": [
            {"symbol": "TQQQ", "weight": 0.40}, {"symbol": "NVDA", "weight": 0.25},
            {"symbol": "TSLA", "weight": 0.20}, {"symbol": "QQQ", "weight": 0.15},
        ],
    },
    "balanced": {
        "label": "均衡配置 Balanced",
        "holdings": [
            {"symbol": "QQQ", "weight": 0.25}, {"symbol": "JPM", "weight": 0.15},
            {"symbol": "XOM", "weight": 0.15}, {"symbol": "UNH", "weight": 0.15},
            {"symbol": "GLD", "weight": 0.15}, {"symbol": "SGOV", "weight": 0.15},
        ],
    },
    "ai_semis": {
        "label": "AI / 半导体 AI & Semis",
        "holdings": [
            {"symbol": "NVDA", "weight": 0.30}, {"symbol": "AMD", "weight": 0.25},
            {"symbol": "TSM", "weight": 0.25}, {"symbol": "MSFT", "weight": 0.20},
        ],
    },
}


def list_demo_portfolios() -> list[dict[str, str]]:
    """Return ``[{id, label}]`` for the selectable demo portfolios."""
    return [{"id": k, "label": v["label"]} for k, v in DEMO_PORTFOLIOS.items()]


def get_demo_portfolio(name: str) -> list[dict[str, Any]]:
    """Return the holdings rows for a named demo portfolio (falls back to sample)."""
    entry = DEMO_PORTFOLIOS.get(name) or DEMO_PORTFOLIOS["sample"]
    return entry["holdings"]


def _coerce_weight(raw: dict[str, Any]) -> float | None:
    """Best-effort position weight from a holding row, without live quotes.

    Priority: explicit ``weight`` -> ``market_value(_base)`` -> cost basis
    (cost_price * quantity). Returns ``None`` when nothing usable is present so
    the caller can apply equal-weight fallback.
    """
    for key in ("weight", "market_value_base", "market_value"):
        v = raw.get(key)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    cost = raw.get("cost_price")
    qty = raw.get("quantity")
    if isinstance(cost, (int, float)) and isinstance(qty, (int, float)) and cost > 0 and qty > 0:
        return float(cost) * float(qty)
    return None


def build_portfolio(holdings: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Adapter: holdings rows -> normalized exposure portfolio.

    Returns a dict::

        {
          "positions": [{"exposure": HoldingExposure, "weight": float,
                          "weight_basis": "cost"|"market"|"explicit"|"equal",
                          "matched_profile": bool}],
          "weighting": "cost-basis" | "market-value" | "explicit" | "equal-weight",
          "weight_is_fallback": bool,   # True when equal-weight was used
          "is_sample": bool,
        }

    ``weight`` values sum to 1.0 (normalized). The function never touches the
    network and never mutates the input rows.
    """
    is_sample = False
    if not holdings:
        holdings = SAMPLE_PORTFOLIO
        is_sample = True

    raw_weights: list[float | None] = []
    bases: list[str] = []
    exposures: list[HoldingExposure] = []
    matched: list[bool] = []

    for row in holdings:
        symbol = str(row.get("symbol") or row.get("ticker") or "").strip().upper()
        if not symbol:
            continue
        prof = get_profile(symbol)
        if prof is None:
            prof = _generic_profile(symbol, str(row.get("name") or ""))
            matched.append(False)
        else:
            matched.append(True)
        exposures.append(prof)

        w = _coerce_weight(row)
        raw_weights.append(w)
        if "weight" in row:
            bases.append("explicit")
        elif row.get("market_value_base") or row.get("market_value"):
            bases.append("market")
        elif w is not None:
            bases.append("cost")
        else:
            bases.append("equal")

    n = len(exposures)
    if n == 0:
        return {
            "positions": [],
            "weighting": "equal-weight",
            "weight_is_fallback": True,
            "is_sample": is_sample,
        }

    # Equal-weight fallback when any weight is missing -> for transparency we
    # fall back wholesale rather than mixing bases.
    weight_is_fallback = any(w is None or w <= 0 for w in raw_weights)
    if weight_is_fallback:
        weights = [1.0 / n] * n
        weighting = "equal-weight"
        bases = ["equal"] * n
    else:
        total = sum(raw_weights)  # type: ignore[arg-type]
        weights = [(w / total) if total else 1.0 / n for w in raw_weights]  # type: ignore[operator]
        # All same basis at this point (none missing); report the dominant one.
        weighting_map = {"explicit": "explicit", "market": "market-value", "cost": "cost-basis"}
        weighting = weighting_map.get(bases[0], "cost-basis")

    positions = [
        {
            "exposure": exposures[i],
            "weight": weights[i],
            "weight_basis": bases[i],
            "matched_profile": matched[i],
        }
        for i in range(n)
    ]
    return {
        "positions": positions,
        "weighting": weighting,
        "weight_is_fallback": weight_is_fallback,
        "is_sample": is_sample,
    }
