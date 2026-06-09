"""V5.10.2 Opponent Identity & Presence (First Pass) tests.

Presentation layer only: fictional banker display names, abstract monogram
sigils, seat presence states, and finite scripted dialogue for robot_1 /
robot_2. Internal ids stay robot_1 / robot_2; nothing enters engine/API/state.
"""

import re
from pathlib import Path

from app import app


_ROOT = Path(__file__).resolve().parents[1]
_MATCH_HTML = _ROOT / "static" / "modeling" / "arena_match.html"
_MATCH_JS = _ROOT / "static" / "modeling" / "js" / "arena_match.js"
_ID_JS = _ROOT / "static" / "modeling" / "js" / "opponent_identity.js"
_ENGINE_JS = _ROOT / "static" / "modeling" / "js" / "match_engine.js"
_ROBOT_JS = _ROOT / "static" / "modeling" / "js" / "robot_opponent.js"


def _r(p):
    return p.read_text(encoding="utf-8")


def _func_body(js, start_marker, end_marker):
    a = js.index(start_marker)
    b = js.index(end_marker, a + len(start_marker))
    return js[a:b]


# ── Python port of opponent_identity.js (for deterministic contract tests) ────

RANK = {
    "intern": {"cn": "实习生", "en": "Intern"},
    "analyst": {"cn": "分析师", "en": "Analyst"},
    "associate": {"cn": "高级分析师", "en": "Associate"},
    "vp": {"cn": "副总裁", "en": "VP"},
    "md": {"cn": "董事总经理", "en": "MD"},
}

NAME_POOL = {
    "intern": [
        {"first": "Theo", "last": "Vance"},
        {"first": "Priya", "last": "Anand"},
        {"first": "Sam", "last": "Okoro"},
        {"first": "Mia", "last": "Chen"},
    ],
    "analyst": [
        {"first": "Marcus", "last": "Lehn"},
        {"first": "Sofia", "last": "Reyes"},
        {"first": "Jun", "last": "Park"},
        {"first": "Nora", "last": "Ellis"},
    ],
    "associate": [
        {"first": "Dana", "last": "Osei"},
        {"first": "Ken", "last": "Murata"},
        {"first": "Elena", "last": "Faro"},
        {"first": "Iris", "last": "Novak"},
    ],
    "vp": [
        {"first": "Adrian", "last": "Cole"},
        {"first": "Lena", "last": "Volkov"},
        {"first": "Raymond", "last": "Suh"},
        {"first": "Clara", "last": "Wynn"},
    ],
    "md": [
        {"first": "Jerry", "last": "Lin"},
        {"first": "Vivienne", "last": "Vale"},
        {"first": "Sterling", "last": "Voss"},
        {"first": "Margaret", "last": "Ainsley"},
        {"first": "Arthur", "last": "Vale"},
    ],
}

# Fix Vivienne last name in pool to match JS
NAME_POOL["md"][1] = {"first": "Vivienne", "last": "Roark"}

HUE_BAND = {
    "intern": (32, 48),
    "analyst": (198, 218),
    "associate": (158, 178),
    "vp": (252, 272),
    "md": (36, 52),
}


def hash_mix(seed, *parts):
    h = int(seed) & 0xFFFFFFFF or 1
    for part in parts:
        s = str(part)
        for ch in s:
            h = ((31 * h) + ord(ch)) & 0xFFFFFFFF
            if h >= 0x80000000:
                h -= 0x100000000
        t1 = (h ^ (h >> 16)) & 0xFFFFFFFF
        if t1 >= 0x80000000:
            t1 -= 0x100000000
        t2 = (t1 * 2246822507) & 0xFFFFFFFF
        if t2 >= 0x80000000:
            t2 -= 0x100000000
        t3 = (h ^ (h >> 13)) & 0xFFFFFFFF
        if t3 >= 0x80000000:
            t3 -= 0x100000000
        t4 = (t3 * 3266489909) & 0xFFFFFFFF
        if t4 >= 0x80000000:
            t4 -= 0x100000000
        h = (t2 ^ t4) & 0xFFFFFFFF
    return h & 0xFFFFFFFF


