# app.py
# v3.2：_fetch_dcf_defaults() 改用 router 统一拉数据，
#       FCF 默认增长率改为 3%（不再用历史 CAGR），
#       响应里加 data_source 字段供前端显示。
# 其他路由、_clean_nan() 兜底、PT 现有功能完全保留。

import json
import math
import os
from datetime import date, datetime
from flask      import Flask, jsonify, request, send_from_directory, send_file
from flask_cors import CORS

from data_fetcher import (
    get_quote, get_history, get_fx_rate,
    get_quote_router, get_financials_router, get_data_source,
    FINANCIALS_CACHE_VERSION,
)
from calculator   import calc_pnl, calc_daily_pnl, calc_portfolio_summary, convert_to_base

from modeling.dcf_calculator import (
    DCFInputs, run_dcf, detect_market, MARKET_CONFIG, derive_driver_defaults,
    NET_DEBT_TREATMENTS, NET_DEBT_TREATMENT_LABELS, DEFAULT_NET_DEBT_TREATMENT,
    normalize_net_debt_treatment, available_net_debt_treatments,
    SHARE_COUNT_TREATMENTS, SHARE_COUNT_TREATMENT_LABELS, DEFAULT_SHARE_COUNT_TREATMENT,
    normalize_share_count_treatment, available_share_count_treatments,
    BUYBACK_METHODS, BUYBACK_METHOD_LABELS, DEFAULT_BUYBACK_METHOD,
    normalize_buyback_method, available_buyback_methods,
    WACC_TREATMENTS, WACC_TREATMENT_LABELS, DEFAULT_WACC_TREATMENT,
    normalize_wacc_treatment, available_wacc_treatments,
    TERMINAL_TREATMENTS, TERMINAL_TREATMENT_LABELS, DEFAULT_TERMINAL_TREATMENT,
    DEFAULT_FADE_YEARS, DEFAULT_H_MODEL_HALF_LIFE, DEFAULT_CASH_FLOOR,
    DEFAULT_BUYBACK_FUNDING_TREATMENT, normalize_terminal_treatment, available_terminal_treatments,
    normalize_operating_path_source,
    apply_aapl_base_defaults, apply_aapl_bear_defaults,
    AAPL_BASE_DEFAULT_WACC, AAPL_BASE_DEFAULT_EXIT_MULTIPLE,
    AAPL_BASE_DEFAULT_TERMINAL_G,
    AAPL_BASE_DEFAULT_WACC_TREATMENT, AAPL_BASE_DEFAULT_TERMINAL_TREATMENT,
    AAPL_BASE_DEFAULT_NET_DEBT_TREATMENT,
    AAPL_BASE_DEFAULT_BLEND_WEIGHT_GORDON, AAPL_BASE_DEFAULT_BLEND_WEIGHT_EXIT,
    AAPL_BASE_REVENUE_GROWTH_PATH, AAPL_BASE_EBIT_MARGIN_PATH,
    AAPL_BASE_FORECAST_RATIONALE,
    AAPL_BEAR_DEFAULT_WACC, AAPL_BEAR_DEFAULT_EXIT_MULTIPLE,
    AAPL_BEAR_DEFAULT_TERMINAL_G,
    AAPL_BEAR_DEFAULT_WACC_TREATMENT, AAPL_BEAR_DEFAULT_TERMINAL_TREATMENT,
    AAPL_BEAR_DEFAULT_NET_DEBT_TREATMENT,
    AAPL_BEAR_DEFAULT_BLEND_WEIGHT_GORDON, AAPL_BEAR_DEFAULT_BLEND_WEIGHT_EXIT,
    AAPL_BEAR_REVENUE_GROWTH_PATH, AAPL_BEAR_EBIT_MARGIN_PATH,
    AAPL_BEAR_FORECAST_RATIONALE,
)
from modeling.excel_exporter import generate_excel, MODEL_VERSION as _EXPORTER_MODEL_VERSION
from modeling.trading_comps import build_trading_comps
from modeling.lbo_calculator import run_lbo
from modeling.lbo_defaults import build_lbo_defaults
from modeling.lbo_formula_workbook import generate_lbo_formula_excel
from modeling.lbo_suitability import assess_lbo_suitability
from modeling.lbo_attribution import build_lbo_attribution
from modeling.lbo_scenarios import build_lbo_scenarios
from modeling.lbo_sensitivity import build_lbo_sensitivity
from modeling.lbo_return_context import build_return_context
from modeling.ma.api import build_ma_response
from modeling.ma.sample_companies import list_sample_companies
from modeling.ma.precompute import get_arena_pairs_response
from modeling.v6.api import build_intelligence_response

# v3.3.0 段 1 的工具函数（本段段 2 复用）
from thesis_utils import canonical_ticker
from thesis_store import read_thesis, write_thesis
from dcf_scenario_store import read_scenarios, write_scenario, delete_scenario

app = Flask(__name__, static_folder="static")
app.json.sort_keys = False
# Local-only app: the bundled static UI is served same-origin by Flask, so it
# needs no CORS at all. We scope CORS to loopback origins for /api/* only, so a
# public deployment does not silently expose the API to arbitrary web origins.
CORS(app, resources={r"/api/*": {"origins": [
    "http://127.0.0.1:5000",
    "http://localhost:5000",
]}})

# v3.2.6：动态 API 禁用浏览器缓存
# 系统已有 server-side cache_layer（财报24h、行情5min），浏览器再缓存
# JSON 会让 Ctrl+F5 都刷不动数据（本轮就踩过）。金融产品 freshness 优先，
# 统一 no-store 能显著降低 debug complexity。
# 仅作用于 /api/* 路径，静态资源不受影响。
@app.after_request
def _no_store_for_api(response):
    # Default no-store for every /api/* JSON response, but respect a stronger
    # Cache-Control a specific route already set (e.g. the V6 freshness guard).
    if request.path.startswith("/api/") and "Cache-Control" not in response.headers:
        response.headers["Cache-Control"] = "no-store"
    return response

PORTFOLIO_FILE   = "portfolio.json"
VALID_CURRENCIES = {"HKD", "USD", "CNY"}

STATIC_FX_REPORTING_TO_TRADING = {
    ("CNY", "HKD"): 1.08,
    ("USD", "HKD"): 7.80,
}

HK_REPORTING_CURRENCY_REVIEW_OVERRIDES = {
    "2359.HK": ("CNY", "hk_prc_issuer_override_review_required"),
    "0700.HK": ("CNY", "hk_prc_issuer_override_review_required"),
    "0883.HK": ("USD", "hk_reporting_currency_override_review_required"),
    "0005.HK": ("USD", "hk_reporting_currency_override_review_required"),
    "1299.HK": ("USD", "hk_reporting_currency_override_review_required"),
}

UNSUITABLE_SECURITY_RECOMMENDED_METHODS = {
    "etf": ["NAV", "holdings look-through", "tracking error", "expense ratio", "asset allocation"],
    "index": ["index methodology", "constituent look-through", "factor exposure", "asset allocation"],
    "fund": ["NAV", "holdings look-through", "expense ratio", "asset allocation"],
    "reit": ["AFFO", "NAV", "dividend yield"],
    "trust": ["NAV", "holdings look-through", "distribution yield"],
}

COMMON_US_ETFS = {
    "SPY", "QQQ", "IWM", "DIA", "VOO", "IVV", "VTI", "ARKK",
    "XLK", "XLF", "XLE", "TLT", "GLD", "SLV",
}
COMMON_HK_ETFS = {"2800.HK", "2822.HK", "3033.HK", "3067.HK"}
COMMON_CN_ETFS = {"510300.SS", "510500.SS", "512100.SS", "159919.SZ", "159915.SZ"}
KNOWN_REITS = {"O", "VNQ", "IYR"}


def _security_type_reason(security_type: str) -> str:
    if security_type == "index":
        return "DCF is not suitable for indices because they do not have operating company cash flows."
    if security_type == "etf":
        return "DCF is not suitable for ETFs because they represent portfolios rather than operating company cash flows."
    if security_type == "fund":
        return "DCF is not suitable for funds because NAV, holdings, fees, and mandate drive valuation."
    if security_type == "reit":
        return "Standard FCFF DCF is not suitable for REITs; use AFFO, NAV, dividend yield, and cap-rate analysis."
    if security_type == "trust":
        return "DCF is not suitable for trust products because NAV, distributions, and underlying assets drive value."
    return "DCF is designed for operating companies and is not suitable for this security type."


def _suitability_payload(security_type: str, source: str, suitability: str, reason: str | None = None) -> dict:
    recommended_key = security_type if security_type in UNSUITABLE_SECURITY_RECOMMENDED_METHODS else "fund"
    return {
        "security_type": security_type,
        "security_type_source": source,
        "dcf_suitability": suitability,
        "reason": reason or (_security_type_reason(security_type) if suitability == "unsuitable" else "Security appears suitable for operating-company DCF."),
        "recommended_methods": UNSUITABLE_SECURITY_RECOMMENDED_METHODS.get(recommended_key, []),
    }


def detect_security_type(symbol: str, quote_info: dict | None = None, market: str | None = None, metadata: dict | None = None) -> dict:
    ticker = str(symbol or "").strip().upper()
    quote_info = quote_info or {}
    metadata = metadata or {}
    text = " ".join(
        str(x or "")
        for x in [
            ticker,
            quote_info.get("name"),
            quote_info.get("quote_type"),
            quote_info.get("type_disp"),
            quote_info.get("sector"),
            quote_info.get("industry"),
            metadata.get("name"),
            metadata.get("security_type"),
        ]
    ).upper()
    quote_type = str(quote_info.get("quote_type") or metadata.get("quoteType") or "").upper()
    type_disp = str(quote_info.get("type_disp") or metadata.get("typeDisp") or "").upper()

    if ticker.startswith("^"):
        return _suitability_payload("index", "ticker_pattern", "unsuitable")
    if quote_type in {"ETF", "MUTUALFUND", "INDEX"} or type_disp in {"ETF", "MUTUAL FUND", "INDEX"}:
        mapped = "index" if "INDEX" in {quote_type, type_disp} else ("fund" if "MUTUAL" in type_disp or quote_type == "MUTUALFUND" else "etf")
        return _suitability_payload(mapped, "yfinance_quote_type", "unsuitable")
    if ticker in COMMON_US_ETFS or ticker in COMMON_HK_ETFS or ticker in COMMON_CN_ETFS:
        return _suitability_payload("etf", "manual_rule", "unsuitable")
    if "TRACKER FUND" in text or " ETF" in f" {text}" or text.endswith("ETF"):
        return _suitability_payload("etf", "akshare_metadata", "unsuitable")
    if "MUTUAL FUND" in text or "CLOSED-END FUND" in text or " CLOSED END" in text:
        return _suitability_payload("fund", "yfinance_quote_type", "unsuitable")
    if "TRUST PRODUCT" in text or "UNIT TRUST" in text:
        return _suitability_payload("trust", "manual_rule", "unsuitable")
    if ticker in KNOWN_REITS or "REIT" in text or "REAL ESTATE INVESTMENT TRUST" in text:
        return _suitability_payload("reit", "manual_rule", "unsuitable")
    if ticker.endswith(".SS") and ticker[:6].isdigit() and ticker.startswith("51"):
        return _suitability_payload(
            "fund",
            "ticker_pattern",
            "review",
            "CN 51xxxx.SS tickers are often ETFs or funds; allow DCF only after confirming this is an operating company.",
        )
    if ticker.endswith(".SZ") and ticker[:6].isdigit() and ticker.startswith("159"):
        return _suitability_payload(
            "fund",
            "ticker_pattern",
            "review",
            "CN 159xxx.SZ tickers are often ETFs; known ETF codes are blocked, otherwise review security type before use.",
        )
    return _suitability_payload("operating_company", "unknown", "suitable")


