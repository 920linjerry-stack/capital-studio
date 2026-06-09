"""V5.3 Real-World Viability Rule Layer v1 tests.

Covers the pure deterministic rule engine, its separation from the economic /
A&D result, and its compact + full surfacing through the API and precompute.
"""

from app import app
from modeling.ma.ad_engine import run_accretion_dilution
from modeling.ma.company_deck import get_engine_company
from modeling.ma.precompute import build_pair_payload, get_arena_pair
from modeling.ma.viability import (
    assess_viability,
    compact_viability,
)


_LEVEL_RANK = {"green": 0, "yellow": 1, "red": 2}


def _via(acq_id, tgt_id):
    return assess_viability(get_engine_company(acq_id), get_engine_company(tgt_id))


def _rule_ids(result):
    return {f["rule_id"] for f in result["flags"]}


def _categories(result):
    return {f["category"] for f in result["flags"]}


# ── Output shape ────────────────────────────────────────────────────────────

def test_viability_result_shape():
    v = _via("aapl", "msft")
    assert v["viability_level"] in {"green", "yellow", "red"}
    assert v["viability_label"].startswith("现实可行性")
    assert v["disclaimer_level"] == "light"
    assert isinstance(v["flags"], list) and v["flags"]
    for f in v["flags"]:
        assert set(f) >= {"severity", "category", "title", "message", "rule_id", "triggered_tags"}
        assert f["severity"] in {"green", "yellow", "red"}
    # V5.3 emits flags only -- no overall score / win-rate / merged number.
    assert "overall_score" not in v
    assert "score" not in v
    assert "win_rate" not in v


# ── Starter rule behavior (required cases) ──────────────────────────────────

def test_googl_meta_triggers_data_or_antitrust_flag():
    v = _via("googl", "meta")
    rules = _rule_ids(v)
    cats = _categories(v)
    assert "data_ai_platform_sensitivity" in rules or "antitrust" in cats
    assert v["viability_level"] in {"yellow", "red"}


def test_nvda_avgo_triggers_semiconductor_flag():
    v = _via("nvda", "avgo")
    semi_flags = [f for f in v["flags"] if "semiconductor" in f["rule_id"]]
    assert semi_flags
    assert "semiconductors" in semi_flags[0]["triggered_tags"]
    # both-sides semiconductor should be the elevated (red) variant
    assert v["viability_level"] == "red"


def test_ai_infra_not_caught_by_semiconductor_rule():
    """V5.3.1: ORCL's 'AI infrastructure' tag is data/AI sensitivity, not a
    semiconductor signal. Enterprise/cloud combos may be yellow but must NOT
    fire the semiconductor rule."""
    for a, b in [("orcl", "msft"), ("orcl", "crm"), ("msft", "orcl")]:
        v = _via(a, b)
        assert not any("semiconductor" in f["rule_id"] for f in v["flags"]), (a, b)
        assert v["viability_level"] == "yellow"
        assert "data_ai_platform_sensitivity" in _rule_ids(v)


def test_one_side_semiconductor_is_yellow():
    v = _via("nvda", "msft")  # NVDA semiconductor, MSFT not
    semi = [f for f in v["flags"] if f["rule_id"] == "semiconductors_one"]
    assert semi and semi[0]["severity"] == "yellow"
    assert semi[0]["triggered_tags"] == ["semiconductors"]


def test_both_side_semiconductor_is_red():
    v = _via("nvda", "avgo")
    semi = [f for f in v["flags"] if f["rule_id"] == "semiconductors_both"]
    assert semi and semi[0]["severity"] == "red"


def test_xom_combo_triggers_energy_flag():
    for other in ("cat", "cost", "dis"):
        v = _via("xom", other)
        assert any(f["rule_id"] == "energy_climate_sector" for f in v["flags"]), other
        assert v["viability_level"] in {"yellow", "red"}


def test_dis_hd_is_lower_risk_than_sensitive_combos():
    cross = _via("dis", "hd")
    assert cross["viability_level"] == "green"
    assert _LEVEL_RANK[cross["viability_level"]] < _LEVEL_RANK[_via("nvda", "avgo")["viability_level"]]
    assert _LEVEL_RANK[cross["viability_level"]] < _LEVEL_RANK[_via("googl", "meta")["viability_level"]]
    assert _LEVEL_RANK[cross["viability_level"]] < _LEVEL_RANK[_via("xom", "cat")["viability_level"]]


def test_capacity_flag_is_directional_not_a_block():
    # A much smaller acquirer buying a much larger target -> capacity flag.
    small_big = _via("dis", "xom")  # DIS equity << XOM equity
    assert any(f["rule_id"] == "acquirer_smaller_than_target" for f in small_big["flags"])
    # Reversed, the (now larger) acquirer should not get the capacity flag.
    big_small = _via("xom", "dis")
    assert not any(f["rule_id"] == "acquirer_smaller_than_target" for f in big_small["flags"])


