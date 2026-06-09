"""V5.9.2 Match Loop Shell — five-round match tests.

The Match turns the existing Arena sandbox (real seed deck + precomputed pairs +
deterministic Robot Opponent) into a playable five-round game: a Setup lobby
picks two robot opponents, then the formal Match table runs a turn loop, a LOCAL
Match Points scoreboard, and a settlement end screen.

Like the rest of the V5 front-end, the deterministic game logic lives in JS
(`match_engine.js`, pure/no-DOM) and is wired into a dedicated Match table page.
These tests lock the contract via source/static assertions (the repo convention)
plus backend data checks; live turn-by-turn play is covered by the documented
browser smoke. They assert:

* the Setup + Match routes serve and Setup exposes two robot difficulty pickers
  + randomize + start,
* the Match table reads the two-robot setup config and has NO in-game difficulty
  selector,
* a pure match engine with MAX_ROUNDS=5, a per-round player/robot turn flow, a
  deterministic Match Points score, self-deal-free + duplicate-free robot picks,
  and a complete-after-5-rounds lifecycle,
* Match Points is a LOCAL game score — never an Overall Score, never on the
  Economic/Viability boards, never in calculate, no source_meta stored,
* the Match reuses the V5.8 Queue (light only) + V5.4 Ticket (EPS consistency),
* no LLM / network / randomness / innerHTML interpolation on the match surface,
* engine / synergy / viability / calculate / pairs contract unchanged.
"""

import re
from pathlib import Path

from app import app
from modeling.ma.precompute import build_pair_payload, get_arena_pair, list_arena_pairs


_ROOT = Path(__file__).resolve().parents[1]
_SETUP_HTML = _ROOT / "static" / "modeling" / "arena_match_setup.html"
_SETUP_JS = _ROOT / "static" / "modeling" / "js" / "match_setup.js"
_MATCH_HTML = _ROOT / "static" / "modeling" / "arena_match.html"
_MATCH_JS = _ROOT / "static" / "modeling" / "js" / "arena_match.js"
_ENGINE_JS = _ROOT / "static" / "modeling" / "js" / "match_engine.js"
_WARROOM_HTML = _ROOT / "static" / "modeling" / "arena.html"
_WARROOM_JS = _ROOT / "static" / "modeling" / "js" / "arena.js"
_QUEUE_JS = _ROOT / "static" / "modeling" / "js" / "deal_queue.js"
_ROBOT_JS = _ROOT / "static" / "modeling" / "js" / "robot_opponent.js"


def _r(p):
    return p.read_text(encoding="utf-8")


# ── 1. Routes serve ─────────────────────────────────────────────────────────

def test_setup_route_serves():
    client = app.test_client()
    resp = client.get("/modeling/ma/arena/match/setup")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Match Setup" in html
    assert "/static/modeling/js/match_setup.js" in html


def test_match_play_route_serves():
    client = app.test_client()
    resp = client.get("/modeling/ma/arena/match/play")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "DEAL ARENA · MATCH" in html
    assert "/static/modeling/js/arena_match.js" in html


def test_match_play_route_serves_with_passthrough_query():
    client = app.test_client()
    resp = client.get("/modeling/ma/arena/match/play?acq=meta&tgt=googl")
    assert resp.status_code == 200
    assert "/static/modeling/js/arena_match.js" in resp.get_data(as_text=True)


# ── 2/3. Setup page: two robot difficulty selectors + randomize + start ─────

def test_setup_has_two_robot_seats():
    html = _r(_SETUP_HTML)
    js = _r(_SETUP_JS)
    assert 'id="ms-seats"' in html
    # Two seats are configured in the setup state.
    assert "{ seat: 1, difficulty:" in js
    assert "{ seat: 2, difficulty:" in js


def test_setup_offers_all_five_difficulties_per_seat():
    js = _r(_SETUP_JS)
    # The five rungs of the ladder are offered as choices.
    for d in ("intern", "analyst", "associate", "vp", "md"):
        assert d in js, d
    assert "实习生" in js and "董事总经理" in js


def test_setup_has_randomize_and_start():
    html = _r(_SETUP_HTML)
    js = _r(_SETUP_JS)
    assert 'id="ms-randomize-all"' in html and "全部随机" in html
    assert 'id="ms-start-match"' in html
    assert "随机抽取难度" in js          # per-seat randomize
    assert "function randomizeAll(" in js
    assert "function startMatch(" in js