# ── _clean_nan helper（保护清单：保留）──────────────────────────────────────
def _clean_nan(obj):
    """
    递归把 NaN / Infinity 替换成 None，避免污染 JSON 序列化。
    """
    if isinstance(obj, dict):
        return {k: _clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_nan(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
    return obj


def _is_positive_finite(value) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0


def _append_warning_once(warnings: list, warning: str):
    if warning and warning not in warnings:
        warnings.append(warning)


def _elevate_review_status(current_status, target_status):
    order = {"Clean": 0, "Review": 1, "High Review": 2}
    current = current_status or "Clean"
    target = target_status or "Clean"
    return target if order.get(target, 0) > order.get(current, 0) else current


def _normalize_currency_code(value):
    if value is None:
        return None
    code = str(value).strip().upper()
    if not code or code in {"UNKNOWN", "N/A", "NA", "NONE", "NULL"}:
        return None
    if code == "RMB":
        return "CNY"
    return code


def _resolve_currency_translation(
    symbol: str,
    reporting_currency=None,
    trading_currency=None,
    reporting_currency_source=None,
    trading_currency_source=None,
) -> dict:
    ticker = str(symbol or "").strip().upper()
    reporting = _normalize_currency_code(reporting_currency)
    trading = _normalize_currency_code(trading_currency)
    reporting_source = reporting_currency_source or "unknown"
    trading_source = trading_currency_source or "unknown"

    override = HK_REPORTING_CURRENCY_REVIEW_OVERRIDES.get(ticker)
    if override and (reporting in {None, "HKD"} or str(reporting_source).lower() == "default_hkd_unverified"):
        reporting, reporting_source = override

    if not reporting or not trading:
        missing = []
        if not reporting:
            missing.append("reporting_currency")
        if not trading:
            missing.append("trading_currency")
        warning = (
            f"Currency translation blocked: missing {', '.join(missing)}; "
            "market comparison is High Review."
        )
        return {
            "reporting_currency": reporting,
            "reporting_currency_source": reporting_source,
            "trading_currency": trading,
            "trading_currency_source": trading_source,
            "currency_pair": None,
            "fx_rate_reporting_to_trading": None,
            "fx_rate_source": "missing_currency",
            "currency_translation_status": "High Review",
            "currency_translation_warning": warning,
            "market_comparison_allowed": False,
        }

    pair = f"{reporting}/{trading}"
    if reporting == trading:
        return {
            "reporting_currency": reporting,
            "reporting_currency_source": reporting_source,
            "trading_currency": trading,
            "trading_currency_source": trading_source,
            "currency_pair": pair,
            "fx_rate_reporting_to_trading": 1.0,
            "fx_rate_source": "same_currency",
            "currency_translation_status": "Clean",
            "currency_translation_warning": None,
            "market_comparison_allowed": True,
        }

    rate = STATIC_FX_REPORTING_TO_TRADING.get((reporting, trading))
    if rate is not None:
        return {
            "reporting_currency": reporting,
            "reporting_currency_source": reporting_source,
            "trading_currency": trading,
            "trading_currency_source": trading_source,
            "currency_pair": pair,
            "fx_rate_reporting_to_trading": rate,
            "fx_rate_source": "static_fallback_review_required",
            "currency_translation_status": "Review",
            "currency_translation_warning": (
                f"Static fallback FX used for {pair}; verify live FX before IC use."
            ),
            "market_comparison_allowed": True,
        }

    return {
        "reporting_currency": reporting,
        "reporting_currency_source": reporting_source,
        "trading_currency": trading,
        "trading_currency_source": trading_source,
        "currency_pair": pair,
        "fx_rate_reporting_to_trading": None,
        "fx_rate_source": "missing_fx_rate",
        "currency_translation_status": "High Review",
        "currency_translation_warning": (
            f"Currency translation blocked: no FX rate configured for {pair}; "
            "do not compare reporting-currency IV with trading-currency price."
        ),
        "market_comparison_allowed": False,
    }


def _translate_dcf_currency_outputs(out, translation: dict) -> dict:
    rate = translation.get("fx_rate_reporting_to_trading")
    allowed = bool(translation.get("market_comparison_allowed")) and rate is not None

    iv_reporting = out.intrinsic_per_share if _is_positive_finite(out.intrinsic_per_share) else None
    equity_reporting = out.equity_value
    ev_reporting = out.ev

    def _fx(value):
        if value is None or not allowed:
            return None
        return value * float(rate)

    iv_trading = _fx(iv_reporting)
    equity_trading = _fx(equity_reporting)
    ev_trading = _fx(ev_reporting)

    return {
        "intrinsic_value_per_share_reporting_currency": iv_reporting,
        "intrinsic_value_reporting_currency": equity_reporting,
        "ev_reporting_currency": ev_reporting,
        "intrinsic_value_per_share_trading_currency": iv_trading,
        "intrinsic_value_trading_currency": equity_trading,
        "ev_trading_currency": ev_trading,
        "intrinsic_per_share_for_market_comparison": iv_trading,
    }


def _finalize_dcf_market_status(price, currency_translation: dict, currency_outputs: dict, base_warnings=None) -> dict:
    translation = dict(currency_translation or {})
    outputs = dict(currency_outputs or {})
    warnings = list(base_warnings or [])

    reporting = _normalize_currency_code(translation.get("reporting_currency"))
    trading = _normalize_currency_code(translation.get("trading_currency"))
    fx_missing_for_mismatch = bool(reporting and trading and reporting != trading and translation.get("fx_rate_reporting_to_trading") is None)
    price_valid = _is_positive_finite(price)
    iv_valid = _is_positive_finite(outputs.get("intrinsic_value_per_share_reporting_currency"))
    trading_iv_valid = _is_positive_finite(outputs.get("intrinsic_value_per_share_trading_currency"))

    valuation_status = "available" if iv_valid else "unavailable"
    market_comparison_status = "available"

    if fx_missing_for_mismatch:
        translation["currency_translation_status"] = "High Review"
        translation["market_comparison_allowed"] = False
        translation["currency_translation_warning"] = "FX translation unavailable; market comparison blocked."
        _append_warning_once(warnings, translation["currency_translation_warning"])
        outputs["intrinsic_value_per_share_trading_currency"] = None
        outputs["intrinsic_value_trading_currency"] = None
        outputs["ev_trading_currency"] = None
        outputs["intrinsic_per_share_for_market_comparison"] = None
        trading_iv_valid = False
        market_comparison_status = "unavailable"

    if not iv_valid:
        valuation_status = "unavailable"
        market_comparison_status = "unavailable"
        translation["market_comparison_allowed"] = False
        outputs["intrinsic_value_per_share_reporting_currency"] = None
        outputs["intrinsic_value_per_share_trading_currency"] = None
        outputs["intrinsic_per_share_for_market_comparison"] = None
        outputs["intrinsic_value_trading_currency"] = None
        translation["currency_translation_status"] = _elevate_review_status(
            translation.get("currency_translation_status"),
            "High Review" if fx_missing_for_mismatch else "Review",
        )
        _append_warning_once(warnings, "Intrinsic value unavailable; valuation output not clean.")

    if not price_valid:
        market_comparison_status = "unavailable"
        translation["market_comparison_allowed"] = False
        translation["currency_translation_status"] = _elevate_review_status(
            translation.get("currency_translation_status"),
            "High Review" if fx_missing_for_mismatch else "Review",
        )
        _append_warning_once(warnings, "Current price unavailable; upside/downside comparison blocked.")

    if not trading_iv_valid:
        market_comparison_status = "unavailable"
        translation["market_comparison_allowed"] = False

    comparison_iv = outputs.get("intrinsic_per_share_for_market_comparison")
    upside_pct = None
    if market_comparison_status == "available" and _is_positive_finite(comparison_iv) and price_valid:
        upside_pct = round(((float(comparison_iv) - float(price)) / float(price)) * 100, 2)
    else:
        outputs["intrinsic_per_share_for_market_comparison"] = None if not _is_positive_finite(comparison_iv) else comparison_iv

    return {
        "currency_translation": translation,
        "currency_outputs": outputs,
        "warnings": warnings,
        "valuation_status": valuation_status,
        "market_comparison_status": market_comparison_status,
        "upside_pct": upside_pct,
        "comparison_iv": outputs.get("intrinsic_per_share_for_market_comparison"),
    }


def _currency_translation_from_payload(d: dict, out=None) -> dict:
    symbol = (d or {}).get("symbol") or getattr(out, "symbol", None)
    market = detect_market(symbol or "") if symbol else getattr(out, "market", None)
    default_trading = MARKET_CONFIG.get(market or "", {}).get("currency")
    ticker = str(symbol or "").strip().upper()
    trading = (d or {}).get("trading_currency") or (d or {}).get("currency") or getattr(out, "currency", None) or default_trading
    reporting = (d or {}).get("reporting_currency")
    if reporting is None:
        if market in {"US", "CN"}:
            reporting = (d or {}).get("currency") or getattr(out, "currency", None) or MARKET_CONFIG[market]["currency"]
        elif ticker in HK_REPORTING_CURRENCY_REVIEW_OVERRIDES:
            reporting = (d or {}).get("currency") or getattr(out, "currency", None)
    return _resolve_currency_translation(
        symbol=symbol,
        reporting_currency=reporting,
        trading_currency=trading,
        reporting_currency_source=(d or {}).get("reporting_currency_source"),
        trading_currency_source=(d or {}).get("trading_currency_source") or "request_or_market_config",
    )


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def load_portfolio() -> list:
    if not os.path.exists(PORTFOLIO_FILE):
        return []
    with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_portfolio(data: list) -> None:
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── 静态页面路由 ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/detail")
def detail():
    return send_from_directory("static", "detail.html")

@app.route("/modeling")
def modeling_index():
    return send_from_directory("static/modeling", "dcf.html")

@app.route("/modeling/dcf")
def modeling_dcf():
    return send_from_directory("static/modeling", "dcf.html")

@app.route("/modeling/dcf/select")
def page_dcf_select():
    return send_from_directory("static/modeling", "dcf_select.html")

@app.route("/modeling/case")
def modeling_case():
    return send_from_directory("static/modeling", "case.html")

@app.route("/modeling/lbo")
def modeling_lbo():
    return send_from_directory("static/modeling", "lbo.html")

@app.route("/modeling/ma")
def modeling_ma():
    return send_from_directory("static/modeling", "ma_studio.html")

@app.route("/modeling/ma/arena")
def modeling_ma_arena():
    """V5.6 Deal Arena · War Room: high-density prep area (deck, combos,
    Settlement Board, Deal Ticket) over the same deck/engine."""
    return send_from_directory("static/modeling", "arena.html")


@app.route("/modeling/ma/arena/play")
def modeling_ma_arena_play():
    """V5.6.1 Deal Arena · Tabletop: immersive play-view game table. Pure static
    shell; reuses the same deck/pairs/calculate as the War Room. No bots, no
    turn system, no backend per-user state."""
    return send_from_directory("static/modeling", "arena_play.html")


@app.route("/modeling/ma/arena/match/setup")
def modeling_ma_arena_match_setup():
    """V5.9.2 Match Setup: the lobby between the War Room and the formal Match
    table. Picks two robot opponents + difficulties (front-end sessionStorage
    only). No engine/API/backend state."""
    return send_from_directory("static/modeling", "arena_match_setup.html")


@app.route("/modeling/ma/arena/match/play")
def modeling_ma_arena_match_play():
    """V5.9.2 Match table: the formal five-round match (turn loop + two seated
    robots + local Match Points scoreboard + settlement end screen). Reuses the
    same deck/pairs/calculate/Deal Ticket/Queue and the deterministic Robot
    Opponent. No Overall Score, no backend per-user state, no runtime
    network/LLM/plugin."""
    return send_from_directory("static/modeling", "arena_match.html")


@app.route("/modeling/v6")
def modeling_v6():
    """V6 Market Intelligence cockpit: deterministic, rule-based event→holdings
    impact mapping. Static shell; all data comes from
    /api/modeling/v6/intelligence."""
    return send_from_directory("static/modeling", "v6.html")


# ── API：持仓管理（PT 部分，使用 router 后行情更稳）────────────────────────

@app.route("/api/portfolio", methods=["GET"])
def get_portfolio():
    base_currency = request.args.get("base", "HKD").upper()
    if base_currency not in VALID_CURRENCIES:
        base_currency = "HKD"

    holdings             = load_portfolio()
    enriched             = []
    holdings_for_summary = []

    for h in holdings:
        try:
            # 用 router：港股/A 股走 AKShare，美股走 yfinance
            quote    = get_quote_router(h["symbol"])
            if not isinstance(quote, dict):
                quote = {"symbol": h["symbol"], "current_price": None, "_error": "quote source returned no data"}
            price    = quote.get("current_price")
            currency = quote.get("currency", "USD")

            if price is None:
                enriched.append({**h, "error": "行情获取失败"})
                continue

            pnl       = calc_pnl(h["cost_price"], price, h["quantity"])
            daily_pnl = calc_daily_pnl(quote.get("prev_close"), price, h["quantity"])

            mv_base, fx_mv = convert_to_base(pnl["market_value"], currency, base_currency)
            cv_base, fx_cv = convert_to_base(pnl["cost_value"],   currency, base_currency)
            pa_base, fx_pa = convert_to_base(pnl["pnl_amount"],   currency, base_currency)
            dp_base, fx_dp = convert_to_base(daily_pnl,           currency, base_currency)

            is_fallback = any(fx["is_fallback"] for fx in [fx_mv, fx_cv, fx_pa, fx_dp])

            row = {
                **h, **quote,
                "market_value_native": pnl["market_value"],
                "cost_value_native"  : pnl["cost_value"],
                "pnl_amount_native"  : pnl["pnl_amount"],
                "daily_pnl_native"   : daily_pnl,
                "currency"           : currency,
                "market_value_base"  : mv_base,
                "cost_value_base"    : cv_base,
                "pnl_amount_base"    : pa_base,
                "daily_pnl_base"     : dp_base,
                "base_currency"      : base_currency,
                "pnl_pct"            : pnl["pnl_pct"],
                "market_value"       : pnl["market_value"],
                "cost_value"         : pnl["cost_value"],
                "pnl_amount"         : pnl["pnl_amount"],
                "daily_pnl"          : daily_pnl,
                "fx_is_fallback"     : is_fallback,
            }
            enriched.append(row)
            holdings_for_summary.append(row)

        except Exception:
            app.logger.exception("quote enrich failed for %s", h.get("symbol"))
            enriched.append({**h, "error": "行情获取失败"})

    summary = calc_portfolio_summary(holdings_for_summary, base_currency=base_currency)
    return jsonify(_clean_nan({
        "holdings"     : enriched,
        "summary"      : summary,
        "base_currency": base_currency,
    }))


@app.route("/api/portfolio", methods=["POST"])
def add_stock():
    data   = request.get_json()
    symbol = data.get("symbol", "").strip().upper()
    if not symbol:
        return jsonify(_clean_nan({"error": "股票代码不能为空"})), 400
    holdings = load_portfolio()
    if any(h["symbol"] == symbol for h in holdings):
        return jsonify(_clean_nan({"error": f"{symbol} 已在持仓中"})), 400
    new_holding = {
        "symbol"    : symbol,
        "cost_price": float(data.get("cost_price", 0)),
        "quantity"  : float(data.get("quantity",   0)),
        "buy_date"  : data.get("buy_date", ""),
    }
    holdings.append(new_holding)
    save_portfolio(holdings)
    return jsonify(_clean_nan({"message": f"{symbol} 添加成功", "holding": new_holding})), 201


@app.route("/api/portfolio/<symbol>", methods=["DELETE"])
def delete_stock(symbol):
    holdings     = load_portfolio()
    original_len = len(holdings)
    holdings     = [h for h in holdings if h["symbol"].upper() != symbol.upper()]
    if len(holdings) == original_len:
        return jsonify(_clean_nan({"error": f"{symbol} 不在持仓中"})), 404
    save_portfolio(holdings)
    return jsonify(_clean_nan({"message": f"{symbol} 已删除"}))


@app.route("/api/quote/<symbol>", methods=["GET"])
def quote(symbol):
    try:
        q = get_quote_router(symbol)
        if not isinstance(q, dict):
            q = {"symbol": symbol, "current_price": None, "_error": "quote source returned no data"}
        status = 503 if q.get("_error") and q.get("current_price") is None else 200
        return jsonify(_clean_nan(q)), status
    except Exception:
        app.logger.exception("api_quote failed for %s", symbol)
        return jsonify(_clean_nan({"error": "行情获取失败"})), 500


@app.route("/api/history/<symbol>", methods=["GET"])
def history(symbol):
    period = request.args.get("period", "1y")
    try:
        return jsonify(_clean_nan(get_history(symbol, period)))
    except Exception:
        app.logger.exception("api_history failed for %s", symbol)
        return jsonify(_clean_nan({"error": "历史数据获取失败"})), 500


@app.route("/api/fx", methods=["GET"])
def fx_rate():
    from_c = request.args.get("from", "USD").upper()
    to_c   = request.args.get("to",   "HKD").upper()
    try:
        return jsonify(_clean_nan(get_fx_rate(from_c, to_c)))
    except Exception:
        app.logger.exception("api_fx failed for %s->%s", from_c, to_c)
        return jsonify(_clean_nan({"error": "汇率获取失败"})), 500


# ── v3.3.0 段 1：Ontology 只读 API ─────────────────────────────────────────────
# 25 条 driver 的字典常量，启动时从 data/ontology/drivers.json 加载到内存。
# 文件很小，启动加载比每次读盘简单可靠。
# 段 1 范围内只读，不暴露 POST/PUT。
_ONTOLOGY_DRIVERS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data", "ontology", "drivers.json",
)
try:
    with open(_ONTOLOGY_DRIVERS_PATH, "r", encoding="utf-8") as _f:
        _ONTOLOGY_DRIVERS = json.load(_f)
except Exception as _e:
    print(f"[ontology] 加载 drivers.json 失败: {_e}")
    _ONTOLOGY_DRIVERS = {}


@app.route("/api/ontology/drivers", methods=["GET"])
def get_ontology_drivers():
    """
    GET /api/ontology/drivers
    返回 data/ontology/drivers.json 全文（25 条 driver 元数据）。
    无参数、无校验。前端用此端点构造 driver 多选下拉框。
    """
    return jsonify(_clean_nan(_ONTOLOGY_DRIVERS))


# ── v3.3.0 段 2：Thesis GET / PUT API ──────────────────────────────────────────
# 硬边界：
#   - 不调 _fetch_dcf_defaults / DCF 模块
#   - 不读 DCF cache
#   - 不主动拉 industry_warning（由前端 PUT 时显式传 snapshot）
#   - last_modified 完全由 thesis_store.write_thesis 内部生成，此处不参与
#   - get_quote_router 仅在"模板构造时取 company_name"这一处复用，不扩展用途

THESIS_SCHEMA_VERSION = "v340"
THESIS_ACCEPTED_SCHEMA_VERSIONS = {"v330", "v334", "v335", "v340"}
THESIS_SCENARIOS = ("base", "bull", "bear")
THESIS_SCENARIO_STATES = {"stronger", "stable", "weaker", "unknown"}


def _default_scenario_states() -> dict:
    return {scenario: {} for scenario in THESIS_SCENARIOS}


def _normalize_scenario_states(raw_states, valid_driver_ids: set, drivers_selected: list):
    if not isinstance(raw_states, dict):
        return None, {"error": "scenario_states must be dict"}

    invalid_top_keys = [key for key in raw_states.keys() if key not in THESIS_SCENARIOS]
    if invalid_top_keys:
        return None, {
            "error": "invalid scenario_states top-level key(s)",
            "invalid_keys": invalid_top_keys,
        }

    selected_ids = set(drivers_selected)
    normalized = _default_scenario_states()

    for scenario in THESIS_SCENARIOS:
        scenario_values = raw_states.get(scenario, {})
        if not isinstance(scenario_values, dict):
            return None, {
                "error": "scenario_states scenario value must be dict",
                "scenario": scenario,
            }

        invalid_driver_keys = [key for key in scenario_values.keys() if key not in valid_driver_ids]
        if invalid_driver_keys:
            return None, {
                "error": "invalid scenario_states driver key(s)",
                "invalid_keys": invalid_driver_keys,
            }

        cleaned = {}
        for driver_id, state in scenario_values.items():
            if state not in THESIS_SCENARIO_STATES:
                return None, {
                    "error": "invalid scenario_states value",
                    "scenario": scenario,
                    "driver_id": driver_id,
                    "value": state,
                    "allowed": sorted(THESIS_SCENARIO_STATES),
                }
            if driver_id in selected_ids:
                cleaned[driver_id] = state

        normalized[scenario] = cleaned

    return normalized, None


@app.route("/api/thesis/<ticker>", methods=["GET"])
def get_thesis(ticker):
    """
    GET /api/thesis/<ticker>
    文件存在 → 返回文件内容
    文件不存在 → 返回新建模板（不返 404）
    """
    # ── 校验 ticker ──
    try:
        canonical = canonical_ticker(ticker)
    except ValueError as e:
        return jsonify(_clean_nan({"error": str(e)})), 400

    # ── 尝试读已有 thesis ──
    try:
        existing = read_thesis(canonical)
    except Exception:
        # 细节写服务端日志，前端只看到通用错误（避免泄露文件路径/内部信息）
        app.logger.exception("read_thesis failed for %s", canonical)
        return jsonify(_clean_nan({"error": "读取 thesis 失败"})), 500

    if existing is not None:
        existing.setdefault("core_thesis", "")
        existing.setdefault("key_risks", "")
        existing.setdefault("thesis_notes", "")
        existing.setdefault("driver_interpretations", {})
        if existing.get("schema_version") != THESIS_SCHEMA_VERSION:
            scenario_states = existing.get("scenario_states")
            normalized_states = _default_scenario_states()
            if isinstance(scenario_states, dict):
                for scenario in THESIS_SCENARIOS:
                    if isinstance(scenario_states.get(scenario), dict):
                        normalized_states[scenario] = scenario_states[scenario]
            existing["scenario_states"] = normalized_states
        return jsonify(_clean_nan(existing))

    # ── 文件不存在：构造模板 ──
    # 仅在此处允许调 get_quote_router 取 company_name，任何异常 fallback 到 canonical
    company_name = canonical
    try:
        q    = get_quote_router(canonical)
        name = q.get("name") if isinstance(q, dict) else None
        if name and isinstance(name, str) and name.strip():
            company_name = name
    except Exception:
        pass

    template = {
        "ticker"          : canonical,
        "company_name"    : company_name,
        "core_thesis"     : "",
        "key_risks"       : "",
        "thesis_notes"    : "",
        "drivers_selected": [],
        "driver_interpretations": {},
        "scenario_states": _default_scenario_states(),
        "industry_warning": None,
        "schema_version"  : THESIS_SCHEMA_VERSION,
        "last_modified"   : None,
    }
    return jsonify(_clean_nan(template))


@app.route("/api/thesis/<ticker>", methods=["PUT"])
def put_thesis(ticker):
    """
    PUT /api/thesis/<ticker>
    校验 payload + 覆写文件。
    last_modified 由 thesis_store.write_thesis 内部生成（本路由不参与）。
    """
    # ── (a) 校验 ticker ──
    try:
        canonical = canonical_ticker(ticker)
    except ValueError as e:
        return jsonify(_clean_nan({"error": str(e)})), 400

    # ── (b) body 必须是 dict ──
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(_clean_nan({"error": "body 必须是 JSON 对象"})), 400

    # ── (c) body.ticker 必须等于 canonical(path_ticker) ──
    body_ticker = body.get("ticker")
    if body_ticker != canonical:
        return jsonify(_clean_nan({
            "error"        : "path 和 body 中的 ticker 不一致",
            "path_ticker"  : canonical,
            "body_ticker"  : body_ticker,
        })), 400

    # ── (d) schema_version 必须是兼容版本 ──
    if body.get("schema_version") not in THESIS_ACCEPTED_SCHEMA_VERSIONS:
        return jsonify(_clean_nan({
            "error"            : "schema_version 不匹配",
            "expected"         : sorted(THESIS_ACCEPTED_SCHEMA_VERSIONS),
            "received"         : body.get("schema_version"),
        })), 400

    # ── (e) drivers_selected 必须是 list ──
    drivers_selected = body.get("drivers_selected")
    if not isinstance(drivers_selected, list):
        return jsonify(_clean_nan({"error": "drivers_selected 必须是 list"})), 400

    # ── (f) drivers_selected 中每个元素必须是已知 driver id ──
    valid_ids = set(_ONTOLOGY_DRIVERS.keys())
    unknown   = [d for d in drivers_selected if d not in valid_ids]
    if unknown:
        return jsonify(_clean_nan({
            "error"  : "unknown driver id(s)",
            "unknown": unknown,
        })), 400

    body.setdefault("core_thesis", "")
    body.setdefault("key_risks", "")
    body.setdefault("thesis_notes", "")
    driver_interpretations = body.get("driver_interpretations", {})
    if not isinstance(driver_interpretations, dict):
        return jsonify(_clean_nan({"error": "driver_interpretations 必须是 dict"})), 400

    invalid_keys = [k for k in driver_interpretations.keys() if k not in valid_ids]
    if invalid_keys:
        return jsonify(_clean_nan({
            "error"       : "invalid driver_interpretations key(s)",
            "invalid_keys": invalid_keys,
        })), 400

    cleaned_interpretations = {}
    for key, value in driver_interpretations.items():
        if not isinstance(value, str):
            return jsonify(_clean_nan({
                "error": "driver_interpretations value 必须是 string",
                "key"  : key,
            })), 400
        if value.strip():
            cleaned_interpretations[key] = value
    body["driver_interpretations"] = cleaned_interpretations
    scenario_states, scenario_error = _normalize_scenario_states(
        body.get("scenario_states", {}),
        valid_ids,
        drivers_selected,
    )
    if scenario_error is not None:
        return jsonify(_clean_nan(scenario_error)), 400

    body["scenario_states"] = scenario_states
    body["schema_version"] = THESIS_SCHEMA_VERSION

    # ── 写入（write_thesis 内部会覆盖 last_modified 为 UTC now）──
    try:
        write_thesis(canonical, body)
    except Exception:
        app.logger.exception("write_thesis failed for %s", canonical)
        return jsonify(_clean_nan({"error": "写入 thesis 失败"})), 500

    # 返回写入后的 payload（含被覆盖的 last_modified）
    return jsonify(_clean_nan(body))


# ── DCF 默认值拉取 ────────────────────────────────────────────────────────────

# Scenario DCF persistence (v3.4.5): Bull/Bear snapshots only.

@app.route("/api/modeling/dcf/scenarios/<symbol>", methods=["GET"])
def api_get_scenarios(symbol):
    try:
        doc = read_scenarios(symbol)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    def _meta(entry):
        if entry is None:
            return None
        public_entry = _public_scenario_entry(entry)
        v = entry.get("valuation", {})
        return {
            "intrinsic_per_share": v.get("intrinsic_per_share"),
            "currency": v.get("currency"),
            "saved_at": entry.get("saved_at"),
            "updated_at": entry.get("updated_at"),
            "params": public_entry.get("params"),
            "compatibility": public_entry.get("compatibility"),
        }

    return jsonify({
        "symbol": doc["symbol"],
        "bull": _meta(doc["scenarios"]["bull"]),
        "bear": _meta(doc["scenarios"]["bear"]),
    })


def _normalize_dcf_scenario_params(params: dict) -> dict:
    normalized = dict(params or {})
    legacy_fcf_growth_mapped = "revenue_growth" not in normalized and "fcf_growth" in normalized
    fallback_growth = normalized.get("revenue_growth", normalized.get("fcf_growth", 0.03))
    try:
        fallback_growth = float(fallback_growth)
    except (TypeError, ValueError):
        fallback_growth = 0.03

    defaults = derive_driver_defaults(normalized, fallback_growth=fallback_growth)
    for key, val in defaults.items():
        normalized.setdefault(key, val)
    normalized.pop("fcf_growth", None)

    # V3.9.0 Forecast Path Upgrade v1: keep stored path values when present,
    # otherwise fall back to flat 5-year expansion of the single value driver.
    # Old scenarios without path fields therefore behave exactly as before.
    for key in (
        "revenue_growth",
        "ebit_margin",
        "da_pct_revenue",
        "capex_pct_revenue",
        "wc_change_pct_revenue",
    ):
        path_key = f"{key}_path"
        existing = normalized.get(path_key)
        if isinstance(existing, (list, tuple)) and len(existing) > 0:
            try:
                normalized[path_key] = [float(x) for x in existing]
            except (TypeError, ValueError):
                normalized[path_key] = [float(normalized.get(key) or 0.0)] * 5
        else:
            normalized[path_key] = [float(normalized.get(key) or 0.0)] * 5
    if legacy_fcf_growth_mapped:
        normalized["_legacy_fcf_growth_mapped"] = True

    # V3.7.3: scenarios persist the treatment KEY (never the label) so future
    # label edits do not invalidate stored documents. Older scenarios without
    # this field default to reported_input_net_debt - preserving V3.7.2 IV.
    raw_treatment = normalized.get("selected_net_debt_treatment")
    treatment_key, _label, fallback_used = normalize_net_debt_treatment(raw_treatment)
    normalized["selected_net_debt_treatment"] = treatment_key
    if raw_treatment is None:
        normalized["_net_debt_treatment_defaulted"] = True
    elif fallback_used:
        normalized["_net_debt_treatment_fallback_used"] = True

    # V3.7.4 Shareholder Returns v1. Store keys (never labels). Missing fields
    # default to current_reported_shares / pct_fcf so headline IV is preserved
    # for old scenarios.
    raw_share_treatment = normalized.get("selected_share_count_treatment")
    share_key, _, share_fallback = normalize_share_count_treatment(raw_share_treatment)
    normalized["selected_share_count_treatment"] = share_key
    if raw_share_treatment is None:
        normalized["_share_count_treatment_defaulted"] = True
    elif share_fallback:
        normalized["_share_count_treatment_fallback_used"] = True

    raw_method = normalized.get("buyback_method")
    method_key, _, _ = normalize_buyback_method(raw_method)
    normalized["buyback_method"] = method_key

    # V3.7.5 WACC treatment. Store key (never label). Missing defaults to
    # selected_model_wacc, preserving V3.7.4 IV for old scenarios.
    raw_wacc_treatment = normalized.get("selected_wacc_treatment")
    wacc_key, _, wacc_fallback = normalize_wacc_treatment(raw_wacc_treatment)
    normalized["selected_wacc_treatment"] = wacc_key
    if raw_wacc_treatment is None:
        normalized["_wacc_treatment_defaulted"] = True
    elif wacc_fallback:
        normalized["_wacc_treatment_fallback_used"] = True

    # V3.7.6 Terminal Value treatment. Store key (never label). Missing
    # defaults to current_model_terminal, preserving V3.7.5 IV.
    raw_terminal_treatment = normalized.get("selected_terminal_treatment")
    terminal_key, _, terminal_fallback = normalize_terminal_treatment(raw_terminal_treatment)
    normalized["selected_terminal_treatment"] = terminal_key
    if raw_terminal_treatment is None:
        normalized["_terminal_treatment_defaulted"] = True
    elif terminal_fallback:
        normalized["_terminal_treatment_fallback_used"] = True
    for h_key in ("h_model_g_near", "h_model_g_long", "h_model_half_life"):
        if h_key in normalized and normalized.get(h_key) is not None:
            try:
                normalized[h_key] = float(normalized[h_key])
            except (TypeError, ValueError):
                normalized.pop(h_key, None)
    for key in ("minimum_cash_floor", "marketable_securities_available_for_returns", "pre_tax_cost_of_debt"):
        if key in normalized and normalized.get(key) is not None:
            try:
                normalized[key] = float(normalized[key])
            except (TypeError, ValueError):
                normalized.pop(key, None)
    normalized.setdefault("buyback_funding_treatment", DEFAULT_BUYBACK_FUNDING_TREATMENT)
    raw_path_source = normalized.get("selected_operating_path_source")
    op_source, _, op_fallback, op_defaulted = normalize_operating_path_source(
        raw_path_source, normalized.get("symbol")
    )
    normalized["selected_operating_path_source"] = op_source
    if op_defaulted:
        normalized["_operating_path_source_legacy_defaulted"] = True
    elif op_fallback:
        normalized["_operating_path_source_fallback_used"] = True
    return normalized


def _public_scenario_entry(entry: dict) -> dict:
    normalized_entry = dict(entry)
    params = _normalize_dcf_scenario_params(entry.get("params") or {})
    legacy_mapped = bool(params.pop("_legacy_fcf_growth_mapped", False))
    treatment_defaulted = bool(params.pop("_net_debt_treatment_defaulted", False))
    treatment_fallback = bool(params.pop("_net_debt_treatment_fallback_used", False))
    share_count_defaulted = bool(params.pop("_share_count_treatment_defaulted", False))
    share_count_fallback = bool(params.pop("_share_count_treatment_fallback_used", False))
    wacc_treatment_defaulted = bool(params.pop("_wacc_treatment_defaulted", False))
    wacc_treatment_fallback = bool(params.pop("_wacc_treatment_fallback_used", False))
    terminal_treatment_defaulted = bool(params.pop("_terminal_treatment_defaulted", False))
    terminal_treatment_fallback = bool(params.pop("_terminal_treatment_fallback_used", False))
    op_source_defaulted = bool(params.pop("_operating_path_source_legacy_defaulted", False))
    op_source_fallback = bool(params.pop("_operating_path_source_fallback_used", False))
    normalized_entry["params"] = params
    treatment_key = params.get("selected_net_debt_treatment", DEFAULT_NET_DEBT_TREATMENT)
    share_count_key = params.get("selected_share_count_treatment", DEFAULT_SHARE_COUNT_TREATMENT)
    wacc_treatment_key = params.get("selected_wacc_treatment", DEFAULT_WACC_TREATMENT)
    terminal_treatment_key = params.get("selected_terminal_treatment", DEFAULT_TERMINAL_TREATMENT)
    op_source_key = params.get("selected_operating_path_source", "Selected Path")
    normalized_entry["compatibility"] = {
        "legacy_fcf_growth_mapped": legacy_mapped,
        # V3.7.3 transparency.
        "net_debt_treatment_defaulted": treatment_defaulted,
        "net_debt_treatment_fallback_used": treatment_fallback,
        "selected_net_debt_treatment": treatment_key,
        "selected_net_debt_treatment_label": NET_DEBT_TREATMENT_LABELS.get(
            treatment_key, NET_DEBT_TREATMENT_LABELS[DEFAULT_NET_DEBT_TREATMENT]
        ),
        # V3.7.4 transparency: share-count treatment.
        "share_count_treatment_defaulted": share_count_defaulted,
        "share_count_treatment_fallback_used": share_count_fallback,
        "selected_share_count_treatment": share_count_key,
        "selected_share_count_treatment_label": SHARE_COUNT_TREATMENT_LABELS.get(
            share_count_key, SHARE_COUNT_TREATMENT_LABELS[DEFAULT_SHARE_COUNT_TREATMENT]
        ),
        # V3.7.5 transparency: WACC treatment.
        "wacc_treatment_defaulted": wacc_treatment_defaulted,
        "wacc_treatment_fallback_used": wacc_treatment_fallback,
        "selected_wacc_treatment": wacc_treatment_key,
        "selected_wacc_treatment_label": WACC_TREATMENT_LABELS.get(
            wacc_treatment_key, WACC_TREATMENT_LABELS[DEFAULT_WACC_TREATMENT]
        ),
        # V3.7.6 transparency: Terminal Value treatment.
        "terminal_treatment_defaulted": terminal_treatment_defaulted,
        "terminal_treatment_fallback_used": terminal_treatment_fallback,
        "selected_terminal_treatment": terminal_treatment_key,
        "selected_terminal_treatment_label": TERMINAL_TREATMENT_LABELS.get(
            terminal_treatment_key, TERMINAL_TREATMENT_LABELS[DEFAULT_TERMINAL_TREATMENT]
        ),
        "operating_path_source_defaulted_from_legacy": op_source_defaulted,
        "operating_path_source_fallback_used": op_source_fallback,
        "selected_operating_path_source": op_source_key,
        "selected_operating_path_source_label": op_source_key,
        "operating_path_source_audit_flag": (
            "selected_operating_path_source = Selected Path (defaulted from legacy); scenario was saved before Bridge engine-driving was available."
            if op_source_defaulted else ""
        ),
    }
    return normalized_entry


def _normalize_scenario_doc_for_export(doc: dict | None) -> dict | None:
    if not isinstance(doc, dict):
        return doc
    normalized_doc = dict(doc)
    scenarios = dict(normalized_doc.get("scenarios") or {})
    for scenario_type in ("bull", "bear"):
        entry = scenarios.get(scenario_type)
        if isinstance(entry, dict):
            scenarios[scenario_type] = _public_scenario_entry(entry)
    normalized_doc["scenarios"] = scenarios
    return normalized_doc


def _clean_params_for_persist(params: dict) -> dict:
    cleaned = _normalize_dcf_scenario_params(params)
    cleaned.pop("_legacy_fcf_growth_mapped", None)
    cleaned.pop("_net_debt_treatment_defaulted", None)
    cleaned.pop("_net_debt_treatment_fallback_used", None)
    cleaned.pop("_share_count_treatment_defaulted", None)
    cleaned.pop("_share_count_treatment_fallback_used", None)
    cleaned.pop("_wacc_treatment_defaulted", None)
    cleaned.pop("_wacc_treatment_fallback_used", None)
    cleaned.pop("_terminal_treatment_defaulted", None)
    cleaned.pop("_terminal_treatment_fallback_used", None)
    cleaned.pop("_operating_path_source_legacy_defaulted", None)
    cleaned.pop("_operating_path_source_fallback_used", None)
    cleaned.pop("fcf_growth", None)
    return cleaned


@app.route("/api/modeling/dcf/scenario/<symbol>/<scenario_type>", methods=["GET"])
def api_get_scenario(symbol, scenario_type):
    if scenario_type not in {"bull", "bear"}:
        return jsonify({"error": "scenario_type must be bull or bear"}), 400

    try:
        doc = read_scenarios(symbol)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    entry = doc["scenarios"].get(scenario_type)
    if entry is None:
        return jsonify({"error": "scenario not found"}), 404

    return jsonify(_public_scenario_entry(entry))


@app.route("/api/modeling/dcf/scenario/<symbol>/<scenario_type>", methods=["PUT"])
def api_put_scenario(symbol, scenario_type):
    if scenario_type not in {"bull", "bear"}:
        return jsonify({"error": "scenario_type must be bull or bear"}), 400

    payload = request.get_json(silent=True) or {}

    if not isinstance(payload.get("params"), dict):
        return jsonify({"error": "params required"}), 400
    if not isinstance(payload.get("valuation"), dict):
        return jsonify({"error": "valuation required"}), 400

    payload["params"] = _clean_params_for_persist(payload["params"])

    required_params = {
        "symbol", "wacc", "terminal_g",
        "exit_multiple", "tv_method", "forecast_years",
        "revenue", "ebit", "da", "capex", "wc_change",
        "tax_rate", "net_debt", "shares",
    }
    driver_params = {
        "revenue_growth", "ebit_margin", "da_pct_revenue",
        "capex_pct_revenue", "wc_change_pct_revenue",
    }
    missing = required_params - set(payload["params"].keys())
    if "revenue_growth" not in payload["params"]:
        missing.add("revenue_growth")
    missing |= driver_params - set(payload["params"].keys()) - {"revenue_growth"}
    if missing:
        return jsonify({"error": "params missing keys", "missing": sorted(missing)}), 400

    if "intrinsic_per_share" not in payload["valuation"]:
        return jsonify({"error": "valuation.intrinsic_per_share required"}), 400

    try:
        doc = write_scenario(symbol, scenario_type, payload)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception:
        app.logger.exception("write_scenario failed for %s/%s", symbol, scenario_type)
        return jsonify({"error": "write failed"}), 500

    return jsonify(doc["scenarios"][scenario_type])


@app.route("/api/modeling/dcf/scenario/<symbol>/<scenario_type>", methods=["DELETE"])
def api_delete_scenario(symbol, scenario_type):
    if scenario_type not in {"bull", "bear"}:
        return jsonify({"error": "scenario_type must be bull or bear"}), 400

    try:
        delete_scenario(symbol, scenario_type)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception:
        app.logger.exception("delete_scenario failed for %s/%s", symbol, scenario_type)
        return jsonify({"error": "delete failed"}), 500

    return jsonify({"deleted": True, "scenario_type": scenario_type})


_INDUSTRY_BANNER_HARD = {
    "exchange_financial_infra": (
        "交易所基础设施类公司 (港交所/纳斯达克/CME 类)。其收入来自交易手续费、"
        "上市费、数据服务,业务模型与 DCF FCFF 假设不匹配。建议参考 P/E、"
        "EV/EBITDA、ROE。"
    ),
    "bank": (
        "银行业不适用 DCF 模型。银行的'债务'是经营资本,FCFF 概念在银行业不成立。"
        "建议使用 P/B、ROE、Excess Return Model 或 Residual Income Model。"
    ),
    "insurance_life": (
        "寿险公司不适用 DCF 模型。寿险负债是 actuarial reserves,需用 Embedded "
        "Value (EV) 或 Appraisal Value (AV) 估值。建议参考 P/EV、P/B、ROE。"
    ),
    "insurance_property": (
        "财险公司 DCF 适用性有限。建议参考 P/B、Combined Ratio、ROE。"
    ),
    "broker_dealer": (
        "券商类公司 DCF 适用性有限,因 trading book 波动大。建议参考 P/B、ROE、"
        "AUM-based metrics。"
    ),
    "asset_manager": (
        "资管公司估值核心是 AUM × management fee,DCF 可用但建议交叉验证 P/AUM "
        "或 P/Fee revenue。"
    ),
    "reit": (
        "REIT 不适用 FCFF DCF。建议使用 AFFO (Adjusted Funds From Operations)、"
        "Dividend Discount Model、Cap Rate 或 NAV 法。"
    ),
    "mortgage_lender": (
        "抵押贷款公司不适用 DCF 模型。建议使用 P/B、ROE、charge-off rate 分析。"
    ),
}

_INDUSTRY_RECOMMENDED_METHODS = {
    "exchange_financial_infra": ["P/E", "EV/EBITDA", "ROE"],
    "bank": ["P/B", "ROE", "Excess Return Model"],
    "insurance_life": ["P/EV", "P/B", "ROE", "Embedded Value"],
    "insurance_property": ["P/B", "Combined Ratio", "ROE"],
    "broker_dealer": ["P/B", "ROE"],
    "asset_manager": ["P/AUM", "P/Fee revenue"],
    "reit": ["AFFO", "P/FFO", "Cap Rate", "NAV"],
    "mortgage_lender": ["P/B", "ROE"],
}

_INDUSTRY_BANNER_SOFT = {
    "fintech_payment": (
        "支付/Fintech 类公司 DCF 可用,但 take rate、TPV 增长、监管风险需重点关注。"
        "建议交叉验证 EV/Revenue、EV/TPV。"
    ),
    "biotech_clinical_stage": (
        "临床期生物科技公司 DCF 高度不可靠 (FCF 长期为负,价值来自 pipeline 期权)。"
        "建议使用 rNPV (risk-adjusted NPV) 或 Pipeline Sum-of-the-parts。"
    ),
}


def _detect_industry_warning(symbol: str) -> dict | None:
    """
    V3.9.11 Batch 2A: industry-aware DCF suitability banner.

    Uses modeling.industry_classification (ticker whitelist + yfinance sector
    fallback). Returns either a hard banner (model_unsuitable_industry) for
    bank/insurance/REIT/etc., or a soft caution (dcf_caution_industry) for
    fintech/clinical biotech, or None.

    The whitelist is precise; the yfinance fallback only fires when the ticker
    is not in the whitelist. Any yfinance exception → None (avoid false
    positives on a transient outage).
    """
    from modeling.industry_classification import (
        classify_industry,
        MODEL_UNSUITABLE_INDUSTRIES,
        DCF_CAUTION_INDUSTRIES,
    )

    profile = {}
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).info or {}
        sector = info.get("sector", "")
        sym_upper = symbol.upper()
        profile = {
            "is_financial": sector == "Financial Services",
            "is_software_like": sector == "Technology",
            "is_pharma_or_manufacturing": sector in ("Healthcare", "Industrials"),
            "non_us": sym_upper.endswith(".HK") or sym_upper.endswith(".SS") or sym_upper.endswith(".SZ"),
        }
    except Exception:
        profile = {}

    industry = classify_industry(symbol, profile)

    if industry in MODEL_UNSUITABLE_INDUSTRIES:
        return {
            "type": "valuation_warning",
            "category": "model_unsuitable_industry",
            "industry_classification": industry,
            "severity": "hard",
            "message": _INDUSTRY_BANNER_HARD.get(
                industry,
                f"{industry} 类公司 DCF 模型适用性存疑,请审慎使用。",
            ),
            "recommended_methods": _INDUSTRY_RECOMMENDED_METHODS.get(
                industry, ["P/B", "ROE"]
            ),
        }

    if industry in DCF_CAUTION_INDUSTRIES:
        return {
            "type": "valuation_caution",
            "category": "dcf_caution_industry",
            "industry_classification": industry,
            "severity": "soft",
            "message": _INDUSTRY_BANNER_SOFT.get(
                industry, f"{industry} 类公司 DCF 使用请审慎。"
            ),
        }

    return None


