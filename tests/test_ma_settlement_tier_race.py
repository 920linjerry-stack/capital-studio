"""V5.7.0.1 · War Room Settlement Board tier-pip load-race fix.

The Settlement Board tier pips need TWO independent loads to finish: the deck
(`/api/modeling/ma/samples`, which carries `arena_tier`) and the board rows
(`/api/modeling/ma/arena/pairs`, kept deliberately tier-free). In `init()` the
two fetches race. The bug: `loadPairs()` rendered the board immediately, so if
pairs won the race the deck was still empty, `companyById()` returned null, and
no `tier-pip` was emitted — with no later re-render, the pips were lost for the
whole session.

The fix is a deterministic ready gate (`renderSettlementWhenReady`) called by
BOTH loaders: the tier-dependent render is held until the deck is present, and
fires regardless of which load finished first. No timers, no payload change —
`/arena/pairs` stays light, `/calculate` stays tier-free.

These tests assert the gate's source invariants (the suite has no JS runtime)
and mirror the gate's branch logic to prove cards-first and pairs-first both
converge on a single tier-aware render, while a genuine pairs failure still
shows its empty state promptly.
"""

import re
from pathlib import Path

from app import app
from modeling.ma.company_cards import ARENA_TIER_VALUES


_ROOT = Path(__file__).resolve().parents[1]
_WARROOM_JS = _ROOT / "static" / "modeling" / "js" / "arena.js"


def _read(path):
    return path.read_text(encoding="utf-8")


def _func_body(src, name):
    """Return the brace-balanced body of `function <name>(...) { ... }`."""
    start = src.index(f"function {name}(")
    i = src.index("{", start)
    depth, j = 0, i
    while j < len(src):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i : j + 1]
        j += 1
    raise AssertionError(f"unbalanced body for {name}")


# ── Source structure: the race gate exists and is the only render path ───────

def test_loaders_set_flags_and_route_through_the_ready_gate():
    js = _read(_WARROOM_JS)
    cards = _func_body(js, "loadCards")
    pairs = _func_body(js, "loadPairs")

    # Each loader marks itself loaded, then defers to the gate (never the bare
    # renderSettlement) so a single finished load can't render tier-less rows.
    assert "cardsLoaded = true" in cards
    assert "renderSettlementWhenReady()" in cards
    assert "renderSettlement(" not in cards

    assert "pairsLoaded = true" in pairs
    assert "renderSettlementWhenReady()" in pairs
    assert "renderSettlement(" not in pairs


def test_ready_gate_holds_tier_render_until_deck_present():
    js = _read(_WARROOM_JS)
    gate = _func_body(js, "renderSettlementWhenReady")
    # Wait until the board outcome is known ...
    assert re.search(r"if\s*\(\s*!pairsLoaded\s*\)\s*return", gate)
    # ... and, when there ARE rows to draw, until the deck (tier source) loaded.
    assert re.search(r"if\s*\(\s*BOARDS\s*&&\s*!cardsLoaded\s*\)\s*return", gate)
    assert "renderSettlement()" in gate


def test_renderSettlement_is_only_reached_through_the_gate():
    js = _read(_WARROOM_JS)
    # The only direct CALL to renderSettlement(); — `renderSettlement();` with a
    # trailing semicolon — is inside the gate (the `function renderSettlement()`
    # definition has a brace, not a semicolon, so it is excluded).
    callers = [
        m.start()
        for m in re.finditer(r"\brenderSettlement\(\);", js)
    ]
    assert callers, "expected at least one renderSettlement() call site"
    gate = _func_body(js, "renderSettlementWhenReady")
    gate_start = js.index(gate)
    gate_end = gate_start + len(gate)
    for pos in callers:
        assert gate_start <= pos < gate_end, "renderSettlement() called outside the ready gate"


