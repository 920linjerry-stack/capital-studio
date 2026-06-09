# data_fetcher.py
# v3.2.1：在 router 层包磁盘缓存。
# 内部 fetch 函数（_get_quote_internal 等）保留所有手动调试过的逻辑：
#   - history(period="5d").dropna() 取 current_price/prev_close
#   - get_fx_rate() 用 history 方法 + 5 分钟内存缓存 + fallback 表
# 这些核心逻辑不变，只是在 router 入口加了一层缓存壳。

import time
import yfinance as yf

from modeling.unit_utils import normalize_to_millions
from cache_layer import cached_call

# ── 缓存 TTL 配置 ────────────────────────────────────────────────────────────
# TTL 选择理由：
#   - quote (300s = 5分钟)：股价是高频数据，但用户多次刷新场景需快速响应；
#                            盘中 5 分钟内的价格变化对 DCF 估值影响微乎其微。
#   - history (3600s = 1小时)：历史走势按天采样，1 小时内不会变；
#                              即使盘中也只是末端 1 个点会动，不影响图形。
#   - financials (86400s = 24小时)：财报按季度发布，24 小时缓存绰绰有余；
#                                   AKShare 拉财报最慢（5+ 分钟），最值得缓存。
#   - 汇率：沿用现有 _FX_CACHE 5 分钟内存缓存（不走磁盘，因为汇率字段少+频繁查）
TTL_QUOTE       = 300
TTL_HISTORY     = 3600
TTL_FINANCIALS  = 86400

# ── v3.2.6：Per-table cache schema version ──────────────────────────────────
# 每个数据类型独立版本号，只有 schema 改动时 bump 对应的 version。
# cache key 拼成 f"financials_{symbol}_{FINANCIALS_CACHE_VERSION}"，
# 旧文件自然 miss，触发重新拉取，避免静默读旧 schema。
# cache_layer.py 完全不改，版本生命周期属于业务层（data_fetcher）。
#
# bump 规则:
#   - financials 字段语义/算法变 → bump FINANCIALS
#   - quote/history schema 变 → bump 对应版本
#   - 仅性能优化、bug fix 不影响输出结构 → 不 bump
QUOTE_CACHE_VERSION      = "v320"
HISTORY_CACHE_VERSION    = "v320"
FINANCIALS_CACHE_VERSION = "v3912"
# v3.9.11 Batch 2B F008.5: bump cache version. Step A's HK CapEx multi-field
# aggregation (data_fetcher_akshare HK_CAPEX_FIELDS) + EBIT 经营溢利 switch +
# F008 wc_source_audit fields are NOT present in v327 cache files. Reading
# them masks Step A's real impact on FCF (Tencent 0700.HK IV silently held at
# 455 instead of true 343.85 until cache was busted). v3912 adds the HK
# future/preliminary period filter and forces a fresh fetch. Old cache files
# can be left on disk; the router will simply ignore them.


# ── 汇率缓存（保护清单：完整保留）────────────────────────────────────────────
_FX_CACHE: dict = {}
_FX_CACHE_TTL  = 300

_FX_FALLBACK = {
    ("USD", "HKD"): 7.80,
    ("USD", "CNY"): 7.24,
    ("HKD", "CNY"): 0.93,
    ("CNY", "USD"): 0.138,
    ("CNY", "HKD"): 1.08,
    ("HKD", "USD"): 0.128,
}