def _float_or_none(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_path(value):
    """V3.9.0: coerce an optional 5-year path field for DCFInputs.

    Accepts list/tuple of numeric-coercible values. Returns None when the
    payload omits the field or supplies an empty/invalid container, so the
    calculator falls back to flat-expanding the single value driver.
    """
    if value is None:
        return None
    if isinstance(value, (list, tuple)) and len(value) > 0:
        out = []
        for entry in value:
            try:
                out.append(float(entry))
            except (TypeError, ValueError):
                return None
        return out
    return None


_EXIT_MULTIPLE_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "cache"
)


def _exit_multiple_cache_path(symbol: str, today: str) -> str:
    safe_symbol = symbol.replace("/", "_").replace("\\", "_")
    return os.path.join(
        _EXIT_MULTIPLE_CACHE_DIR,
        f"market_defaults_{safe_symbol}_{today}.json",
    )


def _load_exit_multiple_cache(symbol: str, today: str) -> dict | None:
    path = _exit_multiple_cache_path(symbol, today)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return None
    raw = payload.get("raw_value")
    try:
        raw_f = float(raw)
    except (TypeError, ValueError):
        return None
    if not (raw_f > 0):
        return None
    return payload


def _write_exit_multiple_cache(symbol: str, today: str, raw_value: float, rounded: float) -> str:
    os.makedirs(_EXIT_MULTIPLE_CACHE_DIR, exist_ok=True)
    path = _exit_multiple_cache_path(symbol, today)
    payload = {
        "symbol": symbol,
        "date": today,
        "fetched_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "source": "yfinance",
        "field": "enterpriseToEbitda",
        "raw_value": raw_value,
        "rounded_exit_multiple": rounded,
    }
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception:
        return ""
    return path


