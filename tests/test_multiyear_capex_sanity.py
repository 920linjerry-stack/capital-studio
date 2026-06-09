from modeling.data_quality import build_capex_sanity_audit
from modeling.dcf_calculator import DCFInputs, run_dcf


def _fin(history, latest_capex=150):
    return {
        "revenue": 1000,
        "capex": latest_capex,
        "capex_history": history + [{"year": 2025, "revenue": 1000, "capex": latest_capex}],
    }


def test_latest_significantly_above_mean_review():
    audit = build_capex_sanity_audit("0700.HK", _fin([
        {"year": 2022, "revenue": 1000, "capex": 80},
        {"year": 2023, "revenue": 1000, "capex": 90},
        {"year": 2024, "revenue": 1000, "capex": 100},
    ], latest_capex=130))
    assert audit["status"] == "Review"
    assert audit["latest_capex_pct_revenue"] == 0.13


def test_latest_normal_clean():
    audit = build_capex_sanity_audit("AAPL", _fin([
        {"year": 2022, "revenue": 1000, "capex": 90},
        {"year": 2023, "revenue": 1000, "capex": 100},
        {"year": 2024, "revenue": 1000, "capex": 110},
    ], latest_capex=105))
    assert audit["status"] == "Clean"


def test_insufficient_history_review_or_unavailable():
    audit = build_capex_sanity_audit("2359.HK", {"revenue": 1000, "capex": 100})
    assert audit["status"] in {"Review", "Unavailable"}


def test_latest_near_zero_high_review():
    audit = build_capex_sanity_audit("0883.HK", _fin([
        {"year": 2022, "revenue": 1000, "capex": 80},
        {"year": 2023, "revenue": 1000, "capex": 90},
        {"year": 2024, "revenue": 1000, "capex": 100},
    ], latest_capex=0))
    assert audit["status"] == "High Review"


def test_audit_block_does_not_change_valuation():
    inp = DCFInputs(
        symbol="TEST", company="Test Co", revenue=1000, ebit=200, da=30, capex=100, wc_change=10,
        tax_rate=0.21, net_debt=100, shares=100, revenue_growth=0.03,
        ebit_margin=0.2, da_pct_revenue=0.03, capex_pct_revenue=0.1,
        wc_change_pct_revenue=0.01, wacc=0.09, terminal_g=0.025,
        exit_multiple=10, forecast_years=5, tv_method="average", price=10,
    )
    before = run_dcf(inp).intrinsic_per_share
    _ = build_capex_sanity_audit("TEST", _fin([
        {"year": 2022, "revenue": 1000, "capex": 60},
        {"year": 2023, "revenue": 1000, "capex": 70},
        {"year": 2024, "revenue": 1000, "capex": 80},
    ], latest_capex=150))
    after = run_dcf(inp).intrinsic_per_share
    assert after == before
