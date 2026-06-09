"""V4.4 multi-tranche capital structure / waterfall tests."""

import copy
import math

import pytest

from modeling.lbo_calculator import run_lbo
from modeling.lbo_attribution import build_lbo_attribution


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def base_transaction_forecast(n=5, ebitda=None):
    years = list(range(1, n + 1))
    ebitda = ebitda or [1000] * n
    return {
        "symbol": "SYNTH",
        "currency": "USD",
        "transaction": {
            "entry_ebitda": 1000,
            "entry_multiple": 10.0,
            "exit_multiple": 10.0,
            "exit_year": n,
            "transaction_fees_pct_ev": 0.02,
        },
        "operating_forecast": {
            "years": years,
            "revenue": [5000] * n,
            "ebitda": ebitda,
            "cash_taxes": [100] * n,
            "capex": [150] * n,
            "change_in_nwc": [20] * n,
        },
        "tax_rate": 0.25,
        "tax_shield_enabled": False,
    }


def multi_tranche_anchor():
    a = base_transaction_forecast()
    a["capital_structure"] = {
        "mode": "multi_tranche",
        "cash_balance_beginning": 0.0,
        "minimum_cash_balance": 0.0,
        "cash_sweep_enabled": True,
        "tranches": [
            {"id": "revolver", "name": "Revolver", "type": "revolver",
             "opening_balance": 0.0, "commitment": 500.0, "interest_rate": 0.08,
             "mandatory_amortization_pct": 0.0, "maturity_year": 5,
             "sweep_priority": 4, "draw_allowed": True, "optional_repay_allowed": True},
            {"id": "tla", "name": "Term Loan A", "type": "term_loan_a",
             "opening_balance": 1500.0, "commitment": 1500.0, "interest_rate": 0.085,
             "mandatory_amortization_pct": 0.05, "maturity_year": 5,
             "sweep_priority": 1, "draw_allowed": False, "optional_repay_allowed": True},
            {"id": "tlb", "name": "Term Loan B", "type": "term_loan_b",
             "opening_balance": 2500.0, "commitment": 2500.0, "interest_rate": 0.09,
             "mandatory_amortization_pct": 0.01, "maturity_year": 7,
             "sweep_priority": 2, "draw_allowed": False, "optional_repay_allowed": True},
            {"id": "senior_notes", "name": "Senior Notes", "type": "senior_notes",
             "opening_balance": 1000.0, "commitment": 1000.0, "interest_rate": 0.10,
             "mandatory_amortization_pct": 0.0, "maturity_year": 8,
             "sweep_priority": 3, "draw_allowed": False, "optional_repay_allowed": False},
        ],
        "covenants": {"max_net_debt_ebitda": 6.0, "min_interest_coverage": 2.0},
    }
    return a


def revolver_draw_fixture():
    a = base_transaction_forecast(n=3, ebitda=[200, 1000, 1000])
    a["transaction"]["entry_multiple"] = 8.0
    a["transaction"]["transaction_fees_pct_ev"] = 0.0
    a["transaction"]["exit_year"] = 3
    a["operating_forecast"]["cash_taxes"] = [50, 50, 50]
    a["operating_forecast"]["capex"] = [40, 40, 40]
    a["operating_forecast"]["change_in_nwc"] = [10, 10, 10]
    a["capital_structure"] = {
        "mode": "multi_tranche",
        "tranches": [
            {"id": "revolver", "name": "Revolver", "type": "revolver",
             "opening_balance": 0.0, "commitment": 500.0, "interest_rate": 0.08,
             "maturity_year": 3, "sweep_priority": 1, "draw_allowed": True},
            {"id": "tlb", "name": "Term Loan B", "type": "term_loan_b",
             "opening_balance": 2000.0, "commitment": 2000.0, "interest_rate": 0.09,
             "mandatory_amortization_pct": 0.0, "maturity_year": 7,
             "sweep_priority": 2, "draw_allowed": False},
        ],
        "covenants": {"max_net_debt_ebitda": 12.0, "min_interest_coverage": 1.0},
    }
    return a


def revolver_capacity_exceeded_fixture():
    a = revolver_draw_fixture()
    a["capital_structure"]["tranches"][0]["commitment"] = 50.0
    return a


