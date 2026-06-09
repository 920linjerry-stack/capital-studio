# data_fetcher_akshare.py
# v3.2.2：港股逻辑全重写
#   - PE/PB：AKShare 没有稳定港股估值接口，直接返回 None（UI 显示 "--"）
#   - market_cap：用 stock_hk_security_profile_em 的【发行量(股)】× current_price
#   - 财报：stock_financial_hk_report_em 返回长格式表，需先按 REPORT_DATE
#           取最新报告期，再 pivot 成 {STD_ITEM_NAME: AMOUNT} dict
#   - AMOUNT 单位是 actual（元），归一化时用 "actual"
#
# A 股逻辑保留不动（已实测正确）。
# 保留：_to_ak_symbol、_safe_float、_lazy_ak、_extract_cn_individual_info、
#       get_history_ak、get_financials_ak 的 CN 分支。

import datetime
import logging
import re
import time
from modeling.unit_utils import normalize_to_millions, detect_source_unit

logger = logging.getLogger(__name__)


def _lazy_ak():
    import akshare as ak
    return ak


# ── AKShare spot 整表缓存（v3.2.4 P0）─────────────────────────────────────────
# stock_hk_spot_em 拉港股 4630 行实时行情、stock_zh_a_spot_em 拉 A 股 5800 行，
# cold call 各需 50s / 2min。get_quote_ak 仅为拿"名称"字段就触发，
# portfolio 接口每次刷新都打一遍 → 用户等 3+ 分钟。
# 加 24 小时缓存（股票名称几乎不变），失败时返回旧数据胜过 None。

_HK_SPOT_CACHE = {"data": None, "ts": 0}
_CN_SPOT_CACHE = {"data": None, "ts": 0}
_SPOT_TTL      = 86400   # 24 小时


# ── V3.9.11 Step A: HK CapEx multi-field aggregation ─────────────────────
# Pre-V3.9.11 only summed "购建无形资产及其他资产" (intangibles only),
# which for WuXi Bio (02359.HK) gave CapEx ≈ 0.024% of revenue and pushed
# raw EBIT margin to ~52% (artifact). AKShare standardizes HK CF lines but
# different reports use minor name variants; iterate the alias list and
# accumulate matches. Gross CapEx (no disposal netting) preserves the
# V3.7.0 unified-engine assumption + AAPL anchor.
#
# TODO (V3.10+): Energy upstream HK names (CNOOC 0883.HK, PetroChina) report
# CapEx under non-standard CF categories (e.g. lumped under 投资业务其他项目).
# Currently captured as null → flagged by data_health.capex_suspiciously_low.
# Per-ticker override possible when needed.
HK_CAPEX_FIELDS = [
    "购建固定资产",
    "购建物业、厂房及设备",   # 别名
    "购建物业厂房及设备",     # 无顿号变体
    "购建无形资产及其他资产",
    "购建无形资产",           # 简称
]


# ── V3.9.11 Batch 2B F008: HK Working Capital field map + coverage tracking ─
# Probe across 7 HK sectors (CRO/internet/exchange/energy/pharma/bank/insurance)
# showed the V3.9.11 base 7-field list missed 3 line items real reporters use:
# related-party AR/AP (WuXi, CSPC) and notes receivable (CSPC). Adding them
# bumps full reporters (Tencent stays 100%, CSPC -> 100%) and gives partial
# reporters a measurable coverage gap rather than a silent under-sum.
#
# TODO (V3.10+): Banks/insurers not in TICKER_TO_INDUSTRY whitelist may
# still reach the DCF calc path. If wc_change magnitude > 50% revenue,
# this signals financial-statement WC structure (interbank/insurance
# reserves) being misread as operating WC. Currently caught by
# wc_coverage_low (Review tier), but a dedicated absolute-value sanity
# flag would be more precise.
HK_WC_FIELDS = [
    "存货(增加)减少",
    "应收帐款减少",
    "应付帐款及应计费用增加(减少)",
    "营运资本变动其他项目",
    "预付款项、按金及其他应收款项减少(增加)",
    "预收账款、按金及其他应付款增加(减少)",
    "递延收入(增加)减少",
    # Batch 2B additions (probe evidence: WuXi 2359 + CSPC 1093)
    "应收关联方款项(增加)减少",
    "应付关联方款项增加(减少)",
    "应收票据(增加)减少",
]

HK_WC_COVERAGE_THRESHOLD = 0.60


def _extract_hk_wc_change(cf_items: dict):
    """Aggregate HK working-capital change by scanning HK_WC_FIELDS.

    Returns (total, audit_dict). audit_dict carries matched / missing /
    coverage_ratio + coverage_warning so downstream data_health flags can
    surface partial reporters (HKEX / CNOOC / banks / insurers).
    """
    matched = []
    missing = []
    total = 0.0
    for field in HK_WC_FIELDS:
        if field in cf_items:
            val = _safe_float(cf_items.get(field))
            total += val
            matched.append(field)
        else:
            missing.append(field)
    coverage = len(matched) / len(HK_WC_FIELDS) if HK_WC_FIELDS else 0.0
    return total, {
        "matched_fields": matched,
        "matched_count": len(matched),
        "total_keys": len(HK_WC_FIELDS),
        "missing_fields": missing,
        "coverage_ratio": coverage,
        "coverage_warning": coverage < HK_WC_COVERAGE_THRESHOLD,
    }


def _extract_hk_capex(cf_items: dict):
    """
    Aggregate HK CapEx by scanning HK_CAPEX_FIELDS aliases.

    Returns: (total_capex_raw, matched_fields)
      total_capex_raw is in raw units (元), pre-normalization, gross (abs).
      matched_fields lists the exact STD_ITEM_NAME values that contributed.
    """
    total = 0.0
    matched = []
    for field in HK_CAPEX_FIELDS:
        if field in cf_items:
            val = abs(_safe_float(cf_items.get(field)))
            if val > 0:
                total += val
                matched.append(field)
    # dedup safety (defensive — same dict key won't appear twice but list might)
    matched = list(dict.fromkeys(matched))
    return total, matched


