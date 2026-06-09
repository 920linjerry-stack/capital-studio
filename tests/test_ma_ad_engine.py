"""V5.0 M&A Accretion / Dilution engine tests.

Covers the Segment 1 acceptance targets:
* cash / stock / mix all run through one calculation chain
* premium up -> offer value up -> accretion under pressure
* financing cost up -> cash deal accretion under pressure
* acquirer share price / P/E change -> stock deal accretion changes
* break-even synergy ties to the accretion zero point
* all-stock deal uses acquisition value incl. premium (not target raw P/E)
* determinism, and purity (no Flask / file I/O import in the engine module)
"""

import math

import pytest

from modeling.ma.ad_engine import run_accretion_dilution


def base_inputs(**deal_overrides):
    deal = {
        "deal_type": "full_acquisition",
        "premium": 0.30,
        "cash_pct": 0.5,
        "stock_pct": 0.5,
        "financing_cost": 0.05,
        "tax_rate": 0.25,
        "synergy": 0.0,
    }
    deal.update(deal_overrides)
    return {
        "acquirer": {"name": "Acq", "net_income": 4000.0, "shares": 1000.0, "share_price": 200.0},
        "target": {"name": "Tgt", "net_income": 1000.0, "shares": 500.0, "share_price": 80.0},
        "deal": deal,
        "currency": "USD",
    }


# --------------------------------------------------------------------------- #
# Payment-method coverage: cash / stock / mix
# --------------------------------------------------------------------------- #

def test_all_cash_deal_runs():
    out = run_accretion_dilution(base_inputs(cash_pct=1.0, stock_pct=0.0))
    assert out["status"] == "ok"
    r = out["result"]
    # offer value = 500 * 80 * 1.30 = 52000
    assert math.isclose(r["offer_value"], 52000.0)
    assert math.isclose(r["cash_consideration"], 52000.0)
    assert r["stock_consideration"] == 0.0
    assert r["new_shares_issued"] == 0.0  # no stock issued in an all-cash deal
    assert r["pro_forma_shares"] == 4000.0 / 4.0  # acquirer shares unchanged == 1000


def test_all_stock_deal_runs():
    out = run_accretion_dilution(base_inputs(cash_pct=0.0, stock_pct=1.0))
    assert out["status"] == "ok"
    r = out["result"]
    assert r["cash_consideration"] == 0.0
    assert r["after_tax_financing_cost"] == 0.0  # no cash => no financing cost
    # new shares = stock consideration / acquirer price = 52000 / 200 = 260
    assert math.isclose(r["new_shares_issued"], 260.0)
    assert math.isclose(r["pro_forma_shares"], 1260.0)


def test_mix_deal_runs():
    out = run_accretion_dilution(base_inputs(cash_pct=0.6, stock_pct=0.4))
    assert out["status"] == "ok"
    r = out["result"]
    assert math.isclose(r["cash_consideration"], 52000.0 * 0.6)
    assert math.isclose(r["stock_consideration"], 52000.0 * 0.4)
    assert math.isclose(r["new_shares_issued"], (52000.0 * 0.4) / 200.0)


# --------------------------------------------------------------------------- #
# Directional sensitivities
# --------------------------------------------------------------------------- #

def test_premium_up_pressures_accretion():
    low = run_accretion_dilution(base_inputs(premium=0.10))["result"]
    high = run_accretion_dilution(base_inputs(premium=0.50))["result"]
    assert high["offer_value"] > low["offer_value"]
    # higher premium -> more dilutive (lower accretion %) for the same mix
    assert high["accretion_dilution"] < low["accretion_dilution"]


def test_financing_cost_up_pressures_cash_deal():
    cheap = run_accretion_dilution(base_inputs(cash_pct=1.0, stock_pct=0.0, financing_cost=0.03))["result"]
    pricey = run_accretion_dilution(base_inputs(cash_pct=1.0, stock_pct=0.0, financing_cost=0.09))["result"]
    assert pricey["after_tax_financing_cost"] > cheap["after_tax_financing_cost"]
    assert pricey["accretion_dilution"] < cheap["accretion_dilution"]


def test_acquirer_price_affects_stock_deal():
    cheap = base_inputs(cash_pct=0.0, stock_pct=1.0)
    cheap["acquirer"]["share_price"] = 120.0
    rich = base_inputs(cash_pct=0.0, stock_pct=1.0)
    rich["acquirer"]["share_price"] = 320.0
    cheap_r = run_accretion_dilution(cheap)["result"]
    rich_r = run_accretion_dilution(rich)["result"]
    # a higher acquirer price (higher P/E) issues fewer shares -> more accretive
    assert rich_r["new_shares_issued"] < cheap_r["new_shares_issued"]
    assert rich_r["accretion_dilution"] > cheap_r["accretion_dilution"]


