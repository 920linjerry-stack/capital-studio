# calculator.py
# 职责：所有金融计算逻辑集中在这里，与数据抓取和路由完全分离。
# 本次改造：calc_portfolio_summary() 新增 base_currency 参数，
#           各金额先换算到基准货币再加总，使组合层面数据有经济意义。

from data_fetcher import get_fx_rate


def calc_pnl(cost_price, current_price, quantity):
    """
    计算单只股票的盈亏情况（原币种）。

    参数:
        cost_price   (float): 买入均价
        current_price(float): 当前市价
        quantity     (float): 持仓数量（股）

    返回:
        dict:
            cost_value   : 持仓成本（原币种）
            market_value : 当前市值（原币种）
            pnl_amount   : 盈亏金额（原币种）
            pnl_pct      : 盈亏百分比（如 12.5 表示 +12.5%）
    """
    cost_value   = cost_price * quantity
    market_value = current_price * quantity
    pnl_amount   = market_value - cost_value
    pnl_pct      = (pnl_amount / cost_value * 100) if cost_value != 0 else 0.0

    return {
        "cost_value"  : round(cost_value,   2),
        "market_value": round(market_value, 2),
        "pnl_amount"  : round(pnl_amount,   2),
        "pnl_pct"     : round(pnl_pct,      2),
    }


def calc_daily_pnl(prev_close, current_price, quantity):
    """
    计算单只股票的当日盈亏（原币种）。
    """
    if prev_close is None or prev_close == 0:
        return 0.0
    return round((current_price - prev_close) * quantity, 2)


def calc_change_pct(prev_close, current_price):
    """
    计算涨跌幅（日内百分比变动）。
    """
    if prev_close is None or prev_close == 0:
        return 0.0
    return round((current_price - prev_close) / prev_close * 100, 2)


def convert_to_base(amount, from_currency, base_currency):
    """
    将金额从原币种换算到基准货币。

    参数:
        amount        (float): 原币种金额
        from_currency (str)  : 原币种，如 "USD"
        base_currency (str)  : 目标基准货币，如 "HKD"

    返回:
        tuple: (换算后金额 float, fx_result dict)
    """
    fx = get_fx_rate(from_currency, base_currency)
    return round(amount * fx["rate"], 2), fx


def calc_portfolio_summary(holdings, base_currency="HKD"):
    """
    汇总整个组合的关键指标，所有金额统一换算到 base_currency。

    参数:
        holdings      (list[dict]): 每只股票的持仓数据，每个 dict 需包含：
                                    market_value, cost_value, pnl_amount,
                                    daily_pnl, currency
        base_currency (str)      : 基准货币，默认 "HKD"

    返回:
        dict:
            total_market_value : 总市值（基准货币）
            total_cost         : 总成本（基准货币）
            total_pnl_amount   : 总盈亏金额（基准货币）
            total_pnl_pct      : 总盈亏百分比
            total_daily_pnl    : 当日总盈亏（基准货币）
            base_currency      : 使用的基准货币
            has_fallback_fx    : 是否有任何一笔换算使用了 fallback 汇率
    """
    total_market = 0.0
    total_cost   = 0.0
    total_pnl    = 0.0
    total_daily  = 0.0
    has_fallback = False

    for h in holdings:
        currency = h.get("currency", "USD")

        # 换算市值
        mv_base, fx1 = convert_to_base(h.get("market_value", 0), currency, base_currency)
        cv_base, fx2 = convert_to_base(h.get("cost_value",   0), currency, base_currency)
        pa_base, fx3 = convert_to_base(h.get("pnl_amount",   0), currency, base_currency)
        dp_base, fx4 = convert_to_base(h.get("daily_pnl",    0), currency, base_currency)

        total_market += mv_base
        total_cost   += cv_base
        total_pnl    += pa_base
        total_daily  += dp_base

        # 只要有一笔用了 fallback，就标记
        if any(fx["is_fallback"] for fx in [fx1, fx2, fx3, fx4]):
            has_fallback = True

    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost != 0 else 0.0

    return {
        "total_market_value": round(total_market,  2),
        "total_cost"        : round(total_cost,    2),
        "total_pnl_amount"  : round(total_pnl,     2),
        "total_pnl_pct"     : round(total_pnl_pct, 2),
        "total_daily_pnl"   : round(total_daily,   2),
        "base_currency"     : base_currency,
        "has_fallback_fx"   : has_fallback,
    }