def mandatory_optional_cap_fixture():
    a = base_transaction_forecast(n=2)
    a["transaction"]["exit_year"] = 2
    a["capital_structure"] = {
        "mode": "multi_tranche",
        "tranches": [
            {"id": "tla", "name": "Term Loan A", "type": "term_loan_a",
             "opening_balance": 100.0, "commitment": 100.0, "interest_rate": 0.05,
             "mandatory_amortization_pct": 0.05, "maturity_year": 5,
             "sweep_priority": 1, "draw_allowed": False},
            {"id": "tlb", "name": "Term Loan B", "type": "term_loan_b",
             "opening_balance": 3000.0, "commitment": 3000.0, "interest_rate": 0.09,
             "mandatory_amortization_pct": 0.0, "maturity_year": 7,
             "sweep_priority": 2, "draw_allowed": False},
        ],
    }
    return a


def low_leverage_high_fcf_cash_build_fixture():
    a = base_transaction_forecast(n=5)
    a["operating_forecast"]["capex"] = [50] * 5
    a["operating_forecast"]["change_in_nwc"] = [0] * 5
    a["capital_structure"] = {
        "mode": "multi_tranche",
        "tranches": [
            {"id": "tla", "name": "Term Loan A", "type": "term_loan_a",
             "opening_balance": 500.0, "commitment": 500.0, "interest_rate": 0.08,
             "mandatory_amortization_pct": 0.10, "maturity_year": 5,
             "sweep_priority": 1, "draw_allowed": False},
        ],
        "covenants": {"max_net_debt_ebitda": 6.0, "min_interest_coverage": 2.0},
    }
    return a


def _tranche_row(row, tid):
    return next(t for t in row["tranches"] if t["id"] == tid)


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


def test_single_tranche_path_unaffected_without_capital_structure():
    from tests.test_lbo_calculator_core import clean_anchor
    out = run_lbo(clean_anchor())
    assert out["status"] == "ok"
    assert "capital_structure_summary" not in out


def test_multi_tranche_status_ok_and_summary_present():
    out = run_lbo(multi_tranche_anchor())
    assert out["status"] == "ok"
    assert out["capital_structure_summary"]["mode"] == "multi_tranche"
    assert out["transaction_summary"]["debt_amount"] == 5000.0
    assert out["transaction_summary"]["sponsor_equity"] == 5200.0


# ---------------------------------------------------------------------------
# Tranche validation hard errors
# ---------------------------------------------------------------------------


def _assert_error(payload, code):
    out = run_lbo(payload)
    assert out["status"] == "error"
    assert out["returns"] is None
    assert any(f["code"] == code for f in out["flags"])


def test_duplicate_tranche_id_hard_error():
    a = multi_tranche_anchor()
    a["capital_structure"]["tranches"][1]["id"] = "revolver"
    _assert_error(a, "DUPLICATE_TRANCHE_ID")


def test_commitment_below_opening_hard_error():
    a = multi_tranche_anchor()
    a["capital_structure"]["tranches"][1]["commitment"] = 100.0
    _assert_error(a, "COMMITMENT_BELOW_OPENING_BALANCE")


def test_negative_interest_rate_hard_error():
    a = multi_tranche_anchor()
    a["capital_structure"]["tranches"][1]["interest_rate"] = -0.01
    _assert_error(a, "NEGATIVE_INTEREST_RATE")


def test_pik_enabled_hard_error():
    a = multi_tranche_anchor()
    a["capital_structure"]["tranches"].append({
        "id": "mezz", "name": "Mezz", "type": "mezz", "opening_balance": 100.0,
        "commitment": 100.0, "interest_rate": 0.12, "maturity_year": 8,
        "sweep_priority": 5, "draw_allowed": False, "pik_enabled": True,
    })
    _assert_error(a, "PIK_NOT_SUPPORTED_V44")


def test_invalid_maturity_year_hard_error():
    a = multi_tranche_anchor()
    a["capital_structure"]["tranches"][1]["maturity_year"] = 0
    _assert_error(a, "INVALID_MATURITY_YEAR")


def test_invalid_tranche_type_hard_error():
    a = multi_tranche_anchor()
    a["capital_structure"]["tranches"][1]["type"] = "bridge_loan"
    _assert_error(a, "INVALID_TRANCHE_TYPE")


def test_mezz_cash_pay_allowed():
    a = multi_tranche_anchor()
    a["capital_structure"]["tranches"].append({
        "id": "mezz", "name": "Mezz", "type": "mezz", "opening_balance": 100.0,
        "commitment": 100.0, "interest_rate": 0.12, "maturity_year": 8,
        "sweep_priority": 5, "draw_allowed": False, "cash_pay": True, "pik_enabled": False,
    })
    out = run_lbo(a)
    assert out["status"] == "ok"