def get_fx_rate(from_currency: str, to_currency: str) -> dict:
    """汇率获取：history 方法 + 5 分钟内存缓存 + fallback 表（完整保留）"""
    from_c = from_currency.upper()
    to_c   = to_currency.upper()

    if from_c == to_c:
        return {"rate": 1.0, "from": from_c, "to": to_c, "is_fallback": False}

    cache_key = f"{from_c}{to_c}"
    if cache_key in _FX_CACHE:
        entry = _FX_CACHE[cache_key]
        if time.time() - entry["ts"] < _FX_CACHE_TTL:
            return {"rate": entry["rate"], "from": from_c, "to": to_c,
                    "is_fallback": entry["is_fallback"]}

    ticker_symbol = f"{from_c}{to_c}=X"
    rate          = None
    is_fallback   = False

    try:
        ticker = yf.Ticker(ticker_symbol)
        df     = ticker.history(period="5d").dropna(subset=["Close"])
        if not df.empty:
            rate = float(df["Close"].iloc[-1])
            if rate <= 0:
                rate = None
    except Exception:
        rate = None

    if rate is None or rate <= 0:
        is_fallback = True
        pair        = (from_c, to_c)
        rev_pair    = (to_c, from_c)
        if pair in _FX_FALLBACK:
            rate = _FX_FALLBACK[pair]
        elif rev_pair in _FX_FALLBACK:
            rate = round(1.0 / _FX_FALLBACK[rev_pair], 6)
        else:
            rate = 1.0

    rate = round(float(rate), 6)
    _FX_CACHE[cache_key] = {"rate": rate, "ts": time.time(), "is_fallback": is_fallback}
    return {"rate": rate, "from": from_c, "to": to_c, "is_fallback": is_fallback}


# ── 港股 yfinance 估值字段补充缓存 ────────────────────────────────────────────
# yfinance 港股 .info 调用较慢且重，quote 和 financials 都需要这些字段，
# 用 5 分钟内存缓存避免重复打 yfinance。
# 模式参考 _FX_CACHE。
_YF_HK_SUPP_CACHE: dict = {}
_YF_HK_SUPP_TTL   = 300


def get_yfinance_hk_supplements(symbol: str) -> dict:
    """
    专门为港股提供 yfinance 的估值字段补充。

    v3.2.4 起 PT 路径不再调用此函数（港股已走 _get_quote_internal），
    仅 DCF 财报路径（get_financials_ak）在补 shares/beta 时还会用到。

    AKShare 拿不到稳定的港股 PE/PB/总股本/Beta，所以用 yfinance 兜底主力。

    参数:
        symbol : 港股代码，格式 "0700.HK"（用户输入的原始格式，yfinance 直接吃）

    返回:
        {
            "pe_ratio"          : float | None,   # info["trailingPE"]
            "pb_ratio"          : float | None,   # info["priceToBook"]
            "market_cap"        : float | None,   # 百万 HKD
            "shares_outstanding": float | None,   # 百万股
            "beta"              : float | None,   # info["beta"]
        }

    任何异常都返回全 None 的 dict——上层会 fallback 到 AKShare。
    """
    out = {
        "pe_ratio"          : None,
        "pb_ratio"          : None,
        "market_cap"        : None,
        "shares_outstanding": None,
        "beta"              : None,
    }

    # ── 内存缓存命中检查 ────────────────────────────────────
    cache_key = symbol.upper()
    if cache_key in _YF_HK_SUPP_CACHE:
        entry = _YF_HK_SUPP_CACHE[cache_key]
        if time.time() - entry["ts"] < _YF_HK_SUPP_TTL:
            return entry["data"]

    try:
        info = yf.Ticker(symbol).info or {}
    except Exception as e:
        print(f"[yf_hk_supp] {symbol} yf.Ticker.info 异常: {e}")
        # 即使失败也写缓存，避免短时间内反复打慢接口
        _YF_HK_SUPP_CACHE[cache_key] = {"ts": time.time(), "data": out}
        return out

    def _clean(v):
        """过滤 None / 0 / "<MISSING>" 等无效值"""
        if v is None:
            return None
        if isinstance(v, str) and (v == "" or v == "<MISSING>"):
            return None
        try:
            f = float(v)
            if f != f or f == 0:   # NaN 或 0
                return None
            return f
        except (TypeError, ValueError):
            return None

    pe     = _clean(info.get("trailingPE"))
    pb     = _clean(info.get("priceToBook"))
    raw_mc = _clean(info.get("marketCap"))
    raw_sh = _clean(info.get("sharesOutstanding")) or _clean(info.get("impliedSharesOutstanding"))
    beta   = _clean(info.get("beta"))

    if pe is not None:
        out["pe_ratio"] = round(pe, 4)
    if pb is not None:
        out["pb_ratio"] = round(pb, 4)
    if raw_mc is not None:
        # marketCap 是 actual HKD → 百万 HKD
        mc, _ = normalize_to_millions(raw_mc, "actual", "HKD")
        out["market_cap"] = mc
    if raw_sh is not None:
        # sharesOutstanding 是 actual 股数 → 百万股
        # normalize_to_millions 对 "actual" 输入只是 ÷ 1e6，单位语义虽然是"股"不是货币，
        # 但数学行为一致，结果就是"百万股"
        sh, _ = normalize_to_millions(raw_sh, "actual", "HKD")
        out["shares_outstanding"] = sh
    if beta is not None:
        out["beta"] = round(beta, 4)

    print(f"[yf_hk_supp] {symbol} pe={out['pe_ratio']} pb={out['pb_ratio']} "
          f"mc={out['market_cap']}M shares={out['shares_outstanding']}M beta={out['beta']}")

    # 写缓存
    _YF_HK_SUPP_CACHE[cache_key] = {"ts": time.time(), "data": out}
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 内部 fetch 函数（保护清单：history(5d).dropna() 写法等手动调试逻辑保留）
# ─────────────────────────────────────────────────────────────────────────────