AAPL_DEFAULT_REVENUE_GROWTH_PATH = [0.040, 0.045, 0.050, 0.045, 0.040]
AAPL_DEFAULT_EBIT_MARGIN_PATH = [0.328, 0.331, 0.334, 0.336, 0.336]


def _default_forecast_paths(symbol: str, driver_defaults: dict) -> dict:
    """Return explicit 5-year default forecast paths.

    AAPL gets a neutral top-down base default so the base export is not a
    flat template path. Other tickers retain the existing flat fallback.
    """
    if str(symbol or "").strip().upper() == "AAPL":
        return {
            "revenue_growth_path": AAPL_DEFAULT_REVENUE_GROWTH_PATH[:],
            "ebit_margin_path": AAPL_DEFAULT_EBIT_MARGIN_PATH[:],
            "forecast_path_source": "AAPL neutral top-down base default",
            "forecast_path_note": (
                "AAPL default Base path reflects modest Products maturity, Services mix support, "
                "and stable-to-slightly-improving operating margin; it is user-editable and is not a full segment model."
            ),
        }
    return {
        "revenue_growth_path": [round(driver_defaults["revenue_growth"], 6)] * 5,
        "ebit_margin_path": [round(driver_defaults["ebit_margin"], 6)] * 5,
        "forecast_path_source": "flat fallback from single driver",
        "forecast_path_note": (
            "No ticker-specific operating path is configured; defaults flat-expand the single driver."
        ),
    }


def _derive_exit_multiple_default(symbol: str, market: str, quote: dict, fin: dict) -> dict:
    """
    Default exit multiple source chain:
    1. Direct market EV/EBITDA from yfinance when available, with deterministic
       daily cache so successive defaults fetches on the same calendar day
       return the same value. V3.9.2 Input Source Comments & Data Determinism
       Lock fixes the AAPL IV anchor drift observed in V3.9.0/V3.9.1 smoke.
    2. Quote-implied EV/EBITDA: (market cap + net debt) / EBITDA.
    3. Transparent 15.0x industry fallback.
    """
    if market == "US":
        today = date.today().isoformat()
        cached = _load_exit_multiple_cache(symbol, today)
        if cached is not None:
            raw_f = float(cached["raw_value"])
            return {
                "value": max(5.0, min(50.0, raw_f)),
                "source": "yfinance.enterpriseToEbitda (daily cache)",
                "warning": None,
                "fetched_at": cached.get("fetched_at"),
                "cache_file": _exit_multiple_cache_path(symbol, today),
                "raw_value": raw_f,
                "cache_date": cached.get("date"),
            }
        try:
            import yfinance as yf
            info = yf.Ticker(symbol).info
            em = _float_or_none(info.get("enterpriseToEbitda"))
            if em and em > 0:
                rounded = max(5.0, min(50.0, em))
                cache_path = _write_exit_multiple_cache(symbol, today, em, round(rounded, 1))
                return {
                    "value": rounded,
                    "source": "yfinance.enterpriseToEbitda (daily cache)",
                    "warning": None,
                    "fetched_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "cache_file": cache_path or _exit_multiple_cache_path(symbol, today),
                    "raw_value": em,
                    "cache_date": today,
                }
        except Exception:
            pass

    market_cap = _float_or_none((quote or {}).get("market_cap"))
    price = _float_or_none((quote or {}).get("current_price"))
    shares = _float_or_none((fin or {}).get("shares"))
    if not market_cap and price and shares:
        market_cap = price * shares

    ebit = _float_or_none((fin or {}).get("ebit")) or 0.0
    da = _float_or_none((fin or {}).get("da")) or 0.0
    ebitda = ebit + da
    net_debt = _float_or_none((fin or {}).get("net_debt")) or 0.0
    if market_cap and market_cap > 0 and ebitda > 0:
        implied = (market_cap + net_debt) / ebitda
        return {
            "value": max(5.0, min(50.0, implied)),
            "source": "quote_implied_ev_to_ebitda",
            "warning": (
                "Exit multiple derived from quote market cap plus net debt divided by cached EBITDA; "
                "direct market EV/EBITDA was unavailable."
            ),
        }

    return {
        "value": 15.0,
        "source": "industry_fallback",
        "warning": "Exit multiple uses a conservative 15.0x fallback because direct and quote-implied EV/EBITDA were unavailable.",
    }


def _financials_cache_meta(symbol: str) -> dict:
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "data",
        "cache",
        f"financials_{symbol}_{FINANCIALS_CACHE_VERSION}.json",
    )
    meta = {"path": path, "exists": os.path.exists(path), "cached_at": None, "stale": False}
    if not meta["exists"]:
        return meta
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        meta["cached_at"] = payload.get("cached_at")
        if meta["cached_at"]:
            cached_at = datetime.fromisoformat(str(meta["cached_at"]))
            meta["stale"] = (datetime.now() - cached_at).total_seconds() > 36 * 3600
    except Exception:
        meta["stale"] = True
    return meta


def _default_quality_profile(symbol: str, company: str, market: str) -> dict:
    text = f"{symbol} {company}".lower()
    is_financial = _detect_industry_warning(symbol) is not None
    is_software_like = any(x in text for x in (
        "software", "internet", "tencent", "games", "cloud", "platform", "semiconductor"
    ))
    is_pharma_or_manufacturing = any(x in text for x in (
        "wuxi", "apptec", "药", "医", "pharma", "biotech", "cro", "cdmo",
        "manufacturing", "manufacture", "工业", "制造", "maotai", "moutai",
    ))
    return {
        "non_us": market != "US",
        "is_financial": is_financial,
        "is_software_like": is_software_like,
        "is_pharma_or_manufacturing": is_pharma_or_manufacturing,
    }


_TIER_PRIORITY = {"Blocking": 4, "High Review": 3, "Review": 2, "Clean": 1}


def _apply_default_quality_gates(symbol: str, company: str, market: str, fin: dict,
                                 driver_defaults: dict, wacc: float, beta: float) -> tuple[dict, float, dict]:
    """V3.9.11: three-layer flag-only defense.

    Layer 1 data_health     — raw CF coverage / suspicious zeros (does not rewrite values).
    Layer 2 economic_sanity — margin vs industry P95 (does not rewrite values).
    Layer 3 composite_banner — explains the combined picture for the UI.

    The WACC 8% floor is preserved as an independent economic gate. The earlier
    V3.9.10.2 rewrites of ebit_margin / capex_pct_revenue / wc_change_pct_revenue
    are intentionally removed — data is reported as-is and surfaced via flags.
    """
    from modeling.data_quality import (
        build_capex_field_review,
        build_capex_sanity_audit,
        build_net_debt_currency_audit,
        build_normalized_ebit_review,
        build_period_alignment_audit,
        check_data_health,
        check_economic_sanity,
    )

    profile = _default_quality_profile(symbol, company, market)
    adjusted = dict(driver_defaults)
    raw = {
        "revenue": fin.get("revenue"),
        "ebit": fin.get("ebit"),
        "da": fin.get("da"),
        "capex": fin.get("capex"),
        "wc_change": fin.get("wc_change"),
        "net_debt": fin.get("net_debt"),
        "beta": beta,
        "wacc": wacc,
        "driver_defaults": dict(driver_defaults),
        "capex_source_fields": fin.get("capex_source_fields"),
        "ebit_source_field": fin.get("ebit_source_field"),
        "period_alignment": fin.get("period_alignment"),
        "capex_sanity": fin.get("capex_sanity"),
        "capex_review": fin.get("capex_review"),
        "raw_cash_flow_items": fin.get("raw_cash_flow_items"),
        "net_debt_currency_audit": fin.get("net_debt_currency_audit"),
    }

    # Layer 1 + 2: flag-only checks against raw financials.
    raw_for_checks = {
        "revenue": fin.get("revenue"),
        "ebit": fin.get("ebit"),
        "da": fin.get("da"),
        "capex": fin.get("capex"),
        "wc_change": fin.get("wc_change"),
        "capex_source_fields": fin.get("capex_source_fields", []),
        "wc_source_audit": fin.get("wc_source_audit"),
        "capex_history": fin.get("capex_history") or fin.get("historical_capex"),
        "normalized_ebit_adjustments": fin.get("normalized_ebit_adjustments")
            or fin.get("normalized_ebit_candidate_fields")
            or fin.get("ebit_adjustment_candidates"),
    }
    data_health = check_data_health(raw_for_checks, profile)
    economic_sanity = check_economic_sanity(symbol, raw_for_checks, profile)
    normalized_ebit_review = build_normalized_ebit_review(symbol, raw_for_checks, profile, economic_sanity)
    period_alignment = fin.get("period_alignment") or build_period_alignment_audit(fin)
    capex_sanity = fin.get("capex_sanity") or build_capex_sanity_audit(symbol, fin, profile)
    capex_review = fin.get("capex_review") or build_capex_field_review(
        symbol,
        fin.get("raw_cash_flow_items") or fin.get("cash_flow_items"),
        current_capex=fin.get("capex"),
        matched_fields=fin.get("capex_source_fields"),
    )
    all_issues = list(data_health["issues"]) + list(economic_sanity["issues"])
    if capex_sanity.get("status") in {"Review", "High Review"} and capex_sanity.get("years_available", 0) >= 3:
        all_issues.append({
            "key": "capex_multi_year_sanity",
            "tier": capex_sanity["status"],
            "message": capex_sanity.get("warning") or capex_sanity.get("interpretation"),
            "source_field": "financials capex_history",
        })
    if capex_review and capex_review.get("status") == "High Review":
        all_issues.append({
            "key": "capex_override_candidate",
            "tier": "High Review",
            "message": capex_review.get("warning"),
            "source_field": capex_review.get("candidate_field") or "HK cash flow statement",
        })

    # WACC 8% floor (independent economic gate, preserved from V3.9.10.2).
    adjusted_wacc = float(wacc or 0.0)
    if profile["non_us"] and not profile["is_financial"] and adjusted_wacc < 0.08:
        all_issues.append({
            "key": "wacc_below_floor",
            "tier": "Review",
            "raw_value": adjusted_wacc,
            "replacement": 0.08,
            "message": (
                "Selected/model WACC was below the 8.0% floor for HK/CN "
                "non-financial defaults; adjusted upward. User override "
                "remains allowed."
            ),
            "source_field": "MARKET_CONFIG rf/ERP + financials cache beta",
        })
        adjusted_wacc = 0.08

    # Source-quality (stale/missing/fabricated cache) — keep as Review issue.
    cache_meta = _financials_cache_meta(symbol)
    if not cache_meta.get("exists") or cache_meta.get("stale") or fin.get("_error"):
        all_issues.append({
            "key": "source_quality",
            "tier": "Review",
            "message": (
                "Financials source is missing, stale, or fallback-derived; "
                "default assumptions require review before use."
            ),
            "original": fin.get("_error") or cache_meta.get("cached_at"),
            "source_field": f"data/cache/financials_{symbol}_{FINANCIALS_CACHE_VERSION}.json",
        })

    # Overall tier.
    if not all_issues:
        overall_tier = "Clean"
    else:
        overall_tier = max(
            (i["tier"] for i in all_issues),
            key=lambda t: _TIER_PRIORITY.get(t, 0),
        )

    # Composite banner (Layer 3).
    dh_flags = set(data_health["flags"])
    es_flags = set(economic_sanity["flags"])
    composite_banner = None
    if "capex_suspiciously_low" in dh_flags and "ebit_margin_above_industry_p95" in es_flags:
        composite_banner = (
            "Both upstream data quality issues (CapEx may not be fully "
            "captured) AND elevated EBIT margin detected. The high margin "
            "may be an artifact of incomplete CapEx data. Cross-check the "
            "source financial statements before using these defaults."
        )
    elif "ebit_margin_above_industry_p95" in es_flags:
        industry = next(
            (i.get("industry_classification") for i in all_issues
             if i["key"] == "ebit_margin_above_industry_p95"),
            "unknown",
        )
        composite_banner = (
            f"EBIT margin is high but data quality looks normal. May be a "
            f"genuine premium business ({industry}). Review and edit "
            f"assumption if needed."
        )
    elif dh_flags:
        composite_banner = (
            "Upstream data quality issues detected. Default assumptions "
            "may be unreliable; review carefully."
        )

    # Legacy keys preserved for downstream callers (share-count gate, UI).
    legacy_review_tier = "OK" if overall_tier == "Clean" else overall_tier
    legacy_banner = composite_banner or (
        "Default assumptions require review before use."
        if overall_tier != "Clean" else ""
    )

    return adjusted, adjusted_wacc, {
        "version": "V3.9.11",
        "overall_tier": overall_tier,
        "issues": all_issues,
        "composite_banner": composite_banner,
        "data_health_flags": list(dh_flags),
        "economic_sanity_flags": list(es_flags),
        # legacy compatibility
        "requires_review": overall_tier != "Clean",
        "review_tier": legacy_review_tier,
        "banner": legacy_banner,
        "raw_defaults": raw,
        "profile": profile,
        "financials_cache": cache_meta,
        "normalized_ebit_review": normalized_ebit_review,
        "period_alignment": period_alignment,
        "capex_sanity": capex_sanity,
        "capex_review": capex_review,
        "net_debt_currency_audit": fin.get("net_debt_currency_audit"),
    }


