"""V5.6 Arena Tabletop Shell tests.

The Arena is upgraded from a selector + results page into a game-feel tabletop:
a Deal Table with Acquirer/Target drop slots, a Player Hand tray, a draggable
Company Deck, and drag-to-deal direction (A dropped on B = A acquires B). The
deterministic engine, precomputed pairs, V5.4 Deal Ticket and V5.5 Settlement
Board are all reused unchanged.

These tests assert the front-end structure (HTML/JS) and the unchanged backend
contract. The live drag / click / deep-link interactions are covered by the
browser smoke documented in the delivery report; here we lock in:

* Step 0 security fix: deck/hand/slot rendering is safe DOM (no innerHTML
  interpolation of company fields),
* drag-to-deal direction wiring (card drop => setDeal(dragged, dropTarget)),
* self-drop guard, click fallback, deep-link parsing, drop-zone slots,
* Deal Ticket + Settlement Board are still present with no Overall Score,
* engine / synergy / viability / calculate / pairs contract unchanged.
"""

from pathlib import Path

from app import app
from modeling.ma.precompute import build_pair_payload, get_arena_pair


_REPO_ROOT = Path(__file__).resolve().parents[1]
_ARENA_HTML = _REPO_ROOT / "static" / "modeling" / "arena.html"
_ARENA_JS = _REPO_ROOT / "static" / "modeling" / "js" / "arena.js"


def _html():
    return _ARENA_HTML.read_text(encoding="utf-8")


def _js():
    return _ARENA_JS.read_text(encoding="utf-8")


# ── Page still serves ───────────────────────────────────────────────────────

def test_arena_page_still_serves():
    client = app.test_client()
    resp = client.get("/modeling/ma/arena")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Deal Arena" in html
    assert "/static/modeling/js/arena.js" in html
    assert "source_meta" not in html


# ── Step 0: renderDeck() innerHTML security fix ─────────────────────────────

def test_deck_render_uses_safe_dom_not_innerhtml_interpolation():
    js = _js()
    # The old interpolated innerHTML deck render must be gone (the offending
    # V5.5-era pattern was `card.innerHTML = ...${c.ticker}...`).
    assert "card.innerHTML =" not in js
    assert '<span class="co-chip">${' not in js
    # Replaced by a shared safe builder using element + textContent.
    assert "function buildCompanyCard(" in js
    assert "function el(tag, cls, text)" in js
    assert "node.textContent = text" in js
    # renderDeck assembles nodes, it does not interpolate strings.
    assert "grid.appendChild(buildCompanyCard(c" in js
    # The dynamic ticker/name only ever reach the DOM via textContent or a
    # safe setAttribute (aria-label), never via innerHTML.
    assert "el(\"div\", \"co-ticker\", c.ticker)" in js


def test_no_dynamic_innerhtml_interpolation_anywhere():
    """Every remaining innerHTML use must be a constant clear (= "" ), never a
    template interpolation of dynamic text."""
    import re
    js = _js()
    # Find innerHTML assignments and ensure none interpolate a ${...} or concat.
    for m in re.finditer(r"\.innerHTML\s*=\s*(.+)", js):
        rhs = m.group(1).strip()
        assert rhs.startswith('""') or rhs.startswith("''"), rhs


# ── Deal Table + drop slots + Player Hand structure ─────────────────────────

def test_deal_table_and_slots_present():
    html = _html()
    assert "并购牌桌" in html and "Deal Table" in html
    assert 'id="slot-acq"' in html and 'data-role="acq"' in html
    assert 'id="slot-tgt"' in html and 'data-role="tgt"' in html
    assert 'id="slot-acq-body"' in html and 'id="slot-tgt-body"' in html
    assert 'id="reverse-btn"' in html
    assert 'id="clear-btn"' in html


def test_player_hand_present():
    html = _html()
    assert "玩家手牌" in html and "Player Hand" in html
    assert 'id="hand-tray"' in html
    assert 'id="hand-rotate"' in html


def test_company_deck_binder_present():
    html = _html()
    assert "公司牌堆" in html or "Company Deck" in html
    assert 'id="deck-grid"' in html


