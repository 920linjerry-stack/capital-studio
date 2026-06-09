"""V4.4 covenant detection tests (leverage + interest coverage)."""

import math

from modeling.lbo_calculator import run_lbo
from tests.test_lbo_multitranche_schedule import (
    multi_tranche_anchor,
    low_leverage_high_fcf_cash_build_fixture,
    base_transaction_forecast,
)


def _covenant(out):
    return out["covenant_summary"]


def varying_ebitda_fixture():
    a = multi_tranche_anchor()
    a["operating_forecast"]["ebitda"] = [1000, 1100, 1200, 1300, 1400]
    return a


def zero_ebitda_year_fixture():
    a = base_transaction_forecast(n=5, ebitda=[1000, 0, 1000, 1000, 1000])
    a["operating_forecast"]["cash_taxes"] = [100, 100, 100, 100, 100]
    a["operating_forecast"]["capex"] = [50, 50, 50, 50, 50]
    a["operating_forecast"]["change_in_nwc"] = [0, 0, 0, 0, 0]
    a["capital_structure"] = {
        "mode": "multi_tranche",
        "tranches": [
            {"id": "revolver", "name": "Revolver", "type": "revolver",
             "opening_balance": 0.0, "commitment": 3000.0, "interest_rate": 0.05,
             "maturity_year": 5, "sweep_priority": 2, "draw_allowed": True},
            {"id": "tlb", "name": "Term Loan B", "type": "term_loan_b",
             "opening_balance": 500.0, "commitment": 500.0, "interest_rate": 0.05,
             "mandatory_amortization_pct": 0.0, "maturity_year": 7,
             "sweep_priority": 1, "draw_allowed": False},
        ],
        "covenants": {"max_net_debt_ebitda": 6.0, "min_interest_coverage": 2.0},
    }
    return a


# ---------------------------------------------------------------------------


def test_covenant_uses_current_year_ebitda_not_entry():
    out = run_lbo(varying_ebitda_fixture())
    cov = _covenant(out)
    forecast = out["operating_forecast"]["ebitda"]
    for chk, fc in zip(cov["checks"], forecast):
        assert math.isclose(chk["ebitda"], fc)
    # entry ebitda was 1000 but later checks use 1100..1400
    assert cov["checks"][-1]["ebitda"] == 1400


def test_leverage_covenant_pass_case():
    out = run_lbo(multi_tranche_anchor())  # max 6.0, year-1 leverage ~4.7
    cov = _covenant(out)
    assert cov["checks"][0]["leverage_breach"] is False
    assert cov["checks"][0]["leverage_headroom"] > 0


def test_leverage_covenant_breach_case():
    a = multi_tranche_anchor()
    a["capital_structure"]["covenants"]["max_net_debt_ebitda"] = 3.0
    out = run_lbo(a)
    cov = _covenant(out)
    assert cov["status"] == "breach"
    assert cov["checks"][0]["leverage_breach"] is True
    assert 1 in cov["breach_years"]
    codes = {f["code"] for f in out["flags"]}
    assert "COVENANT_BREACH_DETECTED" in codes


def test_interest_coverage_pass_case():
    out = run_lbo(multi_tranche_anchor())  # ebitda 1000 / interest ~452 = 2.2 > 2.0
    cov = _covenant(out)
    assert cov["checks"][0]["interest_coverage_breach"] is False
    assert cov["checks"][0]["interest_coverage"] > 2.0


def test_interest_coverage_breach_case():
    a = multi_tranche_anchor()
    a["capital_structure"]["covenants"]["min_interest_coverage"] = 3.0
    out = run_lbo(a)
    cov = _covenant(out)
    assert cov["status"] == "breach"
    assert cov["checks"][0]["interest_coverage_breach"] is True


def test_ebitda_non_positive_creates_unavailable_flag():
    out = run_lbo(zero_ebitda_year_fixture())
    cov = _covenant(out)
    codes = {f["code"] for f in out["flags"]}
    assert "COVENANT_EBITDA_NON_POSITIVE" in codes
    year2 = cov["checks"][1]
    assert year2["ebitda"] == 0
    assert year2["net_debt_ebitda"] is None


def test_interest_coverage_unavailable_when_interest_zero():
    out = run_lbo(low_leverage_high_fcf_cash_build_fixture())
    cov = _covenant(out)
    # debt fully repaid by year 1; later years have zero interest
    later = cov["checks"][-1]
    assert later["interest_coverage"] is None
    codes = {f["code"] for f in out["flags"]}
    assert "INTEREST_COVERAGE_UNAVAILABLE" in codes


def test_net_cash_display_not_misleading_negative_leverage():
    out = run_lbo(low_leverage_high_fcf_cash_build_fixture())
    cov = _covenant(out)
    later = cov["checks"][-1]
    assert later["is_net_cash"] is True
    assert later["net_debt"] < 0
    assert later["net_debt_ebitda"] is None  # do not show e.g. -3.5x
    assert later["leverage_breach"] is False


def test_covenant_summary_thresholds_echoed():
    out = run_lbo(multi_tranche_anchor())
    cov = _covenant(out)
    assert cov["max_net_debt_ebitda"] == 6.0
    assert cov["min_interest_coverage"] == 2.0
