"""V5.9.3 Game Rule Hardening tests.

This wave turns the Deal Arena Match from an "infinite try-anything sandbox" into
a game with three basic fair-play rules, WITHOUT touching the finance model:

  1. The formal entry is `Start Match`; the old `Start Tabletop` sandbox is
     demoted to a weak dev/sandbox link (the /arena/play page is kept).
  2. Draw is a per-round resource (max 1/round, reset each round); Reshuffle is a
     whole-match resource (max 2 across the five rounds). Play Again resets both;
     Clear Deal resets neither.
  3. A deal can only be PLAYED when both companies are in the current player hand.
     A Queue deal whose companies are not all in hand can still be loaded for
     preview / Deal Ticket / review, but Play Deal stays disabled. Robots are not
     constrained by the player's hand.

Following the repo convention, the deterministic game-rule layer lives in JS and
the contract is locked via source/static assertions plus backend data checks; the
live turn-by-turn behaviour is covered by the documented browser smoke. The
financial engine (A/D, synergy, viability, calculate, pairs, deck, Card Tier,
precompute, Robot base strategy, Match Points formula) is asserted UNCHANGED.
"""

import re
from pathlib import Path

from app import app
from modeling.ma.precompute import build_pair_payload, get_arena_pair, list_arena_pairs


_ROOT = Path(__file__).resolve().parents[1]
_WARROOM_HTML = _ROOT / "static" / "modeling" / "arena.html"
_WARROOM_JS = _ROOT / "static" / "modeling" / "js" / "arena.js"
_MATCH_HTML = _ROOT / "static" / "modeling" / "arena_match.html"
_MATCH_JS = _ROOT / "static" / "modeling" / "js" / "arena_match.js"
_ENGINE_JS = _ROOT / "static" / "modeling" / "js" / "match_engine.js"
_ROBOT_JS = _ROOT / "static" / "modeling" / "js" / "robot_opponent.js"
_PLAY_HTML = _ROOT / "static" / "modeling" / "arena_play.html"


def _r(p):
    return p.read_text(encoding="utf-8")


def _func_body(js, start_marker, end_marker):
    """Return the source slice between two markers (a single function body)."""
    a = js.index(start_marker)
    b = js.index(end_marker, a + len(start_marker))
    return js[a:b]


# ── A. Old Start Tabletop demoted; Start Match is the only primary entry ─────

def test_warroom_primary_entry_is_start_match():
    html = _r(_WARROOM_HTML)
    # Start Match is the primary CTA (its own dedicated CTA class + id).
    assert 'class="start-match-btn" id="start-match-btn"' in html
    assert "/modeling/ma/arena/match/setup" in html
    assert "Start Match" in html
    # The header no longer co-seats the old prominent Start Tabletop CTA.
    assert "进入正式牌桌" not in html
    assert 'class="start-tabletop-btn"' not in html  # the old prominent style is gone


def test_warroom_start_tabletop_demoted_to_sandbox_link_but_kept():
    html = _r(_WARROOM_HTML)
    # The sandbox page is preserved: same id + route + the literal "Start Tabletop"
    # label, but now a weak demoted sandbox link, not a co-equal primary button.
    assert 'class="sandbox-link" id="start-tabletop-btn"' in html
    assert "/modeling/ma/arena/play" in html
    assert "Start Tabletop" in html
    assert "Sandbox" in html
    # The demoted link is NOT the primary CTA class.
    assert 'class="start-match-btn" id="start-tabletop-btn"' not in html
    # The copy now directs players to Start Match for the formal game.
    assert "正式游戏" in html


def test_warroom_js_handoff_still_wires_both_entries():
    js = _r(_WARROOM_JS)
    # The selection handoff still targets both the (demoted) sandbox link and the
    # Start Match entry — neither id was renamed/removed by the demotion.
    assert "start-tabletop-btn" in js and "/modeling/ma/arena/play" in js
    assert "start-match-btn" in js and "/modeling/ma/arena/match/setup" in js


def test_sandbox_play_route_not_regressed():
    client = app.test_client()
    resp = client.get("/modeling/ma/arena/play")
    assert resp.status_code == 200
    assert "/static/modeling/js/arena_play.js" in resp.get_data(as_text=True)
    # Deep-link form still serves too.
    resp2 = client.get("/modeling/ma/arena/play?acq=meta&tgt=googl")
    assert resp2.status_code == 200


# ── B. Draw (per round) / Reshuffle (per match) resource counters ────────────

