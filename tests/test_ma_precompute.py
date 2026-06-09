"""V5.2.2 Precompute & Runtime Scalability Guardrail tests.

These cover the deterministic, read-only pairwise precompute that backs the
Arena lookup path, and assert it stays consistent with the live calculate path
without regressing any V5.0/V5.1/V5.2 behavior.
"""

from app import app
from modeling.ma.api import build_ma_response
from modeling.ma.company_deck import list_company_cards
from modeling.ma.precompute import (
    ARENA_DEAL_TERMS,
    build_arena_pairs,
    build_pair_payload,
    get_arena_pair,
    get_arena_pairs,
    list_arena_pairs,
    pair_key,
)


REAL_DECK_SIZE = 100
EXPECTED_PAIRS = REAL_DECK_SIZE * (REAL_DECK_SIZE - 1)  # 100 * 99 = 9900


def _light_from_calculate(result):
    """Derive the light comparison shape from a full calculate result."""
    ctx = result.get("synergy_context") or {}
    default_synergy = ctx.get("default_cost_synergy") or {}
    via = result.get("viability_context") or {}
    return {
        "acquirer_id": result["acquirer"]["id"],
        "target_id": result["target"]["id"],
        "acquirer_ticker": result["acquirer"]["ticker"],
        "target_ticker": result["target"]["ticker"],
        "accretion_dilution_pct": result["accretion_dilution"],
        "is_accretive": bool(result["is_accretive"]),
        "synergy_status": result["synergy_status"],
        "synergy_status_label": result["synergy_status_label"],
        "default_synergy_tier": default_synergy.get("synergy_tier"),
        "viability_level": via.get("viability_level"),
        "viability_label": via.get("viability_label"),
    }


# ── Count / shape ───────────────────────────────────────────────────────────

def test_pair_count_is_n_times_n_minus_one():
    bundle = build_arena_pairs()
    assert bundle["deck_size"] == REAL_DECK_SIZE
    assert bundle["pair_count"] == EXPECTED_PAIRS
    assert len(bundle["pairs"]) == EXPECTED_PAIRS


def test_no_self_deal():
    for p in build_arena_pairs()["pairs"]:
        assert p["acquirer_id"] != p["target_id"]


def test_pair_light_shape_has_no_heavy_fields():
    p = build_arena_pairs()["pairs"][0]
    for key in [
        "acquirer_id", "target_id", "acquirer_ticker", "target_ticker",
        "accretion_dilution_pct", "is_accretive", "direction",
        "synergy_status", "synergy_status_label", "default_synergy_tier",
        "pre_ppa_chip", "economic_chip",
        # V5.3 compact viability light fields
        "viability_level", "viability_label", "viability_flags_top",
    ]:
        assert key in p, key
    # Light only: no source_meta / no full economics table leakage.
    assert "source_meta" not in p
    assert "offer_value" not in p
    assert "consideration_mix" not in p
    # Viability stays compact: no long message / triggered_tags / audit leak.
    for f in p["viability_flags_top"]:
        assert set(f) <= {"severity", "category", "title", "rule_id"}
        assert "message" not in f
        assert "triggered_tags" not in f


def test_pair_light_keeps_economic_and_viability_separate():
    """The economic axis and the viability axis must be distinct fields; the
    economic chip must never be a viability value and vice versa."""
    for p in build_arena_pairs()["pairs"]:
        assert p["economic_chip"] in {"增厚", "摊薄"}
        assert p["viability_level"] in {"green", "yellow", "red"}
        # No merged overall score / win-rate anywhere in the light result.
        assert "overall_score" not in p
        assert "score" not in p
        assert "win_rate" not in p


# ── Consistency with the live calculate path ────────────────────────────────

def test_representative_pairs_match_calculate_api():
    client = app.test_client()
    index = build_arena_pairs()["index"]
    sample_pairs = [
        ("aapl", "msft"),
        ("msft", "aapl"),   # reverse direction
        ("nvda", "avgo"),
        ("xom", "cat"),
        ("dis", "cost"),
        ("wmt", "pep"),
        ("isrg", "dhr"),
        ("txn", "lrcx"),
        ("ups", "lmt"),
    ]
    for acq, tgt in sample_pairs:
        resp = client.post("/api/modeling/ma/calculate", json=build_pair_payload(acq, tgt))
        assert resp.status_code == 200
        live_light = _light_from_calculate(resp.get_json()["result"])
        pre = index[pair_key(acq, tgt)]
        for field, value in live_light.items():
            assert pre[field] == value, f"{acq}->{tgt} mismatch on {field}"