def _get_hk_spot_cached(ak):
    """港股 spot 整表 24 小时缓存。失败时返回旧数据（即使过期），最差 None。"""
    now = time.time()
    if _HK_SPOT_CACHE["data"] is not None and now - _HK_SPOT_CACHE["ts"] < _SPOT_TTL:
        return _HK_SPOT_CACHE["data"]
    try:
        spot = ak.stock_hk_spot_em()
        _HK_SPOT_CACHE["data"] = spot
        _HK_SPOT_CACHE["ts"]   = now
        print(f"[hk_spot cache] 重新拉取整表 {len(spot)} 行")
        return spot
    except Exception as e:
        print(f"[hk_spot cache ERR] {e}")
        return _HK_SPOT_CACHE["data"]   # 即使过期也返回旧数据，胜过 None


def _get_cn_spot_cached(ak):
    """A 股 spot 整表 24 小时缓存，逻辑同港股。"""
    now = time.time()
    if _CN_SPOT_CACHE["data"] is not None and now - _CN_SPOT_CACHE["ts"] < _SPOT_TTL:
        return _CN_SPOT_CACHE["data"]
    try:
        spot = ak.stock_zh_a_spot_em()
        _CN_SPOT_CACHE["data"] = spot
        _CN_SPOT_CACHE["ts"]   = now
        print(f"[cn_spot cache] 重新拉取整表 {len(spot)} 行")
        return spot
    except Exception as e:
        print(f"[cn_spot cache ERR] {e}")
        return _CN_SPOT_CACHE["data"]


# ── 代码格式转换（保留）────────────────────────────────────────────────────────

def _to_ak_symbol(symbol: str) -> tuple[str, str]:
    """
    "0700.HK"   → ("00700", "HK")     港股需要 5 位带前导零
    "00700.HK"  → ("00700", "HK")
    "600519.SS" → ("600519", "CN")    A 股沪市
    "000858.SZ" → ("000858", "CN")    A 股深市
    """
    s = symbol.upper().strip()
    if s.endswith(".HK"):
        code = s.replace(".HK", "").zfill(5)
        return code, "HK"
    if s.endswith(".SS") or s.endswith(".SZ"):
        code = re.sub(r"\.(SS|SZ)$", "", s)
        return code, "CN"
    raise ValueError(f"非港股或 A 股代码：{symbol}")


def _safe_float(v) -> float:
    """安全转 float，处理 None、空字符串、"--"、NaN"""
    if v is None or v == "" or v == "--":
        return 0.0
    try:
        f = float(str(v).replace(",", "").replace("--", "0"))
        if f != f:
            return 0.0
        return f
    except (TypeError, ValueError):
        return 0.0


# ── A 股 sina 三大表"找最新年报"helper（v3.2.5）──────────────────────────────

def _find_latest_annual(df, key_field: str = None):
    """
    在 sina 三大表 DataFrame 里找最近一个完整年报。

    问题背景：
        ak.stock_financial_report_sina 返回的 DataFrame 按时间倒序排，
        iloc[0] 通常是【季报】（如 2026Q1），不是完整年报。
        季报 revenue 只覆盖 3 个月，DCF 算出来差 4 倍；季报 D&A、CapEx 经常 NaN。

    策略：
        - sina 接口"报告日"列格式 YYYYMMDD，年报特征是以 "1231" 结尾
        - 按 DataFrame 顺序遍历（已是时间倒序），返回第一个匹配的年报行
        - 如果指定 key_field，还要求该字段非 NaN（进一步过滤"年报但部分字段缺失"的脏数据）
        - 找不到符合条件的年报 → 返回 None，调用方自己 fallback 到 iloc[0]

    参数:
        df        : ak.stock_financial_report_sina 返回的 DataFrame
        key_field : 可选，关键字段名（如 "营业总收入"），None 表示不校验

    返回:
        pandas.Series（单行）或 None
    """
    if df is None or df.empty:
        return None
    if "报告日" not in df.columns:
        return None

    # v3.2.6：显式按报告日倒序排，不再依赖 AKShare 返回顺序
    # 让"年报顺序保证"成为 helper contract 而非调用方责任
    df = df.sort_values("报告日", ascending=False)

    for _, row in df.iterrows():
        date_str = str(row.get("报告日", "")).strip()
        # 年报判定：8 位 YYYYMMDD 字符串，以 "1231" 结尾
        if not date_str.endswith("1231"):
            continue
        # 关键字段校验（可选）
        if key_field is not None:
            v = row.get(key_field)
            if v is None:
                continue
            if isinstance(v, float) and v != v:  # NaN 检查
                continue
        return row   # 命中

    return None


# ── 港股长格式财报：pivot 到最新一期 ──────────────────────────────────────────

def _filter_hk_future_periods(df, date_col: str, ticker: str = "HK", today: datetime.date | None = None):
    """Drop HK financial rows whose period end is strictly after today."""
    today = today or datetime.date.today()
    df = df.copy()
    df[date_col] = df[date_col].astype("datetime64[ns]")
    latest_available = df[date_col].max()
    before_count = len(df)
    df = df[df[date_col].dt.date <= today]
    filtered_count = before_count - len(df)
    if filtered_count > 0:
        latest_retained = df[date_col].max() if not df.empty else "<none>"
        logger.warning(
            f"[future_period_filter] {ticker}: dropped {filtered_count} rows "
            f"with period_end > {today.isoformat()}. "
            f"Latest retained period: {latest_retained}"
        )
    if df.empty:
        raise ValueError(
            f"[future_period_filter] {ticker}: no HK financial rows remain after "
            f"dropping period_end > {today.isoformat()}"
        )
    df.attrs["hk_period_policy_audit"] = {
        "selected_period_end": df[date_col].max(),
        "dropped_future_period_count": filtered_count,
        "latest_available_period_end_before_filter": latest_available,
        "period_policy": "latest_non_future_period",
        "period_policy_warning": (
            f"dropped {filtered_count} rows with period_end > {today.isoformat()}"
            if filtered_count > 0
            else None
        ),
    }
    return df