def test_setup_randomness_is_controlled_not_math_random():
    """Difficulty randomize uses a controlled session-seeded LCG, never
    Math.random, and it only drives the UI — it never touches finance/strategy."""
    js = _r(_SETUP_JS)
    assert "Math.random" not in js
    assert "function seededInt(" in js
    assert "function randomDifficulty(" in js


def test_setup_persists_config_and_navigates_to_match():
    js = _r(_SETUP_JS)
    assert 'SETUP_STORAGE_KEY = "ma_match_setup_v1"' in js
    assert "sessionStorage.setItem(SETUP_STORAGE_KEY" in js
    assert "/modeling/ma/arena/match/play" in js


# ── 4/5. Match table reads config + NO in-game difficulty selector ──────────

def test_match_reads_two_robot_setup_config():
    js = _r(_MATCH_JS)
    assert 'SETUP_STORAGE_KEY = "ma_match_setup_v1"' in js
    assert "function loadSetupConfig(" in js
    # V5.9.6.2: a new match is built via startNewMatch (fresh seed + clean table),
    # which wraps MatchEngine.createMatch.
    assert "startNewMatch(MATCH_CONFIG)" in js
    assert "window.MatchEngine.createMatch(config)" in js
    # Two seated robots are rendered from the config.
    assert 'id="seat-robot-1"' in _r(_MATCH_HTML)
    assert 'id="seat-robot-2"' in _r(_MATCH_HTML)
    assert "robot_1" in js and "robot_2" in js


def test_match_has_no_ingame_difficulty_selector():
    """The formal match locks difficulty at setup — the in-match table must NOT
    carry the sandbox difficulty selector / robot control bar."""
    html = _r(_MATCH_HTML)
    assert "data-diff=" not in html
    assert "robot-diff-btn" not in html
    assert 'class="robot-bar"' not in html
    js = _r(_MATCH_JS)
    assert "setRobotDifficulty" not in js


# ── 6/12. Pure engine: MAX_ROUNDS=5 + complete-after-5 lifecycle ────────────

def test_engine_max_rounds_is_five():
    js = _r(_ENGINE_JS)
    assert "const MAX_ROUNDS = 5;" in js
    assert "max_rounds: MAX_ROUNDS" in js


def test_engine_phase_enum_and_lifecycle():
    js = _r(_ENGINE_JS)
    for phase in ("waiting_player", "robots_playing", "round_result", "match_complete"):
        assert phase in js, phase
    assert "function nextRound(state)" in js
    # After the last round, the match completes.
    assert "state.round_index >= state.max_rounds" in js
    assert "state.phase = PHASE.MATCH_COMPLETE" in js


# ── 7. Player plays one deal per round ──────────────────────────────────────

def test_engine_player_plays_one_deal_per_round():
    js = _r(_ENGINE_JS)
    assert "function playerPlay(state, acquirerId, targetId, getPair, cardById)" in js
    # Only valid in the waiting_player phase, then it advances to robots_playing.
    assert 'if (!state || state.phase !== PHASE.WAITING_PLAYER) return { ok: false, reason: "phase" };' in js
    assert "state.phase = PHASE.ROBOTS_PLAYING" in js
    assert "rec.player = deal" in js


# ── 8/9/10. Two robots each play one valid, non-self, non-duplicate deal ────

def test_engine_two_robots_play_each_round():
    js = _r(_ENGINE_JS)
    assert "function robotsPlay(state, pairs, getPair, cardById, selectFn)" in js
    assert "state.participants.robot_1.difficulty" in js
    assert "state.participants.robot_2.difficulty" in js
    assert "rec.robot_1 = d1" in js and "rec.robot_2 = d2" in js


def test_engine_robots_avoid_duplicate_pair_in_same_round():
    js = _r(_ENGINE_JS)
    # Robot 2's exclude set includes everything already played this match AND
    # Robot 1's just-played pick, so the two never play the exact same directed
    # pair in one round.
    assert "const baseExclude = playedKeys(state).slice();" in js
    assert "baseExclude.push(dirKey(d1.acquirer_id, d1.target_id));" in js