def test_reverse_pair_is_an_independent_result():
    index = build_arena_pairs()["index"]
    forward = index[pair_key("aapl", "msft")]
    reverse = index[pair_key("msft", "aapl")]
    # Distinct stored entries, recomputed from the acquirer's own base -- not a
    # mirrored copy of the forward text.
    assert forward["acquirer_id"] == "aapl" and forward["target_id"] == "msft"
    assert reverse["acquirer_id"] == "msft" and reverse["target_id"] == "aapl"
    assert forward["accretion_dilution_pct"] != reverse["accretion_dilution_pct"]


# ── Determinism / immutable cache ───────────────────────────────────────────

def test_repeated_build_is_identical():
    assert build_arena_pairs()["pairs"] == build_arena_pairs()["pairs"]


def test_rebuild_matches_cached_bundle():
    cached = get_arena_pairs()
    rebuilt = get_arena_pairs(rebuild=True)
    assert cached["pairs"] == rebuilt["pairs"]


def test_public_getters_return_defensive_copies():
    pairs = list_arena_pairs()
    pairs[0]["accretion_dilution_pct"] = 999.0
    pairs[0]["acquirer_ticker"] = "MUTATED"
    # Mutating the returned copy must not touch the shared cache.
    fresh = list_arena_pairs()
    assert fresh[0]["acquirer_ticker"] != "MUTATED"
    assert fresh[0]["accretion_dilution_pct"] != 999.0

    one = get_arena_pair("aapl", "msft")
    one["synergy_status"] = "MUTATED"
    assert get_arena_pair("aapl", "msft")["synergy_status"] != "MUTATED"


def test_get_arena_pairs_returns_detached_copy():
    """V5.2.3: get_arena_pairs() must not hand back the internal cache.

    Mutating the returned bundle -- top-level scalars, the pairs list, the
    index, and a nested pair dict -- must never affect later precomputed reads.
    """
    bundle = get_arena_pairs()
    bundle["deck_size"] = -1
    bundle["pair_count"] = -1
    bundle["pairs"].append({"acquirer_id": "HACK", "target_id": "HACK"})
    bundle["pairs"][0]["acquirer_ticker"] = "MUTATED"
    bundle["index"][pair_key("aapl", "msft")]["synergy_status"] = "MUTATED"

    fresh = get_arena_pairs()
    assert fresh["deck_size"] == REAL_DECK_SIZE
    assert fresh["pair_count"] == EXPECTED_PAIRS
    assert len(fresh["pairs"]) == EXPECTED_PAIRS
    assert all(p["acquirer_id"] != "HACK" for p in fresh["pairs"])
    assert fresh["pairs"][0]["acquirer_ticker"] != "MUTATED"
    # And the targeted single-pair accessor is likewise unaffected.
    assert get_arena_pair("aapl", "msft")["synergy_status"] != "MUTATED"


def test_get_arena_pair_returns_none_for_self_or_unknown():
    assert get_arena_pair("aapl", "aapl") is None
    assert get_arena_pair("aapl", "no_such_id") is None


# ── API endpoint ────────────────────────────────────────────────────────────

def test_arena_pairs_endpoint():
    import gzip
    import json
    client = app.test_client()
    # V5.11.2: the 100-card body is gzip-negotiated. Browsers always send
    # Accept-Encoding: gzip; the compressed wire body is what is transferred.
    resp = client.get("/api/modeling/ma/arena/pairs", headers={"Accept-Encoding": "gzip"})
    assert resp.status_code == 200
    assert resp.headers.get("Content-Encoding") == "gzip"
    data = json.loads(gzip.decompress(resp.data))
    assert data["status"] == "ok"
    assert data["deck_size"] == REAL_DECK_SIZE
    assert data["pair_count"] == EXPECTED_PAIRS
    assert len(data["pairs"]) == EXPECTED_PAIRS
    keys = {(p["acquirer_id"], p["target_id"]) for p in data["pairs"]}
    assert ("aapl", "msft") in keys
    assert all(p["acquirer_id"] != p["target_id"] for p in data["pairs"])
    # 100-card / 9900-pair body is ~9 MB raw but gzips ~29x to ~0.31 MB, well
    # under the 3 MB transfer guardrail (with large headroom for deck growth).
    assert len(resp.data) < 3_000_000


def test_arena_pairs_endpoint_does_not_mutate_cache():
    client = app.test_client()
    before = list_arena_pairs()
    client.get("/api/modeling/ma/arena/pairs")
    after = list_arena_pairs()
    assert before == after


