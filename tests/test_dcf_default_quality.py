"""V3.9.11 default-quality three-layer defense tests.

Replaces the V3.9.10.2 ebit_margin/capex/wc_change rewrite tests. The new
gate is flag-only: data values are reported as-is and surfaced via tiered
flags + composite banner. WACC 8% floor and share-count reconciliation
remain as independent gates.
"""
from app import (
    _apply_default_quality_gates,
    _apply_share_count_quality_gate,
    _detect_industry_warning,
    _dcf_input_from_payload,
    _fetch_dcf_defaults,
)
from modeling.dcf_calculator import run_dcf
from data_fetcher import _is_financials_meaningful, _compute_meaningful_quorum


def _gate(symbol, company, market, fin, defaults, wacc=0.10, beta=1.0):
    return _apply_default_quality_gates(symbol, company, market, fin, defaults, wacc, beta)


def test_aapl_clean_no_flags(monkeypatch):
    """AAPL: real defaults pass all three layers — Clean tier, no flags."""
    import app

    monkeypatch.setattr(
        app,
        "_financials_cache_meta",
        lambda symbol: {"path": "test", "exists": True, "cached_at": "test", "stale": False},
    )
    fin = {
        "revenue": 416161.0, "ebit": 133050.0, "da": 11519.0,
        "capex": 12715.0, "wc_change": -25000.0, "net_debt": 0.0,
    }
    defaults = {
        "revenue_growth": 0.05, "ebit_margin": 0.3197,
        "da_pct_revenue": 0.028, "capex_pct_revenue": 0.0306,
        "wc_change_pct_revenue": -0.06,
    }
    adjusted, wacc, quality = _gate("AAPL", "Apple Inc.", "US", fin, defaults, 0.0865, 1.1)

    assert adjusted == defaults, "defaults must not be mutated"
    assert quality["overall_tier"] == "Clean"
    assert quality["data_health_flags"] == []
    assert quality["economic_sanity_flags"] == []
    assert quality["composite_banner"] is None
    assert wacc == 0.0865  # US WACC unaffected by HK/CN floor


def test_tencent_clean_pass():
    """0700.HK: Step A fixed CapEx to 15%, margin 32.5% < tech_internet P95 40%."""
    fin = {
        "revenue": 743689.0, "ebit": 241562.0, "da": 66028.0,
        "capex": 112875.0, "wc_change": 16484.0, "net_debt": 109946.0,
        "capex_source_fields": ["购建固定资产", "购建无形资产及其他资产"],
    }
    defaults = {
        "revenue_growth": 0.08, "ebit_margin": 0.3248,
        "da_pct_revenue": 0.0888, "capex_pct_revenue": 0.1518,
        "wc_change_pct_revenue": 0.0222,
    }
    adjusted, wacc, quality = _gate("0700.HK", "Tencent", "HK", fin, defaults, 0.07, 0.753)

    assert adjusted == defaults
    assert quality["data_health_flags"] == []
    assert quality["economic_sanity_flags"] == []
    # WACC floor still fires (independent economic gate)
    assert wacc == 0.08
    assert any(i["key"] == "wacc_below_floor" for i in quality["issues"])
    # industry resolution
    from modeling.industry_classification import classify_industry
    assert classify_industry("0700.HK", quality["profile"]) == "tech_internet_platform"


