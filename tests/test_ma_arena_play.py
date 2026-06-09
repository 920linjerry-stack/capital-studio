"""V5.6.1 Deal Arena · Tabletop (formal play view) tests.

The War Room (/modeling/ma/arena) is kept as the high-density prep area and a
new immersive play table is added at /modeling/ma/arena/play. The play page is a
pure static shell that reuses the SAME deck / precomputed pairs / calculate path
/ Deal Ticket as the War Room — it re-implements no economics and adds no
Overall Score, bots, or backend state.

These tests lock in:
* the new route serves and the War Room links into it (with query handoff),
* play-page deep link + drag-to-deal direction + self-drop guard + click
  fallback + deterministic draw/hand are wired,
* the play page reuses /api/modeling/ma/calculate (no second engine),
* light / ticket / calculate EPS agree, dual axis preserved, no Overall Score,
* safe DOM rendering (no innerHTML interpolation),
* engine / synergy / viability / calculate / pairs contract unchanged.
"""

from pathlib import Path

from app import app
from modeling.ma.precompute import build_pair_payload, get_arena_pair


_ROOT = Path(__file__).resolve().parents[1]
_WARROOM_HTML = _ROOT / "static" / "modeling" / "arena.html"
_WARROOM_JS = _ROOT / "static" / "modeling" / "js" / "arena.js"
_PLAY_HTML = _ROOT / "static" / "modeling" / "arena_play.html"
_PLAY_JS = _ROOT / "static" / "modeling" / "js" / "arena_play.js"


def _r(p):
    return p.read_text(encoding="utf-8")


# ── Routes ──────────────────────────────────────────────────────────────────

def test_play_route_serves():
    client = app.test_client()
    resp = client.get("/modeling/ma/arena/play")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Deal Arena" in html and "Tabletop" in html
    assert "/static/modeling/js/arena_play.js" in html


def test_play_deep_link_route_serves_with_params():
    client = app.test_client()
    resp = client.get("/modeling/ma/arena/play?acq=meta&tgt=googl")
    assert resp.status_code == 200
    assert "/static/modeling/js/arena_play.js" in resp.get_data(as_text=True)


def test_warroom_still_serves_and_is_renamed():
    client = app.test_client()
    html = client.get("/modeling/ma/arena").get_data(as_text=True)
    assert html  # served
    war = _r(_WARROOM_HTML)
    assert "War Room" in war or "备战区" in war


# ── War Room -> Play entry + query handoff ──────────────────────────────────

def test_warroom_has_start_tabletop_entry():
    war = _r(_WARROOM_HTML)
    assert 'id="start-tabletop-btn"' in war
    assert "/modeling/ma/arena/play" in war
    assert "Start Tabletop" in war


def test_warroom_hands_off_selection_via_query():
    js = _r(_WARROOM_JS)
    assert "start-tabletop-btn" in js
    assert "/modeling/ma/arena/play" in js
    # The handoff appends acq/tgt from the current selection.
    assert "acq=${encodeURIComponent(selected.acq)}" in js
    assert "tgt=${encodeURIComponent(selected.tgt)}" in js


# ── Play page back-links + Ticket reuse ─────────────────────────────────────

def test_play_links_back_to_warroom_and_studio():
    html = _r(_PLAY_HTML)
    assert "/modeling/ma/arena" in html  # back to War Room
    assert "War Room" in html
    assert "/modeling/ma/arena#settlement-card" in html  # full board jump
    assert "/modeling/ma" in html  # Deal Studio


def test_play_reuses_deal_ticket_markup():
    html = _r(_PLAY_HTML)
    assert 'id="ticket-overlay"' in html
    assert 'id="rc-ticket-btn"' in html
    assert 'id="tk-econ-grid"' in html and 'id="tk-via-flags"' in html


# ── Immersive elements present ──────────────────────────────────────────────

def test_play_has_table_drawpile_hand_opponents_skyline():
    html = _r(_PLAY_HTML)
    assert 'class="felt"' in html              # central table
    assert 'id="draw-pile"' in html            # draw pile
    assert 'id="hand-fan"' in html             # player hand
    assert "VP Seat" in html and "MD Seat" in html  # opponent seats (visual)
    assert 'class="skyline"' in html           # Wall Street skyline
    assert 'id="slot-acq"' in html and 'id="slot-tgt"' in html


def test_play_has_clear_deal_button():
    """V5.7.2: visible Clear Deal control on the play table."""
    html = _r(_PLAY_HTML)
    js = _r(_PLAY_JS)
    assert 'id="clear-deal-btn"' in html
    assert "清空交易 · Clear Deal" in html
    assert "clear-deal-btn" in js
    assert "function clearSelection(" in js
    assert 'clearBtn.disabled = !(selected.acq || selected.tgt)' in js


def test_play_ticket_viability_user_friendly_not_raw_rule_id():
    """V5.7.2: Ticket viability flags use product copy; raw rule_id/tags live in audit."""
    js = _r(_PLAY_JS)
    assert "formatViaCategory(" in js
    assert "formatViaSeverity(" in js
    assert "Audit / Debug details" in js
    assert "tk-flag-audit" in js
    # Primary ticket render must not expose the old engineering meta line.
    assert "tk-flag-meta" not in js
    assert '`rule: ${f.rule_id' not in js


# ── Drag-to-deal direction + guards (play JS) ───────────────────────────────

def test_play_drag_direction_a_onto_b():
    js = _r(_PLAY_JS)
    assert "setDeal(acqId, id); // dragged A onto card B => A acquires B" in js
    assert 'if (side === "acq") setDeal(id, selected.tgt);' in js
    assert "else setDeal(selected.acq, id);" in js