def test_arena_pairs_endpoint_error_branch_hides_internal_exception(monkeypatch):
    """V5.2.3: the 500 branch must return a fixed structured error and never
    leak the raw exception string (paths / stack / internals)."""
    import app as app_module

    secret = "INTERNAL_TRACE C:/secret/path/precompute.py line 42 token=abc123"

    def boom(*_args, **_kwargs):
        raise RuntimeError(secret)

    # The route references the module-global name at call time, so patching the
    # name in the app module is enough to drive the except branch.
    monkeypatch.setattr(app_module, "get_arena_pairs_response", boom)

    client = app_module.app.test_client()
    resp = client.get("/api/modeling/ma/arena/pairs")
    assert resp.status_code == 500
    body = resp.get_json()
    assert body["status"] == "error"
    assert body["pairs"] == []
    flag = body["flags"][0]
    assert flag["code"] == "ARENA_PAIRS_UNAVAILABLE"
    assert flag["message"] == "Arena pair results are temporarily unavailable."
    # The raw exception text (and its sensitive fragments) must not appear.
    raw = resp.get_data(as_text=True)
    assert secret not in raw
    assert "INTERNAL_TRACE" not in raw
    assert "precompute.py" not in raw
    assert "token=abc123" not in raw


# ── Default synergy stays upstream of the engine ────────────────────────────

def test_default_synergy_layer_still_upstream_of_engine():
    """The precomputed pair must reflect default synergy applied before the
    engine: it equals calculate(default) and differs from calculate(zero)."""
    client = app.test_client()
    pre = get_arena_pair("aapl", "msft")
    assert pre["default_synergy_tier"] in {"high", "medium", "low", "none"}

    zero_payload = build_pair_payload("aapl", "msft")
    zero_payload["deal"] = dict(zero_payload["deal"], synergy_mode="zero")
    zero = client.post("/api/modeling/ma/calculate", json=zero_payload).get_json()["result"]
    # Default-synergy pair and zero-synergy result must not be the same number
    # (proves synergy is layered upstream, not ignored).
    assert pre["accretion_dilution_pct"] != zero["accretion_dilution"]


# ── No regression: synergy modes, strict validation ─────────────────────────

def test_default_manual_zero_modes_no_regression():
    client = app.test_client()

    default = client.post("/api/modeling/ma/calculate", json=build_pair_payload("aapl", "msft")).get_json()["result"]
    assert default["synergy"] == default["synergy_context"]["default_cost_synergy"]["synergy_amount"]

    manual = build_pair_payload("aapl", "msft")
    manual["deal"] = dict(manual["deal"], synergy_mode="manual", synergy=250.0)
    mr = client.post("/api/modeling/ma/calculate", json=manual).get_json()["result"]
    assert mr["synergy"] == 250.0 and mr["synergy_context"]["manual_override"] is True

    zero = build_pair_payload("aapl", "msft")
    zero["deal"] = dict(zero["deal"], synergy_mode="zero")
    zr = client.post("/api/modeling/ma/calculate", json=zero).get_json()["result"]
    assert zr["synergy"] == 0.0 and zr["synergy_context"]["zero_synergy_selected"] is True


def test_financing_cost_strict_validation_no_regression():
    """build_pair_payload through the engine still rejects all-cash w/o cost."""
    payload = build_pair_payload("aapl", "msft")
    payload["deal"] = dict(payload["deal"], cash_pct=1.0, stock_pct=0.0)
    payload["deal"].pop("financing_cost", None)
    body, code = build_ma_response(payload)
    assert code == 400
    assert any(f["code"] == "FINANCING_COST_REQUIRED" for f in body["flags"])


def test_market_cap_only_rejection_no_regression():
    payload = build_pair_payload("aapl", "msft")
    payload["target"] = {"name": "Tgt", "net_income": 1000.0, "market_cap": 40000.0}
    body, code = build_ma_response(payload)
    assert code == 400
    codes = {f["code"] for f in body["flags"]}
    assert "TARGET_SHARES_REQUIRED" in codes
    assert "TARGET_PRICE_REQUIRED" in codes


# ── No regression: Arena route ──────────────────────────────────────────────

def test_arena_route_still_serves():
    client = app.test_client()
    resp = client.get("/modeling/ma/arena")
    assert resp.status_code == 200
    assert "/static/modeling/js/arena.js" in resp.get_data(as_text=True)


def test_arena_terms_mirror_constant():
    # Guard against drift between the precompute terms and the documented set.
    assert ARENA_DEAL_TERMS["synergy_mode"] == "default"
    assert ARENA_DEAL_TERMS["premium"] == 0.30
    assert ARENA_DEAL_TERMS["cash_pct"] == 0.5
    assert ARENA_DEAL_TERMS["stock_pct"] == 0.5
    assert ARENA_DEAL_TERMS["financing_cost"] == 0.05
    assert ARENA_DEAL_TERMS["tax_rate"] == 0.25