def test_maotai_review_high_margin_NOT_rewritten():
    """600519.SS: margin 67% — under consumer_staples_premium P95 70%, so
    economic_sanity does NOT fire. WACC floor still fires → Review tier.
    Critically, ebit_margin must NOT be rewritten (V3.9.10.2 used to push to 0.30).
    """
    fin = {
        "revenue": 172054.17, "ebit": 114808.95, "da": 1815.14,
        "capex": 3127.59, "wc_change": 6156.40, "net_debt": -100000.0,
    }
    defaults = {
        "revenue_growth": 0.10, "ebit_margin": 0.6673,
        "da_pct_revenue": 0.0105, "capex_pct_revenue": 0.0182,
        "wc_change_pct_revenue": 0.0358,
    }
    adjusted, wacc, quality = _gate("600519.SS", "贵州茅台", "CN", fin, defaults, 0.065, 0.423)

    assert adjusted["ebit_margin"] == 0.6673, "margin must NOT be rewritten"
    assert adjusted["capex_pct_revenue"] == 0.0182
    assert quality["economic_sanity_flags"] == []  # 67% < 70% P95, no flag
    assert quality["data_health_flags"] == []
    assert wacc == 0.08  # floor applied
    assert quality["overall_tier"] == "Review"  # wacc_below_floor lifts tier off Clean
    from modeling.industry_classification import classify_industry
    assert classify_industry("600519.SS", quality["profile"]) == "consumer_staples_premium"


def test_wuxi_high_review_with_composite_banner():
    """2359.HK: Step A fixed CapEx to 12% (no capex_suspiciously_low),
    but margin 52% > cro_cdmo_pharma P95 30% → economic_sanity fires.
    Banner explains 'high margin, data quality normal'.
    """
    fin = {
        "revenue": 45456.17, "ebit": 23804.90, "da": 3563.49,
        "capex": 5538.15, "wc_change": -1825.47, "net_debt": -21649.99,
        "capex_source_fields": ["购建固定资产", "购建无形资产及其他资产"],
    }
    defaults = {
        "revenue_growth": 0.05, "ebit_margin": 0.5237,
        "da_pct_revenue": 0.0784, "capex_pct_revenue": 0.1218,
        "wc_change_pct_revenue": -0.0402,
    }
    adjusted, wacc, quality = _gate("2359.HK", "WuXi AppTec", "HK", fin, defaults, 0.0611, 0.558)
    # Compose with share-count gate (matches the live pipeline order in app.py).
    _, quality = _apply_share_count_quality_gate(
        "2359.HK",
        {"market_cap": 386396.5532, "current_price": 129.5},
        {"shares": 510.4769},
        quality,
    )

    assert adjusted["ebit_margin"] == 0.5237, "margin must NOT be rewritten"
    assert "capex_suspiciously_low" not in quality["data_health_flags"]
    assert "ebit_margin_above_industry_p95" in quality["economic_sanity_flags"]
    # High Review = elevated by share-count reconciliation (V3.9.10.3) in full pipeline.
    assert quality["overall_tier"] == "High Review"
    banner = quality["composite_banner"] or ""
    assert "high" in banner.lower() and "data quality looks normal" in banner
    assert "cro_cdmo_pharma" in banner


def test_cnooc_data_health_only():
    """0883.HK: CapEx field-names non-standard → CapEx=0 → capex_suspiciously_low.
    Margin 43.6% < energy_upstream P95 50% → economic_sanity does NOT fire.
    Banner is the data-quality variant.
    """
    fin = {
        "revenue": 389336.0, "ebit": 169593.0, "da": 79771.0,
        "capex": 0.0, "wc_change": -6249.0, "net_debt": -209593.0,
        "capex_source_fields": [],
    }
    defaults = {
        "revenue_growth": 0.05, "ebit_margin": 0.4356,
        "da_pct_revenue": 0.2049, "capex_pct_revenue": 0.0,
        "wc_change_pct_revenue": -0.016,
    }
    adjusted, wacc, quality = _gate("0883.HK", "CNOOC", "HK", fin, defaults, 0.07, 0.304)

    assert "capex_suspiciously_low" in quality["data_health_flags"]
    assert "ebit_margin_above_industry_p95" not in quality["economic_sanity_flags"]
    assert quality["overall_tier"] == "High Review"
    assert quality["composite_banner"] == (
        "Upstream data quality issues detected. Default assumptions "
        "may be unreliable; review carefully."
    )


