from modeling.dcf_calculator import DCFInputs, run_dcf


def test_operating_assumptions_drive_forecast_not_historical_line_items():
    inp = DCFInputs(
        symbol="TEST",
        company="Test Co",
        price=10.0,
        revenue=1000.0,
        ebit=9999.0,
        da=9999.0,
        capex=9999.0,
        wc_change=-9999.0,
        tax_rate=0.20,
        net_debt=0.0,
        shares=100.0,
        revenue_growth=0.0,
        ebit_margin=0.25,
        da_pct_revenue=0.05,
        capex_pct_revenue=0.04,
        wc_change_pct_revenue=0.02,
        wacc=0.10,
        terminal_g=0.02,
        exit_multiple=10.0,
        forecast_years=1,
    )

    out = run_dcf(inp, historical_context={"available": False})

    assert out.revenue_projections[0] == 1000.0
    assert out.ebit_projections[0] == 250.0
    assert out.nopat_projections[0] == 200.0
    assert out.da_projections[0] == 50.0
    assert out.capex_projections[0] == 40.0
    assert out.delta_nwc_projections[0] == 20.0
    assert out.fcf_projections[0] == 190.0


def test_operating_assumptions_drive_forecast_even_with_historical_context():
    inp = DCFInputs(
        symbol="TEST",
        company="Test Co",
        price=10.0,
        revenue=1000.0,
        ebit=9999.0,
        da=9999.0,
        capex=9999.0,
        wc_change=-9999.0,
        tax_rate=0.20,
        net_debt=0.0,
        shares=100.0,
        revenue_growth=0.0,
        ebit_margin=0.25,
        da_pct_revenue=0.05,
        capex_pct_revenue=0.04,
        wc_change_pct_revenue=0.02,
        wacc=0.10,
        terminal_g=0.02,
        exit_multiple=10.0,
        forecast_years=1,
        operating_override_keys=["da_pct_revenue", "capex_pct_revenue", "wc_change_pct_revenue"],
    )
    hist_ctx = {
        "available": True,
        "dso": 100.0,
        "dio": 100.0,
        "dpo": 10.0,
        "gross_margin": 0.50,
        "da_pct_begin_ppe": 0.90,
        "beginning_ppe": 9999.0,
        "initial_nwc": -9999.0,
    }

    out = run_dcf(inp, historical_context=hist_ctx)

    assert out.revenue_projections[0] == 1000.0
    assert out.ebit_projections[0] == 250.0
    assert out.nopat_projections[0] == 200.0
    assert out.da_projections[0] == 50.0
    assert out.capex_projections[0] == 40.0
    assert out.delta_nwc_projections[0] == 20.0
    assert out.fcf_projections[0] == 190.0


def test_aapl_default_preserves_schedule_derived_delta_nwc_when_not_overridden():
    inp = DCFInputs(
        symbol="AAPL",
        company="Apple Inc.",
        price=100.0,
        revenue=1000.0,
        ebit=300.0,
        da=50.0,
        capex=40.0,
        wc_change=-60.0,
        tax_rate=0.20,
        net_debt=0.0,
        shares=100.0,
        revenue_growth=0.0,
        ebit_margin=0.30,
        da_pct_revenue=0.05,
        capex_pct_revenue=0.04,
        wc_change_pct_revenue=-0.060073,
        wacc=0.10,
        terminal_g=0.02,
        exit_multiple=10.0,
        forecast_years=1,
    )
    hist_ctx = {
        "available": True,
        "dso": 10.0,
        "dio": 0.0,
        "dpo": 0.0,
        "gross_margin": 1.0,
        "da_pct_begin_ppe": 0.10,
        "beginning_ppe": 500.0,
        "initial_nwc": 0.0,
    }

    out = run_dcf(inp, historical_context=hist_ctx)

    assert out.delta_nwc_projections[0] == round(1000.0 / 365.0 * 10.0, 2)
    assert out.delta_nwc_projections[0] != round(1000.0 * -0.060073, 2)
    assert out.audit["active_forecast_sources"]["delta_nwc"] == "schedule_derived_working_capital_days"
    assert out.audit["active_forecast_sources"]["da"] == "schedule_derived_beginning_ppe"


def test_manual_working_capital_override_uses_pct_revenue_with_historical_context():
    inp = DCFInputs(
        symbol="2359.HK",
        company="WuXi AppTec",
        price=100.0,
        revenue=1000.0,
        ebit=9999.0,
        da=9999.0,
        capex=9999.0,
        wc_change=-9999.0,
        tax_rate=0.20,
        net_debt=0.0,
        shares=100.0,
        revenue_growth=0.0,
        ebit_margin=0.25,
        da_pct_revenue=0.05,
        capex_pct_revenue=0.04,
        wc_change_pct_revenue=0.02,
        wacc=0.10,
        terminal_g=0.02,
        exit_multiple=10.0,
        forecast_years=1,
        operating_override_keys=["da_pct_revenue", "capex_pct_revenue", "wc_change_pct_revenue"],
    )
    hist_ctx = {
        "available": True,
        "dso": 100.0,
        "dio": 100.0,
        "dpo": 10.0,
        "gross_margin": 0.50,
        "da_pct_begin_ppe": 0.90,
        "beginning_ppe": 9999.0,
        "initial_nwc": -9999.0,
    }

    out = run_dcf(inp, historical_context=hist_ctx)

    assert out.da_projections[0] == 50.0
    assert out.capex_projections[0] == 40.0
    assert out.delta_nwc_projections[0] == 20.0
    assert out.audit["active_forecast_sources"]["delta_nwc"] == "user_override_pct_revenue"
