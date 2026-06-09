from modeling.data_quality import build_capex_field_review
from modeling.dcf_calculator import DCFInputs, run_dcf


def test_high_confidence_field_included_candidate_applied_when_matched():
    audit = build_capex_field_review(
        "0883.HK",
        {"Purchase of property plant equipment": -1000},
        current_capex=1000,
        matched_fields=["Purchase of property plant equipment"],
    )
    assert audit["confidence"] == "HIGH"
    assert audit["applied"] is True


def test_medium_confidence_field_candidate_only():
    audit = build_capex_field_review(
        "0883.HK",
        {"Investing activities other": -800},
        current_capex=0,
        matched_fields=[],
    )
    assert audit["confidence"] == "MEDIUM"
    assert audit["applied"] is False
    assert audit["status"] == "High Review"


def test_no_field_leaves_high_review():
    audit = build_capex_field_review("0883.HK", {"Dividend paid": -10}, current_capex=0, matched_fields=[])
    assert audit["status"] == "High Review"
    assert audit["candidate_field"] is None


def test_candidate_not_applied_does_not_change_valuation():
    inp = DCFInputs(
        symbol="0883.HK", company="CNOOC", price=20, revenue=1000, ebit=400,
        da=200, capex=0, wc_change=0, tax_rate=0.2, net_debt=-100,
        shares=100, revenue_growth=0.03, ebit_margin=0.4, da_pct_revenue=0.2,
        capex_pct_revenue=0.0, wc_change_pct_revenue=0.0, wacc=0.09,
        terminal_g=0.025, exit_multiple=8, forecast_years=5, tv_method="average",
    )
    before = run_dcf(inp).intrinsic_per_share
    audit = build_capex_field_review("0883.HK", {"Investing activities other": -800}, 0, [])
    after = run_dcf(inp).intrinsic_per_share
    assert audit["applied"] is False
    assert after == before


def test_other_hk_tickers_unaffected():
    assert build_capex_field_review("0700.HK", {"Investing activities other": -800}, 0, []) is None
    assert build_capex_field_review("2359.HK", {"Investing activities other": -800}, 0, []) is None