def _apply_share_count_quality_gate(symbol: str, quote: dict, fin: dict, default_quality: dict) -> tuple[float, dict]:
    """V3.9.10.3: reconcile DCF per-share denominator to total-company equity value.

    For DCF equity value, the denominator must be total ordinary/diluted shares,
    not a listed H-share float or partial share class. The most reliable local
    cross-check available in defaults is quote market cap / current price.
    """
    shares_cached = _float_or_none((fin or {}).get("shares")) or 0.0
    market_cap = _float_or_none((quote or {}).get("market_cap")) or 0.0
    price = _float_or_none((quote or {}).get("current_price")) or 0.0
    implied_shares = market_cap / price if market_cap > 0 and price > 0 else 0.0
    selected_shares = shares_cached
    issue = None

    if shares_cached > 0 and implied_shares > 0:
        ratio = max(shares_cached, implied_shares) / max(min(shares_cached, implied_shares), 1e-9)
        if ratio > 1.25:
            selected_shares = implied_shares
            issue = {
                "key": "shares",
                "tier": "High Review",
                "message": (
                    "Financials cache shares materially differ from market_cap / price implied total shares. "
                    "DCF equity value uses total-company equity, so the denominator was set to market-implied total shares pending source review."
                ),
                "original": shares_cached,
                "replacement": implied_shares,
                "source_field": "quote market_cap / current_price vs financials cache shares",
                "ratio": ratio,
            }
    elif implied_shares > 0 and shares_cached <= 0:
        selected_shares = implied_shares
        issue = {
            "key": "shares",
            "tier": "Review",
            "message": "Financials cache shares unavailable; using market_cap / price implied shares.",
            "original": shares_cached,
            "replacement": implied_shares,
            "source_field": "quote market_cap / current_price",
            "ratio": None,
        }

    quality = dict(default_quality or {})
    issues = list(quality.get("issues") or [])
    if issue:
        issues.append(issue)
        quality["issues"] = issues
        new_tier = max(
            (i.get("tier", "Review") for i in issues),
            key=lambda t: _TIER_PRIORITY.get(t, 0),
        )
        quality["overall_tier"] = new_tier
        quality["requires_review"] = True
        quality["review_tier"] = new_tier
        if not quality.get("composite_banner"):
            quality["banner"] = "Default assumptions require review before use."
    quality["share_count_reconciliation"] = {
        "cached_financials_shares_m": shares_cached,
        "market_cap_m": market_cap,
        "price": price,
        "market_implied_shares_m": implied_shares,
        "selected_default_shares_m": selected_shares,
        "selected_basis": (
            "market_cap / price implied total shares"
            if issue and selected_shares == implied_shares
            else "financials cache shares"
        ),
    }
    return selected_shares, quality


def _fetch_dcf_defaults(symbol: str, scenario: str = "base") -> dict:
    """
    用 router 拉取财报数据并组装 DCF 默认值。
    所有金额已在数据源层归一化为"百万原币种"。

    FCF 增长率默认值说明：
        v3.2 起不再用过去 3 年历史 CAGR——历史 CAGR 易因周期波动产生误导
        （例如 Apple 算出来 -0.41% 会让用户困惑）。
        现统一使用 3.0% 作为温和保守的跨行业起点，由用户根据公司实际调整。
    """
    market = detect_market(symbol)
    cfg    = MARKET_CONFIG[market]
    pre_security_type = detect_security_type(symbol, {}, market)
    if pre_security_type.get("dcf_suitability") == "unsuitable":
        return _build_unsuitable_defaults(symbol, symbol, market, cfg, {}, 0, cfg["currency"], pre_security_type, scenario)

    # ── 行情快照 ────────────────────────────────────────────
    q = {}
    try:
        q     = get_quote_router(symbol)
        price = q.get("current_price") or 0
        ccy   = q.get("currency") or cfg["currency"]
        name  = q.get("name") or symbol
    except Exception:
        q = {}
        price = 0
        ccy   = cfg["currency"]
        name  = symbol

    security_type = detect_security_type(symbol, q, market)
    if security_type.get("dcf_suitability") == "unsuitable":
        return _build_unsuitable_defaults(symbol, name, market, cfg, q, price, ccy, security_type, scenario)

    # ── 财务数据（已归一化为"百万"）────────────────────────
    defaults_warnings = []
    try:
        fin = get_financials_router(symbol)
    except Exception as e:
        fin = {
            "revenue": 0.0, "ebit": 0.0, "da": 0.0, "capex": 0.0,
            "wc_change": 0.0, "tax_rate": 0.21, "net_debt": 0.0,
            "shares": 1000.0, "beta": 1.0, "currency": ccy,
            "_error": f"financials_fetch_failed: {repr(e)}",
            "_fabricated": True,
            "_fabrication_reason": "fetch_exception",
        }
    if fin.get("warnings"):
        defaults_warnings.extend(list(fin.get("warnings") or []))
    if fin.get("_fabricated"):
        defaults_warnings.append(
            "Financial data fetch failed; defaults are placeholders with shares=1000M and beta=1.0. All assumptions require manual review before valuation use."
        )
    reporting_currency = fin.get("currency") or ccy
    reporting_currency_source = fin.get("reporting_currency_source") or fin.get("currency_detection")
    if not reporting_currency_source:
        reporting_currency_source = "us_default" if market == "US" else ("cn_default" if market == "CN" else "default_hkd_unverified")
    trading_currency_source = "quote_currency" if q.get("currency") else "market_config_default"
    currency_translation = _resolve_currency_translation(
        symbol,
        reporting_currency=reporting_currency,
        trading_currency=ccy,
        reporting_currency_source=reporting_currency_source,
        trading_currency_source=trading_currency_source,
    )
    from modeling.data_quality import build_net_debt_currency_audit
    net_debt_currency_audit = build_net_debt_currency_audit(symbol, fin, currency_translation)
    fin["net_debt_currency_audit"] = net_debt_currency_audit
    reporting_currency = currency_translation["reporting_currency"]
    reporting_currency_source = currency_translation["reporting_currency_source"]
    if currency_translation.get("currency_translation_warning"):
        defaults_warnings.append(currency_translation["currency_translation_warning"])
    if reporting_currency and ccy and str(reporting_currency).upper() != str(ccy).upper():
        defaults_warnings.append(
            f"financial statements reported in {reporting_currency}; quote in {ccy}; per-share IV requires explicit FX translation"
        )
    default_market_comparison_status = "available"
    if not _is_positive_finite(price):
        default_market_comparison_status = "unavailable"
        currency_translation = dict(currency_translation)
        currency_translation["market_comparison_allowed"] = False
        currency_translation["currency_translation_status"] = _elevate_review_status(
            currency_translation.get("currency_translation_status"),
            "Review",
        )
        _append_warning_once(defaults_warnings, "Current price unavailable; upside/downside comparison blocked.")

    # ── WACC：CAPM 法估算 ───────────────────────────────────
    beta = fin.get("beta", 1.0)
    beta = max(0.3, min(3.0, beta))
    ke   = cfg["rf"] + beta * cfg["erp"]
    # 假设 D/E = 30/70，债务税后成本 4%
    wacc = round(ke * 0.7 + 0.04 * (1 - fin.get("tax_rate", 0.21)) * 0.3, 4)

    # ── Exit Multiple 默认值 ────────────────────────────────
    # AKShare/yfinance 不一定有这个字段，给一个行业中枢值
    exit_multiple = 15.0
    # 美股可以从 yfinance 拿
    if False and market == "US":
        try:
            import yfinance as yf
            info = yf.Ticker(symbol).info
            em   = float(info.get("enterpriseToEbitda") or 15.0)
            exit_multiple = max(5.0, min(50.0, em))
        except Exception:
            pass

    exit_multiple_meta = _derive_exit_multiple_default(symbol, market, q, fin)
    exit_multiple = exit_multiple_meta["value"]

    # V3.9.8.9 AAPL Case Separation: the default-builder layer now serves the
    # true Base (default) OR Bear / Downside Case depending on the ``scenario``
    # argument. Both calibrations live in modeling.dcf_calculator and the
    # helper functions return overrides without mutating run_dcf. Non-AAPL
    # tickers are unaffected.
    aapl_case_calibration_meta = None
    is_aapl = str(symbol or "").strip().upper() == "AAPL"
    scenario_key = (scenario or "base").strip().lower()
    if scenario_key not in {"base", "bear"}:
        scenario_key = "base"
    if is_aapl:
        if scenario_key == "bear":
            wacc = AAPL_BEAR_DEFAULT_WACC
            exit_multiple = AAPL_BEAR_DEFAULT_EXIT_MULTIPLE
            case_label = "Bear / Downside Case"
            rationale = AAPL_BEAR_FORECAST_RATIONALE
            sel_wacc_t = AAPL_BEAR_DEFAULT_WACC_TREATMENT
            sel_term_t = AAPL_BEAR_DEFAULT_TERMINAL_TREATMENT
            sel_nd_t = AAPL_BEAR_DEFAULT_NET_DEBT_TREATMENT
            term_g = AAPL_BEAR_DEFAULT_TERMINAL_G
            blend_g = AAPL_BEAR_DEFAULT_BLEND_WEIGHT_GORDON
            blend_e = AAPL_BEAR_DEFAULT_BLEND_WEIGHT_EXIT
            scenario_rev_path = list(AAPL_BEAR_REVENUE_GROWTH_PATH)
            scenario_ebit_path = list(AAPL_BEAR_EBIT_MARGIN_PATH)
            forecast_source_label = "AAPL Bear / Downside Case forecast path (V3.9.8.5 path retained)"
        else:
            wacc = AAPL_BASE_DEFAULT_WACC
            exit_multiple = AAPL_BASE_DEFAULT_EXIT_MULTIPLE
            case_label = "Base Case"
            rationale = AAPL_BASE_FORECAST_RATIONALE
            sel_wacc_t = AAPL_BASE_DEFAULT_WACC_TREATMENT
            sel_term_t = AAPL_BASE_DEFAULT_TERMINAL_TREATMENT
            sel_nd_t = AAPL_BASE_DEFAULT_NET_DEBT_TREATMENT
            term_g = AAPL_BASE_DEFAULT_TERMINAL_G
            blend_g = AAPL_BASE_DEFAULT_BLEND_WEIGHT_GORDON
            blend_e = AAPL_BASE_DEFAULT_BLEND_WEIGHT_EXIT
            scenario_rev_path = list(AAPL_BASE_REVENUE_GROWTH_PATH)
            scenario_ebit_path = list(AAPL_BASE_EBIT_MARGIN_PATH)
            forecast_source_label = "AAPL Base Case forecast path (Services-mix supported)"
        aapl_case_calibration_meta = {
            "applied": True,
            "scenario": scenario_key,
            "case_label": case_label,
            "wacc": wacc,
            "exit_multiple": exit_multiple,
            "terminal_g": term_g,
            "selected_wacc_treatment": sel_wacc_t,
            "selected_terminal_treatment": sel_term_t,
            "selected_net_debt_treatment": sel_nd_t,
            "blend_weight_gordon": blend_g,
            "blend_weight_exit": blend_e,
            "revenue_growth_path": scenario_rev_path,
            "ebit_margin_path": scenario_ebit_path,
            "rationale": rationale,
            "supersedes_exit_multiple_market_default": exit_multiple_meta.get("source"),
        }
    else:
        sel_wacc_t = DEFAULT_WACC_TREATMENT
        sel_term_t = DEFAULT_TERMINAL_TREATMENT
        sel_nd_t = DEFAULT_NET_DEBT_TREATMENT
        term_g = 0.025
        blend_g = 0.5
        blend_e = 0.5
        scenario_rev_path = None
        scenario_ebit_path = None
        forecast_source_label = None

    fcf_growth_default = 0.03
    driver_defaults = derive_driver_defaults({
        "revenue": fin.get("revenue", 0),
        "ebit": fin.get("ebit", 0),
        "da": fin.get("da", 0),
        "capex": fin.get("capex", 0),
        "wc_change": fin.get("wc_change", 0),
        "fcf_growth": fcf_growth_default,
    }, fallback_growth=fcf_growth_default)
    driver_defaults, wacc, default_quality = _apply_default_quality_gates(
        symbol, name, market, fin, driver_defaults, wacc, beta
    )
    if fin.get("_fabricated"):
        default_quality["financials_fabricated"] = True
    selected_default_shares, default_quality = _apply_share_count_quality_gate(symbol, q, fin, default_quality)
    for audit_key in ("capex_sanity", "capex_review", "net_debt_currency_audit"):
        audit = default_quality.get(audit_key) or {}
        if audit.get("status") in {"Review", "High Review"} and audit.get("warning"):
            _append_warning_once(defaults_warnings, audit.get("warning"))
    forecast_paths = _default_forecast_paths(symbol, driver_defaults)
    # V3.9.8.9 scenario override: when AAPL Base or Bear calibration is active,
    # use its scenario-specific forecast path instead of the v3.9.8.6 path.
    if is_aapl and aapl_case_calibration_meta is not None:
        forecast_paths = {
            "revenue_growth_path": scenario_rev_path,
            "ebit_margin_path": scenario_ebit_path,
            "forecast_path_source": forecast_source_label,
            "forecast_path_note": rationale,
        }

    return {
        "symbol"        : symbol,
        "company"       : name,
        "price"         : round(price, 4),
        "currency"      : ccy,
        "reporting_currency": reporting_currency,
        "reporting_currency_source": reporting_currency_source,
        "trading_currency": currency_translation["trading_currency"],
        "trading_currency_source": currency_translation["trading_currency_source"],
        "currency_pair": currency_translation["currency_pair"],
        "fx_rate_reporting_to_trading": currency_translation["fx_rate_reporting_to_trading"],
        "fx_rate_source": currency_translation["fx_rate_source"],
        "currency_translation_status": currency_translation["currency_translation_status"],
        "currency_translation_warning": currency_translation["currency_translation_warning"],
        "net_debt_currency_audit": net_debt_currency_audit,
        "market_comparison_allowed": currency_translation["market_comparison_allowed"],
        "market_comparison_status": default_market_comparison_status,
        "market"        : market,
        "data_source"   : get_data_source(symbol),    # "yfinance" / "AKShare"
        "financials_warning": fin.get("_error"),
        "warnings": defaults_warnings,
        "_schema_drift_detected": fin.get("_schema_drift_detected"),
        "_schema_drift_details": fin.get("_schema_drift_details"),
        "_financials_fabricated": bool(fin.get("_fabricated")),
        "industry_warning": _detect_industry_warning(symbol),  # v3.2.7 金融行业 DCF 不适用警告
        "security_type": security_type["security_type"],
        "security_type_source": security_type["security_type_source"],
        "dcf_suitability": security_type["dcf_suitability"],
        "security_type_reason": security_type["reason"],
        "model_unsuitable": False,
        "model_unsuitable_reason": None,
        "recommended_methods": security_type["recommended_methods"],

        # 金额字段：百万原币种
        "revenue"       : round(fin.get("revenue", 0),   2),
        "ebit"          : round(fin.get("ebit", 0),      2),
        "da"            : round(fin.get("da", 0),        2),
        "capex"         : round(fin.get("capex", 0),     2),
        "wc_change"     : round(fin.get("wc_change", 0), 2),
        "tax_rate"      : round(fin.get("tax_rate", 0.21), 4),
        "net_debt"      : round(fin.get("net_debt", 0),  2),
        "shares"        : round(selected_default_shares or fin.get("shares", 1000), 2),

        # 假设参数
        "revenue_growth": round(driver_defaults["revenue_growth"], 6),
        "ebit_margin"   : round(driver_defaults["ebit_margin"], 6),
        "da_pct_revenue": round(driver_defaults["da_pct_revenue"], 6),
        "capex_pct_revenue": round(driver_defaults["capex_pct_revenue"], 6),
        "wc_change_pct_revenue": round(driver_defaults["wc_change_pct_revenue"], 6),
        "default_quality": default_quality,
        "period_alignment": default_quality.get("period_alignment"),
        "capex_sanity": default_quality.get("capex_sanity"),
        "capex_review": default_quality.get("capex_review"),
        "net_debt_currency_audit": net_debt_currency_audit,
        "normalized_ebit_review": default_quality.get("normalized_ebit_review"),
        # V3.9.8.6: AAPL retains the neutral top-down Base operating path.
        # Other tickers keep the prior flat fallback from single-value drivers.
        "revenue_growth_path": [round(v, 6) for v in forecast_paths["revenue_growth_path"]],
        "ebit_margin_path": [round(v, 6) for v in forecast_paths["ebit_margin_path"]],
        "forecast_path_source": forecast_paths["forecast_path_source"],
        "forecast_path_note": forecast_paths["forecast_path_note"],
        "da_pct_revenue_path": [round(driver_defaults["da_pct_revenue"], 6)] * 5,
        "capex_pct_revenue_path": [round(driver_defaults["capex_pct_revenue"], 6)] * 5,
        "wc_change_pct_revenue_path": [round(driver_defaults["wc_change_pct_revenue"], 6)] * 5,
        "fcf_growth"    : fcf_growth_default,
        "wacc"          : round(wacc, 4),
        "terminal_g"    : term_g,
        "exit_multiple" : round(exit_multiple, 1),
        "exit_multiple_source": exit_multiple_meta["source"],
        "exit_multiple_warning": exit_multiple_meta["warning"],
        "exit_multiple_fetched_at": exit_multiple_meta.get("fetched_at"),
        "exit_multiple_cache_file": exit_multiple_meta.get("cache_file"),
        "exit_multiple_raw": exit_multiple_meta.get("raw_value"),
        "exit_multiple_cache_date": exit_multiple_meta.get("cache_date"),
        "forecast_years": 5,
        "tv_method"     : "average",

        # V3.9.8.9 AAPL Case Separation: treatment fields and blend weights are
        # set from the per-scenario calibration above (Base or Bear). Non-AAPL
        # tickers fall through to global / legacy defaults so prior behavior
        # is preserved exactly.
        "selected_wacc_treatment": sel_wacc_t,
        "selected_terminal_treatment": sel_term_t,
        "selected_net_debt_treatment": sel_nd_t,
        "blend_weight_gordon": blend_g,
        "blend_weight_exit": blend_e,
        "h_model_g_near": (
            scenario_rev_path[-1]
            if is_aapl and scenario_rev_path
            else (forecast_paths.get("revenue_growth_path") or [0.03])[-1]
        ),
        "h_model_g_long": term_g,
        "h_model_half_life": 4.0 if is_aapl and scenario_key == "bear" else DEFAULT_H_MODEL_HALF_LIFE,
        "pre_tax_cost_of_debt": 0.043 if is_aapl else None,
        "buyback_funding_treatment": DEFAULT_BUYBACK_FUNDING_TREATMENT,
        "minimum_cash_floor": DEFAULT_CASH_FLOOR,
        "aapl_case_calibration": aapl_case_calibration_meta,
        # Back-compat alias for callers that read the v3.9.8.8.3 key name.
        "aapl_base_calibration": aapl_case_calibration_meta if (
            aapl_case_calibration_meta and aapl_case_calibration_meta.get("scenario") == "base"
        ) else None,
        "scenario": scenario_key if is_aapl else None,
        "case_label": (aapl_case_calibration_meta or {}).get("case_label") if is_aapl else None,
        "selected_operating_path_source": "Selected Path",
        "available_operating_path_sources": (
            ["Selected Path", "AAPL Operating Thesis Bridge"] if is_aapl else ["Selected Path"]
        ),

        # WACC 组件（透传给前端展示）
        "rf"            : cfg["rf"],
        "erp"           : cfg["erp"],
        "beta"          : round(beta, 2),
    }