def _get_quote_internal(symbol: str) -> dict:
    """
    yfinance 行情（仅美股）。current_price/prev_close 用 history 方法。
    market_cap 在出口处归一化为"百万原币种"。
    """
    ticker = yf.Ticker(symbol)

    current_price = None
    prev_close    = None
    try:
        hist = ticker.history(period="5d").dropna(subset=["Close"])
        if not hist.empty:
            current_price = float(hist["Close"].iloc[-1])
            prev_close    = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current_price
    except Exception:
        pass

    change_pct = 0.0
    if prev_close and prev_close != 0 and current_price:
        change_pct = round((current_price - prev_close) / prev_close * 100, 2)

    try:
        full_info = ticker.info
    except Exception:
        full_info = {}

    name        = full_info.get("longName") or full_info.get("shortName") or symbol
    quote_type  = full_info.get("quoteType")
    type_disp   = full_info.get("typeDisp")
    pe_ratio    = full_info.get("trailingPE")
    pb_ratio    = full_info.get("priceToBook")
    raw_mkt_cap = full_info.get("marketCap")
    w52_high    = full_info.get("fiftyTwoWeekHigh")
    w52_low     = full_info.get("fiftyTwoWeekLow")
    currency    = full_info.get("currency", "USD")

    market_cap_m = None
    if raw_mkt_cap:
        market_cap_m, _ = normalize_to_millions(raw_mkt_cap, "actual", currency)

    return {
        "symbol"       : symbol,
        "name"         : name,
        "current_price": round(current_price, 4) if current_price else None,
        "prev_close"   : round(prev_close,    4) if prev_close    else None,
        "change_pct"   : change_pct,
        "pe_ratio"     : round(pe_ratio, 2)   if pe_ratio   else None,
        "pb_ratio"     : round(pb_ratio, 2)   if pb_ratio   else None,
        "market_cap"   : market_cap_m,
        "week52_high"  : round(w52_high, 4)   if w52_high   else None,
        "week52_low"   : round(w52_low,  4)   if w52_low    else None,
        "currency"     : currency,
        "quote_type"   : quote_type,
        "type_disp"    : type_disp,
        "sector"       : full_info.get("sector"),
        "industry"     : full_info.get("industry"),
    }


# 保留旧名 get_quote 作为美股直接入口（部分代码可能直接调用）
def get_quote(symbol: str) -> dict:
    """美股 yfinance 行情（不带缓存的直接版本，给老代码兼容用）"""
    return _get_quote_internal(symbol)