def _format_hk_period_end(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _serialize_hk_period_policy_audit(audit: dict | None) -> dict:
    audit = dict(audit or {})
    return {
        "selected_period_end": _format_hk_period_end(audit.get("selected_period_end")),
        "dropped_future_period_count": int(audit.get("dropped_future_period_count") or 0),
        "latest_available_period_end_before_filter": _format_hk_period_end(
            audit.get("latest_available_period_end_before_filter")
        ),
        "period_policy": audit.get("period_policy") or "latest_non_future_period",
        "period_policy_warning": audit.get("period_policy_warning"),
    }


def _hk_pivot_latest(df, value_col: str = "AMOUNT",
                     item_col: str = "STD_ITEM_NAME",
                     date_col: str = "REPORT_DATE",
                     ticker: str = "HK") -> dict:
    """
    把 stock_financial_hk_report_em 的长格式表 pivot 成 {科目名: 金额} dict。
    只取最新报告期。

    AKShare 港股财报实测 schema:
        columns: [SECUCODE, SECURITY_CODE, ..., REPORT_DATE, STD_ITEM_NAME, AMOUNT]
        每行 = 某一报告期某个科目
        REPORT_DATE 形如 "2025-12-31 00:00:00"
        AMOUNT 单位 = actual（元，不是百万也不是亿）
    """
    if df is None or df.empty:
        return {}
    missing_cols = [c for c in (value_col, item_col, date_col) if c not in df.columns]
    if missing_cols:
        return {
            "_error": f"schema_mismatch: missing columns {missing_cols}",
            "_available_columns": list(df.columns),
            "_attempted_columns": [value_col, item_col, date_col],
        }
    try:
        df = _filter_hk_future_periods(df, date_col, ticker=ticker)
        latest_date  = df[date_col].max()
        latest_df    = df[df[date_col] == latest_date]
        items = dict(zip(latest_df[item_col].astype(str), latest_df[value_col]))
        items["_period_policy_audit"] = dict(df.attrs.get("hk_period_policy_audit") or {})
        return items
    except ValueError:
        raise
    except Exception as e:
        print(f"[_hk_pivot_latest] 解析失败: {e}")
        return {}


# ── A 股个股信息（保留 v3.2.1 实现，未改动）──────────────────────────────────

_HK_REPORTING_CURRENCY_KEYS = {
    "货币单位", "貨幣單位", "币种", "幣種", "报表币种", "報表幣種",
    "CURRENCY", "REPORT_CURRENCY", "REPORTING_CURRENCY",
}

_HK_KNOWN_USD_REPORTERS = {
    "0005.HK", "0011.HK", "0388.HK", "1299.HK", "0883.HK", "0939.HK",
    "1398.HK", "3988.HK", "2318.HK", "1288.HK", "3328.HK",
}


def _detect_hk_reporting_currency(symbol: str, financial_items_dict: dict) -> tuple[str, str]:
    """Detect HK issuer reporting currency without changing quote currency."""
    items = financial_items_dict or {}
    for key in _HK_REPORTING_CURRENCY_KEYS:
        raw = items.get(key)
        if raw is None:
            continue
        text = str(raw).strip().upper()
        if "USD" in text or "美元" in text or "美金" in text:
            return "USD", f"financial_field:{key}"
        if "HKD" in text or "港元" in text or "港币" in text or "港幣" in text:
            return "HKD", f"financial_field:{key}"
        if "CNY" in text or "RMB" in text or "人民币" in text or "人民幣" in text:
            return "CNY", f"financial_field:{key}"

    code = str(symbol or "").strip().upper()
    if "." in code:
        base, suffix = code.split(".", 1)
        normalized = f"{base.zfill(4)}.{suffix}"
    else:
        normalized = f"{code.zfill(4)}.HK"
    if normalized in _HK_KNOWN_USD_REPORTERS:
        return "USD", "whitelist_known_usd_hk"
    return "HKD", "default_hkd_unverified"


def _extract_cn_individual_info(ak, code: str) -> dict:
    """A 股从 stock_individual_info_em 提取 PE/PB/市值/股本"""
    out = {"pe_ratio": None, "pb_ratio": None, "market_cap": None, "total_shares": None}
    try:
        info = ak.stock_individual_info_em(symbol=code)
        if info is None or info.empty:
            return out
        info_dict = dict(zip(info["item"].astype(str), info["value"]))

        pe = _safe_float(info_dict.get("市盈率(动)") or info_dict.get("市盈率"))
        pb = _safe_float(info_dict.get("市净率"))
        mc = _safe_float(info_dict.get("总市值"))
        ts = _safe_float(info_dict.get("总股本"))

        if pe > 0:  out["pe_ratio"] = round(pe, 2)
        if pb > 0:  out["pb_ratio"] = round(pb, 2)
        if mc > 0:
            mv, _ = normalize_to_millions(mc, "actual", "CNY")
            out["market_cap"] = mv
        if ts > 0:
            sh, _ = normalize_to_millions(ts, "actual", "CNY")
            out["total_shares"] = sh
    except Exception:
        pass
    return out


# ── 港股个股信息（v3.2.3 简化为 AKShare 兜底）─────────────────────────────────

def _extract_hk_individual_info(ak, code: str) -> dict:
    """
    AKShare 港股证券资料兜底，只在 yfinance 拿不到 sharesOutstanding 时用。
    
    ⚠️ stock_hk_security_profile_em 的"发行量(股)"是【IPO 发行量】（如腾讯 2004
       IPO 的 4.83 亿股），不是当前总股本（腾讯当前 90.37 亿股）。
       明知不准但有总比没有强——yfinance 可用时永远不应该走这里。
    """
    out = {"shares_outstanding": None}
    try:
        prof = ak.stock_hk_security_profile_em(symbol=code)
        if prof is not None and not prof.empty and "发行量(股)" in prof.columns:
            shares_raw = _safe_float(prof["发行量(股)"].iloc[0])
            if shares_raw > 0:
                sh, _ = normalize_to_millions(shares_raw, "actual", "HKD")
                out["shares_outstanding"] = sh
                print(f"[hk_info AKShare兜底] {code} 发行量={shares_raw:,.0f} 股(注意:这是 IPO 发行量,可能不准)")
    except Exception as e:
        print(f"[_extract_hk_individual_info] {code} 失败: {e}")
    return out


# ── 行情快照 ──────────────────────────────────────────────────────────────────

def get_quote_ak(symbol: str) -> dict:
    """港股 / A 股行情，返回与 yfinance 一致的结构。"""
    ak = _lazy_ak()
    code, market = _to_ak_symbol(symbol)
    currency = "HKD" if market == "HK" else "CNY"

    result = {
        "symbol"       : symbol,
        "name"         : symbol,
        "current_price": None,
        "prev_close"   : None,
        "change_pct"   : 0.0,
        "pe_ratio"     : None,
        "pb_ratio"     : None,
        "market_cap"   : None,
        "week52_high"  : None,
        "week52_low"   : None,
        "currency"     : currency,
    }

    try:
        if market == "HK":
            # ── 港股价格（走 AKShare，保留原逻辑）──
            try:
                df = ak.stock_hk_hist(symbol=code, period="daily", adjust="")
                if df is not None and not df.empty:
                    df = df.dropna(subset=["收盘"])
                    last = float(df["收盘"].iloc[-1])
                    prev = float(df["收盘"].iloc[-2]) if len(df) >= 2 else last
                    high = float(df["最高"].tail(252).max())
                    low  = float(df["最低"].tail(252).min())
                    result["current_price"] = round(last, 4)
                    result["prev_close"]    = round(prev, 4)
                    result["change_pct"]    = round((last - prev) / prev * 100, 2) if prev else 0.0
                    result["week52_high"]   = round(high, 4)
                    result["week52_low"]    = round(low, 4)
            except Exception as e:
                print(f"[get_quote_ak HK price] {code} 失败: {e}")

            # ── 港股名称（从 spot 整表取，spot 没有 PE/PB/市值）──
            try:
                spot = _get_hk_spot_cached(ak)
                if spot is not None:
                    row = spot[spot["代码"] == code]
                    if not row.empty and "名称" in row.columns:
                        result["name"] = str(row["名称"].iloc[0])
            except Exception as e:
                print(f"[get_quote_ak HK name] {code} 失败: {e}")

            # ── 估值字段：主走 yfinance，AKShare 兜底 ──
            # import 放函数内，避免与 data_fetcher.py 循环 import
            from data_fetcher import get_yfinance_hk_supplements
            yf_supp = get_yfinance_hk_supplements(symbol)  # symbol 是用户原始格式 "0700.HK"

            result["pe_ratio"]   = yf_supp.get("pe_ratio")
            result["pb_ratio"]   = yf_supp.get("pb_ratio")
            result["market_cap"] = yf_supp.get("market_cap")

            # 如果 yfinance 没拿到 market_cap，用 AKShare 发行量 × 当前价兜底
            if result["market_cap"] is None and result["current_price"]:
                ak_info = _extract_hk_individual_info(ak, code)
                shares_m = ak_info.get("shares_outstanding")
                if shares_m:
                    # shares_m 是百万股，price 是港元/股，乘出来就是百万港元
                    result["market_cap"] = round(shares_m * result["current_price"], 2)
                    print(f"[get_quote_ak HK mcap] {code} AKShare 兜底 = {shares_m:,.2f}M股 × {result['current_price']} = {result['market_cap']:,.2f} 百万 HKD")
            else:
                if result["market_cap"]:
                    print(f"[get_quote_ak HK mcap] {code} 来自 yfinance = {result['market_cap']:,.2f} 百万 HKD")

        else:  # A 股
            # ── A 股价格 ──
            try:
                df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="")
                if df is not None and not df.empty:
                    df = df.dropna(subset=["收盘"])
                    last = float(df["收盘"].iloc[-1])
                    prev = float(df["收盘"].iloc[-2]) if len(df) >= 2 else last
                    high = float(df["最高"].tail(252).max())
                    low  = float(df["最低"].tail(252).min())
                    result["current_price"] = round(last, 4)
                    result["prev_close"]    = round(prev, 4)
                    result["change_pct"]    = round((last - prev) / prev * 100, 2) if prev else 0.0
                    result["week52_high"]   = round(high, 4)
                    result["week52_low"]    = round(low, 4)
            except Exception:
                pass

            try:
                spot = _get_cn_spot_cached(ak)
                if spot is not None:
                    row = spot[spot["代码"] == code]
                    if not row.empty:
                        if "名称" in row.columns:
                            result["name"] = str(row["名称"].iloc[0])
                        if "市盈率-动态" in row.columns:
                            pe = _safe_float(row["市盈率-动态"].iloc[0])
                            if pe > 0: result["pe_ratio"] = round(pe, 2)
                        if "市净率" in row.columns:
                            pb = _safe_float(row["市净率"].iloc[0])
                            if pb > 0: result["pb_ratio"] = round(pb, 2)
                        if "总市值" in row.columns:
                            mc = _safe_float(row["总市值"].iloc[0])
                            if mc > 0:
                                mv, _ = normalize_to_millions(mc, "actual", "CNY")
                                result["market_cap"] = mv
            except Exception:
                pass

            if result["pe_ratio"] is None or result["market_cap"] is None:
                cn_info = _extract_cn_individual_info(ak, code)
                if result["pe_ratio"]   is None: result["pe_ratio"]   = cn_info["pe_ratio"]
                if result["pb_ratio"]   is None: result["pb_ratio"]   = cn_info["pb_ratio"]
                if result["market_cap"] is None: result["market_cap"] = cn_info["market_cap"]

    except Exception as e:
        result["_error"] = f"AKShare 行情失败: {str(e)[:80]}"
        print(f"[get_quote_ak] {symbol} 整体异常: {e}")

    return result