def _build_unsuitable_defaults(symbol: str, name: str, market: str, cfg: dict, q: dict, price, ccy: str, security_type: dict, scenario: str = "base") -> dict:
    warnings = [security_type["reason"]]
    return {
        "symbol": symbol,
        "company": name,
        "price": round(float(price or 0), 4),
        "currency": ccy,
        "reporting_currency": ccy,
        "reporting_currency_source": "security_type_gate",
        "trading_currency": ccy,
        "trading_currency_source": "quote_currency" if q.get("currency") else "market_config_default",
        "currency_pair": f"{ccy}/{ccy}" if ccy else None,
        "fx_rate_reporting_to_trading": 1.0 if ccy else None,
        "fx_rate_source": "same_currency" if ccy else "missing_currency",
        "currency_translation_status": "N/A",
        "currency_translation_warning": None,
        "market_comparison_allowed": False,
        "market_comparison_status": "unavailable",
        "valuation_status": "model_unsuitable",
        "market": market,
        "data_source": get_data_source(symbol),
        "financials_warning": "Financial statement defaults are not used because DCF is unsuitable for this security type.",
        "warnings": warnings,
        "_schema_drift_detected": False,
        "_schema_drift_details": None,
        "_financials_fabricated": False,
        "industry_warning": None,
        "security_type": security_type["security_type"],
        "security_type_source": security_type["security_type_source"],
        "dcf_suitability": security_type["dcf_suitability"],
        "security_type_reason": security_type["reason"],
        "model_unsuitable": True,
        "model_unsuitable_reason": security_type["reason"],
        "recommended_methods": security_type["recommended_methods"],
        "revenue": 0.0,
        "ebit": 0.0,
        "da": 0.0,
        "capex": 0.0,
        "wc_change": 0.0,
        "tax_rate": 0.21,
        "net_debt": 0.0,
        "shares": 1.0,
        "revenue_growth": 0.0,
        "ebit_margin": 0.0,
        "da_pct_revenue": 0.0,
        "capex_pct_revenue": 0.0,
        "wc_change_pct_revenue": 0.0,
        "default_quality": {"security_type_gate": security_type},
        "normalized_ebit_review": None,
        "revenue_growth_path": [0.0] * 5,
        "ebit_margin_path": [0.0] * 5,
        "forecast_path_source": "model_unsuitable",
        "forecast_path_note": security_type["reason"],
        "da_pct_revenue_path": [0.0] * 5,
        "capex_pct_revenue_path": [0.0] * 5,
        "wc_change_pct_revenue_path": [0.0] * 5,
        "fcf_growth": 0.0,
        "wacc": round(cfg["rf"] + cfg["erp"], 4),
        "terminal_g": 0.0,
        "exit_multiple": 0.0,
        "exit_multiple_source": "model_unsuitable",
        "exit_multiple_warning": security_type["reason"],
        "exit_multiple_fetched_at": None,
        "exit_multiple_cache_file": None,
        "exit_multiple_raw": None,
        "exit_multiple_cache_date": None,
        "forecast_years": 5,
        "tv_method": "average",
        "selected_wacc_treatment": DEFAULT_WACC_TREATMENT,
        "selected_terminal_treatment": DEFAULT_TERMINAL_TREATMENT,
        "selected_net_debt_treatment": DEFAULT_NET_DEBT_TREATMENT,
        "blend_weight_gordon": 0.5,
        "blend_weight_exit": 0.5,
        "h_model_g_near": 0.0,
        "h_model_g_long": 0.0,
        "h_model_half_life": DEFAULT_H_MODEL_HALF_LIFE,
        "pre_tax_cost_of_debt": None,
        "buyback_funding_treatment": DEFAULT_BUYBACK_FUNDING_TREATMENT,
        "minimum_cash_floor": DEFAULT_CASH_FLOOR,
        "aapl_case_calibration": None,
        "aapl_base_calibration": None,
        "scenario": scenario,
        "case_label": None,
        "selected_operating_path_source": "Selected Path",
        "available_operating_path_sources": ["Selected Path"],
        "rf": cfg["rf"],
        "erp": cfg["erp"],
        "beta": 1.0,
    }


@app.route("/api/modeling/dcf", methods=["GET"])
def api_dcf():
    """GET：拉取默认值并返回，供前端预填表单"""
    symbol = request.args.get("symbol", "AAPL").strip().upper()
    # V3.9.8.9: optional scenario selector ('base' default, 'bear' for AAPL
    # Downside Case). Non-AAPL tickers ignore the parameter — only the AAPL
    # case-calibration helper reads it.
    scenario = (request.args.get("scenario") or "base").strip().lower()
    try:
        defaults = _fetch_dcf_defaults(symbol, scenario=scenario)
        return jsonify(_clean_nan({"defaults": defaults}))
    except Exception:
        app.logger.exception("dcf defaults fetch failed for %s", symbol)
        return jsonify(_clean_nan({"error": "数据拉取失败"})), 500


def _dcf_input_from_payload(d: dict) -> DCFInputs:
    legacy_growth = float(d.get("fcf_growth", d.get("revenue_growth", 0.03)))
    revenue_growth = d.get("revenue_growth", None)
    if revenue_growth is None:
        revenue_growth = legacy_growth
    shares = float(d.get("shares", 1))
    try:
        quality_rec = ((d.get("default_quality") or {}).get("share_count_reconciliation") or {})
        selected_q_shares = _float_or_none(quality_rec.get("selected_default_shares_m"))
        if selected_q_shares and selected_q_shares > 0:
            shares = float(selected_q_shares)
        else:
            q = get_quote_router(d["symbol"])
            implied = (
                (_float_or_none(q.get("market_cap")) or 0.0) /
                (_float_or_none(q.get("current_price")) or _float_or_none(d.get("price")) or 0.0)
            )
            if shares > 0 and implied > 0:
                ratio = max(shares, implied) / max(min(shares, implied), 1e-9)
                if ratio > 1.25:
                    shares = float(implied)
    except Exception:
        pass

    return DCFInputs(
        symbol         = d["symbol"],
        company        = d.get("company", d["symbol"]),
        price          = float(d.get("price", 0)),
        revenue        = float(d.get("revenue", 0)),
        ebit           = float(d.get("ebit", 0)),
        da             = float(d.get("da", 0)),
        capex          = float(d.get("capex", 0)),
        wc_change      = float(d.get("wc_change", 0)),
        tax_rate       = float(d.get("tax_rate", 0.21)),
        net_debt       = float(d.get("net_debt", 0)),
        shares         = shares,
        revenue_growth = float(revenue_growth),
        ebit_margin    = float(d["ebit_margin"]) if d.get("ebit_margin") is not None else None,
        da_pct_revenue = float(d["da_pct_revenue"]) if d.get("da_pct_revenue") is not None else None,
        capex_pct_revenue = float(d["capex_pct_revenue"]) if d.get("capex_pct_revenue") is not None else None,
        wc_change_pct_revenue = (
            float(d["wc_change_pct_revenue"])
            if d.get("wc_change_pct_revenue") is not None
            else None
        ),
        # V3.9.0 Forecast Path Upgrade v1. Optional 5-year paths. If absent or
        # invalid the calculator flat-expands the single value above, preserving
        # the legacy headline IV exactly.
        revenue_growth_path = _coerce_path(d.get("revenue_growth_path")),
        ebit_margin_path = _coerce_path(d.get("ebit_margin_path")),
        da_pct_revenue_path = _coerce_path(d.get("da_pct_revenue_path")),
        capex_pct_revenue_path = _coerce_path(d.get("capex_pct_revenue_path")),
        wc_change_pct_revenue_path = _coerce_path(d.get("wc_change_pct_revenue_path")),
        fcf_growth     = legacy_growth,
        wacc           = float(d.get("wacc", 0.09)),
        beta           = float(d.get("beta", 1.0)),
        terminal_g     = float(d.get("terminal_g", 0.025)),
        exit_multiple  = float(d.get("exit_multiple", 15.0)),
        forecast_years = int(d.get("forecast_years", 5)),
        tv_method      = d.get("tv_method", "average"),
        # V3.7.2 Net Debt Bridge selector; V3.7.3 normalizes via helper so an
        # unknown / legacy key silently falls back to reported_input_net_debt.
        selected_net_debt_treatment = normalize_net_debt_treatment(
            d.get("selected_net_debt_treatment")
        )[0],
        # V3.7.4 Shareholder Returns v1 - all optional; missing fields stay None
        # so the calculator falls back to historical defaults / zero baselines.
        dividend_payout_pct_net_income = _float_or_none(d.get("dividend_payout_pct_net_income")),
        buyback_method = normalize_buyback_method(d.get("buyback_method"))[0],
        buyback_pct_fcf = _float_or_none(d.get("buyback_pct_fcf")),
        flat_buyback_amount = _float_or_none(d.get("flat_buyback_amount")),
        repurchase_price_growth = _float_or_none(d.get("repurchase_price_growth")) or 0.0,
        # V3.9.9.4: None means "use model default" (derived from historical SBC
        # when available, else conservative placeholder). Explicit 0 / non-zero
        # values from the user are passed through verbatim - override safety.
        annual_dilution_pct = _float_or_none(d.get("annual_dilution_pct")),
        selected_share_count_treatment = normalize_share_count_treatment(
            d.get("selected_share_count_treatment")
        )[0],
        # V3.7.5 WACC Decision Layer.
        selected_wacc_treatment = normalize_wacc_treatment(
            d.get("selected_wacc_treatment")
        )[0],
        pre_tax_cost_of_debt = _float_or_none(d.get("pre_tax_cost_of_debt")),
        buyback_funding_treatment = d.get("buyback_funding_treatment", DEFAULT_BUYBACK_FUNDING_TREATMENT),
        minimum_cash_floor = _float_or_none(d.get("minimum_cash_floor")),
        marketable_securities_available_for_returns = _float_or_none(d.get("marketable_securities_available_for_returns")),
        # V3.7.6 Terminal Value Decision Layer.
        selected_terminal_treatment = normalize_terminal_treatment(
            d.get("selected_terminal_treatment")
        )[0],
        fade_years = int(d.get("fade_years") or DEFAULT_FADE_YEARS),
        fade_terminal_growth = _float_or_none(d.get("fade_terminal_growth")),
        blend_weight_gordon = float(d.get("blend_weight_gordon") or 0.5),
        blend_weight_exit = float(d.get("blend_weight_exit") or 0.5),
        h_model_g_near = _float_or_none(d.get("h_model_g_near")),
        h_model_g_long = _float_or_none(d.get("h_model_g_long")),
        h_model_half_life = _float_or_none(d.get("h_model_half_life")),
        selected_operating_path_source = normalize_operating_path_source(
            d.get("selected_operating_path_source"), d.get("symbol")
        )[0],
        operating_override_keys = [
            str(x) for x in (d.get("operating_override_keys") or [])
            if str(x) in {"da_pct_revenue", "capex_pct_revenue", "wc_change_pct_revenue"}
        ],
    )


def _security_type_from_payload(d: dict) -> dict:
    symbol = (d or {}).get("symbol", "")
    if (d or {}).get("dcf_suitability") or (d or {}).get("security_type"):
        security_type = (d or {}).get("security_type") or "unknown"
        suitability = (d or {}).get("dcf_suitability") or ("unsuitable" if (d or {}).get("model_unsuitable") else "suitable")
        return _suitability_payload(
            security_type,
            (d or {}).get("security_type_source") or "payload",
            suitability,
            (d or {}).get("model_unsuitable_reason") or (d or {}).get("security_type_reason"),
        )
    return detect_security_type(symbol, {}, detect_market(symbol) if symbol else None)


