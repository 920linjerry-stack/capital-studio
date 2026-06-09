import math

from modeling.lbo_defaults import build_lbo_defaults


def clean_synthetic_anchor():
    return {
        "symbol": "SYNTH",
        "currency": "USD",
        "entry_ebitda": 1000,
        "entry_multiple": 10.0,
        "tax_rate": 0.25,
        "operating_forecast": {
            "years": [1, 2, 3, 4, 5],
            "revenue": [5000, 5050, 5100, 5150, 5200],
            "ebitda": [1000, 1010, 1020, 1030, 1040],
            "cash_taxes": [100, 101, 102, 103, 104],
            "capex": [100, 100, 100, 100, 100],
            "change_in_nwc": [10, 10, 10, 10, 10],
        },
    }


def thin_coverage_synthetic_anchor():
    return {
        "symbol": "THIN",
        "currency": "USD",
        "entry_ebitda": 1000,
        "entry_multiple": 10.0,
        "tax_rate": 0.25,
        "operating_forecast": {
            "years": [1, 2, 3, 4, 5],
            "revenue": [5000, 5000, 5000, 5000, 5000],
            "ebitda": [1000, 1000, 1000, 1000, 1000],
            "cash_taxes": [250, 250, 250, 250, 250],
            "capex": [300, 300, 300, 300, 300],
            "change_in_nwc": [100, 100, 100, 100, 100],
        },
    }


def distressed_synthetic_anchor():
    return {
        "symbol": "DIST",
        "currency": "USD",
        "entry_ebitda": 1000,
        "entry_multiple": 10.0,
        "tax_rate": 0.25,
        "operating_forecast": {
            "years": [1, 2, 3, 4, 5],
            "revenue": [5000, 5000, 5000, 5000, 5000],
            "ebitda": [1000, 1000, 1000, 1000, 1000],
            "cash_taxes": [300, 300, 300, 300, 300],
            "capex": [850, 850, 850, 850, 850],
            "change_in_nwc": [120, 120, 120, 120, 120],
        },
    }


def codes(result):
    return {flag["code"] for flag in result["flags"]}


def test_clean_synthetic_anchor_passes_5x_without_haircut():
    result = build_lbo_defaults("SYNTH", clean_synthetic_anchor())
    assert result["status"] == "ok"
    assert result["assumptions"]["leverage_multiple"] == 5.0
    assert result["serviceability"]["haircut_applied"] is False
    assert result["serviceability"]["debt_service_pass"] is True
    assert result["serviceability"]["initial_candidate_leverage"] == 5.0


def test_thin_coverage_anchor_triggers_haircut_and_passes_lower_leverage():
    result = build_lbo_defaults("THIN", thin_coverage_synthetic_anchor())
    assert result["status"] == "ok"
    assert result["assumptions"]["leverage_multiple"] < 5.0
    assert result["serviceability"]["haircut_applied"] is True
    assert result["serviceability"]["debt_service_pass"] is True
    assert "LEVERAGE_HAIRCUT_APPLIED" in codes(result)


def test_distressed_anchor_warns_when_1x_still_not_serviceable():
    result = build_lbo_defaults("DIST", distressed_synthetic_anchor())
    assert result["status"] == "warning"
    assert result["assumptions"]["leverage_multiple"] == 1.0
    assert result["serviceability"]["debt_service_pass"] is False
    assert "DEFAULT_DEBT_NOT_SERVICEABLE_AT_MIN_LEVERAGE" in codes(result)


def test_policy_defaults_and_provenance_are_present():
    result = build_lbo_defaults("SYNTH", clean_synthetic_anchor())
    assumptions = result["assumptions"]
    assert assumptions["exit_multiple"] == assumptions["entry_multiple"]
    assert assumptions["cash_sweep_pct"] == 1.0
    assert assumptions["cash_to_balance_sheet"] == 0.0
    for key in [
        "entry_ebitda",
        "entry_multiple",
        "exit_multiple",
        "leverage_multiple",
        "interest_rate",
        "entry_structure",
        "tax_shield_serviceability",
    ]:
        assert result["provenance"][key]["rationale_cn"]


def test_entry_ebitda_missing_or_non_positive_returns_error():
    result = build_lbo_defaults("BAD", {"currency": "USD"})
    assert result["status"] == "error"
    assert result["assumptions"] is None
    assert "ENTRY_EBITDA_UNAVAILABLE" in codes(result)

    result = build_lbo_defaults("BAD", {"entry_ebitda": 0})
    assert result["status"] == "error"
    assert "ENTRY_EBITDA_UNAVAILABLE" in codes(result)


def test_forecast_ebitda_non_positive_returns_error():
    raw = clean_synthetic_anchor()
    raw["operating_forecast"]["ebitda"][2] = 0
    result = build_lbo_defaults("BAD", raw)
    assert result["status"] == "error"
    assert "EBITDA_NON_POSITIVE_IN_FORECAST" in codes(result)


def test_ebitda_decline_risk_reduces_base_candidate_to_3x():
    raw = clean_synthetic_anchor()
    raw["operating_forecast"]["ebitda"] = [1000, 800, 805, 810, 815]
    result = build_lbo_defaults("DROP", raw)
    assert result["serviceability"]["initial_candidate_leverage"] == 3.0
    assert "EBITDA_DECLINE_RISK_DEFAULT_LEVERAGE_REDUCED" in codes(result)


def test_missing_tax_rate_uses_placeholder_flag():
    raw = clean_synthetic_anchor()
    raw.pop("tax_rate")
    raw["operating_forecast"]["cash_taxes"] = [0, 0, 0, 0, 0]
    result = build_lbo_defaults("SYNTH", raw)
    assert result["serviceability"]["tax_rate_source"] == "cash_taxes_over_ebitda"

    raw.pop("operating_forecast")
    result = build_lbo_defaults("SYNTH", raw)
    assert result["serviceability"]["tax_rate_source"] == "placeholder"
    assert math.isclose(result["serviceability"]["tax_rate_used"], 0.25)
    assert "TAX_RATE_PLACEHOLDER_USED" in codes(result)


def test_interest_is_recalculated_for_selected_candidate_leverage():
    result = build_lbo_defaults("THIN", thin_coverage_synthetic_anchor())
    leverage = result["serviceability"]["final_leverage"]
    debt = result["assumptions"]["entry_ebitda"] * leverage
    y1 = result["serviceability"]["yearly_serviceability"][0]
    assert math.isclose(y1["beginning_debt"], debt)
    assert math.isclose(y1["cash_interest"], debt * result["assumptions"]["interest_rate"])
    assert not math.isclose(y1["cash_interest"], 5000 * result["assumptions"]["interest_rate"])


def test_entry_ebitda_can_be_approximated_by_ebit_with_flag():
    result = build_lbo_defaults("EBIT", {"ebit": 900, "currency": "USD"})
    assert result["status"] == "ok"
    assert result["assumptions"]["entry_ebitda"] == 900
    assert "EBITDA_APPROXIMATED_BY_EBIT" in codes(result)


def test_entry_multiple_placeholder_flag_when_market_ev_missing():
    raw = clean_synthetic_anchor()
    raw.pop("entry_multiple")
    result = build_lbo_defaults("SYNTH", raw)
    assert result["assumptions"]["entry_multiple"] == 10.0
    assert "ENTRY_MULTIPLE_PLACEHOLDER_USED" in codes(result)
