"""V5.5 Settlement Board · dual deterministic result-layer tests.

Two INDEPENDENT rankings over the precomputed directed pairs:

* Economic board  -> most accretive first (EPS accretion/dilution descending).
* Viability board -> steadiest first (green > yellow > red, then fewer risk
  flags, then higher EPS, then a stable ticker tie-break).

Hard boundaries asserted here:
* both boards are pure deterministic functions of the frozen deck (repeat
  builds are byte-identical),
* AAPL->MSFT and MSFT->AAPL stay distinct directed deals,
* there is NO merged overall score / win-rate,
* the boards ride on the existing /api/modeling/ma/arena/pairs response as an
  additive `boards` field and stay light (no source_meta / full economics /
  audit trail / raw exception),
* the engine / default synergy / viability rules / calculate contract are
  unchanged, and V5.2.x precompute determinism + cache isolation hold.
"""

from app import app
from modeling.ma.api import build_ma_response
from modeling.ma.precompute import (
    build_pair_payload,
    build_settlement_boards,
    get_arena_pair,
    get_settlement_boards,
    list_arena_pairs,
)
from modeling.ma.viability import assess_viability, compact_viability


REAL_DECK_SIZE = 100
EXPECTED_PAIRS = REAL_DECK_SIZE * (REAL_DECK_SIZE - 1)  # 9900
_VIA_ORDER = {"green": 0, "yellow": 1, "red": 2}


# ── compact_viability gained exactly the two light board fields ──────────────

def test_compact_viability_adds_summary_and_risk_count():
    full = assess_viability(
        {"tags": {}}, {"tags": {}},
    )
    compact = compact_viability(full)
    assert "viability_summary" in compact
    assert "viability_flags_count" in compact
    # A clean cross-industry deal carries one synthetic green flag => 0 risk.
    assert compact["viability_flags_count"] == 0
    # Still compact: no long per-flag messages / triggered_tags leak.
    for f in compact["viability_flags_top"]:
        assert set(f) <= {"severity", "category", "title", "rule_id"}


def test_compact_viability_counts_only_real_concern_flags():
    # AAPL + MSFT: same big-tech family global leaders + data/AI => red + yellow.
    from modeling.ma.sample_companies import get_sample_company
    full = assess_viability(get_sample_company("aapl"), get_sample_company("msft"))
    compact = compact_viability(full)
    assert compact["viability_level"] == "red"
    # Two genuine concern flags, none of them the synthetic green.
    assert compact["viability_flags_count"] == sum(
        1 for f in full["flags"] if f["severity"] != "green"
    )
    assert compact["viability_flags_count"] >= 1


# ── Board shape / counts ────────────────────────────────────────────────────

def test_boards_cover_all_pairs_and_have_no_self_deal():
    boards = build_settlement_boards()
    assert boards["pair_count"] == EXPECTED_PAIRS
    for board in ("economic", "viability"):
        assert len(boards[board]) == 10  # first pass Top 10
        for row in boards[board]:
            assert row["acquirer_id"] != row["target_id"]


def test_boards_are_light_no_heavy_fields():
    boards = build_settlement_boards()
    for board in ("economic", "viability", "tension"):
        for row in boards[board]:
            for heavy in ("source_meta", "offer_value", "consideration_mix",
                          "synergy_context", "pro_forma_eps", "break_even_synergy"):
                assert heavy not in row, heavy


def test_boards_have_no_overall_score():
    boards = build_settlement_boards()
    for board in ("economic", "viability", "tension"):
        for row in boards[board]:
            for banned in ("overall_score", "score", "win_rate", "combined_score"):
                assert banned not in row, banned


# ── Economic board ordering ─────────────────────────────────────────────────

def test_economic_board_sorted_by_eps_descending():
    econ = build_settlement_boards(top_n=EXPECTED_PAIRS)["economic"]
    values = [r["accretion_dilution_pct"] for r in econ]
    # Non-increasing across the full ranking.
    assert values == sorted(values, reverse=True)
    # Top row is the single most accretive directed pair in the whole deck.
    assert econ[0]["accretion_dilution_pct"] == max(
        r["accretion_dilution_pct"] for r in list_arena_pairs()
    )


def test_economic_board_ticker_tiebreak_is_stable():
    """Equal-EPS rows (if any) and overall order must be deterministic via the
    ticker tie-break: two builds are byte-identical."""
    a = build_settlement_boards(top_n=EXPECTED_PAIRS)["economic"]
    b = build_settlement_boards(top_n=EXPECTED_PAIRS)["economic"]
    assert [(r["acquirer_ticker"], r["target_ticker"]) for r in a] == \
           [(r["acquirer_ticker"], r["target_ticker"]) for r in b]


# ── Viability board ordering ────────────────────────────────────────────────

def test_viability_board_level_then_flags_then_eps_then_ticker():
    via = build_settlement_boards(top_n=EXPECTED_PAIRS)["viability"]
    prev = None
    for r in via:
        key = (
            _VIA_ORDER.get(r["viability_level"], 3),
            r["viability_flags_count"],
            -r["accretion_dilution_pct"],
            r["acquirer_ticker"],
            r["target_ticker"],
        )
        if prev is not None:
            assert prev <= key, f"viability order broken at {r['acquirer_ticker']}->{r['target_ticker']}"
        prev = key
    # Green deals lead the board.
    assert via[0]["viability_level"] == "green"


def test_viability_board_is_deterministic():
    a = build_settlement_boards(top_n=EXPECTED_PAIRS)["viability"]
    b = build_settlement_boards(top_n=EXPECTED_PAIRS)["viability"]
    assert [(r["acquirer_ticker"], r["target_ticker"]) for r in a] == \
           [(r["acquirer_ticker"], r["target_ticker"]) for r in b]


