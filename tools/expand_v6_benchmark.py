"""Expand the V6 replay benchmark with curated REAL historical events.

Why: the benchmark drives the bp calibration (pillar 2) and the contagion matrix
(pillar 3). With only ~50 events the holdout hit-rate had a ~+/-22pp confidence
interval -- too thin to trust. This script appends a larger set of real, dated,
sourced events so the learned coefficients become statistically meaningful.

Integrity rules (do not break):
* Every event is a REAL event on a REAL date. The realized returns are fetched
  from yfinance by replay_benchmark_prices.py -- we never invent returns.
* Headlines are TRUTHFUL about direction (beat/miss, hot/cool, hike/cut) so the
  classifier's read is fairly scored against what actually happened.
* known_at == event_time (no look-ahead). Tickers all have V6 exposure profiles.
* Deliberate hard cases (a beat that still sold off -- the "AVGO effect") are
  kept and labelled with lower confidence; they are signal, not noise.

Run:  python -m tools.expand_v6_benchmark           # append rows (idempotent)
then: python -m modeling.v6.replay_benchmark_prices # fetch real yfinance returns
then: refit calibration + contagion (see __main__ of this file for the one-liner)
"""

from __future__ import annotations

import csv
from pathlib import Path

from modeling.v6.replay_benchmark import EVENTS_CSV

# Column order must match replay_benchmark_events.csv exactly.
_COLUMNS = [
    "event_id", "event_time", "known_at", "event_title", "event_type",
    "source_type", "source_name", "source_url", "source_note",
    "affected_tickers", "affected_tags", "benchmark_ticker",
    "expected_direction_if_known", "confidence_of_event_label", "category",
    "subcategory", "notes", "no_lookahead_flag", "split", "return_status",
    "asset_class", "sector", "price_anchor", "timestamp_precision",
]

# Representative UTC release time + default precision per price anchor.
_ANCHOR_TIME = {
    "pre_market": ("12:30:00Z", "timestamp"),
    "post_market": ("20:05:00Z", "timestamp"),
    "intraday": ("18:00:00Z", "timestamp"),
    "date": ("20:00:00Z", "date"),
}

_SRC = {
    "macro_fed": ("Federal Reserve", "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"),
    "macro_bls_cpi": ("Bureau of Labor Statistics", "https://www.bls.gov/cpi/"),
    "macro_bls_jobs": ("Bureau of Labor Statistics", "https://www.bls.gov/ces/"),
    "company": ("Issuer investor relations", ""),
    "official_fda": ("U.S. Food and Drug Administration", "https://www.fda.gov/news-events"),
    "official_bis": ("U.S. Department of Commerce (BIS)", "https://www.bis.gov/"),
    "opec": ("OPEC", "https://www.opec.org/"),
    "sentiment": ("Public market data (Cboe / index)", "https://www.cboe.com/tradable_products/vix/"),
}

# Category by source/event family (matches existing canonical categories).
_CATEGORY = {
    "macro": "macro_rates_inflation",
    "company": "company_earnings_guidance",
    "institutional": "institutional_analyst",
    "official": "official_filing",
    "sentiment": "sentiment_reflexivity",
}


def _split_for(event_id: str) -> str:
    """Deterministic ~1/3 holdout split, spread across types by id hash."""
    return "holdout" if (sum(ord(c) for c in event_id) % 3 == 0) else "dev"


def E(eid, date, anchor, title, etype, stype, tickers, tags, bench, edir, conf,
      src_key, sub="", note="", category=None, asset="equity", sector="",
      precision=None):
    t, default_precision = _ANCHOR_TIME[anchor]
    ts = f"{date}T{t}"
    name, url = _SRC[src_key]
    return {
        "event_id": eid,
        "event_time": ts,
        "known_at": ts,
        "event_title": title,
        "event_type": etype,
        "source_type": stype,
        "source_name": name,
        "source_url": url,
        "source_note": note or "Curated real event; returns fetched from public yfinance feed.",
        "affected_tickers": "|".join(tickers),
        "affected_tags": "|".join(tags),
        "benchmark_ticker": bench,
        "expected_direction_if_known": edir,
        "confidence_of_event_label": conf,
        "category": category or _CATEGORY.get(stype, "breaking_news_shock"),
        "subcategory": sub or etype,
        "notes": note or "",
        "no_lookahead_flag": "true",
        "split": _split_for(eid),
        "return_status": "missing",
        "asset_class": asset,
        "sector": sector or "mixed",
        "price_anchor": anchor,
        "timestamp_precision": precision or default_precision,
    }