# --------------------------------------------------------------------------- #
# All-stock deal must use acquisition value INCLUDING premium
# --------------------------------------------------------------------------- #

def test_all_stock_uses_acquisition_pe_not_target_raw_pe():
    out = run_accretion_dilution(base_inputs(cash_pct=0.0, stock_pct=1.0))["result"]
    # acquisition P/E reflects the premium and exceeds the target's raw P/E
    assert out["acquisition_pe"] > out["target_unaffected_pe"]
    # new shares are sized off offer_value (incl premium), not the unaffected cap
    target_equity = 500.0 * 80.0
    assert math.isclose(out["new_shares_issued"], target_equity * 1.30 / 200.0)
    # the classic identity: all-stock is accretive iff acquirer P/E > acquisition P/E
    if out["acquirer_pe"] > out["acquisition_pe"]:
        assert out["is_accretive"]
    else:
        assert not out["is_accretive"]


# --------------------------------------------------------------------------- #
# Break-even synergy ties to the accretion zero point
# --------------------------------------------------------------------------- #

def test_break_even_synergy_zeroes_accretion():
    out = run_accretion_dilution(base_inputs(cash_pct=0.6, stock_pct=0.4))["result"]
    be = out["break_even_synergy"]
    # plugging the break-even synergy back in must drive accretion to ~0
    tied = run_accretion_dilution(base_inputs(cash_pct=0.6, stock_pct=0.4, synergy=be))["result"]
    assert abs(tied["accretion_dilution"]) < 1e-9
    assert abs(tied["accretion_dilution_per_share"]) < 1e-9


def test_break_even_direction_consistency():
    out = run_accretion_dilution(base_inputs(cash_pct=0.6, stock_pct=0.4, synergy=0.0))["result"]
    be = out["break_even_synergy"]
    if be > 0:
        # below break-even is dilutive, above is accretive
        below = run_accretion_dilution(base_inputs(cash_pct=0.6, stock_pct=0.4, synergy=be * 0.5))["result"]
        above = run_accretion_dilution(base_inputs(cash_pct=0.6, stock_pct=0.4, synergy=be * 1.5))["result"]
        assert not below["is_accretive"]
        assert above["is_accretive"]


# --------------------------------------------------------------------------- #
# Three synergy states
# --------------------------------------------------------------------------- #

def test_self_accretive_state():
    # cheap target + high acquirer P/E -> accretive with zero synergy
    inp = base_inputs(cash_pct=0.0, stock_pct=1.0, premium=0.05, synergy=0.0)
    inp["acquirer"]["share_price"] = 400.0
    out = run_accretion_dilution(inp)["result"]
    assert out["break_even_synergy"] <= 0
    assert out["synergy_status"] == "self_accretive"
    assert out["synergy_status_label"] == "自带增厚"


def test_synergy_supported_and_short_states():
    base = base_inputs(cash_pct=1.0, stock_pct=0.0, premium=0.60, financing_cost=0.09, synergy=0.0)
    be = run_accretion_dilution(base)["result"]["break_even_synergy"]
    assert be > 0
    short = run_accretion_dilution(base_inputs(
        cash_pct=1.0, stock_pct=0.0, premium=0.60, financing_cost=0.09, synergy=be * 0.5))["result"]
    supported = run_accretion_dilution(base_inputs(
        cash_pct=1.0, stock_pct=0.0, premium=0.60, financing_cost=0.09, synergy=be * 1.2))["result"]
    assert short["synergy_status"] == "synergy_short"
    assert supported["synergy_status"] == "synergy_supported"


# --------------------------------------------------------------------------- #
# Pre-PPA boundary
# --------------------------------------------------------------------------- #

def test_pre_ppa_flags_present():
    out = run_accretion_dilution(base_inputs())["result"]
    assert out["pre_ppa"] is True
    assert out["ppa_amortization_modeled"] is False
    assert "PPA" in out["pre_ppa_detail"] or "PP&E" in out["pre_ppa_detail"]


def test_viability_is_separate_placeholder():
    out = run_accretion_dilution(base_inputs())["result"]
    assert out["viability"]["status"] == "not_assessed"