def test_two_boards_are_independent_axes():
    """The same deck produces two orderings; the boards must not be identical
    lists (otherwise they'd be one merged ranking)."""
    boards = build_settlement_boards(top_n=EXPECTED_PAIRS)
    econ_order = [(r["acquirer_id"], r["target_id"]) for r in boards["economic"]]
    via_order = [(r["acquirer_id"], r["target_id"]) for r in boards["viability"]]
    assert econ_order != via_order


# ── Directed pairs stay distinct ────────────────────────────────────────────

def test_directed_pairs_not_merged():
    pairs = list_arena_pairs()
    keys = {(r["acquirer_id"], r["target_id"]) for r in pairs}
    assert ("aapl", "msft") in keys
    assert ("msft", "aapl") in keys
    fwd = get_arena_pair("aapl", "msft")
    rev = get_arena_pair("msft", "aapl")
    assert fwd["accretion_dilution_pct"] != rev["accretion_dilution_pct"]


# ── Tension callout is explanatory only ─────────────────────────────────────

def test_tension_only_lists_high_economic_with_risk_viability():
    boards = build_settlement_boards(top_n=EXPECTED_PAIRS)
    tension = boards["tension"]
    assert len(tension) <= 3
    econ_index = {
        (r["acquirer_id"], r["target_id"]): i
        for i, r in enumerate(boards["economic"])
    }
    for r in tension:
        # Every tension pick is yellow/red on viability ...
        assert r["viability_level"] in {"yellow", "red"}
        # ... and is drawn from the economic ranking (a real deal, in order).
        assert (r["acquirer_id"], r["target_id"]) in econ_index


# ── Determinism + cache isolation (V5.2.3 discipline) ───────────────────────

def test_repeated_build_is_identical():
    assert build_settlement_boards() == build_settlement_boards()


def test_get_settlement_boards_returns_detached_copy():
    bundle = get_settlement_boards()
    bundle["economic"].append({"acquirer_id": "HACK", "target_id": "HACK"})
    bundle["economic"][0]["accretion_dilution_pct"] = -999.0
    bundle["pair_count"] = -1
    fresh = get_settlement_boards()
    assert all(r["acquirer_id"] != "HACK" for r in fresh["economic"])
    assert fresh["economic"][0]["accretion_dilution_pct"] != -999.0
    assert fresh["pair_count"] == EXPECTED_PAIRS


def test_building_boards_does_not_mutate_pair_cache():
    before = list_arena_pairs()
    build_settlement_boards()
    after = list_arena_pairs()
    assert before == after


# ── Endpoint: additive `boards` field, backward compatible, light ───────────

def test_arena_pairs_endpoint_now_carries_boards():
    client = app.test_client()
    data = client.get("/api/modeling/ma/arena/pairs").get_json()
    assert data["status"] == "ok"
    # Existing contract still intact.
    assert data["pair_count"] == EXPECTED_PAIRS
    assert len(data["pairs"]) == EXPECTED_PAIRS
    # Additive board layer present.
    boards = data["boards"]
    assert len(boards["economic"]) == 10
    assert len(boards["viability"]) == 10
    assert boards["pair_count"] == EXPECTED_PAIRS


def test_endpoint_boards_stay_light_no_audit_or_source_meta():
    client = app.test_client()
    raw = client.get("/api/modeling/ma/arena/pairs").get_data(as_text=True)
    assert "source_meta" not in raw
    assert "ppa_amortization_modeled" not in raw
    assert "viability_context" not in raw  # internal field name must not leak


def test_endpoint_pairs_carry_board_sort_fields():
    client = app.test_client()
    pairs = client.get("/api/modeling/ma/arena/pairs").get_json()["pairs"]
    sample = pairs[0]
    for field in ("accretion_dilution_pct", "viability_level",
                  "viability_flags_count", "viability_summary"):
        assert field in sample, field


# ── Click-to-load consistency: board row == calculate full result ───────────

def test_board_row_eps_matches_calculate_full_result():
    """Clicking a board row loads that directed pair; the Arena light card and
    the Deal Ticket both read the same accretion/dilution. Prove the precomputed
    board number equals the live calculate number for representative rows."""
    client = app.test_client()
    boards = build_settlement_boards()
    rows = [boards["economic"][0], boards["viability"][0], boards["economic"][-1]]
    for row in rows:
        acq, tgt = row["acquirer_id"], row["target_id"]
        full = client.post(
            "/api/modeling/ma/calculate", json=build_pair_payload(acq, tgt)
        ).get_json()["result"]
        assert row["accretion_dilution_pct"] == full["accretion_dilution"]
        assert row["viability_level"] == full["viability_context"]["viability_level"]


# ── No regression: engine / synergy / viability / calculate contract ────────

def test_calculate_contract_unchanged_no_boards_leak():
    """The Settlement Board must not bleed into the calculate response: a single
    deal result has no `boards` / `economic` / `viability` top-level ranking."""
    client = app.test_client()
    r = client.post("/api/modeling/ma/calculate", json=build_pair_payload("aapl", "msft")).get_json()
    assert r["status"] == "ok"
    assert "boards" not in r
    assert "economic" not in r["result"]
    # The per-deal viability axis is still attached as before.
    assert r["result"]["viability_context"]["viability_level"] in {"green", "yellow", "red"}


def test_financing_cost_strict_validation_no_regression():
    payload = build_pair_payload("aapl", "msft")
    payload["deal"] = dict(payload["deal"], cash_pct=1.0, stock_pct=0.0)
    payload["deal"].pop("financing_cost", None)
    body, code = build_ma_response(payload)
    assert code == 400
    assert any(f["code"] == "FINANCING_COST_REQUIRED" for f in body["flags"])