def test_company_deck_has_collapse_and_scroll_affordance():
    # V5.9.1.1 War Room scalability: the deck must not flood the page. It lives in
    # a scroll container that is collapsed by default with a toggle to expand.
    html = _html()
    js = _js()
    assert 'id="deck-scroll"' in html
    assert 'id="deck-toggle"' in html
    assert 'class="deck-scroll collapsed"' in html
    # The card grid still exists inside the scroll container.
    assert 'id="deck-grid"' in html
    # Both states are capped (page never stretches) and the toggle is wired safely.
    assert ".deck-scroll.collapsed" in html
    assert ".deck-scroll.expanded" in html
    assert "max-height" in html
    assert "function toggleDeckExpanded(" in js
    assert 'getElementById' in js or "$(\"deck-toggle\")" in js
    assert "classList.toggle" in js


# ── Drag-to-deal direction wiring ───────────────────────────────────────────

def test_cards_are_draggable_and_have_drag_handlers():
    js = _js()
    assert 'setAttribute("draggable", "true")' in js
    assert "function attachDragSource(" in js
    assert "function attachCardDropZone(" in js
    assert "function attachSlotDropZone(" in js
    assert '"dragstart"' in js and '"dragover"' in js and '"drop"' in js


def test_drag_direction_dragged_onto_card_is_acquirer():
    """Dropping dragged card A onto card B must mean A -> B (A acquires B):
    setDeal(acqId=draggedId, tgtId=dropTargetId)."""
    js = _js()
    assert "setDeal(acqId, id); // dragged A onto card B => A acquires B" in js
    # Slot drops set only that slot's role, keeping the other side.
    assert "if (side === \"acq\") setDeal(id, selected.tgt);" in js
    assert "else setDeal(selected.acq, id);" in js


def test_self_drop_is_rejected_without_error():
    js = _js()
    # Card-on-itself and self-deal in setDeal both no-op with a light hint.
    assert "if (acqId === id) { flashHint(" in js
    assert "if (a && t && a === t) { flashHint(" in js


def test_drag_id_is_validated_against_deck():
    """dataTransfer / DOM content is never trusted: the dragged id is resolved
    through companyById before it can change selection."""
    js = _js()
    assert "function getDragId(" in js
    assert "return companyById(id) ? id : null;" in js


# ── Click fallback + deep link ──────────────────────────────────────────────

def test_click_fallback_still_selects():
    js = _js()
    assert "function onCardClick(" in js
    # Cards wire a click (and keyboard) path to onCardClick.
    assert 'card.addEventListener("click", () => onCardClick(c.id));' in js
    assert 'e.key === "Enter"' in js  # keyboard fallback


def test_deep_link_seats_deal_on_table():
    js = _js()
    assert "function deepLinkInit(" in js
    assert 'params.get("acq")' in js and 'params.get("tgt")' in js
    # Deep-link ids are validated against the deck before use.
    assert "companyById(acq) ? acq : null" in js


def test_deep_link_route_serves_with_params():
    client = app.test_client()
    resp = client.get("/modeling/ma/arena?acq=aapl&tgt=msft")
    assert resp.status_code == 200
    assert "/static/modeling/js/arena.js" in resp.get_data(as_text=True)


# ── V5.4 Ticket + V5.5 Settlement Board still present, no Overall Score ──────

def test_deal_ticket_preserved():
    html = _html()
    assert 'id="rc-ticket-btn"' in html
    assert 'id="ticket-overlay"' in html
    assert "查看推演票据" in html


def test_settlement_board_preserved():
    html = _html()
    assert 'id="settlement-card"' in html
    assert "结算榜" in html
    assert 'id="sb-board-econ"' in html and 'id="sb-board-via"' in html


def test_no_overall_score_anywhere_in_shell():
    html = _html()
    for banned in ("综合评分", "Overall Score", "胜率", "win_rate", "overall_score"):
        assert banned not in html, banned


# ── Board row load + Ticket consistency (data level) ────────────────────────

def test_board_pick_matches_calculate_for_acceptance_pairs():
    """A board row / drag / deep link all funnel through setDeal -> the SAME
    precomputed pair, which equals the live calculate full result. Verify the
    number is identical so the table, light card and ticket cannot diverge."""
    client = app.test_client()
    for acq, tgt in [("aapl", "msft"), ("msft", "aapl"), ("nvda", "avgo"), ("dis", "hd")]:
        light = get_arena_pair(acq, tgt)
        full = client.post(
            "/api/modeling/ma/calculate", json=build_pair_payload(acq, tgt)
        ).get_json()["result"]
        assert light["accretion_dilution_pct"] == full["accretion_dilution"]


# ── Backend contract unchanged ──────────────────────────────────────────────

