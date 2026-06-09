"""V5.2 Deal Arena Lite tests (Segment 5 acceptance).

Arena is a light card table over the SAME real seed deck and the SAME
deterministic A/D engine as Deal Studio. There is no separate Arena engine or
Arena API: the page reuses /api/modeling/ma/samples and
/api/modeling/ma/calculate with V5.1 default cost synergy. These tests assert:

* the page route serves and links the deck/JS,
* an Arena deal is the SAME deterministic result Deal Studio would produce,
* reversing direction swaps acquirer/target and recomputes,
* default / manual / zero synergy do not regress,
* V5.0 financing-cost strict validation and market-cap-only rejection do not
  regress.
"""

from app import app


# Fixed light-table deal terms used by the Arena front end (arena.js
# ARENA_DEAL_TERMS). Kept in sync here so the determinism guarantee is tested
# against the real terms the page sends.
ARENA_DEAL_TERMS = {
    "deal_type": "full_acquisition",
    "premium": 0.30,
    "cash_pct": 0.5,
    "stock_pct": 0.5,
    "financing_cost": 0.05,
    "tax_rate": 0.25,
    "synergy_mode": "default",
}


def _arena_payload(acq_id, tgt_id):
    return {
        "acquirer": {"sample_id": acq_id},
        "target": {"sample_id": tgt_id},
        "deal": dict(ARENA_DEAL_TERMS),
        "currency": "USD",
    }


# ── Segment 1: page route smoke ────────────────────────────────────────────

def test_arena_page_route_serves():
    client = app.test_client()
    resp = client.get("/modeling/ma/arena")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Deal Arena" in html
    assert "/static/modeling/js/arena.js" in html
    # Light table only: it must not preload a full economics table or a
    # source_meta dump in the page shell.
    assert "source_meta" not in html


def test_arena_links_back_to_deal_studio():
    client = app.test_client()
    html = client.get("/modeling/ma/arena").get_data(as_text=True)
    assert "/modeling/ma" in html  # Deal Studio is still the full entry point


def test_homepage_exposes_both_studio_and_arena_ctas():
    client = app.test_client()
    html = client.get("/").get_data(as_text=True)
    assert 'href="/modeling/ma"' in html
    assert 'href="/modeling/ma/arena"' in html


# ── Segment 5: Arena == Deal Studio determinism ────────────────────────────

def test_arena_deal_matches_deal_studio_same_inputs():
    """Same deck ids + same terms -> identical result (no Arena-only engine)."""
    client = app.test_client()
    arena = client.post("/api/modeling/ma/calculate", json=_arena_payload("aapl", "msft"))
    # A Deal-Studio-shaped payload with the identical resolved inputs.
    studio = client.post("/api/modeling/ma/calculate", json={
        "acquirer": {"sample_id": "aapl"},
        "target": {"sample_id": "msft"},
        "deal": dict(ARENA_DEAL_TERMS),
        "currency": "USD",
    })
    assert arena.status_code == 200 and studio.status_code == 200
    assert arena.get_json()["result"] == studio.get_json()["result"]


def test_arena_deal_is_deterministic_across_calls():
    client = app.test_client()
    first = client.post("/api/modeling/ma/calculate", json=_arena_payload("nvda", "avgo"))
    second = client.post("/api/modeling/ma/calculate", json=_arena_payload("nvda", "avgo"))
    assert first.get_json()["result"] == second.get_json()["result"]


def test_arena_default_synergy_tier_present_and_light():
    client = app.test_client()
    r = client.post("/api/modeling/ma/calculate", json=_arena_payload("aapl", "msft")).get_json()["result"]
    # Light result fields the card relies on.
    assert r["acquirer"]["ticker"] == "AAPL"
    assert r["target"]["ticker"] == "MSFT"
    assert "accretion_dilution" in r
    assert r["synergy_status"] in {"self_accretive", "synergy_supported", "synergy_short"}
    assert r["synergy_status_label"]
    assert r["pre_ppa_chip"]["label"] == "Pre-PPA"
    ctx = r["synergy_context"]
    assert ctx["mode"] == "default"
    assert ctx["default_cost_synergy"]["synergy_tier"] in {"high", "medium", "low", "none"}


# ── Reverse direction swaps acquirer/target and recomputes ─────────────────

def test_reverse_direction_swaps_and_recomputes():
    client = app.test_client()
    forward = client.post("/api/modeling/ma/calculate", json=_arena_payload("aapl", "dis")).get_json()["result"]
    reverse = client.post("/api/modeling/ma/calculate", json=_arena_payload("dis", "aapl")).get_json()["result"]
    assert forward["acquirer"]["ticker"] == "AAPL"
    assert forward["target"]["ticker"] == "DIS"
    assert reverse["acquirer"]["ticker"] == "DIS"
    assert reverse["target"]["ticker"] == "AAPL"
    # A different acquirer base => a recomputed (different) accretion/dilution.
    assert forward["accretion_dilution"] != reverse["accretion_dilution"]


# ── Synergy modes do not regress (default / manual / zero) ─────────────────

def test_arena_synergy_modes_no_regression():
    client = app.test_client()

    default = client.post("/api/modeling/ma/calculate", json=_arena_payload("aapl", "msft")).get_json()["result"]
    assert default["synergy"] == default["synergy_context"]["default_cost_synergy"]["synergy_amount"]

    manual_payload = _arena_payload("aapl", "msft")
    manual_payload["deal"]["synergy_mode"] = "manual"
    manual_payload["deal"]["synergy"] = 250.0
    manual = client.post("/api/modeling/ma/calculate", json=manual_payload).get_json()["result"]
    assert manual["synergy"] == 250.0
    assert manual["synergy_context"]["manual_override"] is True

    zero_payload = _arena_payload("aapl", "msft")
    zero_payload["deal"]["synergy_mode"] = "zero"
    zero = client.post("/api/modeling/ma/calculate", json=zero_payload).get_json()["result"]
    assert zero["synergy"] == 0.0
    assert zero["synergy_context"]["zero_synergy_selected"] is True


# ── V5.0 strict validation does not regress through the Arena path ──────────

def test_arena_terms_preserve_financing_cost_validation():
    """All-cash with no financing cost must still 400 (no silent zero)."""
    client = app.test_client()
    payload = _arena_payload("aapl", "msft")
    payload["deal"]["cash_pct"] = 1.0
    payload["deal"]["stock_pct"] = 0.0
    payload["deal"].pop("financing_cost", None)
    resp = client.post("/api/modeling/ma/calculate", json=payload)
    assert resp.status_code == 400
    codes = {f["code"] for f in resp.get_json()["flags"]}
    assert "FINANCING_COST_REQUIRED" in codes


def test_arena_path_preserves_market_cap_only_rejection():
    client = app.test_client()
    payload = _arena_payload("aapl", "msft")
    # Override target with a market-cap-only block (no shares / price).
    payload["target"] = {"name": "Tgt", "net_income": 1000.0, "market_cap": 40000.0}
    resp = client.post("/api/modeling/ma/calculate", json=payload)
    assert resp.status_code == 400
    codes = {f["code"] for f in resp.get_json()["flags"]}
    assert "TARGET_SHARES_REQUIRED" in codes
    assert "TARGET_PRICE_REQUIRED" in codes