def _model_unsuitable_api_response(d: dict, inp: DCFInputs, security_type: dict) -> dict:
    reason = security_type["reason"]
    warnings = list((d or {}).get("warnings") or [])
    _append_warning_once(warnings, reason)
    currency = (d or {}).get("trading_currency") or (d or {}).get("currency") or getattr(inp, "currency", None)
    return {
        "intrinsic_per_share": None,
        "current_price": inp.price,
        "upside_pct": None,
        "ev": None,
        "equity_value": None,
        "intrinsic_value_per_share_reporting_currency": None,
        "intrinsic_value_reporting_currency": None,
        "ev_reporting_currency": None,
        "intrinsic_value_per_share_trading_currency": None,
        "intrinsic_value_trading_currency": None,
        "ev_trading_currency": None,
        "reporting_currency": (d or {}).get("reporting_currency") or currency,
        "reporting_currency_source": (d or {}).get("reporting_currency_source") or "security_type_gate",
        "trading_currency": currency,
        "trading_currency_source": (d or {}).get("trading_currency_source") or "request_or_market_config",
        "currency_pair": f"{currency}/{currency}" if currency else None,
        "fx_rate_reporting_to_trading": 1.0 if currency else None,
        "fx_rate_source": "same_currency" if currency else "missing_currency",
        "currency_translation_status": "N/A",
        "currency_translation_warning": None,
        "market_comparison_allowed": False,
        "market_comparison_status": "unavailable",
        "valuation_status": "model_unsuitable",
        "pv_fcf_sum": None,
        "tv_used": None,
        "tv_gordon": None,
        "tv_exit": None,
        "tv_pct": None,
        "model_status": "unsuitable",
        "model_unsuitable": True,
        "model_unsuitable_reason": reason,
        "security_type": security_type["security_type"],
        "security_type_source": security_type["security_type_source"],
        "dcf_suitability": security_type["dcf_suitability"],
        "recommended_methods": security_type["recommended_methods"],
        "warnings": warnings,
        "normalized_ebit_review": None,
        "assumption_provenance": (d or {}).get("assumption_provenance") or {},
        "revenue_projections": [],
        "revenue_growth_projections": [],
        "ebit_margin_projections": [],
        "ebit_projections": [],
        "tax_projections": [],
        "nopat_projections": [],
        "da_projections": [],
        "capex_projections": [],
        "delta_nwc_projections": [],
        "fcf_projections": [],
        "discount_factors": [],
        "pv_fcfs": [],
        "sensitivity_gordon": [],
        "sensitivity_exit": [],
        "sensitivity_operating": [],
        "terminal_sanity": {},
        "currency": currency,
        "market": detect_market(inp.symbol),
        "wacc_components": {},
        "forecast_years": inp.forecast_years,
        "schedules": {},
        "audit": {"warnings": warnings, "security_type_gate": security_type},
        "active_forecast_sources": {},
        "historical_context": {},
        "net_debt_bridge": {},
        "selected_net_debt_treatment": (d or {}).get("selected_net_debt_treatment"),
        "selected_net_debt_treatment_label": None,
        "available_net_debt_treatments": available_net_debt_treatments(),
        "shareholder_returns": {},
        "selected_share_count_treatment": (d or {}).get("selected_share_count_treatment"),
        "selected_share_count_treatment_label": None,
        "available_share_count_treatments": available_share_count_treatments(),
        "available_buyback_methods": available_buyback_methods(),
        "wacc_decision_bridge": {},
        "selected_wacc_treatment": (d or {}).get("selected_wacc_treatment"),
        "selected_wacc_treatment_label": None,
        "available_wacc_treatments": available_wacc_treatments(),
        "terminal_decision_bridge": {},
        "selected_terminal_treatment": (d or {}).get("selected_terminal_treatment"),
        "selected_terminal_treatment_label": None,
        "available_terminal_treatments": available_terminal_treatments(),
        "operating_forecast_paths": {},
        "forecast_paths_active": False,
        "selected_operating_path_source": (d or {}).get("selected_operating_path_source"),
        "operating_path_bridge": {},
        "trading_comps": None,
    }


def _blocked_input_from_payload(d: dict) -> DCFInputs:
    return DCFInputs(
        symbol=d["symbol"],
        company=d.get("company", d["symbol"]),
        price=float(d.get("price", 0) or 0),
        revenue=float(d.get("revenue", 0) or 0),
        ebit=float(d.get("ebit", 0) or 0),
        da=float(d.get("da", 0) or 0),
        capex=float(d.get("capex", 0) or 0),
        wc_change=float(d.get("wc_change", 0) or 0),
        tax_rate=float(d.get("tax_rate", 0.21) or 0.21),
        net_debt=float(d.get("net_debt", 0) or 0),
        shares=float(d.get("shares", 1) or 1),
        revenue_growth=float(d.get("revenue_growth", 0) or 0),
        ebit_margin=float(d.get("ebit_margin", 0) or 0),
        da_pct_revenue=float(d.get("da_pct_revenue", 0) or 0),
        capex_pct_revenue=float(d.get("capex_pct_revenue", 0) or 0),
        wc_change_pct_revenue=float(d.get("wc_change_pct_revenue", 0) or 0),
        fcf_growth=float(d.get("fcf_growth", d.get("revenue_growth", 0)) or 0),
        wacc=float(d.get("wacc", 0.09) or 0.09),
        beta=float(d.get("beta", 1.0) or 1.0),
        terminal_g=float(d.get("terminal_g", 0) or 0),
        exit_multiple=float(d.get("exit_multiple", 0) or 0),
        forecast_years=int(d.get("forecast_years", 5) or 5),
        tv_method=d.get("tv_method", "average"),
    )


_SUPPORTED_LBO_CURRENCIES = ("USD", "HKD", "CNY")


def _normalize_lbo_currency(value) -> str:
    """Defensive normalization: uppercase, restrict to the V4.7 supported set,
    fallback to USD. Keeps illegal currency (e.g. 'usd', 'USDT', 'rmb') out of
    workbook titles, unit labels and filenames. Does not touch engine math."""
    code = str(value or "").strip().upper()
    return code if code in _SUPPORTED_LBO_CURRENCIES else "USD"


def _normalize_payload_currency(payload: dict) -> dict:
    """Normalize the currency field on an LBO input payload in place."""
    if isinstance(payload, dict):
        payload["currency"] = _normalize_lbo_currency(payload.get("currency"))
    return payload


def _fetch_lbo_defaults(symbol: str) -> dict:
    symbol = (symbol or "SYNTH").upper()
    currency = "USD"
    raw = {"symbol": symbol, "currency": currency}
    try:
        q = get_quote_router(symbol)
        currency = _normalize_lbo_currency(q.get("currency") or currency)
        raw["currency"] = currency
        for src, dst in [
            ("enterprise_value", "enterprise_value"),
            ("enterpriseValue", "enterprise_value"),
            ("ev", "enterprise_value"),
        ]:
            if q.get(src) is not None:
                raw[dst] = q.get(src)
                raw[f"{dst}_unit"] = (
                    q.get(f"{src}_unit") or q.get(f"{src}_units") or
                    ("actual" if (_float_or_none(q.get(src)) or 0.0) >= 1_000_000_000 else "millions")
                )
                break
        for src in ("market_cap", "marketCap"):
            if q.get(src) is not None:
                raw["market_cap"] = q.get(src)
                raw["market_cap_unit"] = (
                    q.get(f"{src}_unit") or q.get(f"{src}_units") or
                    ("actual" if (_float_or_none(q.get(src)) or 0.0) >= 1_000_000_000 else "millions")
                )
                break
        for src in ("net_debt", "netDebt"):
            if q.get(src) is not None:
                raw["net_debt"] = q.get(src)
                break
    except Exception:
        pass

    entry_ebitda = 1000.0
    revenue = 5000.0
    ebitda = 1000.0
    try:
        fin = get_financials_router(symbol)
        if isinstance(fin, dict):
            entry_ebitda = _float_or_none(fin.get("ebitda")) or entry_ebitda
            revenue = _float_or_none(fin.get("revenue")) or revenue
            ebitda = entry_ebitda
            for key in [
                "entry_ebitda", "ebitda", "ebit", "operating_income", "da",
                "d_and_a", "depreciation_amortization", "tax_rate",
            ]:
                if fin.get(key) is not None:
                    raw[key] = fin.get(key)
    except Exception:
        pass

    entry_multiple = 10.0
    years = [1, 2, 3, 4, 5]
    raw.update({
        "entry_ebitda": entry_ebitda,
        "entry_multiple": entry_multiple,
        "operating_forecast": {
            "years": years,
            "revenue": [revenue] * 5,
            "ebitda": [ebitda] * 5,
            "cash_taxes": [ebitda * 0.10] * 5,
            "capex": [ebitda * 0.15] * 5,
            "change_in_nwc": [ebitda * 0.02] * 5,
        },
    })
    built = build_lbo_defaults(symbol, raw)
    payload = built.get("defaults") or {}
    if payload:
        payload["default_builder"] = {
            "status": built.get("status"),
            "assumptions": built.get("assumptions"),
            "provenance": built.get("provenance"),
            "serviceability": built.get("serviceability"),
            "flags": built.get("flags") or [],
        }
    else:
        payload = {
            "symbol": symbol,
            "currency": currency,
            "transaction": {},
            "operating_forecast": {},
            "debt": {},
            "default_builder": built,
        }
    payload["v41_defaults_result"] = {
        "status": built.get("status"),
        "symbol": built.get("symbol"),
        "currency": built.get("currency"),
        "assumptions": built.get("assumptions"),
        "provenance": built.get("provenance"),
        "serviceability": built.get("serviceability"),
        "flags": built.get("flags") or [],
    }
    if symbol == "AAPL":
        aapl_lbo_review_flag = {
            "severity": "warning",
            "code": "EARLY_LBO_SUITABILITY_REVIEW",
            "message": "AAPL is a mega-cap / net-cash issuer; financing feasibility and existing capital structure require review. V4.1 defaults are a modeling starter, not a suitability conclusion.",
        }
        payload.setdefault("early_flags", [])
        payload["early_flags"].append(aapl_lbo_review_flag)
        payload.setdefault("default_builder", {}).setdefault("flags", [])
        payload["default_builder"]["flags"].append(aapl_lbo_review_flag)
        payload.setdefault("v41_defaults_result", {}).setdefault("flags", [])
        payload["v41_defaults_result"]["flags"].append(aapl_lbo_review_flag)
    try:
        suitability = assess_lbo_suitability(symbol, built, raw)
    except Exception as exc:
        suitability = {
            "status": "error",
            "symbol": symbol,
            "suitability": None,
            "veto_triggered": False,
            "flags": [{
                "severity": "warning",
                "code": "LBO_SUITABILITY_GATE_FAILED",
                "message": f"Suitability gate raised an unexpected exception: {exc}",
            }],
        }
    payload["suitability"] = suitability
    return payload


@app.route("/api/modeling/lbo/defaults", methods=["GET"])
def api_lbo_defaults():
    try:
        symbol = request.args.get("symbol", "SYNTH")
        defaults = _fetch_lbo_defaults(symbol)
        built = defaults.get("v41_defaults_result") or defaults.get("default_builder") or {}
        status = built.get("status", "ok")
        return jsonify(_clean_nan({
            "status": status,
            "symbol": defaults.get("symbol", (symbol or "SYNTH").upper()),
            "currency": defaults.get("currency", "USD"),
            "defaults": defaults,
            "provenance": built.get("provenance") or {},
            "serviceability": built.get("serviceability") or {},
            "flags": built.get("flags") or [],
            "suitability": defaults.get("suitability") or {},
        }))
    except Exception as e:
        return jsonify(_clean_nan({
            "status": "error",
            "returns": None,
            "flags": [{"severity": "error", "code": "LBO_DEFAULTS_FAILED", "message": str(e)}],
        })), 500


@app.route("/api/modeling/lbo", methods=["POST"])
def api_lbo_calc():
    try:
        payload = _normalize_payload_currency(request.get_json() or {})
        result = run_lbo(payload)
        try:
            result["attribution"] = build_lbo_attribution(payload, result)
        except Exception as attr_exc:
            result["attribution"] = {
                "status": "unavailable",
                "components": [],
                "flags": [{
                    "severity": "warning",
                    "code": "ATTRIBUTION_BUILD_FAILED",
                    "message": f"Attribution bridge raised an unexpected exception: {attr_exc}",
                }],
            }
        try:
            result["return_context"] = build_return_context(result, result.get("attribution"))
        except Exception:
            result["return_context"] = {"status": "none", "codes": [], "badge_en": "", "badge_cn": ""}
        return jsonify(_clean_nan(result))
    except Exception as e:
        return jsonify(_clean_nan({
            "status": "error",
            "returns": None,
            "flags": [{"severity": "error", "code": "LBO_CALCULATION_FAILED", "message": str(e)}],
        })), 500


@app.route("/api/modeling/lbo/scenarios", methods=["POST"])
def api_lbo_scenarios():
    try:
        payload = request.get_json() or {}
        base_inputs = _normalize_payload_currency(payload.get("inputs") or {})
        scenario_config = payload.get("scenario_config")
        base_suitability = payload.get("base_suitability")
        result = build_lbo_scenarios(base_inputs, scenario_config, base_suitability)
        return jsonify(_clean_nan(result))
    except Exception as e:
        return jsonify(_clean_nan({
            "status": "error",
            "comparison": None,
            "flags": [{"severity": "error", "code": "LBO_SCENARIOS_FAILED", "message": str(e)}],
        })), 500


@app.route("/api/modeling/lbo/sensitivity", methods=["POST"])
def api_lbo_sensitivity():
    try:
        payload = request.get_json() or {}
        base_inputs = _normalize_payload_currency(payload.get("inputs") or {})
        result = build_lbo_sensitivity(base_inputs)
        return jsonify(_clean_nan(result))
    except Exception as e:
        return jsonify(_clean_nan({
            "status": "error",
            "grids": None,
            "flags": [{"severity": "error", "code": "LBO_SENSITIVITY_FAILED", "message": str(e)}],
        })), 500


@app.route("/api/modeling/lbo/excel", methods=["POST"])
def api_lbo_excel():
    d = _normalize_payload_currency(request.get_json() or {})
    try:
        result = run_lbo(d)
        if result.get("status") != "ok":
            return jsonify(_clean_nan(result)), 200
        if not d.get("attribution"):
            try:
                d["attribution"] = build_lbo_attribution(d, result)
            except Exception:
                d["attribution"] = None
        # V4.1.0: the user-facing export is the formula-native workbook. The
        # legacy values-only builder (generate_lbo_excel) is retained as the
        # Python-oracle / gold-master reference path.
        buf = generate_lbo_formula_excel(d, result)
        mode = "multi" if (result.get("capital_structure_summary") or {}).get("mode") == "multi_tranche" else "single"
        sym = (d.get("symbol") or "SYNTH").replace(".", "_")
        fname = f"LBO_{sym}_{mode}_formula_{date.today().isoformat()}.xlsx"
        return send_file(
            buf,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=fname,
        )
    except Exception as e:
        return jsonify(_clean_nan({
            "status": "error",
            "returns": None,
            "flags": [{"severity": "error", "code": "LBO_EXCEL_EXPORT_FAILED", "message": str(e)}],
        })), 500


@app.route("/api/modeling/ma/samples", methods=["GET"])
def api_ma_samples():
    """V5.0 Deal Studio: built-in sample companies (smoke data, not a deck)."""
    try:
        return jsonify(_clean_nan({"status": "ok", "companies": list_sample_companies()}))
    except Exception as e:
        return jsonify(_clean_nan({
            "status": "error",
            "companies": [],
            "flags": [{"severity": "error", "code": "MA_SAMPLES_FAILED", "message": str(e)}],
        })), 500


@app.route("/api/modeling/ma/arena/pairs", methods=["GET"])
def api_ma_arena_pairs():
    """V5.2.2 Arena guardrail: compact precomputed directed pair results.

    Deterministic, read-only lookup over the frozen real seed deck. No per-request
    compute beyond serializing an immutable in-memory cache, no file write, no
    external API, no LLM. Deal Studio still uses /api/modeling/ma/calculate.
    """
    try:
        # V5.11.2: the full pairs+boards body (status/deck_size/pair_count/pairs/
        # boards, V5.5 Settlement Board additive `boards`) is serialized + gzipped
        # ONCE into an immutable module-level cache and served read-only as bytes,
        # so a request never mutates the shared in-memory caches and never
        # re-serializes. A 100-card deck is ~9 MB raw but ~0.31 MB gzipped; every
        # browser sends Accept-Encoding: gzip, so the compressed body (well under
        # the 3 MB guardrail) is what is actually transferred and fetch()
        # decompresses it transparently. Clients that do not negotiate gzip still
        # get the identical uncompressed JSON.
        accept_gzip = "gzip" in (request.headers.get("Accept-Encoding") or "").lower()
        data, is_gzip = get_arena_pairs_response(accept_gzip=accept_gzip)
        resp = app.response_class(data, mimetype="application/json")
        resp.headers["Vary"] = "Accept-Encoding"
        if is_gzip:
            resp.headers["Content-Encoding"] = "gzip"
        return resp
    except Exception:
        # Do not surface the raw exception (paths / stack / internals) to the
        # client. Log server-side only and return a fixed structured error.
        app.logger.exception("api_ma_arena_pairs failed")
        return jsonify(_clean_nan({
            "status": "error",
            "pairs": [],
            "flags": [{
                "severity": "error",
                "code": "ARENA_PAIRS_UNAVAILABLE",
                "message": "Arena pair results are temporarily unavailable.",
            }],
        })), 500


@app.route("/api/modeling/ma/calculate", methods=["POST"])
def api_ma_calculate():
    """V5.0 Deal Studio: deterministic pre-PPA accretion / dilution.

    Pure compute path: no file write, no external API, no LLM, no DCF/LBO call.
    """
    try:
        payload = request.get_json(silent=True) or {}
        # Known validation problems come back as a structured 4xx body from
        # build_ma_response (e.g. FINANCING_COST_REQUIRED, TARGET_SHARES_REQUIRED);
        # those are returned as-is and are NOT turned into 500s.
        body, code = build_ma_response(payload)
        return jsonify(_clean_nan(body)), code
    except Exception:
        # Only truly unexpected errors reach here. Do not surface the raw
        # exception (paths / stack / internals) to the client.
        app.logger.exception("api_ma_calculate failed")
        return jsonify(_clean_nan({
            "status": "error",
            "result": None,
            "flags": [{
                "severity": "error",
                "code": "MA_CALCULATION_UNAVAILABLE",
                "message": "M&A calculation is temporarily unavailable.",
            }],
        })), 500


def _v6_market_values(holdings: list, base_currency: str) -> list:
    """Best-effort market-value enrichment for V6 weighting.

    Reuses the same quote router + FX conversion as the portfolio view to attach
    ``market_value_base`` to each row so V6 can weight by market value. Any
    quote/FX failure is swallowed and the row is left untouched, so the V6
    engine falls back to its deterministic cost-basis weighting
    (cost_price * quantity). Never raises, never touches the on-disk store.
    """
    enriched = []
    for h in holdings:
        row = dict(h)
        symbol = str(h.get("symbol") or h.get("ticker") or "").strip()
        qty = h.get("quantity")
        if symbol and isinstance(qty, (int, float)) and qty > 0:
            try:
                quote = get_quote_router(symbol)
                if isinstance(quote, dict):
                    price = quote.get("current_price")
                    currency = quote.get("currency", "USD")
                    if price is not None:
                        mv_native = float(price) * float(qty)
                        mv_base, _fx = convert_to_base(mv_native, currency, base_currency)
                        if mv_base is not None:
                            row["market_value_base"] = mv_base
            except Exception:
                app.logger.exception("v6 market-value lookup failed for %s", symbol)
        enriched.append(row)
    return enriched