def initials(first, last):
    a = first[0].upper() if first else "?"
    b = last[0].upper() if last else "?"
    return a + b


def build_one_identity(seed, seat, difficulty, used_names):
    norm = difficulty if difficulty in RANK else "analyst"
    pool = NAME_POOL.get(norm, NAME_POOL["analyst"])
    rank = RANK[norm]
    idx = hash_mix(seed, seat, norm, "name") % len(pool)
    guard = 0
    while guard < len(pool):
        entry = pool[idx]
        display = f"{entry['first']} {entry['last']}"
        if display not in used_names:
            used_names.add(display)
            band = HUE_BAND[norm]
            span = band[1] - band[0] + 1
            hue = band[0] + (hash_mix(seed, seat, norm, "hue") % span)
            shape = hash_mix(seed, seat, norm, "shape") % 3
            return {
                "seat": seat,
                "difficulty": norm,
                "displayName": display,
                "initials": initials(entry["first"], entry["last"]),
                "rankCn": rank["cn"],
                "hue": hue,
                "shape": shape,
            }
        idx = (idx + 1) % len(pool)
        guard += 1
    entry = pool[0]
    return {
        "seat": seat,
        "difficulty": norm,
        "displayName": f"{entry['first']} {entry['last']}",
        "initials": initials(entry["first"], entry["last"]),
        "rankCn": rank["cn"],
        "hue": HUE_BAND[norm][0],
        "shape": 0,
    }


def build_for_match(seed, robots):
    used = set()
    out = {}
    for seat, diff in robots:
        out[f"robot_{seat}"] = build_one_identity(seed, seat, diff, used)
    return out


# ── 1. Module present + wired ───────────────────────────────────────────────

def test_opponent_identity_module_loaded_before_arena_match():
    html = _r(_MATCH_HTML)
    assert "opponent_identity.js" in html
    assert html.index("js/opponent_identity.js") < html.index("js/arena_match.js")
    js = _r(_ID_JS)
    assert "window.OpponentIdentity" in js
    assert "buildForMatch" in js
    assert "pickShowdownLine" in js
    assert "pickRoundResultLine" in js
    assert "makeSigilNode" in js
    assert "RANK_COLOR" in js
    assert "rankClass" in js


def test_arena_match_wires_identity_layer():
    js = _r(_MATCH_JS)
    assert "refreshOpponentIdentities" in js
    assert "opponentIdentity(id)" in js
    assert "window.OpponentIdentity.buildForMatch(MATCH)" in js
    assert "bankerLabel(id)" in js
    assert "emphasizeWinnerSeat" in js
    assert "refreshSeatPresence" in js
    assert "applyRankVisual" in js
    assert "robot_1" in js and "robot_2" in js


# ── 2. Identity deterministic + dedupe + variability ────────────────────────

def test_identity_deterministic_same_seed_seat_difficulty():
    robots = [(1, "analyst"), (2, "vp")]
    a = build_for_match(424242, robots)
    b = build_for_match(424242, robots)
    assert a == b
    assert a["robot_1"]["displayName"]
    assert a["robot_1"]["initials"] == initials(*a["robot_1"]["displayName"].split(" ", 1))


def test_identity_varies_across_seeds():
    robots = [(1, "analyst"), (2, "vp")]
    a = build_for_match(1001, robots)
    b = build_for_match(9001, robots)
    # Different seeds should usually pick different names (not guaranteed for all,
    # but at least one field should differ across a few seeds).
    names_a = {a["robot_1"]["displayName"], a["robot_2"]["displayName"]}
    names_b = {b["robot_1"]["displayName"], b["robot_2"]["displayName"]}
    assert names_a != names_b or a["robot_1"]["hue"] != b["robot_1"]["hue"]