# ── 历史走势（保留 v3.2.1 实现）─────────────────────────────────────────────

def get_history_ak(symbol: str, period: str = "1y") -> list:
    ak = _lazy_ak()
    code, market = _to_ak_symbol(symbol)

    days_map = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 252, "2y": 504,
                "5y": 1260, "ytd": 252, "max": 5000}
    days = days_map.get(period, 252)

    try:
        if market == "HK":
            df = ak.stock_hk_hist(symbol=code, period="daily", adjust="")
        else:
            df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="")

        if df is None or df.empty:
            return []

        df = df.dropna(subset=["收盘"]).tail(days)

        result = []
        for _, row in df.iterrows():
            try:
                date_val = row["日期"]
                date_str = str(date_val)[:10] if date_val is not None else ""
                result.append({
                    "date"  : date_str,
                    "open"  : round(_safe_float(row.get("开盘")), 4),
                    "high"  : round(_safe_float(row.get("最高")), 4),
                    "low"   : round(_safe_float(row.get("最低")), 4),
                    "close" : round(_safe_float(row.get("收盘")), 4),
                    "volume": int(_safe_float(row.get("成交量")) or 0),
                })
            except Exception:
                continue
        return result
    except Exception as e:
        print(f"[get_history_ak] {symbol} 失败: {e}")
        return []