def test_wacc_floor_still_enforced_for_hk_non_financial():
    """WACC 8% floor preserved as independent economic gate."""
    fin = {"revenue": 100000, "ebit": 30000, "da": 5000, "capex": 4000, "wc_change": 0}
    defaults = {
        "revenue_growth": 0.05, "ebit_margin": 0.30,
        "da_pct_revenue": 0.05, "capex_pct_revenue": 0.04,
        "wc_change_pct_revenue": 0.0,
    }
    _, wacc, quality = _gate("0700.HK", "Tencent", "HK", fin, defaults, 0.06, 0.75)
    assert wacc == 0.08
    assert any(i["key"] == "wacc_below_floor" for i in quality["issues"])


def test_aapl_negative_wc_minus_6pct_does_not_flag_under_minus10_threshold():
    """AAPL has structural -6% WC release — V3.9.11 -10% threshold leaves it Clean."""
    fin = {"revenue": 416161.0, "ebit": 133050.0, "da": 11519.0,
           "capex": 12715.0, "wc_change": -25000.0}
    defaults = {"revenue_growth": 0.05, "ebit_margin": 0.32,
                "da_pct_revenue": 0.028, "capex_pct_revenue": 0.0306,
                "wc_change_pct_revenue": -0.06}
    _, _, quality = _gate("AAPL", "Apple Inc.", "US", fin, defaults, 0.0865, 1.1)
    assert "wc_release_extreme" not in quality["data_health_flags"]


def test_share_count_gate_uses_market_implied_total_shares_when_cache_is_partial():
    quote = {"market_cap": 386396.5532, "current_price": 129.5}
    fin = {"shares": 510.4769}

    shares, quality = _apply_share_count_quality_gate(
        "2359.HK", quote, fin, {"issues": [], "overall_tier": "Clean"}
    )

    assert round(shares, 2) == 2983.76
    assert quality["requires_review"] is True
    assert quality["overall_tier"] in ("High Review", "Review")
    assert quality["share_count_reconciliation"]["selected_basis"] == "market_cap / price implied total shares"


def test_dcf_post_payload_reconciles_stale_2359_share_denominator_across_sensitivities(monkeypatch):
    """V3.9.10.3 share denominator fix must remain intact under V3.9.11 gates."""
    import app

    frozen_quote = {"market_cap": 386396.5532, "current_price": 129.5}
    monkeypatch.setattr(app, "get_quote_router", lambda symbol: frozen_quote)
    expected_shares = frozen_quote["market_cap"] / frozen_quote["current_price"]

    payload = {
        "symbol": "2359.HK",
        "company": "WuXi AppTec",
        "price": 129.5,
        "revenue": 45456.166,
        "ebit": 23804.896,
        "da": 3563.491,
        "capex": 5538.15,
        "wc_change": -1825.474,
        "tax_rate": 0.19093513766259404,
        "net_debt": -21649.993,
        "shares": 510.4769,
        "revenue_growth": 0.03,
        "ebit_margin": 0.5237,
        "da_pct_revenue": 0.0784,
        "capex_pct_revenue": 0.1218,
        "wc_change_pct_revenue": -0.0402,
        "revenue_growth_path": [0.03] * 5,
        "ebit_margin_path": [0.5237] * 5,
        "da_pct_revenue_path": [0.0784] * 5,
        "capex_pct_revenue_path": [0.1218] * 5,
        "wc_change_pct_revenue_path": [-0.0402] * 5,
        "wacc": 0.08,
        "terminal_g": 0.025,
        "exit_multiple": 15.0,
        "forecast_years": 5,
        "tv_method": "average",
    }

    inp = _dcf_input_from_payload(payload)
    out = run_dcf(inp, historical_context={"available": False})

    assert round(inp.shares, 2) == round(expected_shares, 2)
    assert out.audit["shares_used_in_dcf"] == inp.shares
    assert out.audit["per_share_denominator_consistency"]["status"] == "OK"
    # V3.9.11: real margin/capex preserved → IV in 100-200 band (vs V3.9.10.2 ~76)
    assert 100 <= out.intrinsic_per_share <= 200