def test_engine_defines_draw_and_reshuffle_allowances():
    js = _r(_ENGINE_JS)
    assert "const DRAW_PER_ROUND = 1;" in js
    assert "const RESHUFFLE_PER_MATCH = 2;" in js
    # A fresh match seeds both counters.
    assert "draw_allowance: DRAW_PER_ROUND" in js
    assert "reshuffle_allowance: RESHUFFLE_PER_MATCH" in js
    # Spend/check helpers exist and are exported for the controller.
    for fn in ("function canDraw(state)", "function useDraw(state)",
               "function canReshuffle(state)", "function useReshuffle(state)",
               "function drawRemaining(state)", "function reshuffleRemaining(state)"):
        assert fn in js, fn
    for ex in ("DRAW_PER_ROUND,", "RESHUFFLE_PER_MATCH,", "useDraw,", "useReshuffle,",
               "drawRemaining,", "reshuffleRemaining,"):
        assert ex in js, ex


def test_engine_next_round_resets_draw_not_reshuffle():
    js = _r(_ENGINE_JS)
    body = _func_body(js, "function nextRound(state)", "function rankings(state)")
    # A new round restores the per-round Draw allowance...
    assert "state.draw_allowance = DRAW_PER_ROUND;" in body
    # ...but never the match-wide Reshuffle allowance.
    assert "reshuffle_allowance" not in body


def test_match_draw_limited_per_round():
    js = _r(_MATCH_JS)
    body = _func_body(js, "function drawOne()", "function rotateHand()")
    # drawOne consumes one Draw via the engine and bails (with a hint) when spent.
    assert "window.MatchEngine.useDraw(MATCH)" in body
    assert "本回合的抽牌次数已用完" in body


def test_match_reshuffle_limited_per_match():
    js = _r(_MATCH_JS)
    body = _func_body(js, "function rotateHand()", "function updateResourceButtons(")
    assert "window.MatchEngine.useReshuffle(MATCH)" in body
    assert "本局的换牌次数已用完" in body


def test_match_resource_buttons_show_remaining_counts():
    js = _r(_MATCH_JS)
    assert "function updateResourceButtons(" in js
    # Draw button shows the per-round count; Reshuffle shows match-wide remaining.
    assert "Draw (${drawLeft}/${window.MatchEngine.DRAW_PER_ROUND})" in js
    assert "Reshuffle (${reshLeft} left)" in js
    # Both disable when their allowance is exhausted.
    assert "drawBtn.disabled = drawLeft <= 0;" in js
    assert "reshBtn.disabled = reshLeft <= 0;" in js
    # The HTML wires disabled styling for the hand buttons + draw pile.
    html = _r(_MATCH_HTML)
    assert ".pbtn:disabled" in html
    assert ".pile-stack.depleted" in html


def test_match_resources_refresh_on_round_and_play_again_not_clear():
    js = _r(_MATCH_JS)
    # New round + new match refresh the resource UI.
    next_round = _func_body(js, "function nextRound(", "function showEndScreen(")
    assert "updateResourceButtons()" in next_round
    play_again = _func_body(js, "function playAgain(", "function syncMatchView(")
    assert "updateResourceButtons()" in play_again
    # Play Again recreates the match (which reseeds both allowances). V5.9.6.2:
    # via startNewMatch (fresh game seed + clean table).
    assert "MATCH = startNewMatch(MATCH_CONFIG)" in play_again
    # Clear Deal (clearSelection) NEVER touches the allowances or recreates MATCH.
    clear = _func_body(js, "function clearSelection(", "function renderSlot(")
    assert "draw_allowance" not in clear
    assert "reshuffle_allowance" not in clear
    assert "createMatch" not in clear and "startNewMatch" not in clear
    assert "useDraw" not in clear and "useReshuffle" not in clear


# ── C. Queue hand-validity: a deal must come from the current hand to be played

def test_engine_is_hand_agnostic_player_hand_is_a_controller_rule():
    """The pure engine knows nothing about the player's hand — the hand-validity
    rule is enforced in the controller. This also proves robots (which select via
    the engine + RobotOpponent over ALL pairs) are NOT constrained by the hand."""
    assert "handHas" not in _r(_ENGINE_JS)
    assert "HAND" not in _r(_ENGINE_JS)
    assert "handHas" not in _r(_ROBOT_JS)


def test_match_defines_hand_validity_check():
    js = _r(_MATCH_JS)
    assert "function handHas(id) { return HAND.indexOf(id) >= 0; }" in js
    assert "function dealPlayable()" in js
    body = _func_body(js, "function dealPlayable()", "function setPlayChip(")
    # Playability requires: player's turn, complete + non-self selection, a light
    # pair, AND both companies in the current hand.
    assert 'reason: "incomplete"' in body
    assert 'reason: "no_pair"' in body
    assert "!handHas(selected.acq) || !handHas(selected.tgt)" in body
    assert 'reason: "not_in_hand"' in body


def test_play_deal_button_gated_by_hand_validity():
    js = _r(_MATCH_JS)
    body = _func_body(js, "function updatePlayDealButton()", "function playDeal(")
    assert "const state = dealPlayable();" in body
    assert "btn.disabled = !state.ok;" in body
    # The not-in-hand case shows the documented light hint + a blocked chip.
    assert "不在当前手牌中" in body
    assert "不在手牌" in body  # chip label