def build_events() -> list[dict]:
    ev: list[dict] = []
    # ===================== MACRO: FOMC decisions ==========================
    # 2022 hiking cycle (headline reads as a hike => classifier bearish for
    # growth; realized reaction is genuinely mixed -- that is the point).
    fomc_hike = [
        ("2022-03-16", "Fed raises rates 25 basis points to start its hiking cycle"),
        ("2022-05-04", "Fed raises rates 50 basis points"),
        ("2022-06-15", "Fed raises rates 75 basis points"),
        ("2022-07-27", "Fed raises rates 75 basis points"),
        ("2022-09-21", "Fed raises rates 75 basis points and signals higher for longer"),
        ("2022-11-02", "Fed raises rates 75 basis points"),
        ("2022-12-14", "Fed raises rates 50 basis points"),
        ("2023-02-01", "Fed raises rates 25 basis points"),
        ("2023-03-22", "Fed raises rates 25 basis points amid banking stress"),
        ("2023-05-03", "Fed raises rates 25 basis points"),
        ("2023-07-26", "Fed raises rates 25 basis points"),
    ]
    for d, title in fomc_hike:
        ev.append(E(f"fomc-hike-{d}", d, "intraday", title, "rate_hike", "macro",
                    ["QQQ", "TQQQ"], ["rates", "yields"], "SPY", -1, 0.9, "macro_fed",
                    sub="fomc_rate_hike", category="macro_rates_inflation",
                    asset="etf", sector="rates"))
    fomc_dovish = [
        ("2023-09-20", "Fed holds rates but signals higher for longer", "rate_hike", -1),
        ("2024-11-07", "Fed cuts rates 25 basis points", "rate_cut", 1),
        ("2024-12-18", "Fed cuts rates but signals fewer rate cuts ahead", "rate_cut", 1),
    ]
    for d, title, et, edir in fomc_dovish:
        ev.append(E(f"fomc-{et}-{d}", d, "intraday", title, et, "macro",
                    ["QQQ", "SPY"], ["rates", "yields"], "SPY", edir, 0.85, "macro_fed",
                    sub="fomc", category="macro_rates_inflation", asset="etf", sector="rates"))

    # ===================== MACRO: CPI prints ==============================
    cpi = [
        ("2022-02-10", "hot", -1), ("2022-03-10", "hot", -1), ("2022-04-12", "hot", -1),
        ("2022-05-11", "hot", -1), ("2022-07-13", "hot", -1), ("2022-09-13", "hot", -1),
        ("2022-11-10", "cool", 1), ("2022-12-13", "cool", 1),
        ("2023-01-12", "cool", 1), ("2023-05-10", "cool", 1), ("2023-06-13", "cool", 1),
        ("2023-07-12", "cool", 1), ("2023-11-14", "cool", 1),
        ("2024-02-13", "hot", -1), ("2024-04-10", "hot", -1), ("2024-05-15", "cool", 1),
        ("2024-07-11", "cool", 1),
    ]
    for d, hc, edir in cpi:
        if hc == "hot":
            title = "CPI hotter than expected as inflation accelerates"
            et, tags = "macro_inflation_hot", ["inflation", "yields", "inflation_fear"]
        else:
            title = "CPI cooler than expected as inflation eases"
            et, tags = "macro_inflation_cool", ["inflation", "yields"]
        ev.append(E(f"cpi-{hc}-{d}", d, "pre_market", title, et, "macro",
                    ["TQQQ", "GLD"], tags, "SPY", edir, 0.9, "macro_bls_cpi",
                    sub=f"cpi_{hc}", category="macro_rates_inflation", asset="etf", sector="mixed_macro"))

    # ===================== MACRO: jobs reports ============================
    jobs = [
        ("2023-10-06", "strong", "Payrolls surge in a hot jobs report", -1, 0.75),
        ("2024-09-06", "weak", "Payroll growth slows sharply and unemployment rises", 1, 0.7),
        ("2024-10-04", "strong", "Payrolls jump in a much stronger jobs report", -1, 0.7),
        ("2025-01-10", "strong", "Payrolls surge in a hot jobs report", -1, 0.7),
    ]
    for d, hw, title, edir, conf in jobs:
        et = "jobs_hot" if hw == "strong" else "jobs_weak"
        tags = ["rates", "cyclical_strength"] if hw == "strong" else ["rates", "risk_sentiment", "recession_risk"]
        ev.append(E(f"jobs-{hw}-{d}", d, "pre_market", title, "jobs_report", "macro",
                    ["IWM", "SPY"], tags, "SPY", edir, conf, "macro_bls_jobs",
                    sub=f"jobs_{hw}", category="macro_rates_inflation", asset="etf", sector="broad_market"))

    # ===================== COMPANY: iconic single-name earnings ===========
    # (ticker, date, anchor, title, event_type, expected_dir, confidence, bench, tags, sector, [extra_ticker])
    earn = [
        # META
        ("META", "2022-02-02", "post_market", "Meta misses estimates and warns on advertising headwinds", "earnings_miss", -1, 0.9, "XLK", ["earnings", "advertising"], "communication_services"),
        ("META", "2022-10-26", "post_market", "Meta misses estimates as costs surge and ad revenue falls", "earnings_miss", -1, 0.9, "XLK", ["earnings", "advertising"], "communication_services"),
        ("META", "2023-02-01", "post_market", "Meta beats estimates and announces a large buyback", "earnings_beat", 1, 0.9, "XLK", ["earnings", "advertising"], "communication_services"),
        ("META", "2024-02-01", "post_market", "Meta beats estimates and initiates its first dividend", "earnings_beat", 1, 0.9, "XLK", ["earnings", "advertising"], "communication_services"),
        ("META", "2024-04-24", "post_market", "Meta beats on revenue but heavy AI spending guidance weighs on shares", "earnings_beat", 1, 0.6, "XLK", ["earnings", "advertising", "ai_capex"], "communication_services"),
        # NVDA
        ("NVDA", "2023-02-22", "post_market", "NVIDIA beats estimates as data center demand strengthens", "earnings_beat", 1, 0.9, "SOXX", ["earnings", "ai_capex", "semiconductors"], "technology"),
        ("NVDA", "2023-05-24", "post_market", "NVIDIA beats and issues blowout guidance on AI chip demand", "earnings_beat", 1, 0.95, "SOXX", ["earnings", "ai_capex", "semiconductors"], "technology"),
        ("NVDA", "2024-02-21", "post_market", "NVIDIA beats estimates with surging AI data center revenue", "earnings_beat", 1, 0.95, "SOXX", ["earnings", "ai_capex", "semiconductors"], "technology"),
        ("NVDA", "2024-05-22", "post_market", "NVIDIA beats estimates on strong AI demand and announces a split", "earnings_beat", 1, 0.9, "SOXX", ["earnings", "ai_capex", "semiconductors"], "technology"),
        ("NVDA", "2024-08-28", "post_market", "NVIDIA beats estimates but shares slip on lofty expectations", "earnings_beat", 1, 0.6, "SOXX", ["earnings", "ai_capex", "semiconductors"], "technology"),
        # GOOGL
        ("GOOGL", "2023-02-02", "post_market", "Alphabet misses estimates as advertising revenue weakens", "earnings_miss", -1, 0.85, "XLK", ["earnings", "advertising"], "communication_services"),
        ("GOOGL", "2024-01-30", "post_market", "Alphabet misses estimates on weak advertising revenue", "earnings_miss", -1, 0.85, "XLK", ["earnings", "advertising"], "communication_services"),
        ("GOOGL", "2024-04-25", "post_market", "Alphabet beats estimates and announces first dividend", "earnings_beat", 1, 0.9, "XLK", ["earnings", "advertising", "cloud"], "communication_services"),
        # MSFT
        ("MSFT", "2024-01-30", "post_market", "Microsoft beats estimates on cloud and AI strength", "earnings_beat", 1, 0.9, "XLK", ["earnings", "cloud", "ai_capex"], "technology"),
        ("MSFT", "2024-07-30", "post_market", "Microsoft beats estimates but Azure cloud growth disappoints", "earnings_beat", 1, 0.6, "XLK", ["earnings", "cloud"], "technology"),
        # AAPL
        ("AAPL", "2023-02-02", "post_market", "Apple misses estimates as iPhone revenue declines", "earnings_miss", -1, 0.8, "SPY", ["earnings", "consumer_hardware"], "technology"),
        ("AAPL", "2024-05-02", "post_market", "Apple beats estimates and announces a record buyback", "earnings_beat", 1, 0.85, "SPY", ["earnings", "consumer_hardware"], "technology"),
        ("AAPL", "2024-08-01", "post_market", "Apple beats estimates as services revenue hits a record", "earnings_beat", 1, 0.8, "SPY", ["earnings", "consumer_hardware"], "technology"),
        # AMZN
        ("AMZN", "2023-02-02", "post_market", "Amazon guides lower on a soft operating income outlook", "guidance_cut", -1, 0.85, "QQQ", ["earnings", "guidance", "consumer_demand"], "consumer_discretionary"),
        ("AMZN", "2024-02-01", "post_market", "Amazon beats estimates as cloud and advertising accelerate", "earnings_beat", 1, 0.9, "QQQ", ["earnings", "cloud"], "consumer_discretionary"),
        ("AMZN", "2024-08-01", "post_market", "Amazon misses estimates and guides lower", "guidance_cut", -1, 0.85, "QQQ", ["earnings", "guidance", "consumer_demand"], "consumer_discretionary"),
        # TSLA
        ("TSLA", "2024-01-24", "post_market", "Tesla misses estimates and warns of slower growth", "earnings_miss", -1, 0.9, "QQQ", ["earnings", "guidance", "ev_auto"], "consumer_discretionary"),
        ("TSLA", "2024-07-23", "post_market", "Tesla misses estimates on shrinking automotive margins", "earnings_miss", -1, 0.85, "QQQ", ["earnings", "ev_auto"], "consumer_discretionary"),
        # AMD
        ("AMD", "2024-01-30", "post_market", "AMD guides lower for the first quarter despite AI optimism", "guidance_cut", -1, 0.7, "SOXX", ["earnings", "guidance", "semiconductors"], "technology"),
        ("AMD", "2024-07-30", "post_market", "AMD beats estimates on data center and AI demand", "earnings_beat", 1, 0.85, "SOXX", ["earnings", "ai_capex", "semiconductors"], "technology"),
        # AVGO
        ("AVGO", "2023-12-07", "post_market", "Broadcom beats estimates and guides higher on AI demand", "earnings_beat", 1, 0.85, "SOXX", ["earnings", "ai_capex", "semiconductors"], "technology"),
        ("AVGO", "2024-12-12", "post_market", "Broadcom beats estimates and guides higher on AI revenue", "guidance_raise", 1, 0.9, "SOXX", ["earnings", "guidance", "ai_capex", "semiconductors"], "technology"),
        # TSM (ADR, pre-market)
        ("TSM", "2024-01-18", "pre_market", "TSMC beats estimates on resilient AI chip demand", "earnings_beat", 1, 0.9, "SOXX", ["earnings", "ai_capex", "semiconductors"], "technology"),
        ("TSM", "2024-07-18", "pre_market", "TSMC beats and raises its revenue outlook on AI demand", "guidance_raise", 1, 0.9, "SOXX", ["earnings", "guidance", "ai_capex", "semiconductors"], "technology"),
        ("TSM", "2024-10-17", "pre_market", "TSMC beats and raises full-year outlook on AI demand", "guidance_raise", 1, 0.9, "SOXX", ["earnings", "guidance", "ai_capex", "semiconductors"], "technology"),
        # Banks (pre-market)
        ("JPM", "2024-01-12", "pre_market", "JPMorgan beats estimates on strong net interest income", "earnings_beat", 1, 0.85, "XLF", ["earnings", "banks", "rates"], "financials"),
        ("JPM", "2024-04-12", "pre_market", "JPMorgan beats estimates but guides cautiously on net interest income", "earnings_beat", -1, 0.6, "XLF", ["earnings", "guidance", "banks"], "financials"),
        ("BAC", "2024-01-12", "pre_market", "Bank of America misses estimates as net interest income falls", "earnings_miss", -1, 0.8, "XLF", ["earnings", "banks"], "financials"),
        ("GS", "2023-04-18", "pre_market", "Goldman Sachs misses estimates as trading revenue slows", "earnings_miss", -1, 0.8, "XLF", ["earnings", "market_turnover"], "financials"),
        ("GS", "2024-01-16", "pre_market", "Goldman Sachs beats estimates on rebounding investment banking", "earnings_beat", 1, 0.8, "XLF", ["earnings", "market_turnover"], "financials"),
        # Energy (pre-market)
        ("XOM", "2024-02-02", "pre_market", "Exxon beats estimates on strong production volumes", "earnings_beat", 1, 0.8, "XLE", ["earnings", "oil", "commodities"], "energy"),
        ("CVX", "2024-02-02", "pre_market", "Chevron beats estimates and raises its dividend", "earnings_beat", 1, 0.8, "XLE", ["earnings", "oil", "commodities"], "energy"),
        # Healthcare (pre-market)
        ("LLY", "2024-02-06", "pre_market", "Eli Lilly beats and raises guidance on obesity drug demand", "guidance_raise", 1, 0.9, "XLV", ["earnings", "guidance", "pharma"], "healthcare"),
        ("UNH", "2024-01-12", "pre_market", "UnitedHealth beats estimates on membership growth", "earnings_beat", 1, 0.8, "XLV", ["earnings"], "healthcare"),
        ("NVO", "2024-01-31", "pre_market", "Novo Nordisk beats and lifts outlook on Wegovy demand", "guidance_raise", 1, 0.9, "XLV", ["earnings", "guidance", "pharma"], "healthcare"),
    ]
    for tk, d, anchor, title, et, edir, conf, bench, tags, sector in earn:
        asset = "adr" if tk in {"TSM", "ASML", "NVO"} else "equity"
        ev.append(E(f"earn-{tk}-{d}", d, anchor, title, et, "company",
                    [tk], tags, bench, edir, conf, "company",
                    sub=et, category="company_earnings_guidance", asset=asset, sector=sector))

    # ===================== SECTOR / SHOCK events ==========================
    shocks = [
        ("svb-collapse-2023-03-10", "2023-03-10", "date", "Silicon Valley Bank collapses, triggering banking stress", "bank_stress", "official", ["XLF", "JPM", "BAC"], ["bank_stress", "credit_stress", "risk_off"], "SPY", -1, 0.95, "macro_fed", "financials"),
        ("regional-bank-rout-2023-03-13", "2023-03-13", "date", "Regional bank shares plunge on deposit outflow fears", "bank_stress", "sentiment", ["XLF", "BAC"], ["bank_stress", "credit_stress", "risk_off"], "SPY", -1, 0.9, "sentiment", "financials"),
        ("opec-surprise-cut-2023-04-02", "2023-04-02", "date", "OPEC+ surprise output cut sends crude oil prices higher", "oil_up", "official", ["USO", "XLE", "XOM", "CVX"], ["oil_up", "commodity_inflation", "oil"], "SPY", 1, 0.9, "opec", "energy"),
        ("opec-cut-2023-11-30", "2023-11-30", "date", "OPEC+ output cut drives crude oil prices higher", "oil_up", "official", ["USO", "XLE"], ["oil_up", "commodity_inflation", "oil"], "SPY", 1, 0.85, "opec", "energy"),
        ("chip-export-expand-2023-10-17", "2023-10-17", "date", "US expands export controls on advanced AI chips to China", "regulatory_risk", "official", ["NVDA", "AMD"], ["regulatory", "semiconductors", "china_demand"], "SOXX", -1, 0.9, "official_bis", "technology"),
        ("nvda-ai-rally-2024-02-22", "2024-02-22", "date", "AI chip demand sparks a broad semiconductor rally", "ai_capex_semis", "sentiment", ["SOXX", "QQQ", "AMD", "AVGO"], ["ai_capex", "semiconductors", "risk_sentiment"], "SPY", 1, 0.8, "sentiment", "technology"),
        ("yen-carry-unwind-2024-08-05", "2024-08-05", "date", "Global risk-off shock as the yen carry trade unwinds", "risk_off", "sentiment", ["QQQ", "TQQQ", "IWM"], ["risk_sentiment", "risk_off"], "SPY", -1, 0.9, "sentiment", "broad_market"),
        ("fda-lly-alzheimers-2023-07-06", "2023-07-06", "date", "FDA grants traditional approval to a new Alzheimer's drug", "regulatory_risk", "official", ["LLY", "XLV"], ["pharma", "regulatory"], "XLV", 1, 0.7, "official_fda", "healthcare"),
    ]
    for eid, d, anchor, title, et, stype, tickers, tags, bench, edir, conf, src, sector in shocks:
        asset = "etf" if all(t in {"XLF","XLE","USO","QQQ","TQQQ","IWM","SOXX","XLV"} for t in tickers) else "equity_or_etf"
        ev.append(E(eid, d, anchor, title, et, stype, tickers, tags, bench, edir, conf, src,
                    sub=et, category=_CATEGORY.get(stype, "sector_specific_shock") if stype != "official" else "regulatory_policy",
                    asset=asset, sector=sector))
    return ev


def _existing_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return {row["event_id"] for row in csv.DictReader(fh)}


def append_events(path: Path = EVENTS_CSV) -> int:
    existing = _existing_ids(path)
    rows = [e for e in build_events() if e["event_id"] not in existing]
    if not rows:
        return 0
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_COLUMNS)
        for row in rows:
            writer.writerow(row)
    return len(rows)


def main() -> int:
    all_built = build_events()
    added = append_events()
    from collections import Counter
    by_split = Counter(e["split"] for e in all_built)
    by_type = Counter(e["event_type"] for e in all_built)
    print(f"built {len(all_built)} curated events; appended {added} new rows")
    print("by_split:", dict(by_split))
    print("by_type :", dict(sorted(by_type.items())))
    print("\nNext: python -m modeling.v6.replay_benchmark_prices  (fetch real returns)")
    print("Then: python -c \"from modeling.v6.calibration import build_calibration as a; "
          "from modeling.v6.contagion import build_contagion as b; a(); b()\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
