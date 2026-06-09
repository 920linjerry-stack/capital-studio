import math

from modeling.lbo_calculator import run_lbo


def clean_anchor():
    return {
        "symbol": "SYNTH",
        "currency": "USD",
        "transaction": {
            "entry_ebitda": 1000,
            "entry_multiple": 10.0,
            "exit_multiple": 10.0,
            "exit_year": 5,
            "transaction_fees_pct_ev": 0.02,
        },
        "operating_forecast": {
            "years": [1, 2, 3, 4, 5],
            "revenue": [5000, 5000, 5000, 5000, 5000],
            "ebitda": [1000, 1000, 1000, 1000, 1000],
            "cash_taxes": [100, 100, 100, 100, 100],
            "capex": [150, 150, 150, 150, 150],
            "change_in_nwc": [20, 20, 20, 20, 20],
        },
        "debt": {
            "debt_amount": 5000,
            "interest_rate": 0.09,
            "mandatory_amortization_pct": 0.01,
            "cash_sweep_pct": 1.0,
            "cash_to_balance_sheet": 0.0,
        },
        "tax_rate": 0.25,
        "tax_shield_enabled": False,
    }


def test_sources_uses_waterfall_exit_and_returns():
    out = run_lbo(clean_anchor())
    assert out["status"] == "ok"
    ts = out["transaction_summary"]
    assert ts["entry_ev"] == 10000
    assert ts["transaction_fees"] == 200
    assert ts["total_uses"] == 10200
    assert ts["debt_amount"] == 5000
    assert ts["sponsor_equity"] == 5200

    y1 = out["debt_schedule"][0]
    assert y1 == {
        "year": 1,
        "beginning_debt": 5000,
        "cash_flow_before_debt_service": 730,
        "cash_interest": 450,
        "gross_cash_taxes": 100,
        "tax_shield": 0.0,
        "levered_cash_taxes": 100,
        "tax_rate": 0.25,
        "tax_shield_enabled": False,
        "cash_available_for_debt": 280,
        "mandatory_amortization": 50,
        "cash_after_interest_and_mandatory_amortization": 230,
        "fcf_available_for_sweep": 230,
        "optional_repayment": 230,
        "ending_debt": 4720,
        "debt_service_failure": False,
    }

    assert out["exit"]["exit_ev"] == 10000
    assert out["exit"]["remaining_debt"] == out["debt_schedule"][-1]["ending_debt"]
    assert out["returns"]["moic"] == out["exit"]["exit_equity_value"] / 5200
    assert out["returns"]["cash_flows"] == [-5200, 0.0, 0.0, 0.0, 0.0, out["exit"]["exit_equity_value"]]
    assert math.isclose(out["returns"]["irr"], 0.05123289, rel_tol=1e-5)


def test_leverage_multiple_sizes_debt_when_amount_absent():
    payload = clean_anchor()
    payload["debt"].pop("debt_amount")
    payload["debt"]["leverage_multiple"] = 4.5
    out = run_lbo(payload)
    assert out["status"] == "ok"
    assert out["transaction_summary"]["debt_amount"] == 4500


def assert_error_code(payload, code):
    out = run_lbo(payload)
    assert out["status"] == "error"
    assert out["returns"] is None
    assert any(flag["code"] == code for flag in out["flags"])


def test_hard_errors():
    payload = clean_anchor()
    payload["debt"]["debt_amount"] = 10200
    assert_error_code(payload, "SPONSOR_EQUITY_NON_POSITIVE")

    payload = clean_anchor()
    payload["debt"]["debt_amount"] = 10201
    assert_error_code(payload, "DEBT_EXCEEDS_USES")

    payload = clean_anchor()
    payload["debt"]["cash_sweep_pct"] = 0.5
    assert_error_code(payload, "CASH_SWEEP_LOCKED_V40")

    payload = clean_anchor()
    payload["debt"]["cash_to_balance_sheet"] = 10
    assert_error_code(payload, "CASH_BALANCE_BRIDGE_LOCKED_V40")

    payload = clean_anchor()
    payload["operating_forecast"]["capex"] = [150]
    assert_error_code(payload, "FORECAST_LENGTH_MISMATCH")

    payload = clean_anchor()
    payload["transaction"]["exit_year"] = 4
    assert_error_code(payload, "EXIT_YEAR_MISMATCH")

    payload = clean_anchor()
    payload["transaction"]["exit_multiple"] = 0
    assert_error_code(payload, "IRR_CALCULATION_FAILED")


def test_run_lbo_does_not_call_run_dcf():
    import inspect
    import modeling.lbo_calculator as lbo

    source = inspect.getsource(lbo)
    assert "run_dcf" not in source