def test_same_difficulty_dedupes_names():
    robots = [(1, "intern"), (2, "intern")]
    ids = build_for_match(55555, robots)
    assert ids["robot_1"]["displayName"] != ids["robot_2"]["displayName"]
    assert ids["robot_1"]["initials"] != ids["robot_2"]["initials"]


def test_internal_ids_preserved_not_display_keys():
    js = _r(_MATCH_JS)
    assert 'const id = `robot_${seat}`;' in js or "robot_${seat}" in js
    assert "MATCH.participants[`robot_${seat}`]" in js or "MATCH.participants[id]" in js
    # Display name must not become a state key.
    assert "participants[ident.displayName]" not in js
    assert "participants[identity.displayName]" not in js


# ── 3. UI render hooks ──────────────────────────────────────────────────────

def test_html_has_sigil_and_seat_identity_hooks():
    html = _r(_MATCH_HTML)
    assert 'id="seat-fig-1"' in html
    assert 'id="seat-fig-2"' in html
    assert 'id="score-sigil-robot-1"' in html
    assert 'id="score-sigil-robot-2"' in html
    assert ".scard-line" in html
    assert ".mr-quote" in html
    assert ".mseat.winner-emphasis" in html


# ── V5.10.2.1 rank color polish (separate from card tier) ───────────────────

def test_rank_color_tokens_present_and_separate_from_tier():
    html = _r(_MATCH_HTML)
    id_js = _r(_ID_JS)
    match_js = _r(_MATCH_JS)
    for rank in ("rank-md", "rank-vp", "rank-analyst", "rank-associate", "rank-intern"):
        assert rank in html, rank
    assert "--rank-color" in html
    assert "RANK_COLOR" in id_js
    assert "rankClass" in id_js
    assert "applyRankVisual" in match_js
    # Card tier tokens stay on arena-tier; rank uses --rank-color only.
    assert ".arena-tier { --tier-color:" in html
    assert ".scard-via.green" in html


def test_scoreboard_and_seat_apply_rank_visual():
    js = _r(_MATCH_JS)
    seats = _func_body(js, "function renderSeats()", "function setSeatState(")
    assert "applyRankVisual(seatEl, diff)" in seats
    assert "applyRankVisual(scoreChip, diff)" in seats
    card = _func_body(js, "function buildShowdownCard(", "function buildShowdown(")
    assert "applyRankVisual(card, ident.difficulty)" in card


# ── V5.10.2.3 Opponent Seat Winner State Reset Fix (re-probe: stuck-pip real fix)
# The seat avatar dot + ring mark ONLY the current round winner. The old `.leading`
# cumulative-leader SEAT pip is removed — it welded a dot to the round-1 winner for
# the rest of the match. The total leader now shows ONLY on the scoreboard chip
# glow (.score-chip.lead), never as a seat dot.

def test_seat_avatar_dot_bound_to_round_winner_not_leader():
    html = _r(_MATCH_HTML)
    # The avatar dot pseudo-element must hang off the round-winner class, NOT the
    # old cumulative-leader `.leading` class (which used to weld the dot in place).
    assert ".mseat.winner-emphasis .mseat-fig::after" in html
    assert ".mseat.leading .mseat-fig::after" not in html
    assert ".mseat.leading {" not in html