# ---------------------------------------------------------------------------
# Waterfall mechanics
# ---------------------------------------------------------------------------


def test_interest_on_beginning_balance_by_tranche():
    out = run_lbo(multi_tranche_anchor())
    y1 = out["debt_schedule"][0]
    assert math.isclose(_tranche_row(y1, "tla")["cash_interest"], 1500 * 0.085)
    assert math.isclose(_tranche_row(y1, "tlb")["cash_interest"], 2500 * 0.09)
    assert math.isclose(_tranche_row(y1, "senior_notes")["cash_interest"], 1000 * 0.10)
    assert math.isclose(y1["total_cash_interest"], 127.5 + 225 + 100)


def test_mandatory_amortization_uses_original_opening_capped_by_beginning():
    out = run_lbo(multi_tranche_anchor())
    y1 = out["debt_schedule"][0]
    # scheduled = original_opening * pct, even after balances change in later years
    assert math.isclose(_tranche_row(y1, "tla")["mandatory_amortization"], 1500 * 0.05)
    last = out["debt_schedule"][-1]
    tla_last = _tranche_row(last, "tla")
    # cap by beginning: never amortize more than the remaining balance
    assert tla_last["mandatory_amortization"] <= tla_last["beginning_balance"] + 1e-9


def test_optional_repayment_cap_and_no_negative_balance():
    out = run_lbo(mandatory_optional_cap_fixture())
    assert out["status"] == "ok"
    y1 = out["debt_schedule"][0]
    tla = _tranche_row(y1, "tla")
    # beginning 100, mandatory 5, optional capped at 95 -> ending exactly 0
    assert math.isclose(tla["mandatory_amortization"], 5.0)
    assert math.isclose(tla["optional_repayment"], 95.0)
    assert math.isclose(tla["ending_balance"], 0.0, abs_tol=1e-9)
    # mandatory + optional never exceeds beginning + draw
    for row in out["debt_schedule"]:
        for tr in row["tranches"]:
            assert tr["mandatory_amortization"] + tr["optional_repayment"] <= tr["beginning_balance"] + tr["draw"] + 1e-9
            assert tr["ending_balance"] >= -1e-9


def test_revolver_draw_when_cash_shortfall():
    out = run_lbo(revolver_draw_fixture())
    assert out["status"] == "ok"
    y1 = out["debt_schedule"][0]
    assert y1["revolver_draw"] > 0
    # mutual exclusivity invariant
    rev = _tranche_row(y1, "revolver")
    assert y1["revolver_draw"] * rev["optional_repayment"] == 0
    assert rev["optional_repayment"] == 0


def test_revolver_draw_and_optional_mutually_exclusive_all_years():
    out = run_lbo(revolver_draw_fixture())
    for row in out["debt_schedule"]:
        rev = _tranche_row(row, "revolver")
        assert row["revolver_draw"] * rev["optional_repayment"] == 0


def test_revolver_capacity_exceeded_flags_failure():
    out = run_lbo(revolver_capacity_exceeded_fixture())
    assert out["status"] == "ok"  # not a hard error, but a flagged failure
    codes = {f["code"] for f in out["flags"]}
    assert "REVOLVER_CAPACITY_EXCEEDED" in codes
    assert any(row["debt_service_failure"] for row in out["debt_schedule"])


def test_optional_sweep_follows_priority_ascending():
    out = run_lbo(multi_tranche_anchor())
    y1 = out["debt_schedule"][0]
    # tla (priority 1) is swept before tlb (priority 2); senior_notes (no optional) untouched
    assert _tranche_row(y1, "tla")["optional_repayment"] > 0
    assert _tranche_row(y1, "tlb")["optional_repayment"] == 0
    assert _tranche_row(y1, "senior_notes")["optional_repayment"] == 0


def test_ending_cash_balance_captures_excess_after_repayment():
    out = run_lbo(low_leverage_high_fcf_cash_build_fixture())
    assert out["status"] == "ok"
    last = out["debt_schedule"][-1]
    assert last["total_ending_debt"] <= 1e-9
    assert last["ending_cash_balance"] > 0
    assert out["capital_structure_summary"]["ending_cash_balance"] > 0