def _get_history_internal(symbol: str, period: str) -> list:
    """yfinance 历史价格（不缓存版本）"""
    ticker = yf.Ticker(symbol)
    df     = ticker.history(period=period)
    if df.empty:
        return []
    result = []
    for date, row in df.iterrows():
        result.append({
            "date"  : date.strftime("%Y-%m-%d"),
            "open"  : round(float(row["Open"]),   4),
            "high"  : round(float(row["High"]),   4),
            "low"   : round(float(row["Low"]),    4),
            "close" : round(float(row["Close"]),  4),
            "volume": int(row["Volume"]),
        })
    return result


def _get_financials_internal(symbol: str) -> dict:
    """yfinance 美股财务数据（不缓存版本），所有金额归一化为"百万"""
    t = yf.Ticker(symbol)
    try:
        info = t.info
    except Exception:
        info = {}

    currency = info.get("currency", "USD")

    result = {
        "revenue"  : 0.0, "ebit": 0.0, "da": 0.0, "capex": 0.0,
        "wc_change": 0.0,
        "tax_rate" : float(info.get("effectiveTaxRate") or 0.21),
        "net_debt" : 0.0, "shares": 1000.0, "beta": 1.0,
        "currency" : currency,
    }

    try:
        cf  = t.cashflow
        inc = t.income_stmt
    except Exception:
        cf, inc = None, None

    def _safe_get(df, *keys):
        if df is None or df.empty:
            return 0.0
        for k in keys:
            if k in df.index:
                v = df.loc[k].iloc[0]
                if v is not None and not (isinstance(v, float) and v != v):
                    return float(v)
        return 0.0

    raw_rev   = _safe_get(inc, "Total Revenue", "Revenue")
    raw_ebit  = _safe_get(inc, "EBIT", "Operating Income")
    raw_da    = abs(_safe_get(cf, "Depreciation And Amortization",
                                  "Depreciation Depletion And Amortization"))
    raw_capex = abs(_safe_get(cf, "Capital Expenditure",
                                  "Purchase Of Property Plant And Equipment"))
    raw_wc    = _safe_get(cf, "Change In Working Capital", "Changes In Cash")

    result["revenue"],   _ = normalize_to_millions(raw_rev,   "actual", currency)
    result["ebit"],      _ = normalize_to_millions(raw_ebit,  "actual", currency)
    result["da"],        _ = normalize_to_millions(raw_da,    "actual", currency)
    result["capex"],     _ = normalize_to_millions(raw_capex, "actual", currency)
    result["wc_change"], _ = normalize_to_millions(raw_wc,    "actual", currency)

    raw_debt = float(info.get("totalDebt") or 0)
    raw_cash = float(info.get("totalCash") or 0)
    result["net_debt"], _ = normalize_to_millions(raw_debt - raw_cash, "actual", currency)
    result["net_debt_currency"] = currency
    result["cash_value"] = raw_cash
    result["debt_value"] = raw_debt
    result["cash_source"] = "yfinance.info.totalCash"
    result["debt_source"] = "yfinance.info.totalDebt"

    def _latest_col(df):
        if df is None or df.empty or len(df.columns) == 0:
            return None
        col = df.columns[0]
        if hasattr(col, "strftime"):
            return col.strftime("%Y-%m-%d")
        return str(col)[:10]

    result["income_statement_period"] = _latest_col(inc)
    result["cash_flow_period"] = _latest_col(cf)
    try:
        result["balance_sheet_period"] = _latest_col(t.balance_sheet)
    except Exception:
        result["balance_sheet_period"] = None
    result["latest_available_periods"] = {
        "income_statement": [str(c)[:10] for c in getattr(inc, "columns", [])[:6]],
        "cash_flow": [str(c)[:10] for c in getattr(cf, "columns", [])[:6]],
        "balance_sheet": [],
    }

    raw_shares = float(info.get("sharesOutstanding") or info.get("impliedSharesOutstanding") or 1e9)
    result["shares"], _ = normalize_to_millions(raw_shares, "actual", currency)

    beta = float(info.get("beta") or 1.0)
    result["beta"] = max(0.3, min(3.0, beta))

    return result


