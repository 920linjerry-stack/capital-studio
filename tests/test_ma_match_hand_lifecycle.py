"""V5.9.4 Match Hand Lifecycle & Robot Feedback Foundation tests.

This wave gives the Deal Arena Match a real card-hand life cycle WITHOUT touching
the finance model:

  1. Queue hand-validity display is always recomputed from the LIVE current hand
     (+ used pile), so an in-hand queue deal never shows a stale "not in hand"
     warning and an out-of-hand / used deal always shows why it cannot be played.
  2. A played deal consumes both companies: they leave the hand and enter a
     per-match used pile. Used cards never come back via Draw / Reshuffle / the
     round refresh. Robots are NOT constrained by (and never touch) this pile.
  3. Round transition: the player keeps up to 4 cards, the system refreshes new
     cards back to the 7-card target (keep 4 -> +3). An exhausted pool degrades
     gracefully (fewer cards), never crashes.
  4. Deterministic, sequential opponent turn feedback (you play -> opponent 1
     thinks/plays -> opponent 2 thinks/plays) via fixed short delays + CSS, no
     randomness / network / LLM / animation library.
  5. Player-visible opponent labels are the persona (difficulty) only — never
     "机器人1/2" or "ROBOT · …". Internal ids (robot_1/robot_2) are unchanged.

Following the repo convention the deterministic game-rule layer lives in JS and
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
_MATCH_HTML = _ROOT / "static" / "modeling" / "arena_match.html"
_MATCH_JS = _ROOT / "static" / "modeling" / "js" / "arena_match.js"
_ENGINE_JS = _ROOT / "static" / "modeling" / "js" / "match_engine.js"
_ROBOT_JS = _ROOT / "static" / "modeling" / "js" / "robot_opponent.js"
_QUEUE_JS = _ROOT / "static" / "modeling" / "js" / "deal_queue.js"


def _r(p):
    return p.read_text(encoding="utf-8")


def _func_body(js, start_marker, end_marker):
    a = js.index(start_marker)
    b = js.index(end_marker, a + len(start_marker))
    return js[a:b]


# ── 1. Queue hand-validity: in-hand deal shows positive, never a stale warning ─

def test_queue_in_hand_deal_shows_playable_hint_recomputed_live():
    js = _r(_MATCH_JS)
    body = _func_body(js, "function loadQueueItem(", "function buildQueueRow(")
    # The deal is always loaded for preview...
    assert "setDeal(it.acquirer_id, it.target_id)" in body
    # ...and the hint is recomputed from the LIVE hand every load (both branches
    # exist), so an in-hand deal shows the positive "playable" hint instead of a
    # leftover out-of-hand warning.
    assert "const outOfHand = !handHas(it.acquirer_id) || !handHas(it.target_id);" in body
    assert "可直接「打出交易」" in body  # the positive in-hand hint
    # The Play Deal button / pill stay consistent because they read dealPlayable().
    pdb = _func_body(js, "function updatePlayDealButton()", "function markPlayerUsed(")
    assert "const state = dealPlayable();" in pdb
    assert "btn.disabled = !state.ok;" in pdb


# ── 2. Queue out-of-hand / used deal still previewable but not playable ────────

def test_queue_out_of_hand_deal_blocks_play_but_allows_preview_ticket():
    js = _r(_MATCH_JS)
    body = _func_body(js, "function loadQueueItem(", "function buildQueueRow(")
    assert "可预览 / 看票据" in body
    # Preview / Ticket / Queue add/remove are independent of hand-validity.
    assert "function openTicket(" in js
    assert "window.DealQueue.remove(it.acquirer_id, it.target_id)" in js
    # dealPlayable gates a queue-loaded deal: out-of-hand AND used are blocked.
    dp = _func_body(js, "function dealPlayable()", "function renderHand(")
    assert 'reason: "not_in_hand"' in dp
    assert 'reason: "used"' in dp
    assert "!handHas(selected.acq) || !handHas(selected.tgt)" in dp


# ── 3. Used-card lifecycle: played companies leave hand + never return ────────

def test_played_deal_consumes_both_companies_into_used_pile():
    js = _r(_MATCH_JS)
    body = _func_body(js, "function markPlayerUsed(", "function playDeal(")
    # Both companies are pushed into MATCH.used_cards and spliced out of the hand.
    assert "MATCH.used_cards.push(id)" in body
    assert "MATCH.hand.splice(i, 1)" in body
    # playDeal actually consumes the selection after a successful engine play.
    play = _func_body(js, "function playDeal(", "// ── Deterministic opponent")
    assert "window.MatchEngine.playerPlay(MATCH, selected.acq, selected.tgt" in play
    assert "markPlayerUsed(selected.acq, selected.tgt);" in play


def test_used_cards_excluded_from_draw_refresh_reshuffle():
    js = _r(_MATCH_JS)
    body = _func_body(js, "function drawEligible(", "function initialDeal(")
    # The eligible draw walks the deck and skips used + in-hand + excluded ids,
    # scanning each card at most once (graceful when the pool is exhausted).
    assert "const used = usedSet();" in body
    assert "if (used.has(id) || inHand.has(id) || ex.has(id) || out.indexOf(id) >= 0) continue;" in body
    assert "scanned < N" in body
    # Draw (per-round) and Reshuffle (per-match) both refill from drawEligible, so
    # neither can ever re-deal a used card.
    assert "function drawOne()" in js and "drawEligible(1)" in js
    rot = _func_body(js, "function rotateHand()", "function updateResourceButtons(")
    assert "drawEligible(HAND_SIZE)" in rot


def test_engine_and_robot_stay_used_pile_and_lifecycle_agnostic():
    """The used pile + draw/retain/refresh life cycle stays a CONTROLLER rule: the
    pure engine and the robot selection never read the used pile (markPlayerUsed /
    drawEligible / .used_cards), so used cards are never blocked from robots
    (V5.10.2.4 used-card unlock). V5.10.2.4 does add ONE read — the engine's round
    orchestration consults the player's CURRENT hand (state.hand) for the same-
    round company-overlap rule — but the robot selection itself stays fully
    hand-agnostic (it only receives a company-exclusion set)."""
    for f in (_ENGINE_JS, _ROBOT_JS):
        text = _r(f)
        assert ".used_cards" not in text, f.name      # never reads the used pile
        assert "markPlayerUsed" not in text, f.name
        assert "drawEligible" not in text, f.name
    # The robot selection module never reaches into a hand — it is handed an
    # explicit excludedCompanies set by the engine instead.
    robot = _r(_ROBOT_JS)
    assert "MATCH.hand" not in robot and "state.hand" not in robot
    # The engine's overlap orchestration reads the current hand (not the used pile).
    assert "currentHandCompanies(state)" in _r(_ENGINE_JS)


# ── 4. Round transition: keep up to 4, refresh back to the 7-card target ──────

def test_round_transition_constants_keep4_refresh3_target7():
    js = _r(_MATCH_JS)
    assert "const HAND_SIZE = 7;" in js
    assert "const RETAIN_MAX = 4;" in js
    assert "const REFRESH_COUNT = 3;" in js


def test_apply_retain_caps_at_four_and_refills_to_target():
    js = _r(_MATCH_JS)
    body = _func_body(js, "function applyRetainAndRefresh(", "function nextRound(")
    # At most RETAIN_MAX retained; used cards never retained.
    assert "if (retained.length >= RETAIN_MAX) break;" in body
    assert "companyById(id) && !used.has(id)" in body
    # Refill to HAND_SIZE with fresh eligible cards (keep 4 -> need 3 -> hand 7).
    assert "const need = Math.max(0, HAND_SIZE - MATCH.hand.length);" in body
    assert "drawEligible(need)" in body


def test_next_round_applies_transition_before_advancing():
    js = _r(_MATCH_JS)
    # nextRound is defined AFTER the retain helpers; assert the keep/refresh is
    # applied BEFORE the engine advances the round.
    nr = js[js.index("function nextRound()"):]
    assert "if (!wasLastRound) applyRetainAndRefresh();" in nr
    assert nr.index("applyRetainAndRefresh();") < nr.index("window.MatchEngine.nextRound(MATCH);")


def test_retain_panel_present_and_safe():
    html = _r(_MATCH_HTML)
    assert 'id="retain-panel"' in html
    assert 'id="retain-list"' in html
    assert 'id="retain-count"' in html
    assert "最多 4 张" in html
    js = _r(_MATCH_JS)
    # The retain chips are built with safe DOM (el/textContent), never innerHTML.
    assert "function renderRetainList(" in js
    assert "function toggleRetain(" in js
    assert "function enterRetainPhase(" in js


# ── 5. Player-visible opponent labels are persona-only (never 机器人1/2) ───────

def test_no_robot_numbering_or_robot_prefix_in_visible_copy():
    html = _r(_MATCH_HTML)
    for banned in ("机器人", "Robot 1", "Robot 2", ">BOT<", "Robot ·"):
        assert banned not in html, f"{banned} in {_MATCH_HTML.name}"
    js = _r(_MATCH_JS)
    # The old rendered templates are gone (comments may mention the rule, but no
    # template literal builds "机器人N" or "Robot · …" anymore).
    assert "机器人${" not in js
    assert "Robot · ${" not in js


def test_persona_map_drives_labels_internal_ids_unchanged():
    js = _r(_MATCH_JS)
    assert "const PERSONA = {" in js
    assert "function personaOf(diff)" in js
    for title in ("实习生", "分析师", "高级分析师", "副总裁", "董事总经理"):
        assert title in js, title
    # Internal state ids are NOT renamed for copy.
    assert "robot_1" in js and "robot_2" in js
    assert 'id="seat-robot-1"' in _r(_MATCH_HTML) and 'id="seat-robot-2"' in _r(_MATCH_HTML)
    # Seats / scoreboard are filled from the persona, with id hooks for JS.
    assert "renderSeats" in js
    assert 'id="seat-name-1"' in _r(_MATCH_HTML) and 'id="score-name-robot-1"' in _r(_MATCH_HTML)


# ── 6. Deterministic, sequential opponent turn feedback ──────────────────────

def test_robot_feedback_is_sequential_and_deterministic():
    js = _r(_MATCH_JS)
    html = _r(_MATCH_HTML)
    assert 'id="turn-feedback"' in html
    assert "function beginThinking(seat, id)" in js
    assert "function revealOneRobot(seat, id, rec)" in js
    assert "function finishRobotsTurn(" in js
    body = _func_body(js, "function robotsTakeTurn(", "function finishRobotsTurn(")
    # Opponent 1 then opponent 2 reveal on fixed, ordered delays (no randomness).
    assert 'beginThinking(1, "robot_1");' in body
    assert 'revealOneRobot(1, "robot_1", rec);' in body
    assert 'beginThinking(2, "robot_2");' in body
    assert 'revealOneRobot(2, "robot_2", rec);' in body
    assert "TURN_STEP_MS" in body and "TURN_STEP_MS * 2" in body
    assert "Math.random" not in js
    # The thinking / played feedback lines exist (persona think + play + MP).
    assert "思考中…" in js
    assert "打出 ${deal.acquirer_ticker}→${deal.target_ticker}" in js


def test_final_scoreboard_and_round_result_resolved_after_sequence():
    js = _r(_MATCH_JS)
    finish = _func_body(js, "function finishRobotsTurn(", "function participantName(")
    assert "renderScoreboard();" in finish
    assert "renderRoundResult();" in finish
    # The authoritative engine resolution is unchanged: robotsPlay runs once.
    rtt = _func_body(js, "function robotsTakeTurn(", "function finishRobotsTurn(")
    assert "window.MatchEngine.robotsPlay(MATCH, pairs, getPair, companyById);" in rtt


# ── 7. Regression: Draw 1/round, Reshuffle 2/match unchanged ─────────────────

def test_regression_draw_and_reshuffle_rules_intact():
    eng = _r(_ENGINE_JS)
    assert "const DRAW_PER_ROUND = 1;" in eng
    assert "const RESHUFFLE_PER_MATCH = 2;" in eng
    js = _r(_MATCH_JS)
    draw = _func_body(js, "function drawOne()", "function rotateHand()")
    assert "window.MatchEngine.canDraw(MATCH)" in draw
    assert "window.MatchEngine.useDraw(MATCH)" in draw
    rot = _func_body(js, "function rotateHand()", "function updateResourceButtons(")
    assert "window.MatchEngine.canReshuffle(MATCH)" in rot
    assert "window.MatchEngine.useReshuffle(MATCH)" in rot


def test_regression_match_points_and_robot_strategy_unchanged():
    eng = _r(_ENGINE_JS)
    assert "VIA_LEVEL_POINTS = { green: 20, yellow: 6, red: -18 }" in eng
    assert "SYNERGY_TIER_POINTS = { high: 10, medium: 6, low: 3, none: 0 }" in eng
    robot = _r(_ROBOT_JS)
    assert "intern:    { eps: 1.00" in robot
    # md eps was retuned 0.48 -> 0.46 in V5.9.5 (robot difficulty rebalance); the
    # Match Points formula above is what this hand-lifecycle feature must not
    # touch, and it is intact.
    assert "md:        { eps: 0.46" in robot


# ── 8/9. Regression: Queue / Ticket / EPS consistency + no source_meta leak ──

def test_regression_light_equals_calculate_eps_consistency():
    client = app.test_client()
    for acq, tgt in [("meta", "googl"), ("aapl", "msft"), ("nvda", "avgo")]:
        light = get_arena_pair(acq, tgt)
        full = client.post(
            "/api/modeling/ma/calculate", json=build_pair_payload(acq, tgt)
        ).get_json()["result"]
        assert light["accretion_dilution_pct"] == full["accretion_dilution"]
    assert len(list_arena_pairs()) == 9900


def test_regression_no_source_meta_in_match_or_engine_or_lifecycle():
    for f in (_MATCH_JS, _ENGINE_JS):
        text = _r(f)
        for banned in ("source_meta", "field_sources", "filing_url", "quote_url", "audit_trail"):
            assert banned not in text, f"{banned} in {f.name}"
    client = app.test_client()
    full = client.post("/api/modeling/ma/calculate", json=build_pair_payload("aapl", "msft")).get_json()
    # No new game-rule / lifecycle fields leak into the finance contract.
    for banned in ("used_cards", "deck_cursor", "match_points", "retain"):
        assert banned not in str(full)
    pairs = client.get("/api/modeling/ma/arena/pairs").get_json()
    assert pairs["pair_count"] == 9900
    for banned in ("used_cards", "deck_cursor", "retain", "match_points"):
        assert banned not in str(pairs)


# ── 10. Statelessness: light client-side state only, no backend per-user state ─

def test_match_state_is_light_client_side_only():
    js = _r(_MATCH_JS)
    # Persisted state is the lightweight MATCH blob in sessionStorage (ids + round
    # state), never a full calculation result or provenance trail.
    assert 'MATCH_STATE_KEY = "ma_match_state_v1"' in js
    assert "sessionStorage.setItem(MATCH_STATE_KEY, JSON.stringify(MATCH))" in js
    # No backend mutable per-user state / runtime network beyond the two existing
    # calculate fetches (single-deal fallback + Deal Ticket).
    assert js.count("${API}/api/modeling/ma/calculate") == 2
    for banned in ("localStorage", "WebSocket", "navigator.sendBeacon"):
        assert banned not in js, banned


# ── 11. Safe DOM on the whole V5.9.4 surface ─────────────────────────────────

def test_match_surface_safe_dom_no_innerhtml_interpolation():
    for f in (_MATCH_JS, _ENGINE_JS):
        js = _r(f)
        for m in re.finditer(r"\.innerHTML\s*=\s*(.+)", js):
            rhs = m.group(1).strip()
            assert rhs.startswith('""') or rhs.startswith("''"), f"{rhs} in {f.name}"


def test_backend_contract_unchanged():
    client = app.test_client()
    r = client.post("/api/modeling/ma/calculate", json=build_pair_payload("aapl", "msft")).get_json()
    assert r["status"] == "ok" and "boards" not in r
    pairs = client.get("/api/modeling/ma/arena/pairs").get_json()
    assert pairs["pair_count"] == 9900 and "boards" in pairs
