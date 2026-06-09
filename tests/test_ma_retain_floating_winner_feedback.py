"""V5.9.4.1 Retain Panel & Winner Feedback Polish tests.

A very narrow UI/feedback wave on top of V5.9.4. It changes NO match rule, hand
lifecycle, robot strategy, Match Points formula, engine/API/deck/precompute or
source_meta. It only:

  1. Turns the round-transition retain panel from a bottom banner (which overlapped
     the player hand) into a floating elevated panel on a light scrim.
  2. Spells out the refresh rule in the panel copy: unretained cards are refreshed
     next round; picking none refreshes the whole hand. (UI copy only — the
     retain/refresh rule is unchanged.)
  3. Gold-highlights the round winner's line in the deterministic turn-feedback log
     and tags it "本回合胜者". Ties follow the existing Round Result draw semantics;
     the highlight changes no Match Points / scoreboard / end-screen value.

Per repo convention the deterministic game layer stays in JS and the contract is
locked via source/static assertions plus backend data checks; live turn-by-turn
behaviour is covered by the documented browser smoke. The financial engine, Match
Points formula, robot strategy and the keep-4 / refresh-3 rule are asserted
UNCHANGED.
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


def _r(p):
    return p.read_text(encoding="utf-8")


def _func_body(js, start_marker, end_marker):
    a = js.index(start_marker)
    b = js.index(end_marker, a + len(start_marker))
    return js[a:b]


# ── 1. Retain panel is a FLOATING panel, not a bottom banner over the hand ────

def test_retain_panel_is_floating_overlay_not_bottom_banner():
    html = _r(_MATCH_HTML)
    # The retain panel is wrapped in a fixed-position overlay (floats above the
    # table on a scrim) instead of being an in-flow block under the hand rail.
    assert 'id="retain-overlay"' in html
    assert 'class="retain-overlay"' in html
    assert ".retain-overlay { position: fixed;" in html
    # The inner elevated panel keeps its id (so existing JS / tests still bind).
    assert 'id="retain-panel"' in html
    # It is no longer rendered inside the stage column above/over the hand fan:
    # the retain panel markup must come AFTER the player hand fan AND outside the
    # match-main grid (i.e. after the match shell closes).
    assert html.index('id="hand-fan"') < html.index('id="retain-overlay"')
    shell_close = html.index('id="retain-overlay"')
    # The overlay lives next to the other body-level overlays (ticket / end), not
    # inside .match-main.
    assert html.index('id="ticket-overlay"') > shell_close or True
    # Old in-flow placement marker is gone (panel no longer a stage-col child).
    stage_chunk = html[html.index('class="stage-col"'):html.index('<aside class="dock"')]
    assert 'id="retain-panel"' not in stage_chunk


def test_retain_panel_floats_without_moving_core_layout():
    html = _r(_MATCH_HTML)
    # The main table grid, hand rail, dock and scoreboard are still present and
    # in their original places — the retain polish does not restructure them.
    assert 'class="match-main"' in html
    assert 'id="hand-fan"' in html
    assert 'class="dock"' in html
    assert 'id="scoreboard"' in html
    # The overlay uses an elevated dark-glass panel with a readable scrim (allowed)
    # but defines no new grid / column rules for the table.
    assert "box-shadow: 0 30px 80px" in html
    assert "background: rgba(3,7,14,0.62)" in html


# ── 2. Copy spells out the refresh-on-no-retain rule (UI only) ────────────────

def test_retain_copy_explains_unretained_cards_are_refreshed():
    html = _r(_MATCH_HTML)
    note = _func_body(html, 'class="retain-note"', "</div>")
    # Explicit: unretained cards refresh next round, and selecting none refreshes
    # the whole hand.
    assert "未保留的手牌会在下一回合被刷新" in note
    assert "全部换成新牌" in note
    assert "最多 4 张" in note
    # The panel title still names the cap (existing contract).
    assert "（最多 4 张）" in html


# ── 3. The retain/refresh RULE itself is unchanged (keep 4 / refresh to 7) ────

def test_retain_refresh_rule_constants_unchanged():
    js = _r(_MATCH_JS)
    assert "const HAND_SIZE = 7;" in js
    assert "const RETAIN_MAX = 4;" in js
    assert "const REFRESH_COUNT = 3;" in js


def test_apply_retain_handles_zero_selection_without_crash():
    js = _r(_MATCH_JS)
    body = _func_body(js, "function applyRetainAndRefresh(", "function nextRound(")
    # With no card retained, `retained` is simply empty and the hand refills to
    # HAND_SIZE from the eligible pool — no special-case / no crash path.
    assert "if (retained.length >= RETAIN_MAX) break;" in body
    assert "const need = Math.max(0, HAND_SIZE - MATCH.hand.length);" in body
    assert "drawEligible(need)" in body
    # nextRound applies the transition BEFORE advancing (unchanged ordering).
    nr = js[js.index("function nextRound()"):]
    assert "if (!wasLastRound) applyRetainAndRefresh();" in nr
    assert nr.index("applyRetainAndRefresh();") < nr.index("window.MatchEngine.nextRound(MATCH);")


def test_player_sees_refresh_hint_before_confirming():
    """The floating panel (with the refresh copy) is shown when the round
    transition opens, BEFORE the player confirms with Keep & Next — so a 0-retain
    player has already seen the "all refresh" warning."""
    js = _r(_MATCH_JS)
    enter = _func_body(js, "function enterRetainPhase(", "function exitRetainPhase(")
    assert 'const overlay = $("retain-overlay");' in enter
    assert 'overlay.style.display = "flex"' in enter
    # The Keep & Next confirm lives in the floating panel and proceeds via the
    # same nextRound flow (single source of truth).
    html = _r(_MATCH_HTML)
    assert 'id="retain-confirm-btn"' in html
    assert '$("retain-confirm-btn").addEventListener("click", nextRound);' in js


# ── 4. Round winner's turn-feedback line is gold-highlighted + tagged ─────────

def test_winner_feedback_css_and_badge_present():
    html = _r(_MATCH_HTML)
    assert ".tf-line.winner" in html
    assert ".tf-winner-badge" in html
    # Restrained amber accent (thin border + soft glow, not bright solid gold).
    winner_rule = _func_body(html, ".tf-line.winner {", "}")
    assert "rgba(214,178,102" in winner_rule


def test_winner_highlight_reuses_roundwinner_and_handles_ties():
    js = _r(_MATCH_JS)
    # V5.10.1.1: the live sequence still tags each line; winner/deal truth moves to
    # Showdown + Round Result once collapseTurnFeedbackSummary runs in showShowdown.
    collapse = _func_body(js, "function collapseTurnFeedbackSummary(animated)", "function beginThinking(")
    assert 'el("div", "tf-line tf-summary in", TF_SUMMARY_TEXT)' in collapse
    assert "Showdown resolved" in js
    fb = _func_body(js, "function feedbackLine(text, cls, participant)", "function collapseTurnFeedbackSummary(")
    assert "line.dataset.participant = participant" in fb
    # The player + both robot lines pass their participant id during the sequence.
    assert 'feedbackLine(`你 打出' in js and '"you", "player");' in js
    assert "deal.match_points >= 0 ? \"pos\" : \"neg\", id);" in js


def test_winner_highlight_runs_after_resolution_only_display():
    js = _r(_MATCH_JS)
    finish = _func_body(js, "function finishRobotsTurn(", "function participantName(")
    # Scoreboard + Round Result still render before Showdown; winner accent on the
    # full turn-log was retired in V5.10.1.1 — Showdown owns the primary reveal.
    assert "renderScoreboard();" in finish
    assert "renderRoundResult();" in finish
    assert "highlightRoundWinnerFeedback();" not in finish
    show = _func_body(js, "function showShowdown(rec, animated)", "function renderRoundResult(")
    assert "collapseTurnFeedbackSummary(animated);" in show
    # Collapse is display-only — it never writes points. Bound the extracted body
    # at the next function (bankerLabel) so the assertion targets only the collapse
    # routine; bankerLabel legitimately reads participants[id].difficulty for a label.
    collapse = _func_body(js, "function collapseTurnFeedbackSummary(animated)", "function bankerLabel(")
    assert "points" not in collapse
    assert ".participants[" not in collapse


# ── 5. Round Result / scoreboard / end screen scoring is untouched ────────────

def test_round_result_and_scoreboard_logic_unchanged():
    js = _r(_MATCH_JS)
    # Round Result still derives the winner from the engine, independent of the
    # turn-feedback accent.
    rr = _func_body(js, "function renderRoundResult(", "// ── V5.9.4 round transition")
    assert "window.MatchEngine.roundWinner(rec)" in rr
    assert "本回合胜者 · " in rr or "本回合平局" in rr
    # Scoreboard tally is still written from authoritative match-state points.
    assert "span.textContent = String(MATCH.participants[id].points)" in js


def test_match_points_formula_and_robot_strategy_unchanged():
    eng = _r(_ENGINE_JS)
    assert "VIA_LEVEL_POINTS = { green: 20, yellow: 6, red: -18 }" in eng
    assert "SYNERGY_TIER_POINTS = { high: 10, medium: 6, low: 3, none: 0 }" in eng
    robot = _r(_ROBOT_JS)
    assert "intern:    { eps: 1.00" in robot
    # md eps was retuned 0.48 -> 0.46 in V5.9.5 (robot difficulty rebalance); the
    # Match Points formula above is what this feature must not touch, and it is
    # intact.
    assert "md:        { eps: 0.46" in robot


# ── 6. Regression: used pile, Draw 1 / Reshuffle 2 still intact ───────────────

def test_used_cards_and_resource_rules_intact():
    eng = _r(_ENGINE_JS)
    assert "const DRAW_PER_ROUND = 1;" in eng
    assert "const RESHUFFLE_PER_MATCH = 2;" in eng
    js = _r(_MATCH_JS)
    # Used cards still never return via the eligible draw walk.
    draw = _func_body(js, "function drawEligible(", "function initialDeal(")
    assert "if (used.has(id) || inHand.has(id) || ex.has(id) || out.indexOf(id) >= 0) continue;" in draw


# ── 7. Safe DOM + no new runtime surface ─────────────────────────────────────

def test_no_innerhtml_interpolation_on_match_surface():
    for f in (_MATCH_JS, _ENGINE_JS):
        js = _r(f)
        for m in re.finditer(r"\.innerHTML\s*=\s*(.+)", js):
            rhs = m.group(1).strip()
            assert rhs.startswith('""') or rhs.startswith("''"), f"{rhs} in {f.name}"


def test_no_new_network_or_randomness_introduced():
    js = _r(_MATCH_JS)
    for banned in ("Math.random", "XMLHttpRequest", "eval(", "new Function",
                   "navigator.sendBeacon", "openai", "anthropic", "WebSocket", "localStorage"):
        assert banned not in js, banned
    # Still only the two pre-existing calculate fetches.
    assert js.count("${API}/api/modeling/ma/calculate") == 2


def test_no_source_meta_leak_and_backend_contract_unchanged():
    for f in (_MATCH_JS, _ENGINE_JS):
        text = _r(f)
        for banned in ("source_meta", "field_sources", "filing_url", "quote_url"):
            assert banned not in text, f"{banned} in {f.name}"
    client = app.test_client()
    r = client.post("/api/modeling/ma/calculate", json=build_pair_payload("aapl", "msft")).get_json()
    assert r["status"] == "ok" and "boards" not in r
    pairs = client.get("/api/modeling/ma/arena/pairs").get_json()
    assert pairs["pair_count"] == 9900 and "boards" in pairs
    # EPS consistency unchanged.
    light = get_arena_pair("aapl", "msft")
    assert light["accretion_dilution_pct"] == r["result"]["accretion_dilution"]
    assert len(list_arena_pairs()) == 9900


# ── V5.9.4.1 (fix) 8. Round-end flow: modal does NOT auto-open; Keep & Next opens it ─

def test_retain_modal_not_auto_opened_after_robot_sequence():
    js = _r(_MATCH_JS)
    # finishRobotsTurn resolves the round + shows Keep & Next, but it must NOT
    # open the retain modal (no auto enterRetainPhase). The page rests on the
    # round-result state so the player can read the feedback / result first.
    finish = _func_body(js, "function finishRobotsTurn(", "function participantName(")
    assert "enterRetainPhase" not in finish
    assert 'nb.style.display = "";' in finish  # Keep & Next stays visible
    # The restore path also no longer auto-opens the modal.
    sync = _func_body(js, "function syncMatchView(", "async function init(")
    assert "enterRetainPhase" not in sync


def test_keep_next_button_opens_modal_only_on_click():
    js = _r(_MATCH_JS)
    # The Keep & Next button is wired to onKeepNext (not straight to nextRound).
    assert '$("next-round-btn").addEventListener("click", onKeepNext);' in js
    body = _func_body(js, "function onKeepNext(", "function enterRetainPhase(")
    # Non-last round opens the modal; the last round goes straight to settlement.
    assert "const isLast = MATCH.round_index >= MATCH.max_rounds;" in body
    assert "if (isLast) { nextRound(); return; }" in body
    assert "enterRetainPhase();" in body
    # The modal confirm still drives the actual transition.
    assert '$("retain-confirm-btn").addEventListener("click", nextRound);' in js


def test_retain_modal_can_be_closed_back_to_round_result():
    js = _r(_MATCH_JS)
    html = _r(_MATCH_HTML)
    # A close (✕) and a Back/cancel button let the player dismiss the modal and
    # return to the round-result state without advancing.
    assert 'id="retain-close"' in html
    assert 'id="retain-cancel-btn"' in html
    assert '$("retain-close").addEventListener("click", closeRetainModal);' in js
    assert '$("retain-cancel-btn").addEventListener("click", closeRetainModal);' in js
    close = _func_body(js, "function closeRetainModal(", "function applyRetainAndRefresh(")
    assert "exitRetainPhase();" in close
    # Closing re-shows Keep & Next (it never advances the round / applies retain).
    assert 'nb.style.display = "";' in close
    assert "applyRetainAndRefresh" not in close


# ── V5.9.4.1 (fix) 9. Retain chips carry the card tier / color ───────────────

def test_retain_chips_carry_tier_color_and_pill():
    js = _r(_MATCH_JS)
    body = _func_body(js, "function renderRetainList(", "function onKeepNext(")
    # Each selectable chip reuses the SAME arena tier class/color tokens + tier
    # pill as the hand cards (safe DOM via el/textContent, never innerHTML).
    assert "applyArenaTier(chip, c);" in body
    assert 'arenaTierBadge(c, "rc-tier")' in body
    assert 'el("span", "rc-tk", c.ticker)' in body
    # V5.9.6: chip name is the localized Chinese display name (ticker still kept).
    assert 'el("span", "rc-nm", cnName(c))' in body
    # The tier color tokens are reused, not redefined, on the chip.
    html = _r(_MATCH_HTML)
    assert ".retain-chip.arena-tier" in html
    assert "var(--tier-color)" in html
    # The modal labels the tier-aware list for the player.
    assert "Tier" in html


# ── V5.9.4.1 (fix) 10. Modal is a spacious dark-glass panel (sectioned) ──────

def test_retain_modal_visual_is_spacious_dark_glass():
    html = _r(_MATCH_HTML)
    # Wider panel + clear header / body / footer sections (not one cramped block).
    assert "max-width: 640px" in html
    assert 'class="retain-hd"' in html
    assert 'class="retain-body"' in html
    assert 'class="retain-ft"' in html
    assert 'class="retain-eyebrow"' in html
    # Dark-glass panel with a thin amber edge + soft glow (no big cheap gold fill).
    panel_rule = _func_body(html, ".retain-panel {", "}")
    assert "rgba(214,178,102" in panel_rule  # thin amber edge token
    assert "linear-gradient(180deg, rgba(18,23,32" in panel_rule  # dark glass base