# ──────────────────────────────────────────────────────────────────────────
# V3.9.11 Batch 2A — F005 industry-aware banner tests
# ──────────────────────────────────────────────────────────────────────────

def test_jpm_triggers_bank_banner():
    """JPM (whitelisted) → bank hard banner with P/B + ROE methods."""
    w = _detect_industry_warning("JPM")
    assert w is not None
    assert w["category"] == "model_unsuitable_industry"
    assert w["industry_classification"] == "bank"
    assert w["severity"] == "hard"
    assert "P/B" in w["recommended_methods"]
    assert "ROE" in w["recommended_methods"]
    assert "Excess Return Model" in w["recommended_methods"]


def test_o_reit_triggers_reit_banner():
    """O (Realty Income, whitelisted) → REIT banner with AFFO/NAV, even though
    yfinance sector for REITs is 'Real Estate' not 'Financial Services'."""
    w = _detect_industry_warning("O")
    assert w is not None
    assert w["industry_classification"] == "reit"
    assert w["severity"] == "hard"
    assert "AFFO" in w["recommended_methods"]
    assert "NAV" in w["recommended_methods"]


def test_pypl_fintech_triggers_soft_caution():
    """PYPL → soft caution (does NOT block DCF, but warns)."""
    w = _detect_industry_warning("PYPL")
    assert w is not None
    assert w["category"] == "dcf_caution_industry"
    assert w["industry_classification"] == "fintech_payment"
    assert w["severity"] == "soft"
    # soft cautions intentionally do not carry recommended_methods
    assert "recommended_methods" not in w


def test_aapl_no_industry_banner():
    """AAPL is tech_software — no banner."""
    assert _detect_industry_warning("AAPL") is None


def test_brk_b_dotted_ticker_classified_correctly():
    """BRK.B (dotted) must classify to asset_manager — exercises ticker
    normalization (case + dot preservation)."""
    from modeling.industry_classification import classify_industry
    assert classify_industry("BRK.B", {}) == "asset_manager"
    assert classify_industry("brk.b", {}) == "asset_manager"  # case-insensitive
    w = _detect_industry_warning("BRK.B")
    assert w is not None
    assert w["industry_classification"] == "asset_manager"


def test_000001_sz_pingan_bank_hard_banner():
    """000001.SZ 平安银行 — V3.2.7 历史上 IV=-261/股,现在必须 hard banner 拦截。"""
    w = _detect_industry_warning("000001.SZ")
    assert w is not None
    assert w["industry_classification"] == "bank"
    assert w["severity"] == "hard"


def test_0005_hk_hsbc_bank_hard_banner():
    """0005.HK 汇丰 — hard banner."""
    w = _detect_industry_warning("0005.HK")
    assert w is not None
    assert w["industry_classification"] == "bank"
    assert w["severity"] == "hard"


def test_1299_hk_aia_insurance_hard_banner():
    """1299.HK 友邦保险 — hard banner with EV/P-EV methods."""
    w = _detect_industry_warning("1299.HK")
    assert w is not None
    assert w["industry_classification"] == "insurance_life"
    assert w["severity"] == "hard"
    assert "P/EV" in w["recommended_methods"]


# ──────────────────────────────────────────────────────────────────────────
# V3.9.11 Batch 2A — F004 meaningful-quorum gate tests
# ──────────────────────────────────────────────────────────────────────────

def test_meaningful_quorum_full_data_passes():
    fin = {"revenue": 1000, "ebit": 200, "capex": 50, "wc_change": 10, "da": 30}
    assert _is_financials_meaningful(fin) is True
    q = _compute_meaningful_quorum(fin)
    assert q["satisfied"] is True
    assert set(q["non_zero_secondary_fields"]) == {"ebit", "capex", "wc_change", "da"}
    assert q["missing_secondary_fields"] == []