def test_engine_no_self_deal():
    js = _r(_ENGINE_JS)
    # Player path rejects self-deals; robot path delegates to RobotOpponent which
    # already skips `acquirer_id === target_id`.
    assert 'acquirerId === targetId) return { ok: false, reason: "invalid" };' in js
    robot = _r(_ROBOT_JS)
    assert "pair.acquirer_id === pair.target_id) continue;" in robot


# ── 11. Match state records up to 15 deals (3 participants x 5 rounds) ───────

def test_engine_records_up_to_15_deals():
    js = _r(_ENGINE_JS)
    # Each play pushes exactly one light deal record onto the flat deals list.
    assert "state.deals.push(deal)" in js     # player
    assert "state.deals.push(d1)" in js       # robot 1
    assert "state.deals.push(d2)" in js       # robot 2
    # 3 participants x MAX_ROUNDS(5) = 15 is the ceiling; the universe is big
    # enough that duplicate-avoidance never runs out of pairs.
    assert len(list_arena_pairs()) == 9900


# ── 13. Match Points deterministic + explainable ────────────────────────────

def test_engine_match_points_deterministic_and_explainable():
    js = _r(_ENGINE_JS)
    assert "function matchPoints(pair, cardById)" in js
    assert "function matchPointsBreakdown(pair, cardById)" in js
    # No randomness anywhere in the scoring / engine.
    assert "Math.random" not in js
    # Fixed weight tables (a deterministic, explainable sum — not a black box).
    assert "VIA_LEVEL_POINTS = { green: 20, yellow: 6, red: -18 }" in js
    assert "SYNERGY_TIER_POINTS = { high: 10, medium: 6, low: 3, none: 0 }" in js
    # The score reads only existing LIGHT fields.
    for field in ("accretion_dilution_pct", "viability_level", "viability_flags_count",
                  "default_synergy_tier", "synergy_status"):
        assert field in js, field


def test_engine_round_and_match_winner_deterministic():
    js = _r(_ENGINE_JS)
    assert "function roundWinner(rec)" in js
    assert "function winner(state)" in js
    assert "function rankings(state)" in js
    # Deterministic tie-break by the fixed participant order, never randomness.
    assert "order[a.id] - order[b.id]" in js
    assert 'return tie ? "draw" : best.id;' in js


# ── 14. No Overall Score wording anywhere on the match surface ──────────────

def test_match_surface_has_no_overall_score():
    for f in (_SETUP_HTML, _SETUP_JS, _MATCH_HTML, _MATCH_JS, _ENGINE_JS):
        text = _r(f)
        for banned in ("综合评分", "Overall Score", "胜率", "win_rate", "overall_score"):
            assert banned not in text, f"{banned} in {f.name}"


# ── 15. Match Points never enters the boards / calculate API ────────────────

def test_match_points_is_frontend_only_not_in_backend_contract():
    # The engine never calls calculate / the network; match_points is local.
    engine = _r(_ENGINE_JS)
    for banned in ("fetch(", "XMLHttpRequest", "/api/", "calculate", "boards",
                   "eval(", "new Function", "Math.random"):
        assert banned not in engine, banned
    # The backend calculate + pairs responses carry no match_points field.
    client = app.test_client()
    full = client.post("/api/modeling/ma/calculate", json=build_pair_payload("aapl", "msft")).get_json()
    assert "match_points" not in full and "match_points" not in full.get("result", {})
    pairs = client.get("/api/modeling/ma/arena/pairs").get_json()
    assert all("match_points" not in p for p in pairs["pairs"])
    assert "boards" in pairs and "match_points" not in str(pairs["boards"])


# ── 16. End screen shows compact review, not a raw full-result dump ─────────

def test_end_screen_is_compact_review():
    html = _r(_MATCH_HTML)
    js = _r(_MATCH_JS)
    assert 'id="end-screen"' in html
    assert 'id="end-rounds"' in html and 'id="end-totals"' in html
    assert 'id="end-winner"' in html and 'id="end-review"' in html
    # Compact: small per-deal chips, not a 15-row full table dump.
    assert "function buildDealChip(" in js
    assert "compact" in html.lower() or "compact" in js.lower() or "小卡片" in html
    # The calculating beat + staged reveal exist (light CSS animation, no library).
    assert "正在结算交易表现" in html
    assert "function revealStaged(" in js
    assert "Play Again" in html and "function playAgain(" in js
    assert "Add Best Deals" in html and "function addBestDeals(" in js