# --------------------------------------------------------------------------- #
# Structured errors / no silent 0 fallback
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("field, code", [
    ("net_income", "ACQUIRER_NET_INCOME_REQUIRED"),
    ("shares", "ACQUIRER_SHARES_REQUIRED"),
    ("share_price", "ACQUIRER_PRICE_REQUIRED"),
])
def test_missing_acquirer_core_field_errors(field, code):
    inp = base_inputs()
    del inp["acquirer"][field]
    out = run_accretion_dilution(inp)
    assert out["status"] == "error"
    assert out["result"] is None
    assert any(f["code"] == code for f in out["flags"])


def test_missing_target_net_income_errors():
    inp = base_inputs()
    del inp["target"]["net_income"]
    out = run_accretion_dilution(inp)
    assert out["status"] == "error"
    assert any(f["code"] == "TARGET_NET_INCOME_REQUIRED" for f in out["flags"])


def test_bad_consideration_mix_errors():
    out = run_accretion_dilution(base_inputs(cash_pct=0.7, stock_pct=0.7))
    assert out["status"] == "error"
    assert any(f["code"] == "CONSIDERATION_MIX_INVALID" for f in out["flags"])


def test_tax_rate_out_of_range_errors():
    out = run_accretion_dilution(base_inputs(tax_rate=1.0))
    assert out["status"] == "error"
    assert any(f["code"] == "TAX_RATE_INVALID" for f in out["flags"])


def test_all_cash_missing_financing_cost_errors():
    inp = base_inputs(cash_pct=1.0, stock_pct=0.0)
    del inp["deal"]["financing_cost"]
    out = run_accretion_dilution(inp)
    assert out["status"] == "error"
    assert out["result"] is None
    assert any(f["code"] == "FINANCING_COST_REQUIRED" for f in out["flags"])


def test_mix_missing_financing_cost_errors():
    inp = base_inputs(cash_pct=0.5, stock_pct=0.5)
    del inp["deal"]["financing_cost"]
    out = run_accretion_dilution(inp)
    assert out["status"] == "error"
    assert any(f["code"] == "FINANCING_COST_REQUIRED" for f in out["flags"])


def test_all_stock_missing_financing_cost_ok_and_unaffected():
    with_fc = run_accretion_dilution(base_inputs(cash_pct=0.0, stock_pct=1.0, financing_cost=0.09))
    inp = base_inputs(cash_pct=0.0, stock_pct=1.0)
    del inp["deal"]["financing_cost"]
    without_fc = run_accretion_dilution(inp)
    assert with_fc["status"] == "ok"
    assert without_fc["status"] == "ok"
    # financing cost is irrelevant when there is no cash portion
    assert without_fc["result"]["after_tax_financing_cost"] == 0.0
    assert math.isclose(with_fc["result"]["pro_forma_eps"], without_fc["result"]["pro_forma_eps"])
    assert math.isclose(with_fc["result"]["accretion_dilution"], without_fc["result"]["accretion_dilution"])


def test_all_cash_explicit_zero_financing_cost_ok():
    # explicit 0 is a deliberate user choice, not a silent fallback
    out = run_accretion_dilution(base_inputs(cash_pct=1.0, stock_pct=0.0, financing_cost=0.0))
    assert out["status"] == "ok"
    assert out["result"]["after_tax_financing_cost"] == 0.0


def test_market_cap_only_acquirer_errors():
    inp = base_inputs()
    inp["acquirer"] = {"name": "Acq", "net_income": 4000.0, "market_cap": 200000.0}
    out = run_accretion_dilution(inp)
    assert out["status"] == "error"
    codes = {f["code"] for f in out["flags"]}
    assert "ACQUIRER_SHARES_REQUIRED" in codes
    assert "ACQUIRER_PRICE_REQUIRED" in codes


def test_minority_stake_rejected():
    inp = base_inputs()
    inp["deal"]["deal_type"] = "minority_stake"
    out = run_accretion_dilution(inp)
    assert out["status"] == "error"
    assert any(f["code"] == "DEAL_TYPE_UNSUPPORTED" for f in out["flags"])


# --------------------------------------------------------------------------- #
# Determinism & purity
# --------------------------------------------------------------------------- #

def test_determinism_same_input_same_output():
    inp = base_inputs(cash_pct=0.55, stock_pct=0.45, synergy=120.0)
    first = run_accretion_dilution(inp)
    second = run_accretion_dilution(inp)
    assert first == second


def test_engine_module_is_pure():
    import inspect
    import modeling.ma.ad_engine as engine
    src = inspect.getsource(engine)
    assert "import flask" not in src.lower()
    assert "from flask" not in src.lower()
    assert "open(" not in src
    assert "requests" not in src