# ── Determinism ─────────────────────────────────────────────────────────────

def test_viability_is_deterministic():
    assert _via("aapl", "msft") == _via("aapl", "msft")


def test_missing_tags_degrades_to_green_without_crash():
    bare = {"id": "x", "ticker": "X", "share_price": 10.0, "shares": 100.0}
    v = assess_viability(bare, dict(bare, id="y", ticker="Y"))
    assert v["viability_level"] == "green"
    assert v["flags"]


def test_non_dict_inputs_are_handled():
    v = assess_viability(None, None)
    assert v["viability_level"] == "green"


# ── Separation from the economic / A&D engine ───────────────────────────────

def test_viability_does_not_alter_engine_economics():
    """The engine result must be identical whether or not viability is layered.

    build_ma_response attaches viability_context AFTER the engine runs; here we
    prove the economic numbers equal a direct engine call that has no knowledge
    of viability at all.
    """
    client = app.test_client()
    payload = build_pair_payload("googl", "meta")  # a RED viability pair
    api_result = client.post("/api/modeling/ma/calculate", json=payload).get_json()["result"]

    # Direct engine call with the same resolved inputs + the default synergy
    # amount the API used (so we isolate "did viability touch the math").
    engine_inputs = {
        "acquirer": get_engine_company("googl"),
        "target": get_engine_company("meta"),
        "deal": {
            "deal_type": "full_acquisition",
            "premium": 0.30,
            "cash_pct": 0.5,
            "stock_pct": 0.5,
            "financing_cost": 0.05,
            "tax_rate": 0.25,
            "synergy": api_result["synergy"],
        },
        "currency": "USD",
    }
    engine_result = run_accretion_dilution(engine_inputs)["result"]

    assert api_result["viability_context"]["viability_level"] == "red"
    for key in ["pro_forma_eps", "accretion_dilution", "break_even_synergy", "synergy_status"]:
        assert api_result[key] == engine_result[key], key


def test_reverse_recomputes_viability_without_touching_economics():
    client = app.test_client()
    fwd = client.post("/api/modeling/ma/calculate", json=build_pair_payload("dis", "xom")).get_json()["result"]
    rev = client.post("/api/modeling/ma/calculate", json=build_pair_payload("xom", "dis")).get_json()["result"]

    # Viability recomputes for the new direction (capacity flag flips).
    fwd_rules = {f["rule_id"] for f in fwd["viability_context"]["flags"]}
    rev_rules = {f["rule_id"] for f in rev["viability_context"]["flags"]}
    assert "acquirer_smaller_than_target" in fwd_rules
    assert "acquirer_smaller_than_target" not in rev_rules

    # And the economic axis is genuinely a separate, independently-valid result.
    assert fwd["accretion_dilution"] != rev["accretion_dilution"]


# ── API surfacing ───────────────────────────────────────────────────────────

def test_calculate_returns_viability_context():
    client = app.test_client()
    r = client.post("/api/modeling/ma/calculate", json=build_pair_payload("nvda", "avgo")).get_json()["result"]
    via = r["viability_context"]
    assert via["viability_level"] == "red"
    assert via["disclaimer_level"] == "light"
    assert any("semiconductor" in f["rule_id"] for f in via["flags"])


def test_precomputed_pair_carries_compact_viability():
    p = get_arena_pair("googl", "meta")
    assert p["viability_level"] == "red"
    assert p["viability_label"].startswith("现实可行性")
    assert 1 <= len(p["viability_flags_top"]) <= 2
    for f in p["viability_flags_top"]:
        assert set(f) <= {"severity", "category", "title", "rule_id"}


def test_compact_viability_projection():
    full = _via("nvda", "avgo")
    compact = compact_viability(full)
    assert compact["viability_level"] == full["viability_level"]
    assert compact["viability_label"] == full["viability_label"]
    assert len(compact["viability_flags_top"]) <= 2
    # compact must not leak long fields
    for f in compact["viability_flags_top"]:
        assert "message" not in f and "triggered_tags" not in f


# ── No regression: inline financing-cost strict validation still wins ───────

def test_inline_market_cap_only_still_rejected_with_viability_layer():
    client = app.test_client()
    payload = build_pair_payload("aapl", "msft")
    payload["target"] = {"name": "Tgt", "net_income": 1000.0, "market_cap": 40000.0}
    resp = client.post("/api/modeling/ma/calculate", json=payload)
    assert resp.status_code == 400
    # Error path returns no result (and therefore no viability_context).
    assert resp.get_json()["result"] is None
