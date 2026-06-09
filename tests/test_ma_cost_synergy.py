"""V5.1 deterministic default cost synergy rule tests."""

from copy import deepcopy

from modeling.ma.company_deck import get_company_card
from modeling.ma.cost_synergy import COST_SYNERGY_CONFIG, estimate_default_cost_synergy


def _result(acquirer_id, target_id):
    out = estimate_default_cost_synergy(get_company_card(acquirer_id), get_company_card(target_id))
    assert out["status"] == "ok"
    return out["result"]


def test_same_industry_group_is_high():
    r = _result("atlas_software", "atlas_software")
    assert r["synergy_tier"] == "high"
    assert r["matched_rules"] == ["same_industry_group"]
    assert r["synergy_type"] == "cost_only"
    assert r["calibration"] == "heuristic_v0_unvalidated"
    assert r["illustrative"] is True
    assert r["synergy_amount"] == get_company_card("atlas_software")["revenue"] * COST_SYNERGY_CONFIG["tiers"]["high"]


def test_adjacent_or_strategic_overlap_is_medium():
    r = _result("atlas_software", "beacon_payments")
    assert r["synergy_tier"] == "medium"
    assert r["synergy_pct_of_target_revenue"] == COST_SYNERGY_CONFIG["tiers"]["medium"]
    assert r["matched_rules"] == ["adjacent_industry_group"]


def test_cross_industry_low_overlap_is_low():
    r = _result("atlas_software", "ironbridge_energy")
    assert r["synergy_tier"] == "low"
    assert r["matched_rules"] == ["cross_industry_low_overlap"]
    assert r["synergy_pct_of_target_revenue"] == COST_SYNERGY_CONFIG["tiers"]["low"]


def test_missing_target_revenue_is_structured_error_not_silent_zero():
    acq = get_company_card("atlas_software")
    tgt = deepcopy(get_company_card("fulton_media"))
    del tgt["revenue"]
    out = estimate_default_cost_synergy(acq, tgt)
    assert out["status"] == "error"
    assert out["result"] is None
    assert any(flag["code"] == "TARGET_REVENUE_REQUIRED" for flag in out["flags"])


def test_real_tech_subindustries_do_not_all_default_to_high_synergy():
    pairs = [
        ("aapl", "msft"),
        ("googl", "meta"),
        ("amzn", "msft"),
        ("avgo", "nvda"),
        ("orcl", "crm"),
        ("orcl", "msft"),
        ("crm", "msft"),
        ("avgo", "orcl"),
    ]
    for acquirer_id, target_id in pairs:
        r = _result(acquirer_id, target_id)
        assert r["synergy_tier"] != "high"
        assert "same_industry_group" not in r["matched_rules"]