def test_meaningful_quorum_revenue_only_blocked():
    fin = {"revenue": 1000, "ebit": 0, "capex": 0, "wc_change": 0, "da": 0}
    assert _is_financials_meaningful(fin) is False
    q = _compute_meaningful_quorum(fin)
    assert q["satisfied"] is False
    assert q["non_zero_secondary_fields"] == []


def test_meaningful_quorum_revenue_plus_one_blocked():
    fin = {"revenue": 1000, "ebit": 200, "capex": 0, "wc_change": 0, "da": 0}
    assert _is_financials_meaningful(fin) is False
    q = _compute_meaningful_quorum(fin)
    assert q["satisfied"] is False
    assert q["non_zero_secondary_fields"] == ["ebit"]
    assert set(q["missing_secondary_fields"]) == {"capex", "wc_change", "da"}


def test_meaningful_quorum_revenue_plus_two_passes():
    fin = {"revenue": 1000, "ebit": 200, "capex": 50, "wc_change": 0, "da": 0}
    assert _is_financials_meaningful(fin) is True
    q = _compute_meaningful_quorum(fin)
    assert q["satisfied"] is True
    assert set(q["non_zero_secondary_fields"]) == {"ebit", "capex"}


def test_meaningful_quorum_zero_revenue_blocked():
    """No revenue → no DCF, regardless of how many secondary fields are present."""
    fin = {"revenue": 0, "ebit": 200, "capex": 50, "wc_change": 10, "da": 30}
    assert _is_financials_meaningful(fin) is False
    q = _compute_meaningful_quorum(fin)
    assert q["satisfied"] is False
    assert q["revenue_present"] is False


# ──────────────────────────────────────────────────────────────────────────
# V3.9.11 Batch 2B — F008 HK WC coverage tracking
# ──────────────────────────────────────────────────────────────────────────

def test_hk_wc_extract_full_coverage():
    """Tencent-style reporter — 7 of 10 fields present, > 60% threshold."""
    from data_fetcher_akshare import _extract_hk_wc_change, HK_WC_FIELDS
    items = {
        "存货(增加)减少": -89_000_000,
        "应收帐款减少": -1_242_000_000,
        "应付帐款及应计费用增加(减少)": 13_741_000_000,
        "营运资本变动其他项目": -331_000_000,
        "预付款项、按金及其他应收款项减少(增加)": 17_007_000_000,
        "预收账款、按金及其他应付款增加(减少)": -18_745_000_000,
        "递延收入(增加)减少": 6_143_000_000,
    }
    total, audit = _extract_hk_wc_change(items)
    assert audit["matched_count"] == 7
    assert audit["total_keys"] == 10
    assert audit["coverage_ratio"] == 0.7
    assert audit["coverage_warning"] is False


def test_hk_wc_extract_low_coverage_triggers_warning():
    """CNOOC-style reporter — 3 of 10 fields, coverage_warning True."""
    from data_fetcher_akshare import _extract_hk_wc_change
    items = {
        "存货(增加)减少": -616_000_000,
        "应收帐款减少": -2_158_000_000,
        "营运资本变动其他项目": -3_475_000_000,
    }
    total, audit = _extract_hk_wc_change(items)
    assert audit["matched_count"] == 3
    assert audit["coverage_ratio"] == 0.3
    assert audit["coverage_warning"] is True
    # missing fields should include the 3 Batch 2B additions among others
    assert "应收关联方款项(增加)减少" in audit["missing_fields"]


def test_data_quality_wc_coverage_low_flag():
    """check_data_health emits wc_coverage_low Review issue when coverage_warning set."""
    from modeling.data_quality import check_data_health
    raw = {
        "revenue": 100_000, "ebit": 30_000, "da": 5_000,
        "capex": 4_000, "wc_change": 100,
        "wc_source_audit": {
            "matched_count": 2,
            "total_keys": 10,
            "coverage_ratio": 0.2,
            "missing_fields": ["a", "b", "c", "d"],
            "coverage_warning": True,
        },
    }
    res = check_data_health(raw, {})
    assert "wc_coverage_low" in res["flags"]
    issue = next(i for i in res["issues"] if i["key"] == "wc_coverage_low")
    assert issue["tier"] == "Review"
    assert issue["matched_count"] == 2
    assert issue["total_keys"] == 10
    assert issue["coverage_ratio"] == 0.2