def test_player_played_deal_must_come_from_hand():
    js = _r(_MATCH_JS)
    body = _func_body(js, "function playDeal()", "function robotsTakeTurn(")
    # playDeal re-validates through dealPlayable before calling the engine, so a
    # non-hand selection (e.g. loaded from the Queue) can never be played.
    assert "const state = dealPlayable();" in body
    assert "if (!state.ok)" in body
    assert "window.MatchEngine.playerPlay(MATCH, selected.acq, selected.tgt" in body


def test_queue_deal_loads_for_preview_but_not_forced_play():
    js = _r(_MATCH_JS)
    body = _func_body(js, "function loadQueueItem(", "function buildQueueRow(")
    # A queue item is always loaded onto the table for preview...
    assert "setDeal(it.acquirer_id, it.target_id)" in body
    # ...with a light hint when its companies are not all in the current hand.
    assert "!handHas(it.acquirer_id) || !handHas(it.target_id)" in body
    assert "可预览 / 看票据" in body
    # Loading does NOT disable / bypass the Ticket — openTicket is independent of
    # hand-validity and the Queue add/remove paths are unchanged.
    assert "function openTicket(" in js
    assert "window.DealQueue.remove(it.acquirer_id, it.target_id)" in js
    assert "function addDealToQueue(" in js


# ── D. Boundaries: no engine / Match Points / robot-strategy / contract change

def test_match_points_formula_unchanged():
    js = _r(_ENGINE_JS)
    # The exact V5.9.2 fixed weight tables are untouched by the rule hardening.
    assert "VIA_LEVEL_POINTS = { green: 20, yellow: 6, red: -18 }" in js
    assert "SYNERGY_TIER_POINTS = { high: 10, medium: 6, low: 3, none: 0 }" in js
    assert "TIER_RANK = { gold: 5, red: 4, blue: 3, green: 2, white: 1 }" in js


def test_robot_base_strategy_present():
    js = _r(_ROBOT_JS)
    # The robot weight ladder still exists. (V5.9.3 rule hardening was player-side
    # only and left these alone; V5.9.5 deliberately retuned them — see
    # tests/test_ma_robot_retune.py — so this only checks the ladder is intact,
    # not the exact pre-retune values.)
    assert 'intern:    { eps: 1.00' in js
    assert 'md:        { eps: 0.46' in js


def test_no_overall_score_on_hardened_surface():
    for f in (_WARROOM_HTML, _MATCH_HTML, _MATCH_JS, _ENGINE_JS):
        text = _r(f)
        for banned in ("综合评分", "Overall Score", "胜率", "win_rate", "overall_score"):
            assert banned not in text, f"{banned} in {f.name}"


def test_no_source_meta_in_resource_or_hand_logic():
    for f in (_MATCH_JS, _ENGINE_JS):
        text = _r(f)
        for banned in ("source_meta", "field_sources", "filing_url", "quote_url"):
            assert banned not in text, f"{banned} in {f.name}"


def test_no_network_llm_randomness_added():
    for f in (_MATCH_JS, _ENGINE_JS):
        js = _r(f)
        for banned in ("Math.random", "XMLHttpRequest", "eval(", "new Function",
                       "openai", "anthropic", "WebSocket", "navigator.sendBeacon"):
            assert banned not in js, f"{banned} in {f.name}"


def test_match_surface_still_safe_dom():
    for f in (_MATCH_JS, _ENGINE_JS):
        js = _r(f)
        for m in re.finditer(r"\.innerHTML\s*=\s*(.+)", js):
            rhs = m.group(1).strip()
            assert rhs.startswith('""') or rhs.startswith("''"), f"{rhs} in {f.name}"


def test_backend_contract_unchanged():
    client = app.test_client()
    r = client.post("/api/modeling/ma/calculate", json=build_pair_payload("aapl", "msft")).get_json()
    assert r["status"] == "ok" and "boards" not in r
    # No game-rule fields leak into the finance contract.
    for banned in ("draw_allowance", "reshuffle_allowance", "match_points"):
        assert banned not in str(r)
    pairs = client.get("/api/modeling/ma/arena/pairs").get_json()
    assert pairs["pair_count"] == 9900 and len(pairs["pairs"]) == 9900
    for banned in ("draw_allowance", "reshuffle_allowance"):
        assert banned not in str(pairs)


def test_light_equals_calculate_still_consistent():
    client = app.test_client()
    for acq, tgt in [("meta", "googl"), ("aapl", "msft"), ("nvda", "avgo")]:
        light = get_arena_pair(acq, tgt)
        full = client.post(
            "/api/modeling/ma/calculate", json=build_pair_payload(acq, tgt)
        ).get_json()["result"]
        assert light["accretion_dilution_pct"] == full["accretion_dilution"]
    assert len(list_arena_pairs()) == 9900