@app.route("/api/modeling/v6/intelligence", methods=["GET"])
def api_modeling_v6_intelligence():
    """V6 Market Intelligence: deterministic event→holdings impact mapping.

    Loads the user's portfolio via the existing loader; when none exists it
    falls back to the engine's bundled synthetic sample (not the on-disk store),
    flagged as demo so the UI labels it. On any unexpected failure it logs the
    details server-side and returns a fixed public message only.
    """
    try:
        base_currency = request.args.get("base", "HKD").upper()
        if base_currency not in VALID_CURRENCIES:
            base_currency = "HKD"
        holdings = load_portfolio()
        portfolio_is_demo = not holdings
        if holdings:
            holdings = _v6_market_values(holdings, base_currency)
        payload = build_intelligence_response(
            holdings=holdings or None,
            portfolio_is_demo=portfolio_is_demo,
        )
        resp = jsonify(_clean_nan(payload))
        # Freshness guard: this feed must never be served from a stale cache, so
        # the UI's "latest" reflects the live response, not a yesterday copy.
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        return resp
    except Exception:
        app.logger.exception("api_modeling_v6_intelligence failed")
        return jsonify({"error": "Unable to build V6 intelligence response."}), 500


@app.route("/api/modeling/dcf", methods=["POST"])
def api_dcf_calc():
    """POST：用用户提交的参数（百万原币种）运行 DCF，返回估值结果"""
    d = request.get_json()
    try:
        security_type = _security_type_from_payload(d)
        if security_type.get("dcf_suitability") == "unsuitable":
            inp = _blocked_input_from_payload(d)
            return jsonify(_clean_nan(_model_unsuitable_api_response(d, inp, security_type)))
        inp = _dcf_input_from_payload(d)
        out = run_dcf(inp)
        currency_translation = _currency_translation_from_payload(d, out)
        currency_outputs = _translate_dcf_currency_outputs(out, currency_translation)
        warnings = list(out.audit.get("warnings", []) or [])
        if currency_translation.get("currency_translation_warning"):
            warnings.append(currency_translation["currency_translation_warning"])
        market_status = _finalize_dcf_market_status(inp.price, currency_translation, currency_outputs, warnings)
        currency_translation = market_status["currency_translation"]
        currency_outputs = market_status["currency_outputs"]
        warnings = market_status["warnings"]
        comparison_iv = market_status["comparison_iv"]

        return jsonify(_clean_nan({
            "intrinsic_per_share": comparison_iv,
            "current_price"      : inp.price,
            "upside_pct"         : market_status["upside_pct"],
            "ev"                 : out.ev,
            "equity_value"       : out.equity_value,
            "intrinsic_value_per_share_reporting_currency": currency_outputs["intrinsic_value_per_share_reporting_currency"],
            "intrinsic_value_reporting_currency": currency_outputs["intrinsic_value_reporting_currency"],
            "ev_reporting_currency": currency_outputs["ev_reporting_currency"],
            "intrinsic_value_per_share_trading_currency": currency_outputs["intrinsic_value_per_share_trading_currency"],
            "intrinsic_value_trading_currency": currency_outputs["intrinsic_value_trading_currency"],
            "ev_trading_currency": currency_outputs["ev_trading_currency"],
            "reporting_currency": currency_translation["reporting_currency"],
            "reporting_currency_source": currency_translation["reporting_currency_source"],
            "trading_currency": currency_translation["trading_currency"],
            "trading_currency_source": currency_translation["trading_currency_source"],
            "currency_pair": currency_translation["currency_pair"],
            "fx_rate_reporting_to_trading": currency_translation["fx_rate_reporting_to_trading"],
            "fx_rate_source": currency_translation["fx_rate_source"],
            "currency_translation_status": currency_translation["currency_translation_status"],
            "currency_translation_warning": currency_translation["currency_translation_warning"],
            "market_comparison_allowed": currency_translation["market_comparison_allowed"],
            "market_comparison_status": market_status["market_comparison_status"],
            "valuation_status": market_status["valuation_status"],
            "pv_fcf_sum"         : out.pv_fcf_sum,
            "tv_used"            : out.tv_used,
            "tv_gordon"          : out.tv_gordon,
            "tv_exit"            : out.tv_exit,
            "tv_pct"             : round(out.tv_pct * 100, 1) if out.tv_pct is not None else None,
            "model_status"       : out.model_status,
            "model_unsuitable"   : out.model_unsuitable,
            "model_unsuitable_reason": out.model_unsuitable_reason,
            "security_type": security_type["security_type"],
            "security_type_source": security_type["security_type_source"],
            "dcf_suitability": security_type["dcf_suitability"],
            "recommended_methods": security_type["recommended_methods"],
            "warnings"           : warnings,
            "normalized_ebit_review": (
                d.get("normalized_ebit_review")
                or ((d.get("default_quality") or {}).get("normalized_ebit_review"))
            ),
            "assumption_provenance": d.get("assumption_provenance") or {},
            "revenue_projections": out.revenue_projections,
            "revenue_growth_projections": out.revenue_growth_projections,
            "ebit_margin_projections": out.ebit_margin_projections,
            "ebit_projections"   : out.ebit_projections,
            "tax_projections"    : out.tax_projections,
            "nopat_projections"  : out.nopat_projections,
            "da_projections"     : out.da_projections,
            "capex_projections"  : out.capex_projections,
            "delta_nwc_projections": out.delta_nwc_projections,
            "fcf_projections"    : out.fcf_projections,
            "discount_factors"   : out.discount_factors,
            "pv_fcfs"            : out.pv_fcfs,
            "sensitivity_gordon" : out.sensitivity_gordon,
            "sensitivity_exit"   : out.sensitivity_exit,
            "sensitivity_operating": out.sensitivity_operating,
            "terminal_sanity"     : out.terminal_sanity,
            "currency"           : currency_translation["trading_currency"] or out.currency,
            "market"             : out.market,
            "wacc_components"    : out.wacc_components,
            "forecast_years"     : inp.forecast_years,
            # V3.7.0 Unified Engine extras (additive; UI may ignore safely).
            "schedules"          : out.schedules,
            "audit"              : out.audit,
            "active_forecast_sources": out.audit.get("active_forecast_sources"),
            "historical_context" : out.historical_context,
            # V3.7.2 Net Debt Bridge (additive).
            "net_debt_bridge"    : out.net_debt_bridge,
            # V3.7.3 top-level treatment fields for convenience.
            "selected_net_debt_treatment": out.net_debt_bridge.get("selected_treatment"),
            "selected_net_debt_treatment_label": out.net_debt_bridge.get("selected_treatment_label"),
            "available_net_debt_treatments": available_net_debt_treatments(),
            # V3.7.4 Shareholder Returns v1 (additive).
            "shareholder_returns": out.shareholder_returns,
            "selected_share_count_treatment": out.shareholder_returns.get("selected_share_count_treatment"),
            "selected_share_count_treatment_label": out.shareholder_returns.get("selected_share_count_treatment_label"),
            "available_share_count_treatments": available_share_count_treatments(),
            "available_buyback_methods": available_buyback_methods(),
            # V3.7.5 WACC Decision Layer (additive).
            "wacc_decision_bridge": out.wacc_decision_bridge,
            "selected_wacc_treatment": out.wacc_decision_bridge.get("selected_wacc_treatment"),
            "selected_wacc_treatment_label": out.wacc_decision_bridge.get("selected_wacc_treatment_label"),
            "available_wacc_treatments": available_wacc_treatments(),
            # V3.7.6 Terminal Value Decision Layer (additive).
            "terminal_decision_bridge": out.terminal_decision_bridge,
            "selected_terminal_treatment": out.terminal_decision_bridge.get("selected_terminal_treatment"),
            "selected_terminal_treatment_label": out.terminal_decision_bridge.get("selected_terminal_treatment_label"),
            "available_terminal_treatments": available_terminal_treatments(),
            # V3.7.7 Trading Comps v1. Opt-in via include_trading_comps=true
            # to keep POST latency low (yfinance peer fetches can take seconds).
            # V3.9.0 Forecast Path Upgrade v1: explicit 5-year operating forecast
            # paths actually used by the engine. UI may surface as advanced inputs.
            "operating_forecast_paths": out.operating_forecast_paths,
            "forecast_paths_active": bool(out.audit.get("forecast_paths_active")),
            "selected_operating_path_source": out.audit.get("selected_operating_path_source"),
            "operating_path_bridge": out.operating_path_bridge,
            "trading_comps": _build_trading_comps_for_request(d, inp, out) if d.get("include_trading_comps") else None,
        }))
    except Exception:
        app.logger.exception("api_dcf calculate failed")
        return jsonify(_clean_nan({"error": "DCF 计算失败"})), 500


def _build_trading_comps_for_request(d: dict, inp, out) -> dict | None:
    """V3.7.7: compute trading comps using the model's selected net debt /
    share count. Translates the DCF's millions-scale inputs into yfinance's
    raw-actuals scale so IV/share comes out in absolute USD.
    """
    try:
        # Pull selected net debt (V3.7.3) and selected share count (V3.7.4).
        nd_used_millions = (out.audit or {}).get("net_debt_used_in_dcf")
        if nd_used_millions is None:
            nd_used_millions = inp.net_debt
        shares_used_millions = (out.audit or {}).get("shares_used_in_dcf")
        if shares_used_millions is None:
            shares_used_millions = inp.shares
        # Workbook unit is millions for US; convert to actual currency for
        # yfinance-scale arithmetic.
        nd_actual = float(nd_used_millions or 0.0) * 1_000_000.0
        shares_actual = float(shares_used_millions or 1.0) * 1_000_000.0
        peer_tickers = d.get("peer_tickers")
        if isinstance(peer_tickers, str):
            peer_tickers = [p.strip() for p in peer_tickers.split(",") if p.strip()]
        # V3.9.3: surface the workbook's model-basis target metrics so the
        # Trading Comps sheet can reconcile yfinance TTM peer-comparable values
        # against the FY annual values driving the DCF headline.
        target_model_basis = {
            "currency": getattr(out, "currency", None),
            "revenue": getattr(inp, "revenue", None),
            "ebit": getattr(inp, "ebit", None),
            "da": getattr(inp, "da", None),
            "shares": getattr(inp, "shares", None),
            "net_debt": nd_used_millions,
            "price": getattr(inp, "price", None),
        }
        return build_trading_comps(
            inp.symbol,
            net_debt_used=nd_actual,
            shares_used=shares_actual,
            peer_tickers=peer_tickers,
            target_model_basis=target_model_basis,
        )
    except Exception as e:
        return {"version": "v393_trading_comps_v2", "status": "error", "error": repr(e), "warnings": [repr(e)]}


@app.route("/api/modeling/dcf/export", methods=["POST"])
def api_dcf_export():
    """生成 Excel 并返回下载流"""
    d = request.get_json()
    try:
        security_type = _security_type_from_payload(d)
        inp = _blocked_input_from_payload(d) if security_type.get("dcf_suitability") == "unsuitable" else _dcf_input_from_payload(d)
        out = run_dcf(inp)
        currency_translation = _currency_translation_from_payload(d, out)
        currency_outputs = _translate_dcf_currency_outputs(out, currency_translation)
        export_warnings = list((d.get("warnings") or [])) + list((out.audit or {}).get("warnings") or [])
        if currency_translation.get("currency_translation_warning"):
            export_warnings.append(currency_translation["currency_translation_warning"])
        market_status = _finalize_dcf_market_status(inp.price, currency_translation, currency_outputs, export_warnings)
        currency_translation = market_status["currency_translation"]
        currency_outputs = market_status["currency_outputs"]
        export_warnings = market_status["warnings"]
        if security_type.get("dcf_suitability") == "unsuitable":
            _append_warning_once(export_warnings, security_type["reason"])
            market_status["valuation_status"] = "model_unsuitable"
            market_status["market_comparison_status"] = "unavailable"
            market_status["upside_pct"] = None
            market_status["comparison_iv"] = None
            currency_translation["market_comparison_allowed"] = False
            for key in [
                "intrinsic_value_per_share_reporting_currency",
                "intrinsic_value_reporting_currency",
                "ev_reporting_currency",
                "intrinsic_value_per_share_trading_currency",
                "intrinsic_value_trading_currency",
                "ev_trading_currency",
                "intrinsic_per_share_for_market_comparison",
            ]:
                currency_outputs[key] = None
        try:
            scenario_doc = _normalize_scenario_doc_for_export(read_scenarios(inp.symbol))
        except Exception:
            scenario_doc = None
        explicit_base_params = _clean_params_for_persist(d.get("base_params")) if isinstance(d.get("base_params"), dict) else None
        current_params = {
            **_clean_params_for_persist(d),
            "currency": currency_translation["trading_currency"] or out.currency,
            "market": out.market,
            "reporting_currency": currency_translation["reporting_currency"],
            "reporting_currency_source": currency_translation["reporting_currency_source"],
            "trading_currency": currency_translation["trading_currency"],
            "trading_currency_source": currency_translation["trading_currency_source"],
            "currency_pair": currency_translation["currency_pair"],
            "fx_rate_reporting_to_trading": currency_translation["fx_rate_reporting_to_trading"],
            "fx_rate_source": currency_translation["fx_rate_source"],
            "currency_translation_status": currency_translation["currency_translation_status"],
            "currency_translation_warning": currency_translation["currency_translation_warning"],
            "market_comparison_allowed": currency_translation["market_comparison_allowed"],
            "market_comparison_status": market_status["market_comparison_status"],
            "valuation_status": market_status["valuation_status"],
            "upside_pct": market_status["upside_pct"],
            "normalized_ebit_review": (
                d.get("normalized_ebit_review")
                or ((d.get("default_quality") or {}).get("normalized_ebit_review"))
            ),
            "assumption_provenance": d.get("assumption_provenance") or {},
            "intrinsic_value_per_share_reporting_currency": currency_outputs["intrinsic_value_per_share_reporting_currency"],
            "intrinsic_value_reporting_currency": currency_outputs["intrinsic_value_reporting_currency"],
            "intrinsic_value_per_share_trading_currency": currency_outputs["intrinsic_value_per_share_trading_currency"],
            "intrinsic_value_trading_currency": currency_outputs["intrinsic_value_trading_currency"],
            "rf": out.wacc_components.get("rf"),
            "erp": out.wacc_components.get("erp"),
            "beta": out.wacc_components.get("beta"),
            "cost_of_equity": out.wacc_components.get("cost_of_equity"),
            "warnings": export_warnings,
            "model_status": "unsuitable" if security_type.get("dcf_suitability") == "unsuitable" else out.model_status,
            "model_unsuitable": security_type.get("dcf_suitability") == "unsuitable",
            "model_unsuitable_reason": security_type["reason"] if security_type.get("dcf_suitability") == "unsuitable" else out.model_unsuitable_reason,
            "security_type": security_type["security_type"],
            "security_type_source": security_type["security_type_source"],
            "dcf_suitability": security_type["dcf_suitability"],
            "recommended_methods": security_type["recommended_methods"],
        }
        # V3.7.7: build trading comps for the workbook. Never let comps failure
        # break export - the Excel builder handles trading_comps=None gracefully.
        trading_comps_payload = (
            {"status": "unavailable", "reason": security_type["reason"], "peer_rows": [], "valuation_ranges": []}
            if security_type.get("dcf_suitability") == "unsuitable"
            else _build_trading_comps_for_request(d, inp, out)
        )
        export_context = {
            "current_params": current_params,
            "base_params": explicit_base_params,
            "current_scenario": d.get("scenario"),
            "scenario_doc": scenario_doc,
            "trading_comps": trading_comps_payload,
        }
        buf = generate_excel(inp, out, export_context=export_context)
        scenario_name = (d.get("scenario") or "base").lower()
        scenario_label = scenario_name.title() if scenario_name in {"base", "bull", "bear"} else "Base"
        # V3.8.3 delivery-lock hygiene: embed the exporter MODEL_VERSION slug
        # (e.g. "v383") in the filename so users can never confuse a stale
        # cached download with a freshly exported one. Slug is parsed from the
        # exporter's MODEL_VERSION string at request time, so a Flask restart
        # that loaded an old exporter would still produce the OLD slug -
        # making version mismatches visible from the filename alone.
        _ver_match = __import__("re").match(r'v(\d+)\.(\d+)\.(\d+)', _EXPORTER_MODEL_VERSION)
        _ver_slug = f"v{_ver_match.group(1)}{_ver_match.group(2)}{_ver_match.group(3)}" if _ver_match else "vunknown"
        fname = f"DCF_{inp.symbol}_{scenario_label}_{_ver_slug}_{date.today()}.xlsx"
        return send_file(
            buf,
            mimetype    = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment = True,
            download_name = fname,
        )
    except Exception:
        app.logger.exception("api_dcf_export failed")
        return jsonify(_clean_nan({"error": "导出失败"})), 500


# ── 启动 ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Local-only by default. Debug (including the Werkzeug interactive debugger,
    # which is a remote-code-execution surface) stays OFF unless explicitly
    # enabled via env, e.g. FLASK_DEBUG=1 / true / yes.
    _debug = os.environ.get("FLASK_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
    _port = int(os.environ.get("PORT", "5000"))
    app.run(debug=_debug, host="127.0.0.1", port=_port)