def test_exit_equity_includes_ending_cash():
    out = run_lbo(low_leverage_high_fcf_cash_build_fixture())
    ex = out["exit"]
    expected = ex["exit_ev"] - ex["remaining_debt"] + ex["ending_cash_balance"]
    assert math.isclose(ex["exit_equity_value"], expected, abs_tol=1e-6)
    assert ex["ending_cash_balance"] > 0


def test_total_ending_debt_equals_sum_of_tranches():
    out = run_lbo(multi_tranche_anchor())
    for row in out["debt_schedule"]:
        assert math.isclose(row["total_ending_debt"], sum(t["ending_balance"] for t in row["tranches"]))


def test_cash_bridge_disclosure_present():
    out = run_lbo(multi_tranche_anchor())
    note = out["capital_structure_summary"]["single_vs_multi_cash_bridge_note"]
    assert "ending cash balance" in note.lower()
    assert any("cash balance bridge" in d.lower() for d in out["audit"]["disclosures"])


def test_carry_forward_balances_between_years():
    out = run_lbo(multi_tranche_anchor())
    sched = out["debt_schedule"]
    for prev, cur in zip(sched, sched[1:]):
        for tr in cur["tranches"]:
            prev_tr = _tranche_row(prev, tr["id"])
            assert math.isclose(tr["beginning_balance"], prev_tr["ending_balance"], abs_tol=1e-9)


# ---------------------------------------------------------------------------
# Maturity wall
# ---------------------------------------------------------------------------


def test_maturity_wall_groups_by_year():
    out = run_lbo(multi_tranche_anchor())
    wall = out["maturity_wall"]
    years = [b["year"] for b in wall]
    assert years == sorted(years)
    assert {7, 8} <= set(years)


def test_maturity_within_hold_period_flag():
    out = run_lbo(multi_tranche_anchor())  # exit year 5; revolver & tla mature in year 5
    codes = {f["code"] for f in out["flags"]}
    assert "DEBT_MATURITY_WITHIN_HOLD_PERIOD" in codes


def test_maturity_after_hold_no_auto_refinance():
    out = run_lbo(multi_tranche_anchor())
    # tlb matures year 7 (> exit 5) and is still simply displayed, debt remains outstanding
    tlb = next(b for b in out["maturity_wall"] if 7 == b["year"])
    assert "Term Loan B" in tlb["tranches"]


# ---------------------------------------------------------------------------
# Attribution compatibility
# ---------------------------------------------------------------------------


def test_multi_tranche_attribution_uses_total_debt():
    payload = multi_tranche_anchor()
    res = run_lbo(payload)
    attr = build_lbo_attribution(payload, res)
    comps = {c["key"]: c for c in attr["components"]}
    delev = comps["deleveraging"]["value"]
    expected = res["capital_structure_summary"]["total_opening_debt"] - res["capital_structure_summary"]["total_ending_debt"]
    assert math.isclose(delev, expected, abs_tol=1e-6)


def test_multi_tranche_attribution_has_ending_cash_component():
    payload = low_leverage_high_fcf_cash_build_fixture()
    res = run_lbo(payload)
    attr = build_lbo_attribution(payload, res)
    comps = {c["key"]: c for c in attr["components"]}
    assert "ending_cash_balance" in comps
    assert comps["ending_cash_balance"]["value"] > 0
    assert math.isclose(comps["ending_cash_balance"]["value"], res["capital_structure_summary"]["ending_cash_balance"], abs_tol=1e-6)


def test_multi_tranche_attribution_residual_near_zero():
    for fixture in (multi_tranche_anchor(), low_leverage_high_fcf_cash_build_fixture()):
        res = run_lbo(fixture)
        attr = build_lbo_attribution(fixture, res)
        assert abs(attr["tie_out"]["residual"]) < max(1e-6, abs(attr["tie_out"]["target_equity_value_creation"]) * 1e-6) * 10


def test_low_leverage_fixture_proves_cash_build_and_residual_zero():
    payload = low_leverage_high_fcf_cash_build_fixture()
    res = run_lbo(payload)
    attr = build_lbo_attribution(payload, res)
    comps = {c["key"]: c for c in attr["components"]}
    # cash build is material and accounted for, residual stays near zero
    assert comps["ending_cash_balance"]["value"] > 0
    assert abs(comps["residual"]["value"]) < 1e-3
    total = sum(c["moic_contribution"] for c in attr["components"])
    assert math.isclose(total, res["returns"]["moic"] - 1.0, abs_tol=1e-9)