# ── 17/18/22. Played deals add to the (light) Queue; no source_meta stored ──

def test_played_deals_can_add_to_queue_light_only():
    js = _r(_MATCH_JS)
    # Player + robot deals reuse the shared Queue with a light added_from string.
    assert "function addDealToQueue(" in js
    assert '"match_player"' in js
    assert "`robot_${p.difficulty}`" in js
    assert "window.DealQueue.add(item)" in js
    # The queue stores only the whitelist (asserted in the V5.8 module).
    assert '"added_from"' in _r(_QUEUE_JS)


def test_match_stores_no_source_meta_anywhere():
    # The pure engine (which builds the match STATE records) carries no heavy
    # provenance at all.
    engine = _r(_ENGINE_JS)
    for banned in ("source_meta", "field_sources", "filing_url", "quote_url",
                   "triggered_tags", "audit_trail"):
        assert banned not in engine, f"{banned} in {_ENGINE_JS.name}"
    # The match controller may DISPLAY the V5.4 Ticket's triggered_tags audit
    # (read from the calculate result, never stored), but it must never store the
    # deck source-metadata trail in match state / queue items.
    match_js = _r(_MATCH_JS)
    for banned in ("source_meta", "field_sources", "filing_url", "quote_url"):
        assert banned not in match_js, f"{banned} in {_MATCH_JS.name}"


# ── 19. Ticket / light / calculate EPS consistency for match deals ──────────

def test_match_deal_eps_consistent_light_equals_calculate():
    client = app.test_client()
    for acq, tgt in [("meta", "googl"), ("aapl", "msft"), ("nvda", "avgo"), ("dis", "hd")]:
        light = get_arena_pair(acq, tgt)
        full = client.post(
            "/api/modeling/ma/calculate", json=build_pair_payload(acq, tgt)
        ).get_json()["result"]
        assert light["accretion_dilution_pct"] == full["accretion_dilution"]


def test_match_ticket_reuses_calculate_no_second_engine():
    js = _r(_MATCH_JS)
    assert "function openTicket(" in js
    assert "buildPayload()" in js
    assert "accretion_dilution =" not in js  # never re-derives EPS


def test_match_play_has_no_deal_studio_jump():
    """V5.10.4.x Match Navigation Safety: leaving Match Play resets the live
    match, so neither the right current-deal card nor the Deal Ticket modal may
    deep-link into Deal Studio. The in-match Deal Ticket modal trigger itself is
    kept (it opens an overlay and never navigates away)."""
    html = _r(_MATCH_HTML)
    js = _r(_MATCH_JS)
    # No Deal Studio navigation link / prompt anywhere on the Match surface.
    assert 'id="rc-studio-btn"' not in html
    assert 'id="tk-studio-btn"' not in html
    assert "在 Deal Studio 中查看详情" not in html
    assert "在 Deal Studio 中查看完整参数" not in html
    # The JS no longer builds a Deal Studio deep link on the Match surface.
    assert "/modeling/ma?acq=" not in js
    # The in-match Deal Ticket modal is preserved (overlay, not a page jump).
    assert 'id="rc-ticket-btn"' in html
    assert 'id="ticket-overlay"' in html


# ── 20. Robot/match runtime: no network / LLM / randomness / calculate loop ─

def test_match_no_network_llm_randomness():
    js = _r(_MATCH_JS)
    for banned in ("Math.random", "XMLHttpRequest", "eval(", "new Function",
                   "navigator.sendBeacon", "openai", "anthropic", "WebSocket"):
        assert banned not in js, banned


def test_match_robots_use_precomputed_pairs_no_calculate_loop():
    js = _r(_MATCH_JS)
    assert "Object.values(PAIRS_INDEX)" in js
    assert "window.MatchEngine.robotsPlay(MATCH, pairs" in js
    # Only the two pre-existing calculate fetches (single-deal fallback + Ticket).
    assert js.count("${API}/api/modeling/ma/calculate") == 2


# ── 21. Safe DOM (no innerHTML interpolation) on the whole match surface ────