def test_calculate_contract_unchanged():
    client = app.test_client()
    r = client.post("/api/modeling/ma/calculate", json=build_pair_payload("aapl", "msft")).get_json()
    assert r["status"] == "ok"
    assert "boards" not in r
    res = r["result"]
    assert "accretion_dilution" in res
    assert res["viability_context"]["viability_level"] in {"green", "yellow", "red"}


def test_arena_pairs_endpoint_unchanged_core_meaning():
    client = app.test_client()
    data = client.get("/api/modeling/ma/arena/pairs").get_json()
    assert data["status"] == "ok"
    assert data["pair_count"] == 9900
    assert len(data["pairs"]) == 9900
    assert "boards" in data  # V5.5 additive field still present


# ── V5.11.2.1 War Room Company Deck filter / sort + count copy ───────────────
# The deck grew to 100 cards (V5.11.2). The Company Deck header used to hardcode
# "45 家"; it now binds to the live deck count, and the binder gains a light
# front-end filter/sort. These checks lock the copy fix + the controls without
# touching deck data, the pairs payload, Match Points, the robot or Settlement.


def test_company_deck_count_copy_is_not_hardcoded_45():
    html = _html()
    # The stale literal "45 家" copy must be gone from the deck title.
    assert "45 家" not in html
    # The count is a dynamic slot, not a baked-in number.
    assert 'id="deck-count"' in html


def test_company_deck_count_binds_to_live_deck_length():
    # The count slot is populated from CARDS.length, so a future deck resize
    # updates the header automatically (no second hardcoded number to forget).
    js = _js()
    assert 'deck-count' in js
    assert 'String(CARDS.length)' in js


def test_company_deck_count_reflects_the_100_card_deck():
    # The live deck the count reads from currently has 100 companies (V5.11.2).
    client = app.test_client()
    data = client.get("/api/modeling/ma/samples").get_json()
    assert data["status"] == "ok"
    assert len(data["companies"]) == 100


def test_tier_filter_control_present_with_all_five_tiers():
    html = _html()
    assert 'id="deck-filter-tier"' in html
    for label in ("Legendary", "Elite", "Core", "Specialist", "Basic"):
        assert label in html
    # "All" is the no-filter option.
    assert 'value="all"' in html


def test_sector_filter_control_present_and_built_from_live_deck():
    html = _html()
    js = _js()
    assert 'id="deck-filter-sector"' in html
    # Sector options are generated from the loaded cards, never hardcoded.
    assert "function populateDeckFilters(" in js
    assert "cnSector(c)" in js


def test_sort_control_has_market_cap_tier_and_name_options():
    html = _html()
    assert 'id="deck-sort"' in html
    assert 'value="cap"' in html
    assert 'value="tier"' in html
    assert 'value="name"' in html
    # Default keeps the deck's designed order.
    assert 'value="default"' in html
    assert 'id="deck-sort-dir"' in html


def test_filter_sort_only_change_the_view_not_the_underlying_deck():
    js = _js()
    # The view is a derived array; CARDS is filtered/sliced, never mutated.
    assert "function visibleDeckCards(" in js
    assert "CARDS.filter(" in js
    assert ".slice().sort(" in js
    # Tier order for the Tier sort: gold > red > blue > green > white.
    assert "TIER_RANK" in js
    assert '"all"' in js  # All == no filter


def test_deck_controls_use_safe_dom_not_innerhtml():
    js = _js()
    # The dynamic sector options are appended as elements with textContent, never
    # via innerHTML string interpolation of a sector label.
    assert 'el("option"' in js
    # No new innerHTML interpolation slipped in with the controls.
    import re
    for m in re.finditer(r"\.innerHTML\s*=\s*(.+)", js):
        rhs = m.group(1).strip()
        assert rhs.startswith('""') or rhs.startswith("''"), rhs


def test_deck_shown_count_and_empty_state_present():
    html = _html()
    js = _js()
    assert 'id="deck-shown-count"' in html
    assert 'id="deck-empty"' in html
    # Safe empty-state copy (no internal paths / stack traces).
    assert "没有符合条件的公司牌" in html
    # The shown count is rendered as "显示 N / M 张".
    assert "显示 ${visible.length} / ${CARDS.length} 张" in js


def test_deck_controls_do_not_break_selection_or_collapse():
    js = _js()
    # renderDeck still re-applies selection after rebuilding the binder, so a
    # filter/sort never desyncs the selected buyer/target highlight.
    assert "refreshSelectionUI();" in js
    # Collapse/expand is untouched.
    assert "function toggleDeckExpanded(" in js