def test_play_self_drop_rejected():
    js = _r(_PLAY_JS)
    assert "if (acqId === id) { flashHint(" in js
    assert "if (a && t && a === t) { flashHint(" in js


def test_play_click_fallback_and_deep_link():
    js = _r(_PLAY_JS)
    assert "function onCardClick(" in js
    assert 'card.addEventListener("click", () => onCardClick(c.id));' in js
    assert "function deepLinkInit(" in js
    assert 'params.get("acq")' in js and 'params.get("tgt")' in js
    assert "companyById(acq) ? acq : null" in js


def test_play_drag_id_validated_against_deck():
    js = _r(_PLAY_JS)
    assert "function getDragId(" in js
    assert "return companyById(id) ? id : null;" in js


def test_play_hand_card_uses_stable_hover_wrapper():
    """V5.6.4: each hand card is built inside a stable `.pcard-shell` hitbox; the
    hover lift is driven by the shell (`.pcard-shell:hover .pcard`), not by the
    card changing its own transform on `:hover`. Lifting the inner card never
    moves the shell's box, so the cursor can't bounce in/out at the bottom edge
    (fixes the bottom-edge hover jitter). Guard against regressing to the old
    pattern where the hover element itself changed its hitbox."""
    js = _r(_PLAY_JS)
    html = _r(_PLAY_HTML)
    assert '"pcard-shell"' in js                  # JS wraps each card in the shell
    assert ".pcard-shell:hover .pcard" in html    # hover lift comes from the shell
    assert ".pcard:hover" not in html             # the card never transforms its own hitbox


def test_play_desktop_hand_controls_clear_floating_hud():
    """Desktop hand controls reserve the same right column as the HUD."""
    html = _r(_PLAY_HTML)
    assert "@media (min-width: 1120px)" in html
    assert ".hand-rail-head { padding-right: 360px; }" in html


def test_play_hand_area_visual_lift_does_not_move_table_scene():
    """V5.7.2.1: hand-only translateY lift; table-scene / hand-rail flex footprint unchanged."""
    html = _r(_PLAY_HTML)
    assert "justify-content: center" in html
    assert "justify-content: flex-end" not in html
    assert "padding: 0 22px 64px" in html
    assert "margin-top: -" not in html
    assert "transform: translateY(-22px)" in html
    assert ".pcard-shell:hover .pcard" in html


# ── Deterministic hand / draw (no randomness, no backend) ───────────────────

def test_play_draw_and_hand_are_deterministic():
    js = _r(_PLAY_JS)
    assert "Math.random" not in js           # no randomness
    assert "function drawHand(" in js
    assert "function drawOne(" in js and "function rotateHand(" in js
    assert "handOffset" in js                # deterministic window cursor


def test_play_does_not_batch_calculate():
    """Lookup-first: the light result uses PAIRS_INDEX; calculate is only the
    single-deal fallback / ticket path, never a 182-pair loop."""
    js = _r(_PLAY_JS)
    assert "PAIRS_INDEX[pairKey(" in js
    # The only actual fetch() calls to calculate are the single-deal fallback
    # and the ticket — exactly two (comments mentioning the path don't count).
    assert js.count("${API}/api/modeling/ma/calculate") == 2


# ── Safe DOM rendering ──────────────────────────────────────────────────────

def test_play_uses_safe_dom_no_innerhtml_interpolation():
    import re
    js = _r(_PLAY_JS)
    assert "function el(tag, cls, text)" in js
    assert "node.textContent = text" in js
    for m in re.finditer(r"\.innerHTML\s*=\s*(.+)", js):
        rhs = m.group(1).strip()
        assert rhs.startswith('""') or rhs.startswith("''"), rhs


# ── No Overall Score; dual axis preserved ───────────────────────────────────

def test_play_has_no_overall_score():
    html = _r(_PLAY_HTML)
    for banned in ("综合评分", "Overall Score", "胜率", "win_rate", "overall_score"):
        assert banned not in html, banned


def test_play_keeps_economic_and_viability_dual_axis():
    html = _r(_PLAY_HTML)
    # Light result: separate economic chips + viability chips.
    assert 'id="rc-chips"' in html and 'id="rc-viability-chips"' in html
    # Mini board: separate Economic / Viability tabs.
    assert 'id="pb-board-econ"' in html and 'id="pb-board-via"' in html
    assert "经济性" in html and "现实可行性" in html


# ── EPS consistency (data level) ────────────────────────────────────────────

def test_play_light_matches_calculate_for_acceptance_pairs():
    """Play light result (PAIRS_INDEX lookup) and the ticket (calculate) both
    resolve to the same precomputed pair == calculate full result."""
    client = app.test_client()
    for acq, tgt in [("meta", "googl"), ("googl", "meta"), ("aapl", "msft"), ("nvda", "avgo")]:
        light = get_arena_pair(acq, tgt)
        full = client.post(
            "/api/modeling/ma/calculate", json=build_pair_payload(acq, tgt)
        ).get_json()["result"]
        assert light["accretion_dilution_pct"] == full["accretion_dilution"]


def test_play_ticket_uses_same_calculate_path():
    js = _r(_PLAY_JS)
    assert "function openTicket(" in js
    assert "buildPayload()" in js
    # Ticket never re-derives EPS; it formats the server result.
    assert "accretion_dilution =" not in js


# ── Backend contract unchanged ──────────────────────────────────────────────

def test_calculate_and_pairs_contract_unchanged():
    client = app.test_client()
    r = client.post("/api/modeling/ma/calculate", json=build_pair_payload("aapl", "msft")).get_json()
    assert r["status"] == "ok" and "boards" not in r
    pairs = client.get("/api/modeling/ma/arena/pairs").get_json()
    assert pairs["pair_count"] == 9900 and "boards" in pairs