# ── 财务数据 ──────────────────────────────────────────────────────────────────

def get_financials_ak(symbol: str) -> dict:
    """港股 / A 股财务数据。所有金额归一化为"百万原币种"。"""
    ak = _lazy_ak()
    code, market = _to_ak_symbol(symbol)
    currency = "HKD" if market == "HK" else "CNY"
    currency_detection = "cn_default" if market == "CN" else "default_hkd_unverified"
    if market == "HK":
        currency, currency_detection = _detect_hk_reporting_currency(symbol, {})

    result = {
        "revenue"  : 0.0, "ebit": 0.0, "da": 0.0, "capex": 0.0,
        "wc_change": 0.0, "tax_rate": 0.21,
        "net_debt" : 0.0, "shares": 1000.0, "beta": 1.0,
        "currency" : currency,
        "currency_detection": currency_detection,
        "reporting_currency_source": currency_detection,
        "net_debt_currency": currency,
    }

    try:
        if market == "CN":
            # ── A 股利润表（保留 v3.2.1 逻辑）──
            try:
                prefix = "sh" if code.startswith("6") else "sz"
                inc = ak.stock_financial_report_sina(stock=f"{prefix}{code}", symbol="利润表")
                if inc is not None and not inc.empty:
                    # v3.2.5：找最新年报，避免 iloc[0] 取到季报导致 revenue 差 4 倍
                    latest = _find_latest_annual(inc)
                    if latest is None:
                        latest = inc.iloc[0]
                        print(f"[cn_financials IS WARN] {code} 无年报,用最新行 {str(inc.iloc[0].get('报告日',''))}")
                    else:
                        print(f"[cn_financials IS] {code} 用年报 {str(latest.get('报告日',''))}")

                    rev_raw = _safe_float(latest.get("营业总收入") or latest.get("营业收入"))
                    op_raw  = _safe_float(latest.get("营业利润"))
                    tax_raw = _safe_float(latest.get("所得税"))
                    pretax  = _safe_float(latest.get("利润总额"))

                    result["revenue"], _ = normalize_to_millions(rev_raw, "actual", currency)
                    result["ebit"],    _ = normalize_to_millions(op_raw,  "actual", currency)
                    if pretax and tax_raw and pretax > 0:
                        result["tax_rate"] = max(0.0, min(0.5, tax_raw / pretax))
            except Exception:
                pass

            try:
                prefix = "sh" if code.startswith("6") else "sz"
                cf = ak.stock_financial_report_sina(stock=f"{prefix}{code}", symbol="现金流量表")
                if cf is not None and not cf.empty:
                    # v3.2.5：找最新年报
                    latest = _find_latest_annual(cf)
                    if latest is None:
                        latest = cf.iloc[0]
                        print(f"[cn_financials CF WARN] {code} 无年报,用最新行 {str(cf.iloc[0].get('报告日',''))}")
                    else:
                        print(f"[cn_financials CF] {code} 用年报 {str(latest.get('报告日',''))}")

                    # v3.2.7：D&A 由后续 BS 段累计折旧两期差还原（见 BS 段），
                    # CF 段只取 CapEx。sina 直接法现金流量表本来就没有 D&A 绝对值。

                    # v3.2.6：CapEx 字段名修正 — 真名带"所"字
                    capex_raw = _safe_float(latest.get("购建固定资产、无形资产和其他长期资产所支付的现金"))
                    result["capex"], _ = normalize_to_millions(abs(capex_raw), "actual", currency)
                    print(f"[cn_financials CF] {code} capex={result['capex']:,.2f}M")
            except Exception as e:
                print(f"[cn_financials CF ERR] {code} {e}")

            try:
                prefix = "sh" if code.startswith("6") else "sz"
                bs = ak.stock_financial_report_sina(stock=f"{prefix}{code}", symbol="资产负债表")
                if bs is not None and not bs.empty:
                    # v3.2.5：找最新年报（用于 net_debt）
                    latest = _find_latest_annual(bs)
                    if latest is None:
                        latest = bs.iloc[0]
                        print(f"[cn_financials BS WARN] {code} 无年报,用最新行 {str(bs.iloc[0].get('报告日',''))}")
                    else:
                        print(f"[cn_financials BS] {code} 用年报 {str(latest.get('报告日',''))}")

                    debt = (_safe_float(latest.get("短期借款")) +
                            _safe_float(latest.get("长期借款")) +
                            _safe_float(latest.get("应付债券")))
                    cash = _safe_float(latest.get("货币资金"))
                    nd, _ = normalize_to_millions(debt - cash, "actual", currency)
                    result["net_debt"] = nd

                    # ── v3.2.6：WC change 用两期年报差算 ──
                    # sina 现金流量表是直接法，没有间接法的 WC 调整项，所以从资产
                    # 负债表两期差自己算。公式（DCF 标准定义）：
                    #   ΔWC = (本期应收+存货+预付) - (上期应收+存货+预付)
                    #         - [(本期应付+预收) - (上期应付+预收)]
                    # 即 ΔWC = Δ流动资产经营项 - Δ流动负债经营项
                    # 直觉：经营资产增加（应收/存货变多）= 占用现金 = WC change 为正
                    #       经营负债增加（应付/预收变多）= 释放现金 = WC change 为负
                    # DCF 里 FCF = EBIT(1-t) + D&A - CapEx - ΔWC，所以 ΔWC > 0 减 FCF
                    try:
                        # 找前两个年报
                        bs_annual = bs[bs["报告日"].astype(str).str.endswith("1231")].reset_index(drop=True)
                        if len(bs_annual) >= 2:
                            cur  = bs_annual.iloc[0]   # 本期年报
                            prev = bs_annual.iloc[1]   # 上期年报

                            # ── v3.2.7：D&A 用资产负债表"累计折旧"两期年报差还原 ──
                            # sina 直接法现金流量表里没有 D&A，从累计折旧两期差还原本期计提。
                            # 字段名实测 3 种变体："累计折旧" / "减:累计折旧"(半角) / "减：累计折旧"(全角)
                            # 必须用 fuzzy match，不能 exact match。
                            # 探针 probe_cn_da_v2.py 已验证 6 只样本（轻/重/金融）字段稳定、量级合理。
                            # 策略：max(0, 两期差) + 异常 fallback 到 0 + WARN（保守优先）。
                            try:
                                # fuzzy match：列名同时含"折旧"和"累计"，兼容 3 种变体
                                da_cols = [c for c in bs.columns
                                           if "折旧" in str(c) and "累计" in str(c)]
                                if not da_cols:
                                    print(f"[cn_financials DA WARN] {code} 资产负债表无累计折旧列,留 0")
                                else:
                                    # 一般只有 1 个匹配列；>1 时取第一个（目前样本未出现 >1 情形）
                                    da_col = da_cols[0]
                                    cur_acc_dep  = _safe_float(cur.get(da_col))
                                    prev_acc_dep = _safe_float(prev.get(da_col))

                                    if cur_acc_dep <= 0 or prev_acc_dep <= 0:
                                        # NaN 或 0 → fallback
                                        print(f"[cn_financials DA WARN] {code} 累计折旧 NaN/0 "
                                              f"(cur={cur_acc_dep:,.0f} prev={prev_acc_dep:,.0f}),留 0")
                                    else:
                                        da_raw = cur_acc_dep - prev_acc_dep
                                        if da_raw < 0:
                                            # 处置/减值/重分类导致负值 → fallback
                                            print(f"[cn_financials DA WARN] {code} 累计折旧两期差为负 "
                                                  f"({da_raw/1e8:+.2f}亿),可能存在处置/减值,留 0")
                                        else:
                                            result["da"], _ = normalize_to_millions(
                                                da_raw, "actual", currency)
                                            print(f"[cn_financials DA] {code} = {result['da']:,.2f}M "
                                                  f"(列名='{da_col}', "
                                                  f"本期{cur.get('报告日')} - 上期{prev.get('报告日')})")
                            except Exception as e:
                                print(f"[cn_financials DA ERR] {code} {e}")

                            # helper：合并字段优先，分项兜底，全部 NaN-safe
                            def _ar_total(row):
                                """应收 = 应收票据及应收账款 (合并优先) 或 应收票据+应收账款"""
                                merged = _safe_float(row.get("应收票据及应收账款"))
                                if merged > 0:
                                    return merged
                                return _safe_float(row.get("应收票据")) + _safe_float(row.get("应收账款"))

                            def _ap_total(row):
                                """应付 = 应付票据及应付账款 (合并优先) 或 应付票据+应付账款"""
                                merged = _safe_float(row.get("应付票据及应付账款"))
                                if merged > 0:
                                    return merged
                                return _safe_float(row.get("应付票据")) + _safe_float(row.get("应付账款"))

                            def _prepay_total(row):
                                """预收 = 合同负债 (新会计准则) + 预收款项 (老准则)"""
                                return _safe_float(row.get("合同负债")) + _safe_float(row.get("预收款项"))

                            # 本期经营性流动资产 / 流动负债
                            cur_oa  = _ar_total(cur)  + _safe_float(cur.get("存货"))  + _safe_float(cur.get("预付款项"))
                            prev_oa = _ar_total(prev) + _safe_float(prev.get("存货")) + _safe_float(prev.get("预付款项"))
                            cur_ol  = _ap_total(cur)  + _prepay_total(cur)
                            prev_ol = _ap_total(prev) + _prepay_total(prev)

                            delta_oa = cur_oa - prev_oa
                            delta_ol = cur_ol - prev_ol
                            wc_raw   = delta_oa - delta_ol   # 单位：元

                            result["wc_change"], _ = normalize_to_millions(wc_raw, "actual", currency)
                            print(f"[cn_financials WC] {code} ΔOA={delta_oa/1e8:+.2f}亿 "
                                  f"ΔOL={delta_ol/1e8:+.2f}亿 -> ΔWC={result['wc_change']:,.2f}M "
                                  f"(本期{cur.get('报告日')} vs 上期{prev.get('报告日')})")
                        else:
                            print(f"[cn_financials WC WARN] {code} 年报不足 2 期,wc_change 留 0")
                    except Exception as e:
                        print(f"[cn_financials WC ERR] {code} {e}")
            except Exception as e:
                print(f"[cn_financials BS ERR] {code} {e}")

            # v3.2.6：A 股 shares 优先 AKShare，失败/为空则 fallback 到 yfinance
            # AKShare stock_individual_info_em 限流较多，落到默认 1000M 会让
            # 每股估值算错，必须有兜底。yfinance 对 A 股 "600519.SS" 标准格式
            # 直接支持，实测茅台 sharesOutstanding=1.25B 准确。
            shares_source = "default"
            try:
                cn_info = _extract_cn_individual_info(ak, code)
                if cn_info.get("total_shares"):
                    result["shares"] = cn_info["total_shares"]
                    shares_source = "AKShare"
            except Exception as e:
                print(f"[cn_financials shares AK ERR] {code} {e}")

            # AKShare 没拿到 shares → fallback yfinance
            if shares_source == "default":
                try:
                    # import 放函数内，避免循环 import
                    # 注意：虽然函数名带 "hk"，但 v3.2.6 起 A 股 shares fallback
                    # 也复用此函数 — 内部就是 yf.Ticker(symbol).info，A 股代码
                    # "600519.SS" 是 yfinance 标准格式，直接吃。
                    from data_fetcher import get_yfinance_hk_supplements
                    yf_supp   = get_yfinance_hk_supplements(symbol)
                    shares_yf = yf_supp.get("shares_outstanding")
                    if shares_yf:
                        result["shares"] = shares_yf
                        shares_source = "yfinance_fallback"
                except Exception as e:
                    print(f"[cn_financials shares YF ERR] {code} {e}")

            print(f"[cn_financials shares] {code} = {result['shares']:,.2f}M 股 "
                  f"(source={shares_source})")

        else:
            # ──────────────────────────────────────────────────────
            # 港股财报（v3.2.3 重写）
            # 关键修复:
            #   - 资产负债表用 date_col="STD_REPORT_DATE"
            #   - 科目名用实测真名（"贷款"非"借款"，"等价物"非"现金等价物"）
            #   - 加 wc_change 计算（7 个 WC 相关科目累加）
            #   - shares/beta 优先 yfinance，AKShare 兜底
            # AMOUNT 单位是 actual（元），归一化时传 "actual"
            # ──────────────────────────────────────────────────────

            # ── 利润表 ──
            try:
                inc = ak.stock_financial_hk_report_em(stock=code, symbol="利润表", indicator="年度")
                items = _hk_pivot_latest(inc, date_col="REPORT_DATE", ticker=code)
                if isinstance(items, dict) and items.get("_error"):
                    result["_schema_drift_detected"] = True
                    result["_schema_drift_details"] = items["_error"]
                    result.setdefault("warnings", []).append(
                        f"HK financial schema mismatch in income_statement: {items['_error']}"
                    )
                    raise ValueError(items["_error"])
                period_audit = _serialize_hk_period_policy_audit(
                    items.get("_period_policy_audit")
                )
                result["income_statement_period"] = period_audit.get("selected_period_end")
                result.setdefault("latest_available_periods", {})["income_statement"] = period_audit.get("latest_available_period_end_before_filter")
                currency, currency_detection = _detect_hk_reporting_currency(symbol, items)
                result["currency"] = currency
                result["currency_detection"] = currency_detection
                result["reporting_currency_source"] = currency_detection
                result["net_debt_currency"] = currency

                rev_raw  = _safe_float(items.get("营业额") or items.get("营运收入"))
                # V3.9.11 Step A: EBIT prefers 经营溢利 (operating profit, above-the-line)
                # over 除税前溢利 (pretax, includes associates/finance). Probe across 5 HK
                # tickers confirms 经营溢利 is present and clean. Pretax kept as fallback.
                _ebit_op = items.get("经营溢利")
                _ebit_pretax = items.get("除税前溢利")
                if _ebit_op is not None and _safe_float(_ebit_op) != 0:
                    ebit_raw = _safe_float(_ebit_op)
                    result["ebit_source_field"] = "经营溢利"
                    result["ebit_field_fallback_used"] = False
                else:
                    ebit_raw = _safe_float(_ebit_pretax)
                    result["ebit_source_field"] = "除税前溢利"
                    result["ebit_field_fallback_used"] = True
                    result.setdefault("warnings", []).append(
                        "EBIT field fell back to pretax profit; results may "
                        "include below-the-line items."
                    )

                result["revenue"], _ = normalize_to_millions(rev_raw,  "actual", currency)
                result["ebit"],    _ = normalize_to_millions(ebit_raw, "actual", currency)

                # 税率：除税前溢利 > 0 时，用 税项 / 除税前
                pretax = _safe_float(items.get("除税前溢利"))
                tax    = _safe_float(items.get("税项"))
                if pretax > 0 and tax >= 0:
                    result["tax_rate"] = max(0.0, min(0.5, tax / pretax))

                print(f"[hk_financials IS] {code} revenue={result['revenue']:,.2f}M "
                      f"ebit={result['ebit']:,.2f}M tax_rate={result['tax_rate']:.4f}")
            except Exception as e:
                print(f"[hk_financials IS ERR] {code} {e}")

            # ── 现金流量表 ──
            # 注意：科目名里的冒号是英文 ":"，不是中文 "："
            try:
                cf = ak.stock_financial_hk_report_em(stock=code, symbol="现金流量表", indicator="年度")
                items = _hk_pivot_latest(cf, date_col="REPORT_DATE", ticker=code)
                if isinstance(items, dict) and items.get("_error"):
                    result["_schema_drift_detected"] = True
                    result["_schema_drift_details"] = items["_error"]
                    result.setdefault("warnings", []).append(
                        f"HK financial schema mismatch in cash_flow: {items['_error']}"
                    )
                    raise ValueError(items["_error"])

                da_raw    = abs(_safe_float(items.get("加:折旧及摊销")))
                period_audit = _serialize_hk_period_policy_audit(
                    items.get("_period_policy_audit")
                )
                result["cash_flow_period"] = period_audit.get("selected_period_end")
                result.setdefault("latest_available_periods", {})["cash_flow"] = period_audit.get("latest_available_period_end_before_filter")
                result["raw_cash_flow_items"] = {
                    str(k): v for k, v in items.items() if not str(k).startswith("_")
                }
                # V3.9.11 Step A: multi-field CapEx aggregation (was single field)
                capex_raw, capex_matched = _extract_hk_capex(items)
                result["capex_source_fields"] = capex_matched
                result["capex_field_coverage"] = len(capex_matched)
                try:
                    from modeling.data_quality import build_capex_field_review
                    result["capex_review"] = build_capex_field_review(
                        symbol, result["raw_cash_flow_items"], current_capex=None, matched_fields=capex_matched
                    )
                except Exception:
                    pass
                if not capex_matched:
                    result.setdefault("warnings", []).append(
                        "CapEx fields not matched in HK cash flow statement "
                        f"(tried {HK_CAPEX_FIELDS}); CapEx defaulted to 0."
                    )

                # V3.9.11 Batch 2B F008: 10-field WC scan + coverage tracking.
                # Audit surfaces matched/missing fields so data_health can flag
                # partial reporters (HKEX / CNOOC / banks / insurers).
                wc_raw, wc_audit = _extract_hk_wc_change(items)
                result["wc_source_audit"] = wc_audit

                result["da"],        _ = normalize_to_millions(da_raw,    "actual", currency)
                result["capex"],     _ = normalize_to_millions(capex_raw, "actual", currency)
                result["wc_change"], _ = normalize_to_millions(wc_raw,    "actual", currency)
                if result.get("capex_review"):
                    result["capex_review"]["reported_capex"] = result["capex"]

                print(f"[hk_financials CF] {code} da={result['da']:,.2f}M "
                      f"capex={result['capex']:,.2f}M wc_change={result['wc_change']:,.2f}M "
                      f"capex_fields={capex_matched} "
                      f"wc_coverage={wc_audit['matched_count']}/{wc_audit['total_keys']}")
            except Exception as e:
                print(f"[hk_financials CF ERR] {code} {e}")

            # ── 资产负债表（注意 date_col 是 STD_REPORT_DATE）──
            try:
                bs = ak.stock_financial_hk_report_em(stock=code, symbol="资产负债表", indicator="年度")
                items = _hk_pivot_latest(bs, date_col="STD_REPORT_DATE", ticker=code)
                if isinstance(items, dict) and items.get("_error"):
                    result["_schema_drift_detected"] = True
                    result["_schema_drift_details"] = items["_error"]
                    result.setdefault("warnings", []).append(
                        f"HK financial schema mismatch in balance_sheet: {items['_error']}"
                    )
                    raise ValueError(items["_error"])

                # 港股叫"贷款"不叫"借款"；"现金及等价物"不是"现金及现金等价物"
                period_audit = _serialize_hk_period_policy_audit(
                    items.get("_period_policy_audit")
                )
                result["balance_sheet_period"] = period_audit.get("selected_period_end")
                result.setdefault("latest_available_periods", {})["balance_sheet"] = period_audit.get("latest_available_period_end_before_filter")
                st_debt = _safe_float(items.get("短期贷款"))
                lt_debt = _safe_float(items.get("长期贷款"))
                cash    = _safe_float(items.get("现金及等价物"))

                nd_raw = (st_debt + lt_debt) - cash
                nd, _  = normalize_to_millions(nd_raw, "actual", currency)
                result["net_debt"] = nd
                result["net_debt_currency"] = currency
                result["cash_value"] = cash
                result["debt_value"] = st_debt + lt_debt
                result["cash_source"] = "HK balance sheet cash and equivalents"
                result["debt_source"] = "HK balance sheet short-term loans + long-term loans"

                print(f"[hk_financials BS] {code} st_debt={st_debt:,.0f} "
                      f"lt_debt={lt_debt:,.0f} cash={cash:,.0f} -> net_debt={nd:,.2f}M")
            except Exception as e:
                print(f"[hk_financials BS ERR] {code} {e}")

            # ── 股本数 + Beta（优先 yfinance，AKShare 兜底）──
            try:
                # import 放函数内，避免循环 import
                from data_fetcher import get_yfinance_hk_supplements
                yf_supp = get_yfinance_hk_supplements(symbol)

                shares_yf = yf_supp.get("shares_outstanding")
                if shares_yf:
                    result["shares"] = shares_yf
                    print(f"[hk_financials shares] {code} 来自 yfinance = {shares_yf:,.2f}M 股")
                else:
                    ak_info = _extract_hk_individual_info(ak, code)
                    if ak_info.get("shares_outstanding"):
                        result["shares"] = ak_info["shares_outstanding"]
                        print(f"[hk_financials shares] {code} AKShare 兜底 = {result['shares']:,.2f}M 股")

                # Beta 也用 yfinance
                beta_yf = yf_supp.get("beta")
                if beta_yf:
                    result["beta"] = beta_yf
                    print(f"[hk_financials beta] {code} 来自 yfinance = {beta_yf}")
            except Exception as e:
                print(f"[hk_financials shares ERR] {code} {e}")

    except Exception as e:
        result["_error"] = f"AKShare 财报失败: {str(e)[:80]}"
        print(f"[get_financials_ak] {symbol} 整体异常: {e}")

    return result