def test_match_surface_uses_safe_dom():
    for f in (_SETUP_JS, _MATCH_JS, _ENGINE_JS):
        js = _r(f)
        for m in re.finditer(r"\.innerHTML\s*=\s*(.+)", js):
            rhs = m.group(1).strip()
            assert rhs.startswith('""') or rhs.startswith("''"), f"{rhs} in {f.name}"
    # The match controller builds DOM via el()/textContent.
    assert "function el(tag, cls, text)" in _r(_MATCH_JS)
    assert "node.textContent = text" in _r(_MATCH_JS)


# ── Clear Deal never resets the match; Play Again is the only reset ──────────

def test_clear_deal_keeps_match_state_play_again_resets():
    js = _r(_MATCH_JS)
    assert "function clearSelection(" in js
    # clearSelection only touches `selected` — it must not recreate MATCH.
    clear_body = js[js.index("function clearSelection("):js.index("function renderSlot(")]
    assert "createMatch" not in clear_body and "startNewMatch" not in clear_body
    # Play Again is the single reset of match state (fresh seed via startNewMatch).
    play_again = js[js.index("function playAgain("):]
    assert "startNewMatch(MATCH_CONFIG)" in play_again


# ── War Room Start Match entry (existing Start Tabletop untouched) ──────────

def test_warroom_has_start_match_entry_and_keeps_tabletop():
    html = _r(_WARROOM_HTML)
    js = _r(_WARROOM_JS)
    assert 'id="start-match-btn"' in html
    assert "/modeling/ma/arena/match/setup" in html
    assert "Start Match" in html
    # The existing Start Tabletop entry is untouched.
    assert 'id="start-tabletop-btn"' in html
    assert "/modeling/ma/arena/play" in html
    # The Start Match href carries the current selection too.
    assert "start-match-btn" in js
    assert "/modeling/ma/arena/match/setup" in js


# ── Module load order on the match page ─────────────────────────────────────

def test_match_loads_modules_in_dependency_order():
    html = _r(_MATCH_HTML)
    assert html.index("deal_queue.js") < html.index("robot_opponent.js")
    assert html.index("robot_opponent.js") < html.index("match_engine.js")
    assert html.index("match_engine.js") < html.index("js/arena_match.js")


# ── V5.9.2.1 Scoreboard DOM id consistency (in-match robot tallies) ─────────

def test_scoreboard_dom_ids_match_js_query():
    """The top scoreboard span/chip ids in the HTML must match what
    renderScoreboard() looks up, so the in-match robot tallies actually refresh
    instead of sticking at 0 MP. Participant keys use underscores (`robot_1`);
    the DOM ids use hyphens (`score-robot-1`)."""
    html = _r(_MATCH_HTML)
    js = _r(_MATCH_JS)
    # The controller bridges underscore participant ids to hyphen DOM ids.
    assert "function scoreDomId(id) { return id.replace(" in js
    assert "$(`score-${dom}`)" in js
    assert "$(`score-chip-${dom}`)" in js
    # Every participant's score span + chip exists in the HTML under the hyphen id.
    for pid in ("player", "robot_1", "robot_2"):
        dom = pid.replace("_", "-")
        assert f'id="score-{dom}"' in html, f"missing score-{dom}"
        assert f'id="score-chip-{dom}"' in html, f"missing score-chip-{dom}"
    # The old underscore lookup that left robots at 0 MP must be gone.
    assert "$(`score-${id}`)" not in js
    assert "$(`score-chip-${id}`)" not in js


def test_scoreboard_score_spans_default_to_zero_then_update():
    """The robot score spans start at 0 in markup and are the exact nodes the
    engine total is written into each turn (parity with end-screen totals)."""
    html = _r(_MATCH_HTML)
    js = _r(_MATCH_JS)
    for dom in ("score-robot-1", "score-robot-2"):
        assert f'<span id="{dom}">0</span>' in html, dom
    # The tally is written from the authoritative match-state points.
    assert "span.textContent = String(MATCH.participants[id].points)" in js


# ── Backend contract unchanged ──────────────────────────────────────────────

def test_calculate_and_pairs_contract_unchanged():
    client = app.test_client()
    r = client.post("/api/modeling/ma/calculate", json=build_pair_payload("aapl", "msft")).get_json()
    assert r["status"] == "ok" and "boards" not in r
    pairs = client.get("/api/modeling/ma/arena/pairs").get_json()
    assert pairs["pair_count"] == 9900 and "boards" in pairs
