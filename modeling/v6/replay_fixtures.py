"""Curated historical events for the V6 Replay Lab (illustrative, not exhaustive).

These are hand-authored, representative events across diverse categories with
*curated* post-event returns stored inline so the replay runs fully offline and
deterministically. They are illustrative validation samples -- NOT a
comprehensive or unbiased historical dataset (see README limitations). Titles
are phrased so the deterministic classifier recognises the event type from
pre-event text only (no look-ahead).

Returns are decimals (e.g. 0.03 == +3%) over 1/3/5/10 trading-day windows.
"""

from __future__ import annotations

from modeling.v6.replay import HistoricalEvent


def _ret(d1, d3, d5, d10):
    return {"1": d1, "3": d3, "5": d5, "10": d10}


_RAW: list[HistoricalEvent] = [
    HistoricalEvent(
        event_id="cpi-hot", event_time="2024-04-10T12:30:00Z",
        event_title="CPI report: inflation accelerates, hotter than expected",
        source_type="macro", category="宏观利率 / 通胀",
        affected_tickers=["TQQQ"], affected_tags=["inflation", "yields", "rates"],
        benchmark_ticker="QQQ", expected_direction_if_known=-1,
        notes="热通胀推升利率预期，对高久期成长（杠杆纳指）形成压力。",
        fixture_returns=_ret(-0.062, -0.050, -0.041, -0.022),
        fixture_benchmark_returns=_ret(-0.021, -0.017, -0.014, -0.008),
    ),
    HistoricalEvent(
        event_id="cpi-cool", event_time="2023-11-14T12:30:00Z",
        event_title="CPI cooler than expected; disinflation continues",
        source_type="macro", category="宏观利率 / 通胀",
        affected_tickers=["QQQ"], affected_tags=["inflation", "yields", "rates"],
        benchmark_ticker="SPY", expected_direction_if_known=1,
        notes="通胀降温利好风险偏好与成长股估值。",
        fixture_returns=_ret(0.021, 0.030, 0.034, 0.041),
        fixture_benchmark_returns=_ret(0.019, 0.022, 0.020, 0.023),
    ),
    HistoricalEvent(
        event_id="fomc-hawkish", event_time="2022-09-21T18:00:00Z",
        event_title="Fed hikes rates 75bp and signals a hawkish path",
        source_type="macro", category="宏观利率 / 通胀",
        affected_tickers=["QQQ"], affected_tags=["rates", "yields"],
        benchmark_ticker="SPY", expected_direction_if_known=-1,
        notes="鹰派加息抬升贴现率，压制成长股。",
        fixture_returns=_ret(-0.017, -0.039, -0.052, -0.061),
        fixture_benchmark_returns=_ret(-0.017, -0.030, -0.041, -0.048),
    ),
    HistoricalEvent(
        event_id="nvda-beat", event_time="2023-05-24T20:30:00Z",
        event_title="Nvidia beats estimates on surging AI chip demand",
        source_type="company", category="科技与 AI",
        affected_tickers=["NVDA"], affected_tags=["ai_capex", "semiconductors", "earnings"],
        benchmark_ticker="SPY", expected_direction_if_known=1,
        notes="AI 需求驱动业绩超预期，半导体复合体受益。",
        fixture_returns=_ret(0.243, 0.255, 0.262, 0.241),
        fixture_benchmark_returns=_ret(0.009, 0.012, 0.008, 0.015),
    ),
    HistoricalEvent(
        event_id="tsla-guide-cut", event_time="2024-04-23T20:30:00Z",
        event_title="Tesla cuts guidance after weak vehicle deliveries",
        source_type="company", category="公司公告",
        affected_tickers=["TSLA"], affected_tags=["earnings", "guidance", "auto_demand"],
        benchmark_ticker="QQQ", expected_direction_if_known=-1,
        notes="交付疲软 + 指引下调，对成长性定价不利。",
        fixture_returns=_ret(-0.052, -0.071, -0.063, -0.045),
        fixture_benchmark_returns=_ret(0.004, 0.006, 0.003, 0.010),
    ),
    HistoricalEvent(
        event_id="bank-stress", event_time="2023-03-10T14:00:00Z",
        event_title="Banking sector sell-off intensifies on regional lender stress",
        source_type="sentiment", category="情绪与反身性",
        affected_tickers=["BAC"], affected_tags=["risk_sentiment", "credit_cycle"],
        benchmark_ticker="XLF", expected_direction_if_known=-1,
        notes="区域性银行压力引发避险与存款外流担忧，银行股承压。",
        fixture_returns=_ret(-0.061, -0.092, -0.108, -0.084),
        fixture_benchmark_returns=_ret(-0.040, -0.058, -0.066, -0.052),
    ),
    HistoricalEvent(
        event_id="oil-shock", event_time="2023-10-02T13:00:00Z",
        event_title="OPEC supply cut drives crude up; inflation accelerates",
        source_type="macro", category="宏观利率 / 通胀",
        affected_tickers=["XOM"], affected_tags=["inflation", "commodities", "oil"],
        benchmark_ticker="SPY", expected_direction_if_known=1,
        notes="供给冲击推升油价与通胀，能源股相对受益；该样本曾暴露将热通胀的广义利空方向机械施加到能源主题的结构性问题，现保留作回归检查。",
        fixture_returns=_ret(0.018, 0.027, 0.031, 0.024),
        fixture_benchmark_returns=_ret(-0.006, -0.011, -0.009, -0.005),
    ),
    HistoricalEvent(
        event_id="chip-export-control", event_time="2022-10-07T13:00:00Z",
        event_title="US tightens export controls on advanced chips to China",
        source_type="official", category="监管与政策",
        affected_tickers=["NVDA"], affected_tags=["regulatory", "semiconductors"],
        benchmark_ticker="SPY", expected_direction_if_known=-1,
        notes="出口管制限制销售市场，半导体承压。",
        fixture_returns=_ret(-0.039, -0.061, -0.058, -0.047),
        fixture_benchmark_returns=_ret(-0.028, -0.039, -0.034, -0.030),
    ),
    HistoricalEvent(
        event_id="aapl-upgrade", event_time="2023-06-05T11:00:00Z",
        event_title="Analyst upgrades Apple to overweight on services strength",
        source_type="institutional", category="机构观点",
        affected_tickers=["AAPL"], affected_tags=["analyst_action"],
        benchmark_ticker="SPY", expected_direction_if_known=1,
        notes="卖方上调评级，短线情绪偏正。",
        fixture_returns=_ret(0.015, 0.012, 0.018, 0.022),
        fixture_benchmark_returns=_ret(0.003, 0.005, 0.006, 0.009),
    ),
    HistoricalEvent(
        event_id="aapl-sell-the-news", event_time="2023-09-12T17:00:00Z",
        event_title="Apple raises guidance at launch event; analysts lift targets",
        source_type="company", category="公司公告",
        affected_tickers=["AAPL"], affected_tags=["earnings", "guidance"],
        benchmark_ticker="SPY", expected_direction_if_known=-1,
        notes="发布会利好已被充分定价，兑现后出现「利好出尽」回落（V6 方向读数与实际相反，属典型 miss 样本）。",
        fixture_returns=_ret(-0.018, -0.022, -0.017, -0.009),
        fixture_benchmark_returns=_ret(0.004, 0.006, 0.005, 0.008),
    ),
]


def load_historical_events() -> list[HistoricalEvent]:
    """Return fresh copies of the curated historical events."""
    return [HistoricalEvent(**e.to_dict()) for e in _RAW]
