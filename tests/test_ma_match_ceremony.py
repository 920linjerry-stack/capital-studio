"""V5.10.3 Match Ceremony / End Screen (First Pass) tests.

After the player finishes all five rounds the End Screen is no longer a results
table — it is an **investment-committee verdict ceremony**:

  1. Verdict header  — winner reveal (spotlight + identity + final score + line).
  2. Match trajectory — 5 round nodes, each showing that round's winner + MP.
  3. Best deals       — one highlight card per participant; the overall top-MP
                        deal is tagged "Deal of the Match".
  4. Detailed review  — the full round table + 15-deal compact review, preserved
                        (collapsed), plus Play Again / War Room actions.

It is presentation only. It changes NO Match Points formula, win/loss rule, robot
strategy, engine/API/deck/precompute, source_meta, hand lifecycle, Queue, or the
Showdown / identity / robot-overlap layers. Every value is READ from the existing
match state (rankings / winner / round records / bestDealFor). The final line is a
finite deterministic pool — no runtime LLM / fetch / RNG.

Per repo convention the game layer lives in JS; the contract is locked via
source/static assertions plus a Python port of the deterministic line picker and
backend data checks. The browser smoke covers the live five-round ceremony.
"""

import re
from pathlib import Path

from app import app
from modeling.ma.precompute import build_pair_payload, get_arena_pair, list_arena_pairs


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


# ── Python port of the deterministic final-line picker (opponent_identity.js) ──
# Mirrors hashMix / pickFromPool and the finite final pools. The mirror is kept
# honest by asserting each pooled line also appears verbatim in the JS source.

ROOM_VERDICT = {
    "player": [
        "这张桌子今晚是你的。",
        "委员会听见了你的交易逻辑。",
    ],
    "draw": [
        "委员会未能形成多数意见 · 平局收场。",
        "这一场，没有人完全说服整张桌子。",
    ],
}