_QUORUM_SECONDARY_FIELDS = ("ebit", "capex", "wc_change", "da")


def _compute_meaningful_quorum(fin: dict) -> dict:
    """V3.9.11 Batch 2A: quorum descriptor — used for both the meaningful gate
    and downstream data_health flags (consumers can see which secondary fields
    were missing without re-deriving)."""
    if not isinstance(fin, dict):
        return {"satisfied": False, "revenue_present": False,
                "non_zero_secondary_fields": [],
                "missing_secondary_fields": list(_QUORUM_SECONDARY_FIELDS)}
    revenue_present = float(fin.get("revenue") or 0) > 0
    non_zero = [k for k in _QUORUM_SECONDARY_FIELDS
                if float(fin.get(k) or 0) != 0]
    missing = [k for k in _QUORUM_SECONDARY_FIELDS if k not in non_zero]
    return {
        "satisfied": revenue_present and len(non_zero) >= 2,
        "revenue_present": revenue_present,
        "non_zero_secondary_fields": non_zero,
        "missing_secondary_fields": missing,
    }


def _is_financials_meaningful(fin: dict) -> bool:
    """V3.9.11 Batch 2A: minimum quorum gate.

    Requires revenue > 0 AND at least 2 of (ebit, capex, wc_change, da) non-zero.
    Pre-Batch-2A this was a single-field check; revenue-only data slipped through
    and got cached as if usable. Two non-zero secondary fields is the minimum
    needed for a DCF that touches operating earnings + (investment OR WC) signal.
    """
    if not isinstance(fin, dict):
        return False
    return _compute_meaningful_quorum(fin)["satisfied"]


