"""V5.10.1 The Showdown / Round Result Drama (First Pass) tests.

V5.10.1 re-stages the resolved Match round on the deal-table center as a
three-way **Showdown**: 你 / Banker 1 / Banker 2 each reveal one result card
carrying the SAME light round-result fields the engine already produced (deal
ACQ→TGT, EPS accretion/dilution, Match Points, viability lamp), the existing
round winner is lit with a restrained committee-amber ring + WINNER mark, and
the MP badge does a light pop / count-roll that ALWAYS lands on the exact engine
value.

It is presentation only. It changes NO game rule, Match Points formula, robot
strategy, hand lifecycle, Queue, engine/API/deck/precompute or source_meta. The
deterministic facts (EPS, viability, Match Points, round winner) are read from
the existing round record — nothing is recomputed, fetched, or stored anew.

Per repo convention the game layer lives in JS; the contract is locked via
source/static assertions plus backend data checks, and the live reveal is
covered by the documented browser smoke. The financial engine, Match Points
formula, robot strategy and the keep-4 / refresh-3 rule are asserted UNCHANGED.
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
_LOCAL_JS = _ROOT / "static" / "modeling" / "js" / "card_localization.js"


def _r(p):
    return p.read_text(encoding="utf-8")


def _func_body(js, start_marker, end_marker):
    a = js.index(start_marker)
    b = js.index(end_marker, a + len(start_marker))
    return js[a:b]


# ── 1. Showdown DOM exists with three result cards (player / robot_1 / robot_2) ─

def test_showdown_stage_present_in_html():
    html = _r(_MATCH_HTML)
    assert 'id="showdown-stage"' in html
    assert 'id="showdown-grid"' in html
    assert 'id="showdown-verdict"' in html
    # The Showdown lives inline on the deal table (no full-screen overlay).
    assert "本回合摊牌" in html and "Showdown" in html
    # It is part of the felt/table, after the deal zone and before the hint.
    assert html.index('id="deal-zone"') < html.index('id="showdown-stage"')
    assert html.index('id="showdown-stage"') < html.index('id="deal-hint"')
    # Not a fixed/full-screen overlay (it is on the table center).
    assert ".showdown-stage { position: fixed" not in html


def test_showdown_builds_three_cards_for_each_participant():
    js = _r(_MATCH_JS)
    body = _func_body(js, "function buildShowdown(rec)", "function settleShowdown(")
    # One card per participant, in the canonical order.
    assert 'for (const id of ["player", "robot_1", "robot_2"]) {' in body
    assert "grid.appendChild(buildShowdownCard(id, rec[id], winnerId));" in body
    # Each card is tagged with its participant id (display hook; ids stay internal).
    card = _func_body(js, "function buildShowdownCard(", "function buildShowdown(")
    assert 'card.id = `scard-${id}`;' in card
    assert 'card.dataset.participant = id;' in card


# ── 2. Each card shows deal, MP, EPS, viability lamp ─────────────────────────

def test_showdown_card_shows_deal_mp_eps_viability():
    js = _r(_MATCH_JS)
    card = _func_body(js, "function buildShowdownCard(", "function buildShowdown(")
    # Deal line ACQ → TGT from the existing light record (safe DOM, no innerHTML).
    assert 'const dealEl = el("div", "scard-deal");' in card
    assert 'el("span", "a", deal.acquirer_ticker || "—")' in card
    assert 'el("span", "t", deal.target_ticker || "—")' in card
    # EPS accretion/dilution from the existing field.
    assert "const epsText = pct(deal.accretion_dilution_pct);" in card
    assert 'el("div", `scard-eps ${epsCls}`' in card
    # MP badge from the existing per-deal match_points (display only).
    assert 'el("span", "scard-mp", `${signed(deal.match_points)} MP`)' in card
    # Viability lamp green / yellow / red from the existing viability_level.
    assert 'el("div", `scard-via ${deal.viability_level || "green"}`)' in card
    assert 'via.append(el("span", "via-lamp"),' in card
    # The CSS exposes the three lamp colors.
    html = _r(_MATCH_HTML)
    assert ".scard-via.green .via-lamp" in html
    assert ".scard-via.yellow .via-lamp" in html
    assert ".scard-via.red .via-lamp" in html


def test_showdown_card_shows_chinese_company_name_with_fallback():
    js = _r(_MATCH_JS)
    card = _func_body(js, "function buildShowdownCard(", "function buildShowdown(")
    # Chinese display name via the shared localization map; ticker fallback when a
    # card is unknown so the Showdown never white-screens / shows "undefined".
    assert "const acqCn = acqCard ? cnName(acqCard) : (deal.acquirer_ticker" in card
    assert "const tgtCn = tgtCard ? cnName(tgtCard) : (deal.target_ticker" in card
    # A missing deal renders a muted placeholder, not a crash.
    assert 'el("div", "scard-empty", "本回合未出牌 · No deal")' in card


# ── 3. Winner card gets the amber WINNER styling; losers are not mislabeled ───

def test_showdown_winner_highlight_and_losers_not_mislabeled():
    js = _r(_MATCH_JS)
    body = _func_body(js, "function settleShowdown(", "function numOrZero(")
    # Only the engine winner gets .winner; every other played card dims as a loser.
    assert 'if (id === winnerId) card.classList.add("winner");' in body
    assert 'else card.classList.add("loser", "dim");' in body
    # The winner/loser treatment ONLY applies when there is a real winner (not draw).
    assert 'if (winnerId !== "draw") {' in body
    # The winner mark text is built with safe DOM.
    card = _func_body(js, "function buildShowdownCard(", "function buildShowdown(")
    assert 'el("div", "scard-crown", "本回合胜者 · WINNER")' in card
    # CSS conveys the winner with committee amber (ring + glow), losers dim modestly.
    html = _r(_MATCH_HTML)
    winner_rule = _func_body(html, ".scard.winner {", "}")
    assert "rgba(232,201,135" in winner_rule  # committee amber, not a bright fill
    dim_rule = _func_body(html, ".scard.dim {", "}")
    assert "opacity: 0.62" in dim_rule  # readable, not blacked-out


# ── 4. Tie follows the existing roundWinner semantics (no new win rule) ───────

def test_showdown_tie_uses_engine_roundwinner_no_new_rule():
    js = _r(_MATCH_JS)
    # Both build + settle derive the winner from the SAME engine function.
    assert js.count("window.MatchEngine.roundWinner(rec)") >= 2
    settle = _func_body(js, "function settleShowdown(", "function numOrZero(")
    # A draw highlights NO card and shows the existing draw copy.
    assert 'if (winnerId === "draw") {' in settle
    assert "本回合平局 · Round Draw" in settle
    # The Showdown never defines its own winner — no points comparison lives here.
    assert ".points" not in settle
    assert "match_points >" not in settle


# ── 5. MP animation lands on the exact engine value; formula untouched ────────

def test_showdown_mp_rolls_to_exact_engine_value():
    js = _r(_MATCH_JS)
    roll = _func_body(js, "function rollMatchPoints(", "function buildShowdownCard(")
    # The badge always ends on the exact signed match_points value.
    assert "const final = `${signed(target)} MP`;" in roll
    assert "node.textContent = final;" in roll
    # Reduced-motion / no-rAF sets the final value immediately (no roll).
    assert "if (prefersReducedMotion() || typeof window.requestAnimationFrame" in roll
    # settleShowdown rolls each card's MP from its OWN deal record (never rescored).
    settle = _func_body(js, "function settleShowdown(", "function numOrZero(")
    assert "rollMatchPoints(mpNode, deal ? numOrZero(deal.match_points) : 0, 600);" in settle


def test_match_points_formula_and_scoreboard_unchanged():
    eng = _r(_ENGINE_JS)
    assert "VIA_LEVEL_POINTS = { green: 20, yellow: 6, red: -18 }" in eng
    assert "SYNERGY_TIER_POINTS = { high: 10, medium: 6, low: 3, none: 0 }" in eng
    js = _r(_MATCH_JS)
    # The authoritative scoreboard still reads engine totals, not the Showdown.
    assert "span.textContent = String(MATCH.participants[id].points)" in js


# ── 6. Keep & Next still requires a player click; no auto retain modal ────────

def test_showdown_does_not_auto_open_retain_modal():
    js = _r(_MATCH_JS)
    finish = _func_body(js, "function finishRobotsTurn(", "function participantName(")
    # The Showdown is staged on round resolution, but the modal must NOT open.
    assert "showShowdown(rec, true);" in finish
    assert "enterRetainPhase" not in finish
    # The page rests on the round-result state with Keep & Next visible.
    assert 'nb.style.display = "";' in finish


def test_keep_next_still_player_initiated():
    js = _r(_MATCH_JS)
    assert '$("next-round-btn").addEventListener("click", onKeepNext);' in js
    body = _func_body(js, "function onKeepNext(", "function enterRetainPhase(")
    assert "const isLast = MATCH.round_index >= MATCH.max_rounds;" in body
    assert "if (isLast) { nextRound(); return; }" in body
    assert "enterRetainPhase();" in body
    assert '$("retain-confirm-btn").addEventListener("click", nextRound);' in js


# ── 7. Retain modal close / back / keep-4 + refresh-to-7 not regressed ───────

def test_retain_modal_and_refresh_rule_not_regressed():
    js = _r(_MATCH_JS)
    html = _r(_MATCH_HTML)
    assert "const HAND_SIZE = 7;" in js
    assert "const RETAIN_MAX = 4;" in js
    assert "const REFRESH_COUNT = 3;" in js
    assert '$("retain-close").addEventListener("click", closeRetainModal);' in js
    assert '$("retain-cancel-btn").addEventListener("click", closeRetainModal);' in js
    close = _func_body(js, "function closeRetainModal(", "function applyRetainAndRefresh(")
    assert "exitRetainPhase();" in close
    assert 'nb.style.display = "";' in close
    assert "applyRetainAndRefresh" not in close
    assert 'id="retain-overlay"' in html


# ── 8. V5.10.1.1 turn-feedback collapses when Showdown opens ─────────────────

def test_turn_feedback_collapses_on_showdown_resolved():
    js = _r(_MATCH_JS)
    html = _r(_MATCH_HTML)
    show = _func_body(js, "function showShowdown(rec, animated)", "function renderRoundResult(")
    assert "collapseTurnFeedbackSummary(animated);" in show
    collapse = _func_body(js, "function collapseTurnFeedbackSummary(animated)", "function beginThinking(")
    assert "tf-line tf-summary in" in collapse
    assert 'el("div", "tf-line tf-summary in", TF_SUMMARY_TEXT)' in collapse
    assert "Showdown resolved" in js
    assert "TF_SUMMARY_TEXT" in js
    # Winner gold-highlight on the full log is no longer applied at round end.
    finish = _func_body(js, "function finishRobotsTurn(", "function participantName(")
    assert "highlightRoundWinnerFeedback();" not in finish
    # Compact summary CSS + fade-out helper exist.
    assert ".tf-line.tf-summary" in html
    assert ".tf-line.out" in html
    assert ".turn-feedback.resolved" in html


def test_turn_feedback_resets_on_next_round():
    js = _r(_MATCH_JS)
    next_round = _func_body(js, "function nextRound(", "function showEndScreen(")
    assert 'log.classList.remove("resolved", "collapsing")' in next_round
    play = _func_body(js, "function playDeal(", "// ── Deterministic opponent")
    assert 'log.classList.remove("resolved", "collapsing")' in play


# ── 9. Robot feedback sequence not regressed ─────────────────────────────────

def test_robot_feedback_sequence_not_regressed():
    js = _r(_MATCH_JS)
    html = _r(_MATCH_HTML)
    assert 'id="turn-feedback"' in html
    assert "function beginThinking(seat, id)" in js
    assert "function revealOneRobot(seat, id, rec)" in js
    rtt = _func_body(js, "function robotsTakeTurn(", "function finishRobotsTurn(")
    assert 'beginThinking(1, "robot_1");' in rtt
    assert 'revealOneRobot(1, "robot_1", rec);' in rtt
    assert 'beginThinking(2, "robot_2");' in rtt
    assert 'revealOneRobot(2, "robot_2", rec);' in rtt
    assert "window.MatchEngine.robotsPlay(MATCH, pairs, getPair, companyById);" in rtt


# ── 10. Queue hand-validity not regressed ────────────────────────────────────

def test_queue_hand_validity_not_regressed():
    js = _r(_MATCH_JS)
    assert "function handHas(id) { return HAND.indexOf(id) >= 0; }" in js
    assert "function dealPlayable()" in js
    body = _func_body(js, "function dealPlayable()", "function setPlayChip(")
    assert "if (!handHas(selected.acq) || !handHas(selected.tgt)) return { ok: false, reason: \"not_in_hand\" };" in body


# ── 11. Used-card lifecycle not regressed ────────────────────────────────────

def test_used_card_lifecycle_not_regressed():
    js = _r(_MATCH_JS)
    draw = _func_body(js, "function drawEligible(", "function initialDeal(")
    assert "if (used.has(id) || inHand.has(id) || ex.has(id) || out.indexOf(id) >= 0) continue;" in draw
    assert "function markPlayerUsed(acqId, tgtId)" in js


# ── 12. Card localization / tier border not regressed ────────────────────────

def test_localization_and_tier_border_not_regressed():
    js = _r(_MATCH_JS)
    html = _r(_MATCH_HTML)
    # The Showdown reuses the shared localization accessor (no hardcoded names).
    assert "function cnName(c)" in js
    assert "window.CardLocalization" in _r(_LOCAL_JS)
    # The hand-card tier border fix is intact (selected tier card keeps tier color).
    acq = _func_body(html, ".pcard.arena-tier.sel-acq {", "}")
    assert "border-color: var(--tier-color)" in acq


# ── 13. No source_meta leakage into match state / Showdown DOM / queue ───────

def test_no_source_meta_leak_on_showdown_surface():
    for f in (_MATCH_JS, _ENGINE_JS, _MATCH_HTML):
        text = _r(f)
        for banned in ("source_meta", "field_sources", "filing_url", "quote_url",
                       "audit_trail"):
            assert banned not in text, f"{banned} in {f.name}"
    # The Showdown reads only the light round record (deal/EPS/MP/viability) — no
    # full calculation result or raw audit trail is stored in the card dataset.
    js = _r(_MATCH_JS)
    card = _func_body(js, "function buildShowdownCard(", "function buildShowdown(")
    assert "synergy_context" not in card
    assert "viability_context" not in card


# ── 14. No innerHTML dynamic interpolation on the match surface ──────────────

def test_no_innerhtml_interpolation_on_match_surface():
    for f in (_MATCH_JS, _ENGINE_JS):
        js = _r(f)
        for m in re.finditer(r"\.innerHTML\s*=\s*(.+)", js):
            rhs = m.group(1).strip()
            assert rhs.startswith('""') or rhs.startswith("''"), f"{rhs} in {f.name}"
    # The Showdown builds everything via el()/textContent/createTextNode.
    js = _r(_MATCH_JS)
    card = _func_body(js, "function buildShowdownCard(", "function buildShowdown(")
    assert "innerHTML" not in card
    assert "document.createTextNode" in card


# ── 15. Reduced-motion / motion-safe rules exist (CSS + JS guard) ────────────

def test_prefers_reduced_motion_guard_present():
    html = _r(_MATCH_HTML)
    assert "@media (prefers-reduced-motion: reduce)" in html
    # The reduced-motion block neutralizes the card flip-up / MP pop transforms.
    block = html[html.index("@media (prefers-reduced-motion: reduce)"):]
    assert ".scard { transition: none; opacity: 1; transform: none; }" in block
    assert ".scard-mp.pop { animation: none; }" in block
    js = _r(_MATCH_JS)
    assert "function prefersReducedMotion()" in js
    assert 'window.matchMedia("(prefers-reduced-motion: reduce)").matches' in js


# ── 16. Narrow / mobile layout overflow guard ────────────────────────────────

def test_narrow_layout_overflow_guard_present():
    html = _r(_MATCH_HTML)
    # Three cards stack vertically on narrow screens (no horizontal overflow).
    assert "@media (max-width: 620px) { .showdown-grid { grid-template-columns: 1fr; } }" in html
    # The grid columns are min-width:0 so long tickers/names can never push width.
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in html
    # Card text truncates with ellipsis instead of overflowing.
    deal_rule = _func_body(html, ".scard-deal {", "}")
    assert "text-overflow: ellipsis" in deal_rule


# ── 17. Presentation layer only: no new API / network / randomness ───────────

def test_showdown_adds_no_new_api_or_randomness():
    js = _r(_MATCH_JS)
    # Still only the two pre-existing calculate fetches (fallback + Ticket).
    assert js.count("${API}/api/modeling/ma/calculate") == 2
    for banned in ("Math.random", "XMLHttpRequest", "eval(", "new Function",
                   "navigator.sendBeacon", "openai", "anthropic", "WebSocket", "localStorage"):
        assert banned not in js, banned


# ── 18. The deal table toggles between play mode and Showdown mode ───────────

def test_table_toggles_between_play_and_showdown():
    js = _r(_MATCH_JS)
    body = _func_body(js, "function setTableShowdown(on)", "function resetShowdown(")
    # Showdown mode hides the (empty) deal zone + hint and reveals the stage.
    assert 'if (stage) stage.style.display = on ? "" : "none";' in body
    assert 'if (zone) zone.style.display = on ? "none" : "";' in body
    assert 'if (hint) hint.style.display = on ? "none" : "";' in body
    # A new round / new match returns the table from Showdown to the deal table.
    next_round = _func_body(js, "function nextRound(", "function showEndScreen(")
    assert "resetShowdown();" in next_round
    play_again = _func_body(js, "function playAgain(", "function syncMatchView(")
    assert "resetShowdown();" in play_again


def test_showdown_staged_on_finish_and_restored_on_refresh():
    js = _r(_MATCH_JS)
    finish = _func_body(js, "function finishRobotsTurn(", "function participantName(")
    # Built/revealed with the staged (animated) reveal after the robot sequence.
    assert "showShowdown(rec, true);" in finish
    # A mid-round-result refresh restores it settled (no staged flip).
    sync = _func_body(js, "function syncMatchView(", "async function init(")
    assert "showShowdown(rec, false);" in sync
    # The reveal reuses turnTimers so it is cleared by nextRound / playAgain and
    # never blocks the Keep & Next click.
    show = _func_body(js, "function showShowdown(rec, animated)", "function renderRoundResult(")
    assert "turnTimers.push(setTimeout(" in show


# ── 19. Backend contract unchanged (engine / API / pairs / EPS consistency) ──

def test_backend_contract_unchanged():
    client = app.test_client()
    r = client.post("/api/modeling/ma/calculate", json=build_pair_payload("aapl", "msft")).get_json()
    assert r["status"] == "ok" and "boards" not in r
    pairs = client.get("/api/modeling/ma/arena/pairs").get_json()
    assert pairs["pair_count"] == 9900 and "boards" in pairs
    light = get_arena_pair("aapl", "msft")
    assert light["accretion_dilution_pct"] == r["result"]["accretion_dilution"]
    assert len(list_arena_pairs()) == 9900