FINAL_WINNER = {
    "intern": ["我……我真的赢了这张桌子？", "EPS 还是有用的，对吧？"],
    "analyst": ["模型站住了，结果自然会跟上。", "这场是数字纪律的胜利。"],
    "associate": ["平衡比激进更耐打。", "这五轮，结构赢了噪音。"],
    "vp": ["能被委员会买账的故事，才是好交易。", "这场我赢在叙事，也赢在执行路径。"],
    "md": ["资本会留在最克制的人手里。", "纪律，比兴奋更贵。"],
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


def pick_from_pool(pool, seed, *keys):
    if not pool:
        return ""
    return pool[hash_mix(seed, *keys) % len(pool)]


def pick_final_line(outcome, identity, seed):
    if outcome == "player":
        return pick_from_pool(ROOM_VERDICT["player"], seed, "final", "player")
    if outcome == "draw":
        return pick_from_pool(ROOM_VERDICT["draw"], seed, "final", "draw")
    if not identity:
        return ""
    pool = FINAL_WINNER.get(identity["difficulty"], FINAL_WINNER["analyst"])
    return pick_from_pool(pool, seed, "final", identity["seat"], identity["difficulty"])


# ── 1. Verdict header present (winner reveal + score + final line) ───────────

def test_verdict_header_present_in_html():
    html = _r(_MATCH_HTML)
    assert 'id="reveal-verdict"' in html
    assert 'id="verdict-stage"' in html
    assert 'id="verdict-sigil"' in html
    assert 'id="end-winner"' in html          # winner reveal text (kept id)
    assert 'id="verdict-score"' in html        # final score line
    assert 'id="verdict-line"' in html         # final scripted line
    assert "投资委员会终审" in html and "Committee Verdict" in html
    # The verdict header is the first thing inside the end content.
    assert html.index('id="reveal-verdict"') < html.index('id="reveal-trajectory"')
    assert html.index('id="reveal-trajectory"') < html.index('id="reveal-best"')


def test_verdict_builder_reads_existing_winner_and_score():
    js = _r(_MATCH_JS)
    body = _func_body(js, "function buildVerdict(", "function buildTrajectory(")
    # Winner / ranking come straight from the engine — no new win calculation.
    assert "window.MatchEngine.winner(MATCH)" in body
    assert "window.MatchEngine.rankings(MATCH)" in body
    # The verdict never compares points itself.
    assert ".points >" not in body
    assert "match_points" not in body


# ── 2. Winner identity: banker = name + rank; player = player-win copy ───────

def test_winner_identity_banker_name_rank_player_and_draw():
    js = _r(_MATCH_JS)
    body = _func_body(js, "function buildVerdict(", "function buildTrajectory(")
    # Player win copy.
    assert "你赢得了投委会" in body and "You Won the Committee" in body
    # Banker win = display name + rank (e.g. "Vivienne Roark · 董事总经理 赢得本场").
    assert "ident.displayName" in body
    assert "ident.rankCn" in body
    assert "赢得本场" in body
    # A draw is a split decision, not a fake winner.
    assert "平局" in body and "Split Decision" in body
    # Banker win lights the sigil (presentation only).
    assert "renderSigil(sigil, ident, 44)" in body


def test_winner_spotlight_classes_present():
    html = _r(_MATCH_HTML)
    # Restrained committee-amber spotlight; player blue; draw neutral — no confetti.
    assert ".verdict-stage::before" in html
    assert ".verdict-stage.win-you::before" in html
    assert ".verdict-stage.win-draw::before" in html
    for banned in ("confetti", "slot-machine", "slotmachine"):
        assert banned not in html.lower()
    js = _r(_MATCH_JS)
    body = _func_body(js, "function buildVerdict(", "function buildTrajectory(")
    assert 'stage.classList.add("win-you")' in body
    assert 'stage.classList.add("win-bot")' in body
    assert 'stage.classList.add("win-draw")' in body


# ── 3. Five-round trajectory: 5 nodes, each shows round winner / draw + MP ───

def test_trajectory_has_five_nodes_each_with_winner_and_mp():
    html = _r(_MATCH_HTML)
    js = _r(_MATCH_JS)
    assert 'id="end-trajectory"' in html
    assert "五回合轨迹" in html and "Match Trajectory" in html
    body = _func_body(js, "function buildTrajectory(", "function buildBestCard(")
    # Exactly max_rounds (5) nodes, one per round.
    assert "(MATCH && MATCH.max_rounds) || window.MatchEngine.MAX_ROUNDS" in body
    assert "for (let i = 0; i < maxRounds; i++)" in body
    # Each node reads the existing round winner (no new rule).
    assert "window.MatchEngine.roundWinner(rec)" in body
    # Each node shows who won (你 / banker short name / 平局) + the winning MP.
    assert "`traj-node ${cls}`" in body
    assert "participantNameShort(winnerId)" in body
    assert '"平局"' in body
    assert "signed(winDeal.match_points)" in body
    # The eventual match winner's nodes get a subtle ring.
    assert 'node.classList.add("match-winner")' in body
    assert ".traj-node.match-winner .traj-dot" in html


def test_trajectory_node_winner_classes_present():
    html = _r(_MATCH_HTML)
    assert ".traj-node.win-you .traj-dot" in html
    assert ".traj-node.win-bot .traj-dot" in html
    assert ".traj-node.win-draw .traj-dot" in html


# ── 4. Best deal cards: 3 participants, each deal / MP / EPS / viability ─────

def test_best_deal_cards_for_each_participant():
    html = _r(_MATCH_HTML)
    js = _r(_MATCH_JS)
    assert 'id="end-best-deals"' in html
    assert "本场最佳交易" in html and "Best Deals" in html
    deals = _func_body(js, "function buildBestDeals(", "function buildEndContent(")
    # One best card per participant, read from the engine's bestDealFor.
    assert 'for (const id of ["player", "robot_1", "robot_2"])' in deals
    assert "window.MatchEngine.bestDealFor(MATCH, id)" in deals
    assert "buildBestCard(id, bests[id], domId)" in deals
    card = _func_body(js, "function buildBestCard(", "function buildBestDeals(")
    # Deal ACQ→TGT, EPS, MP, viability lamp — all from the existing light record.
    assert 'el("span", "a", deal.acquirer_ticker || "—")' in card
    assert 'el("span", "t", deal.target_ticker || "—")' in card
    assert "const epsText = pct(deal.accretion_dilution_pct);" in card
    assert 'el("span", "best-mp", `${signed(deal.match_points)} MP`)' in card
    assert 'el("div", `best-via ${deal.viability_level || "green"}`)' in card
    # A participant with no deal gets a muted placeholder, not a crash.
    assert 'el("div", "best-empty", "本局无已出交易 · No deal")' in card


def test_best_deal_player_blue_banker_rank_color():
    js = _r(_MATCH_JS)
    card = _func_body(js, "function buildBestCard(", "function buildBestDeals(")
    # Player card = owner-you (blue); banker card = owner-bot + rank visual color.
    assert 'best-card owner-${id === "player" ? "you" : "bot"}' in card
    assert "applyRankVisual(card, ident.difficulty)" in card
    html = _r(_MATCH_HTML)
    assert ".best-card.owner-you" in html
    assert ".best-card.owner-bot" in html


# ── 5. Deal of the Match: overall highest-MP best deal tagged; draw graceful ──

def test_deal_of_the_match_marks_top_mp_only():
    js = _r(_MATCH_JS)
    deals = _func_body(js, "function buildBestDeals(", "function buildEndContent(")
    # The single highest-MP best deal across the three is the Deal of the Match.
    assert "let domId = null;" in deals
    assert "let domMp = null;" in deals
    assert "const mp = numOrZero(best.match_points);" in deals
    assert "if (domMp === null || mp > domMp) { domMp = mp; domId = id; }" in deals
    card = _func_body(js, "function buildBestCard(", "function buildBestDeals(")
    # Only the dom card gets the badge; it never renders when there is no deal.
    assert "if (deal && id === domId) {" in card
    assert 'card.classList.add("dom")' in card
    assert 'el("div", "best-dom-badge", "本场最佳交易 · Deal of the Match")' in card
    html = _r(_MATCH_HTML)
    assert ".best-dom-badge" in html


# ── 6. Final scripted line: finite pool, deterministic, no RNG / fetch / LLM ──

def test_final_line_pools_exist_in_identity_source():
    js = _r(_ID_JS)
    assert "const ROOM_VERDICT = {" in js
    assert "function pickFinalLine(" in js
    assert "pickFinalLine," in js  # exported
    # Player / draw room verdict lines + each rank's final_winner line are present.
    for line in ROOM_VERDICT["player"] + ROOM_VERDICT["draw"]:
        assert line in js, line
    for rank, lines in FINAL_WINNER.items():
        for line in lines:
            assert line in js, f"{rank}:{line}"


def test_final_line_selection_uses_hash_mix_not_random():
    js = _r(_ID_JS)
    body = _func_body(js, "function pickFinalLine(", "// Inline SVG monogram")
    assert 'pickFromPool(ROOM_VERDICT.player, seed, "final", "player")' in body
    assert 'pickFromPool(ROOM_VERDICT.draw, seed, "final", "draw")' in body
    assert 'pickFromPool(pool, seed, "final", identity.seat, identity.difficulty)' in body
    assert "Math.random" not in js
    assert "fetch(" not in js
    # The match controller wires the final line off the seed + winner outcome only.
    verdict = _func_body(_r(_MATCH_JS), "function buildVerdict(", "function buildTrajectory(")
    assert 'window.OpponentIdentity.pickFinalLine("player", null, seed)' in verdict
    assert 'window.OpponentIdentity.pickFinalLine("draw", null, seed)' in verdict
    assert 'window.OpponentIdentity.pickFinalLine("banker", opponentIdentity(win), seed)' in verdict
    assert "MATCH.match_seed" in verdict


def test_final_line_deterministic_and_in_finite_pool():
    md = {"seat": 2, "difficulty": "md"}
    # Same (outcome, identity, seed) -> identical line, twice.
    assert pick_final_line("banker", md, 4242) == pick_final_line("banker", md, 4242)
    assert pick_final_line("player", None, 99) == pick_final_line("player", None, 99)
    assert pick_final_line("draw", None, 7) == pick_final_line("draw", None, 7)
    # Every result is a member of its finite pool (never generated text).
    assert pick_final_line("banker", md, 4242) in FINAL_WINNER["md"]
    assert pick_final_line("player", None, 99) in ROOM_VERDICT["player"]
    assert pick_final_line("draw", None, 7) in ROOM_VERDICT["draw"]
    # Seed actually drives the choice (at least one seed lands on each pool entry).
    md_lines = {pick_final_line("banker", md, s) for s in range(40)}
    assert md_lines == set(FINAL_WINNER["md"])


# ── 7. Detailed review preserved (round table + 15 deal chips) ───────────────

def test_detailed_review_preserved_collapsible():
    html = _r(_MATCH_HTML)
    js = _r(_MATCH_JS)
    # The 15-deal review + round table still exist, demoted into a <details>.
    assert 'id="end-rounds"' in html and 'id="end-review"' in html
    assert 'id="end-review-details"' in html
    assert "展开完整复盘" in html and "Detailed Review" in html
    assert "function buildDealChip(" in js
    # All deals (<=15) still rendered; nothing dropped.
    end = _func_body(js, "function buildEndContent(", "function addBestDeals(")
    assert "MATCH.deals.filter((d) => d.participant === id)" in end
    assert "chips.appendChild(buildDealChip(d, addedFrom))" in end
    assert "小卡片" in html  # compact review label retained


# ── 8. Play Again / Add Best / War Room actions still present + wired ────────

def test_actions_preserved_and_wired():
    html = _r(_MATCH_HTML)
    js = _r(_MATCH_JS)
    assert 'id="end-play-again"' in html and "Play Again" in html
    assert 'id="end-add-best"' in html and "Add Best Deals" in html
    assert "/modeling/ma/arena" in html and "War Room" in html
    assert '$("end-play-again").addEventListener("click", playAgain)' in js
    assert '$("end-add-best").addEventListener("click", addBestDeals)' in js
    assert "function playAgain(" in js and "function addBestDeals(" in js
    # Play Again is still the only match reset (fresh seed via startNewMatch).
    again = _func_body(js, "function playAgain(", "function syncMatchView(")
    assert "startNewMatch(MATCH_CONFIG)" in again


# ── 9. Match Points totals consistent (scoreboard == end-screen == engine) ──

def test_end_screen_totals_read_engine_rankings():
    js = _r(_MATCH_JS)
    end = _func_body(js, "function buildEndContent(", "function addBestDeals(")
    # End-screen totals are the engine rankings (the authoritative scoreboard),
    # not a re-summed local number.
    assert "const ranking = window.MatchEngine.rankings(MATCH);" in end
    assert 'el("span", "et-pts", `${r.points}`)' in end
    # The live scoreboard reads the same engine participant totals.
    assert "span.textContent = String(MATCH.participants[id].points)" in js


def test_match_points_formula_unchanged():
    eng = _r(_ENGINE_JS)
    assert "VIA_LEVEL_POINTS = { green: 20, yellow: 6, red: -18 }" in eng
    assert "SYNERGY_TIER_POINTS = { high: 10, medium: 6, low: 3, none: 0 }" in eng
    # The end screen never recomputes points (no engine call beyond reads).
    js = _r(_MATCH_JS)
    for builder in ("buildVerdict(", "buildTrajectory(", "buildBestDeals("):
        body = js[js.index(f"function {builder}"):]
        assert "matchPoints(" not in body[:body.index("\n}\n")]


# ── 10. No source_meta / strategy_score / overall_score leakage ─────────────

def test_no_internal_field_leak_on_ceremony():
    for f in (_MATCH_JS, _ID_JS, _MATCH_HTML, _ENGINE_JS):
        text = _r(f)
        for banned in ("source_meta", "field_sources", "filing_url", "quote_url",
                       "strategy_score", "overall_score", "strategy_rank", "audit_trail"):
            assert banned not in text, f"{banned} in {f.name}"


# ── 11. No innerHTML dynamic interpolation across the ceremony surface ───────

def test_ceremony_uses_safe_dom():
    for f in (_MATCH_JS, _ID_JS, _ENGINE_JS):
        js = _r(f)
        for m in re.finditer(r"\.innerHTML\s*=\s*(.+)", js):
            rhs = m.group(1).strip()
            assert rhs.startswith('""') or rhs.startswith("''"), f"{rhs} in {f.name}"
    js = _r(_MATCH_JS)
    for builder, end in (
        ("function buildVerdict(", "function buildTrajectory("),
        ("function buildTrajectory(", "function buildBestCard("),
        ("function buildBestCard(", "function buildBestDeals("),
    ):
        body = _func_body(js, builder, end)
        assert "innerHTML" not in body
        assert "el(" in body or "textContent" in body


# ── 12. Narrow / mobile overflow guard for the ceremony ─────────────────────

def test_ceremony_narrow_overflow_guard():
    html = _r(_MATCH_HTML)
    # Best-deal cards stack on narrow; the 5-node trajectory stays one row.
    block = html[html.index("@media (max-width: 620px) {", html.index("end-best-deals")):]
    assert ".end-best-deals { grid-template-columns: 1fr; }" in block
    # min-width:0 + ellipsis prevent long tickers/names pushing width.
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in html  # best deals
    assert "grid-template-columns: repeat(5, minmax(0, 1fr))" in html  # trajectory
    traj_who = _func_body(html, ".traj-who {", "}")
    assert "text-overflow: ellipsis" in traj_who
    best_deal = _func_body(html, ".best-deal {", "}")
    assert "text-overflow: ellipsis" in best_deal


# ── 13. Showdown / identity / robot-overlap layers not regressed ────────────

def test_showdown_layer_not_regressed():
    html = _r(_MATCH_HTML)
    js = _r(_MATCH_JS)
    assert 'id="showdown-stage"' in html and 'id="showdown-grid"' in html
    assert "function buildShowdownCard(" in js and "function settleShowdown(" in js
    assert "window.MatchEngine.roundWinner(rec)" in js


def test_identity_layer_not_regressed():
    js = _r(_MATCH_JS)
    id_js = _r(_ID_JS)
    assert "window.OpponentIdentity.buildForMatch(MATCH)" in js
    assert "function participantName(id)" in js
    assert "pickShowdownLine" in id_js and "pickRoundResultLine" in id_js


def test_robot_overlap_rule_not_regressed():
    eng = _r(_ENGINE_JS)
    assert "function currentHandCompanies(state)" in eng
    assert "function robotPickWithFallback(" in eng
    assert "function robotsPlay(state, pairs, getPair, cardById, selectFn)" in eng
    robot = _r(_ROBOT_JS)
    assert "selectRobotDeal" in robot


# ── 14. Backend contract unchanged (engine / API / pairs / EPS consistency) ──

def test_backend_contract_unchanged():
    client = app.test_client()
    r = client.post("/api/modeling/ma/calculate", json=build_pair_payload("aapl", "msft")).get_json()
    assert r["status"] == "ok" and "boards" not in r
    pairs = client.get("/api/modeling/ma/arena/pairs").get_json()
    assert pairs["pair_count"] == 9900 and "boards" in pairs
    light = get_arena_pair("aapl", "msft")
    assert light["accretion_dilution_pct"] == r["result"]["accretion_dilution"]
    assert len(list_arena_pairs()) == 9900


# ── 15. No new API / network / randomness added by the ceremony ─────────────

def test_ceremony_adds_no_api_or_randomness():
    js = _r(_MATCH_JS)
    # Still only the two pre-existing calculate fetches (fallback + Ticket).
    assert js.count("${API}/api/modeling/ma/calculate") == 2
    for banned in ("Math.random", "XMLHttpRequest", "eval(", "new Function",
                   "navigator.sendBeacon", "openai", "anthropic", "WebSocket"):
        assert banned not in js, banned