def test_seat_transient_state_cleared_before_reapply():
    js = _r(_MATCH_JS)
    assert "function clearSeatTransientState()" in js
    assert 'classList.remove("leading", "winner-emphasis")' in js
    # The seat presence is driven ONLY by the round winner: clear everything, then
    # re-apply just the round winner — no cumulative-leader seat pip.
    refresh = _func_body(js, "function refreshSeatPresence(", "function scoreDomId(")
    assert "clearSeatTransientState()" in refresh
    assert "emphasizeWinnerSeat(window.MatchEngine.roundWinner(roundRec))" in refresh
    assert "syncSeatLeading" not in refresh
    # syncSeatLeading (the old leader→seat pip) is retired entirely.
    assert "function syncSeatLeading(" not in js
    settle = _func_body(js, "function settleShowdown(", "function numOrZero(")
    assert "refreshSeatPresence(rec)" in settle
    finish = _func_body(js, "function finishRobotsTurn(", "function participantName(")
    assert "refreshSeatPresence(rec)" in finish
    next_r = _func_body(js, "function nextRound()", "// ── End screen")
    assert "refreshSeatPresence(null)" in next_r
    again = _func_body(js, "function playAgain()", "// ── Resume")
    assert "refreshSeatPresence(null)" in again
    reset = _func_body(js, "function resetShowdown()", "// Light count-roll")
    assert "refreshSeatPresence(null)" in reset
    play = _func_body(js, "function playDeal()", "// ── Deterministic opponent")
    assert "refreshSeatPresence(null)" in play
    restore = _func_body(js, "function syncMatchView()", "async function init(")
    assert "refreshSeatPresence(null)" in restore


def test_emphasize_winner_seat_ignores_draw_and_player():
    js = _r(_MATCH_JS)
    body = _func_body(js, "function emphasizeWinnerSeat(", "// Clear all transient")
    # A draw or a player win must place NO seat emphasis (no stale dot on a draw).
    assert 'winnerId === "draw"' in body
    assert 'winnerId === "player"' in body
    assert "return;" in body


def test_match_leader_drives_scoreboard_chip_only_not_seat():
    js = _r(_MATCH_JS)
    body = _func_body(js, "function matchLeaderId()", "function emphasizeWinnerSeat(")
    assert "window.MatchEngine.winner(MATCH)" in body
    # Total leader is a scoreboard-chip glow concern; the seat never reads it.
    score = _func_body(js, "function renderScoreboard()", "function renderRoundPill(")
    assert "matchLeaderId()" in score
    assert 'classList.toggle("lead", leadId === id)' in score
    assert "syncSeatLeading" not in score
    refresh = _func_body(js, "function refreshSeatPresence(", "function scoreDomId(")
    assert "matchLeaderId" not in refresh


def test_player_chip_not_rank_colored():
    html = _r(_MATCH_HTML)
    assert 'id="score-chip-player"' in html
    # Player chip keeps .you styling; rank-* classes are only applied to robots in JS.
    js = _r(_MATCH_JS)
    seats = _func_body(js, "function renderSeats()", "function setSeatState(")
    assert "score-chip-robot-" in seats
    assert "score-chip-player" not in seats.replace("score-chip-robot-", "")


# ── V5.10.2.2 Opponent Rank Label Refinement ─────────────────────────────────

def test_scoreboard_inline_seat_label_no_rank_pill():
    html = _r(_MATCH_HTML)
    js = _r(_MATCH_JS)
    assert 'id="score-rank-robot-1"' in html
    assert 'id="score-rank-robot-2"' in html
    assert "sc-seat-label" in html
    assert "sc-who-inline" in html
    assert "score-role-robot" not in html
    # Rank pill capsule removed from scoreboard (seat-row badge may still use pill).
    assert ".score-chip[class*=\"rank-\"] .sc-role" not in html
    seats = _func_body(js, "function renderSeats()", "function setSeatState(")
    assert "scoreRank" in seats
    assert "scoreRank.textContent = ident.rankCn" in seats
    assert "score-role-robot" not in seats


def test_showdown_and_deal_table_scale_polish():
    html = _r(_MATCH_HTML)
    assert "max-width: 680px" in html  # showdown stage widened
    assert "max-width: 640px" in html  # deal zone widened
    assert "min-height: 128px" in html  # deal slots taller
    scard = _func_body(html, ".scard {", "opacity: 0")
    assert "padding: 15px 14px 14px" in scard
    assert "font-size: 16px" in html  # scard-deal bumped


def test_participant_name_uses_banker_identity():
    js = _r(_MATCH_JS)
    body = _func_body(js, "function participantName(id)", "function participantNameShort(")
    assert "opponentIdentity(id)" in body
    assert "ident.displayName" in body
    assert "ident.rankCn" in body