def test_board_row_still_emits_tier_pip_from_the_deck():
    js = _read(_WARROOM_JS)
    row = _func_body(js, "buildBoardRow")
    # Tier pips are still driven by the deck lookup (the thing the race starved).
    assert "companyById(p.acquirer_id)" in row
    assert "companyById(p.target_id)" in row
    assert "tier-pip arena-tier tier-" in row


# ── Mirror of the gate's branch logic across both load orders ────────────────
#
# A faithful translation of renderSettlementWhenReady's early-returns. We do NOT
# re-implement rendering — we only model "did a tier-aware render fire, and was
# the deck present when it did?" to prove convergence under both orderings.

def _simulate(order, pairs_ok=True):
    state = {"cardsLoaded": False, "pairsLoaded": False, "BOARDS": None}
    renders = []  # (cards_present, has_boards) at each fire of renderSettlement

    def gate():
        if not state["pairsLoaded"]:
            return
        if state["BOARDS"] and not state["cardsLoaded"]:
            return
        renders.append((state["cardsLoaded"], bool(state["BOARDS"])))

    def finish_cards():
        state["cardsLoaded"] = True
        gate()

    def finish_pairs():
        state["BOARDS"] = {"economic": [1]} if pairs_ok else None
        state["pairsLoaded"] = True
        gate()

    for step in order:
        (finish_cards if step == "cards" else finish_pairs)()
    return renders


def test_cards_first_ends_with_a_tier_aware_render():
    renders = _simulate(["cards", "pairs"])
    assert renders, "no render fired"
    # The render with boards happened only after the deck was present.
    assert renders[-1] == (True, True)


def test_pairs_first_ends_with_a_tier_aware_render():
    renders = _simulate(["pairs", "cards"])
    assert renders, "no render fired"
    # Pairs-first must NOT render tier-less rows while the deck is empty.
    assert all(cards_present for cards_present, has_boards in renders if has_boards)
    assert renders[-1] == (True, True)


def test_pairs_failure_shows_empty_state_without_waiting_on_deck():
    # BOARDS null (pairs failed) -> the empty message needs no deck, render now.
    pairs_first = _simulate(["pairs", "cards"], pairs_ok=False)
    cards_first = _simulate(["cards", "pairs"], pairs_ok=False)
    assert pairs_first and pairs_first[0] == (False, False)  # rendered before deck
    assert cards_first and cards_first[-1] == (True, False)


# ── Guardrails: the race fix changed no payload, no engine, no tier policy ────

def test_calculate_and_pairs_payloads_stay_tier_free():
    client = app.test_client()
    calc = client.post(
        "/api/modeling/ma/calculate",
        json={
            "acquirer": {"sample_id": "aapl"},
            "target": {"sample_id": "msft"},
            "deal": {
                "deal_type": "full_acquisition",
                "premium": 0.30,
                "cash_pct": 0.5,
                "stock_pct": 0.5,
                "financing_cost": 0.05,
                "tax_rate": 0.25,
                "synergy_mode": "default",
            },
            "currency": "USD",
        },
    ).get_json()
    assert calc["status"] == "ok"
    assert "arena_tier" not in str(calc)

    pairs = client.get("/api/modeling/ma/arena/pairs").get_data(as_text=True)
    assert "arena_tier" not in pairs  # board rows resolve tier from the deck only


def test_deck_carries_every_tier_so_pips_can_resolve():
    client = app.test_client()
    cards = client.get("/api/modeling/ma/samples").get_json()["companies"]
    assert all(c["arena_tier"] in ARENA_TIER_VALUES for c in cards)


def test_settlement_path_uses_safe_dom_no_dynamic_innerhtml():
    js = _read(_WARROOM_JS)
    row = _func_body(js, "buildBoardRow")
    # No string-interpolated innerHTML carrying ticker/tier in the board rows.
    assert ".innerHTML" not in row
    assert "createTextNode(p.acquirer_ticker" in row
    assert "createTextNode(p.target_ticker" in row