# ──────────────────────────────────────────────────────────────────────────
# V3.9.11 Batch 2B — F014 SBC sector-differentiated floor
# ──────────────────────────────────────────────────────────────────────────

def _run_dcf_for_sbc(symbol, override_sbc_unavailable=False):
    """Tiny harness — fetch defaults, run dcf, return (out, drivers_effective)."""
    defaults = _fetch_dcf_defaults(symbol, scenario="base")
    inp = _dcf_input_from_payload(defaults)
    out = run_dcf(inp)
    drivers = (out.shareholder_returns or {}).get("drivers_effective") or {}
    return out, drivers


def test_sbc_floor_aapl_uses_real_historical_path():
    """AAPL has historical SBC — must NOT fall to sector_floor.
    The V3.9.9.4 real-data path takes precedence."""
    _, drivers = _run_dcf_for_sbc("AAPL")
    # Real-data path sets source_year and sbc_pct_market_cap; industry is None.
    assert drivers.get("annual_dilution_default_source_year") is not None
    assert drivers.get("annual_dilution_default_industry") is None
    assert drivers.get("sbc_pct_market_cap") is not None
    methodology = drivers.get("annual_dilution_default_methodology") or ""
    assert "historical SBC" in methodology


def test_sbc_floor_tencent_uses_sector_floor_with_warning():
    """0700.HK has no historical SBC in cache — falls to tech_internet_platform 1.5%."""
    _, drivers = _run_dcf_for_sbc("0700.HK")
    assert drivers.get("annual_dilution_default_industry") == "tech_internet_platform"
    assert abs(drivers.get("annual_dilution_pct") - 0.015) < 1e-9
    w = drivers.get("annual_dilution_floor_warning")
    assert w is not None
    assert w["key"] == "sbc_high_industry_default"
    assert w["industry"] == "tech_internet_platform"


def test_sbc_floor_maotai_low_industry_no_warning():
    """600519.SS — consumer_staples_premium 0.1% (BELOW legacy 0.25% baseline).
    No floor warning because floor did not rise above legacy."""
    _, drivers = _run_dcf_for_sbc("600519.SS")
    assert drivers.get("annual_dilution_default_industry") == "consumer_staples_premium"
    assert abs(drivers.get("annual_dilution_pct") - 0.0010) < 1e-9
    # 0.10% < 0.25% legacy → no elevated-floor warning
    assert drivers.get("annual_dilution_floor_warning") is None


def test_sbc_floor_wuxi_cro_floor_with_warning():
    """2359.HK — cro_cdmo_pharma 0.3%, warning fires (just above 0.25% baseline)."""
    _, drivers = _run_dcf_for_sbc("2359.HK")
    assert drivers.get("annual_dilution_default_industry") == "cro_cdmo_pharma"
    assert abs(drivers.get("annual_dilution_pct") - 0.003) < 1e-9
    assert drivers.get("annual_dilution_floor_warning") is not None


def test_sbc_floor_default_unknown_preserves_legacy_baseline():
    """Unknown ticker → _default_unknown 0.25% preserves V3.9.9.4 backward compat."""
    from modeling.industry_classification import INDUSTRY_SBC_FLOOR
    assert INDUSTRY_SBC_FLOOR["_default_unknown"] == 0.0025


def test_sbc_floor_table_covers_all_industries():
    """Every industry in INDUSTRY_MARGIN_P95 should also have an SBC floor entry."""
    from modeling.industry_classification import (
        INDUSTRY_MARGIN_P95, INDUSTRY_SBC_FLOOR,
    )
    missing = set(INDUSTRY_MARGIN_P95) - set(INDUSTRY_SBC_FLOOR)
    assert not missing, f"missing SBC floor entries: {missing}"