def _quote_implied_financials_fallback(symbol: str, currency: str = "USD") -> dict:
    """
    Last-resort DCF defaults fallback for markets whose financial statement API is down.
    It is intentionally marked with _error so the API can surface that these are derived,
    not reported financial statement values.
    """
    q = get_quote_router(symbol)
    if not isinstance(q, dict):
        q = {}
    market_cap = float(q.get("market_cap") or 0)  # already in millions
    pe = float(q.get("pe_ratio") or 0)
    price = float(q.get("current_price") or 0)
    if market_cap <= 0 or pe <= 0:
        raise ValueError(f"financial defaults missing and quote fallback unavailable for {symbol}")

    tax_rate = 0.21
    net_income = market_cap / pe
    ebit = net_income / (1 - tax_rate)
    revenue = ebit / 0.30
    capex = revenue * 0.04
    wc_change = revenue * 0.01
    shares = market_cap / price if price > 0 else 1000.0

    print(
        f"[financials fallback] {symbol} using quote-implied defaults "
        f"(market_cap={market_cap:,.2f}M pe={pe:.2f})"
    )
    return {
        "revenue": revenue,
        "ebit": ebit,
        "da": revenue * 0.03,
        "capex": capex,
        "wc_change": wc_change,
        "tax_rate": tax_rate,
        "net_debt": 0.0,
        "shares": shares,
        "beta": 1.0,
        "currency": currency or q.get("currency") or "USD",
        "_error": "financial statement defaults unavailable; using quote-implied fallback",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Router：按市场分发 + 磁盘缓存
# ─────────────────────────────────────────────────────────────────────────────

def _is_yfinance_market(symbol: str) -> bool:
    """美股、欧股 → yfinance；港股、A 股 → AKShare"""
    s = symbol.upper().strip()
    if s.endswith(".HK"):
        return False
    if s.endswith(".SS") or s.endswith(".SZ"):
        return False
    return True


def _route_quote(symbol: str) -> dict:
    """
    v3.2.4：全部市场强制走 yfinance（港股 A 股 yfinance 实测能拿全字段：
    longName/currency/trailingPE/priceToBook/marketCap/sharesOutstanding/
    beta/regularMarketPrice/52周高低）。
    yfinance 失败时返回空 dict 让上层处理（不再 fallback 到 AKShare，
    因为 AKShare spot 整表会被东财服务器限流，反而让用户等更久）。
    """
    return _get_quote_internal(symbol)


def _route_history(symbol: str, period: str) -> list:
    """
    v3.2.4：全部市场走 yfinance。
    yfinance.Ticker(symbol).history() 对 0700.HK / 600519.SS 也能正常返回日 K。
    """
    return _get_history_internal(symbol, period)


def _route_financials(symbol: str) -> dict:
    """财务数据分发。V3.9.11 Batch 2A: stamps _meaningful_quorum on the result so
    downstream data_health flags can surface partial-secondary-fields warnings."""
    if _is_yfinance_market(symbol):
        fin = _get_financials_internal(symbol)
        quorum = _compute_meaningful_quorum(fin)
        if quorum["satisfied"]:
            if isinstance(fin, dict):
                fin["_meaningful_quorum"] = quorum
            return fin
        currency = fin.get("currency", "USD") if isinstance(fin, dict) else "USD"
        fallback = _quote_implied_financials_fallback(symbol, currency)
        fallback["_meaningful_quorum"] = _compute_meaningful_quorum(fallback)
        return fallback
    from data_fetcher_akshare import get_financials_ak
    fin = get_financials_ak(symbol)
    quorum = _compute_meaningful_quorum(fin)
    if quorum["satisfied"]:
        if isinstance(fin, dict):
            fin["_meaningful_quorum"] = quorum
        return fin
    default_currency = "HKD" if symbol.upper().endswith(".HK") else "CNY"
    currency = fin.get("currency", default_currency) if isinstance(fin, dict) else default_currency
    fallback = _quote_implied_financials_fallback(symbol, currency)
    fallback["_meaningful_quorum"] = _compute_meaningful_quorum(fallback)
    return fallback


# ── 对外暴露的统一入口（带缓存）─────────────────────────────────────────────

def get_quote_router(symbol: str) -> dict:
    """
    行情入口（带 5 分钟缓存）。
    第一次调用穿透到数据源，之后 5 分钟内秒返回。
    """
    quote = cached_call(
        f"quote_{symbol}_{QUOTE_CACHE_VERSION}",
        TTL_QUOTE,
        lambda: _route_quote(symbol),
    )
    if isinstance(quote, dict):
        return quote
    return {
        "symbol": symbol,
        "name": symbol,
        "current_price": None,
        "prev_close": None,
        "change_pct": 0.0,
        "pe_ratio": None,
        "pb_ratio": None,
        "market_cap": None,
        "week52_high": None,
        "week52_low": None,
        "currency": "HKD" if symbol.upper().endswith(".HK") else ("CNY" if symbol.upper().endswith((".SS", ".SZ")) else "USD"),
        "_error": "quote source returned no data",
    }


def get_history(symbol: str, period: str = "1y") -> list:
    """
    历史走势入口（带 1 小时缓存）。
    历史数据按天采样，1 小时内变化不影响图形。
    """
    return cached_call(
        f"history_{symbol}_{period}_{HISTORY_CACHE_VERSION}",
        TTL_HISTORY,
        lambda: _route_history(symbol, period),
    )


def get_financials_router(symbol: str) -> dict:
    """
    财务数据入口（带 24 小时缓存）。
    AKShare 拉港股/A 股财报最慢，缓存效果最显著。
    """
    return cached_call(
        f"financials_{symbol}_{FINANCIALS_CACHE_VERSION}",
        TTL_FINANCIALS,
        lambda: _route_financials(symbol),
    )


def get_data_source(symbol: str) -> str:
    """返回数据源名称（用于 UI 提示）"""
    return "yfinance" if _is_yfinance_market(symbol) else "AKShare"