def test_showdown_card_uses_banker_name_and_dialogue():
    js = _r(_MATCH_JS)
    card = _func_body(js, "function buildShowdownCard(", "function buildShowdown(")
    assert 'el("span", "scard-owner-name", ident.displayName)' in card
    assert "pickShowdownLine" in card
    assert 'el("div", "scard-line", line)' in card


def test_turn_feedback_uses_banker_label():
    js = _r(_MATCH_JS)
    assert "function bankerLabel(id)" in js
    think = _func_body(js, "function beginThinking(seat, id)", "function revealOneRobot(")
    assert "bankerLabel(id)" in think


# ── 4. Dialogue deterministic + finite ──────────────────────────────────────

def test_dialogue_from_static_pool_not_random():
    js = _r(_ID_JS)
    assert "const DIALOGUE = {" in js
    assert "Math.random" not in js
    assert "fetch(" not in js
    match_js = _r(_MATCH_JS)
    assert "Math.random" not in match_js
    # Sample lines from the spec appear in the static pool.
    assert "这笔 EPS 看起来很能打。" in js
    assert "模型跑完，这笔能过第一轮。" in js


def test_dialogue_selection_uses_hash_mix():
    js = _r(_ID_JS)
    assert "function pickFromPool(pool, seed, ...keys)" in js
    assert 'pickFromPool(pool, seed, round, identity.seat, "showdown")' in js


# ── 5. Safe DOM + no leakage ────────────────────────────────────────────────

def test_no_innerhtml_for_dynamic_identity_copy():
    js = _r(_MATCH_JS)
    id_js = _r(_ID_JS)
    assert "innerHTML" not in js
    assert "innerHTML" not in id_js
    render = _func_body(js, "function renderSeats()", "function setSeatState(")
    assert "textContent" in render
    assert "makeSigilNode" in js or "renderSigil" in js


def test_no_source_meta_strategy_score_leak():
    for f in (_MATCH_JS, _ID_JS, _MATCH_HTML):
        text = _r(f)
        for banned in ("source_meta", "strategy_score", "overall_score"):
            assert banned not in text, f"{banned} in {f.name}"


# ── 6. Boundaries: engine / robot / retain / showdown not regressed ─────────

def test_robot_strategy_and_engine_untouched():
    eng = _r(_ENGINE_JS)
    robot = _r(_ROBOT_JS)
    assert "function robotsPlay(state, pairs, getPair, cardById, selectFn)" in eng
    assert "selectRobotDeal" in robot


def test_showdown_retain_flow_hooks_intact():
    js = _r(_MATCH_JS)
    finish = _func_body(js, "function finishRobotsTurn(", "function participantName(")
    assert "showShowdown(rec, true);" in finish
    assert "enterRetainPhase" not in finish
    assert "const RETAIN_MAX = 4;" in js
    assert "const HAND_SIZE = 7;" in js


def test_script_load_order_for_match_page():
    html = _r(_MATCH_HTML)
    assert html.index("js/robot_opponent.js") < html.index("js/match_engine.js")
    assert html.index("js/match_engine.js") < html.index("js/opponent_identity.js")
    assert html.index("js/opponent_identity.js") < html.index("js/arena_match.js")


# ── 7. Mobile overflow guard ────────────────────────────────────────────────

def test_mobile_overflow_guard_retained():
    html = _r(_MATCH_HTML)
    assert "@media (max-width: 620px) { .showdown-grid { grid-template-columns: 1fr; } }" in html
    assert "-webkit-line-clamp: 2" in html
    assert "text-overflow: ellipsis" in html


# ── 8. Route still serves match page ────────────────────────────────────────

def test_match_route_serves_html():
    client = app.test_client()
    resp = client.get("/modeling/ma/arena/match/play")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "opponent_identity.js" in body
    assert "seat-fig-1" in body
