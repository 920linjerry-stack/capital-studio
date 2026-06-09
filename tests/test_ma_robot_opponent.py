"""V5.9.0 Robot Opponent · deterministic opponent + difficulty ladder tests.

The Robot Opponent is a DETERMINISTIC strategy over the SAME frozen 45-company
deck and 9900 precomputed directed pairs. It is not an LLM, never goes to the
network, and generates no new financial judgement — it only ranks existing light
compact-pair fields with a fixed per-difficulty weight table. Its internal
`strategy_rank` is robot-selection-only and never becomes a product Overall
Score, never enters the Economic / Viability boards.

The selection logic lives in `static/modeling/js/robot_opponent.js` and is wired
into the Play Table. These tests lock the boundaries via source/static assertions
(the repo's convention for front-end deterministic logic) plus backend data
checks; the live per-difficulty selection + determinism is covered by the
documented browser smoke. They assert:

* the difficulty enum is complete and a fixed, differentiated weight ladder
  exists (Intern = pure EPS, MD = risk-adjusted with a hard red veto),
* selection is deck-bounded, self-deal-free, deterministic with a string
  tie-break, and reuses precomputed pairs (no calculate loop),
* robot deals reuse the V5.8 Queue (light added_from, no source_meta/full result)
  and the V5.4 Ticket (EPS consistency),
* no LLM / network / randomness / Overall Score / innerHTML interpolation,
* engine / synergy / viability / calculate / pairs contract unchanged.
"""

import re
from pathlib import Path

from app import app
from modeling.ma.precompute import build_pair_payload, get_arena_pair, list_arena_pairs


_ROOT = Path(__file__).resolve().parents[1]
_PLAY_HTML = _ROOT / "static" / "modeling" / "arena_play.html"
_PLAY_JS = _ROOT / "static" / "modeling" / "js" / "arena_play.js"
_ROBOT_JS = _ROOT / "static" / "modeling" / "js" / "robot_opponent.js"
_WARROOM_JS = _ROOT / "static" / "modeling" / "js" / "arena.js"


def _r(p):
    return p.read_text(encoding="utf-8")


# ── Difficulty ladder enum + differentiated weight table ────────────────────

def test_robot_difficulty_enum_complete():
    js = _r(_ROBOT_JS)
    assert 'const DIFFICULTIES = ["intern", "analyst", "associate", "vp", "md"]' in js
    assert 'DEFAULT_DIFFICULTY = "analyst"' in js
    for d in ("intern", "analyst", "associate", "vp", "md"):
        assert d in js, d


def test_robot_weight_ladder_is_differentiated():
    """A fixed, explainable weight per difficulty — not five copies of one rule."""
    js = _r(_ROBOT_JS)
    assert "const STRATEGY = {" in js
    for d in ("intern", "analyst", "associate", "vp", "md"):
        assert re.search(rf"\b{d}:\s*\{{", js), d
    # Intern is the naive EPS chaser: no viability penalty, no red veto. (V5.9.5:
    # it carries a small softRedPenalty so it is not *completely* blind to a red,
    # and a rankSkip so it does not land the global optimum — asserted below.)
    assert re.search(r"intern:\s*\{[^}]*eps:\s*1\.00[^}]*viaPenalty:\s*0\.00[^}]*redVeto:\s*\"none\"", js)
    # MD is risk-adjusted: low EPS weight, high viability penalty, HARD red veto.
    assert re.search(r"md:\s*\{[^}]*viaPenalty:\s*0\.78[^}]*redVeto:\s*\"hard\"", js)
    # VP also hard-vetoes reds; the two strongest rungs avoid regulatory dead-ends.
    assert re.search(r"vp:\s*\{[^}]*redVeto:\s*\"hard\"", js)
    # Analyst avoids the most obvious reds via a soft penalty (no veto).
    assert re.search(r"analyst:\s*\{[^}]*softRedPenalty:\s*0\.35[^}]*", js)
    # V5.9.5 retune knobs exist on every rung.
    assert "const EPS_TRUST_CAP = 0.6" in js
    for d in ("intern", "analyst", "associate", "vp", "md"):
        assert re.search(rf"{d}:\s*\{{[^}}]*outlierDistrust:\s*[0-9.]+[^}}]*rankSkip:\s*[0-9]+", js), d
    # Intern alone skips deep into its ranking (good-but-not-top); the elite rungs
    # take their true best (rankSkip 0).
    assert re.search(r"intern:\s*\{[^}]*rankSkip:\s*40", js)
    assert re.search(r"vp:\s*\{[^}]*rankSkip:\s*0", js)
    assert re.search(r"md:\s*\{[^}]*rankSkip:\s*0", js)
    # Outlier distrust rises with skill: Intern 0 (naive), MD highest.
    assert re.search(r"intern:\s*\{[^}]*outlierDistrust:\s*0\.00", js)
    assert re.search(r"md:\s*\{[^}]*outlierDistrust:\s*0\.72", js)


def test_robot_difficulty_fallback_to_default():
    js = _r(_ROBOT_JS)
    assert "function normalizeDifficulty(" in js
    assert "DIFFICULTIES.indexOf(d) >= 0 ? d : DEFAULT_DIFFICULTY" in js


# ── Selection: deck-bounded, no self-deal, deterministic tie-break ──────────

def test_robot_selection_is_deck_bounded_and_no_self_deal():
    js = _r(_ROBOT_JS)
    assert "function selectRobotDeal(" in js
    # Self-deal can never be selected.
    assert "pair.acquirer_id === pair.target_id) continue;" in js
    # Missing ids are skipped (only deck pairs flow in from PAIRS_INDEX).
    assert "if (!pair || !pair.acquirer_id || !pair.target_id) continue;" in js


def test_robot_tie_break_is_deterministic_string():
    js = _r(_ROBOT_JS)
    # Candidates are ranked by score desc, equal score broken by directed key.
    assert "if (a.score > b.score + 1e-9) return -1;" in js
    assert "if (b.score > a.score + 1e-9) return 1;" in js
    assert "return a.key < b.key ? -1 : a.key > b.key ? 1 : 0;" in js
    # The rung's rankSkip selects the Nth-best (clamped) — Intern's keeps it off
    # the global optimum without any randomness.
    assert "const skip = Math.max(0, numOr(weights.rankSkip, 0));" in js
    assert "scored[Math.min(skip, scored.length - 1)]" in js


def test_robot_returns_internal_strategy_rank_not_overall_score():
    js = _r(_ROBOT_JS)
    assert "strategy_rank: chosen.score" in js
    # The rank must never be labelled / merged as a product overall score.
    for banned in ("综合评分", "Overall Score", "胜率", "win_rate", "overall_score"):
        assert banned not in js, banned


def test_robot_directed_pair_key_is_directional():
    js = _r(_ROBOT_JS)
    assert "function dirKey(" in js
    assert "`${acquirerId}->${targetId}`" in js
    # Exclude set is built from directed keys (A->B excluding does not touch B->A).
    assert "function toExcludeSet(" in js


# ── Rationale from fixed templates (no generated text) ──────────────────────

def test_robot_rationale_from_fixed_templates():
    js = _r(_ROBOT_JS)
    assert "const STRATEGY_FLAVOUR = {" in js
    assert "function rationaleFor(" in js
    for d in ("intern", "analyst", "associate", "vp", "md"):
        assert re.search(rf"{d}:\s*\"策略", js), d


# ── No LLM / network / randomness / unsafe exec / source_meta ───────────────

def test_robot_has_no_llm_network_randomness():
    js = _r(_ROBOT_JS)
    # Real network/exec indicators. (The header may *reference* /api/.../pairs as
    # the data source in prose; the guarantee is that it never *calls* the network.)
    for banned in ("Math.random", "fetch(", "XMLHttpRequest", "eval(", "new Function",
                   "navigator.sendBeacon", "openai", "anthropic"):
        assert banned not in js, banned
    assert ".send(" not in js and "WebSocket" not in js


def test_robot_stores_no_source_meta_or_full_result():
    js = _r(_ROBOT_JS)
    for banned in ("source_meta", "field_sources", "filing_url", "quote_url",
                   "triggered_tags", "synergy_context", "offer_value", "pro_forma_eps"):
        assert banned not in js, banned


def test_robot_only_reads_allowed_light_fields():
    """Strategy reads only existing light compact-pair fields, never a runtime
    market/synergy/regulatory generator."""
    js = _r(_ROBOT_JS)
    for field in ("accretion_dilution_pct", "viability_level", "viability_flags_count",
                  "default_synergy_tier", "synergy_status_label", "arena_tier"):
        assert field in js, field


# ── Play Table wiring: control panel, result card, queue + ticket reuse ──────

def test_play_has_robot_control_panel():
    html = _r(_PLAY_HTML)
    assert 'class="robot-bar"' in html
    assert 'id="robot-play-btn"' in html
    for d in ("intern", "analyst", "associate", "vp", "md"):
        assert f'data-diff="{d}"' in html, d
    # Difficulty labels (the five rungs).
    for label in ("实习生", "分析师", "高级分析师", "副总裁", "董事总经理"):
        assert label in html, label


def test_play_robot_seat_activated_but_keeps_seat_names():
    html = _r(_PLAY_HTML)
    assert 'id="robot-seat"' in html
    assert "robot-active" in html
    assert 'id="robot-seat-badge"' in html
    # Existing opponent seat names must stay (V5.6.1 test depends on them).
    assert "VP Seat" in html and "MD Seat" in html


def test_play_robot_result_card_fields():
    html = _r(_PLAY_HTML)
    assert 'id="robot-result"' in html
    assert 'id="rr-acq"' in html and 'id="rr-tgt"' in html
    assert 'id="rr-eps"' in html and 'id="rr-chips"' in html
    assert 'id="robot-queue-btn"' in html
    assert 'id="robot-load-btn"' in html
    assert 'id="robot-ticket-btn"' in html


def test_play_loads_robot_module_before_page_script():
    html = _r(_PLAY_HTML)
    assert "/static/modeling/js/robot_opponent.js" in html
    # Helpers (queue + robot) must be parsed before the page script uses them.
    assert html.index("deal_queue.js") < html.index("robot_opponent.js")
    assert html.index("robot_opponent.js") < html.index("js/arena_play.js")


def test_play_robot_uses_precomputed_pairs_no_calculate_loop():
    js = _r(_PLAY_JS)
    assert "function robotPlay(" in js
    assert "Object.values(PAIRS_INDEX)" in js
    assert "window.RobotOpponent.selectRobotDeal(" in js
    # No new calculate fetch is introduced for the robot — still exactly the two
    # pre-existing calculate calls (single-deal fallback + Deal Ticket).
    assert js.count("${API}/api/modeling/ma/calculate") == 2
    assert "await Promise.all([loadCards(), loadPairs()]);\n  setRobotDifficulty(robotDifficulty);" in js


def test_play_robot_excludes_queue_and_recent_for_variety():
    js = _r(_PLAY_JS)
    assert "window.DealQueue.list().concat(" in js
    assert "robotRecentKeys" in js
    # Variety must not use randomness.
    assert "Math.random" not in js


def test_play_robot_queue_load_ticket_wired():
    js = _r(_PLAY_JS)
    assert "function addRobotToQueue(" in js
    assert "`robot_${robotResult.difficulty}`" in js
    assert "function loadRobotToTable(" in js
    assert "loadQueueItem({ acquirer_id: robotResult.acquirer_id, target_id: robotResult.target_id })" in js
    assert "function robotViewTicket(" in js
    assert "openTicket()" in js


def test_play_robot_validates_ids_against_deck():
    js = _r(_PLAY_JS)
    assert "if (!companyById(robotResult.acquirer_id) || !companyById(robotResult.target_id))" in js


# ── Safe DOM + no Overall Score on the robot surface ────────────────────────

def test_robot_surface_uses_safe_dom_no_innerhtml_interpolation():
    for js in (_r(_ROBOT_JS), _r(_PLAY_JS)):
        for m in re.finditer(r"\.innerHTML\s*=\s*(.+)", js):
            rhs = m.group(1).strip()
            assert rhs.startswith('""') or rhs.startswith("''"), rhs
    # Robot rationale chips reach the DOM via el()/textContent only.
    play = _r(_PLAY_JS)
    assert 'el(`rr-chip ${c.kind || ""}`.trim(), c.text)' in play or \
           'el("span", `rr-chip ${c.kind || ""}`.trim(), c.text)' in play


def test_robot_no_overall_score_in_html_or_module():
    for f in (_PLAY_HTML, _ROBOT_JS):
        text = _r(f)
        for banned in ("综合评分", "Overall Score", "胜率", "win_rate", "overall_score"):
            assert banned not in text, f"{banned} in {f.name}"


# ── War Room renders robot-sourced queue items with a friendly label ────────

def test_warroom_labels_robot_queue_source():
    js = _r(_WARROOM_JS)
    assert "function queueFromLabel(" in js
    assert 'from.indexOf("robot") === 0' in js


# ── Data universe supports a meaningful ladder (red + green pairs exist) ─────

def test_pair_universe_has_red_and_green_for_ladder_differentiation():
    """The ladder only matters if the expanded pairs contain both weaker-viability
    accretive deals (red/yellow — what Intern chases) and clean green deals (what
    MD prefers). MD additionally hard-vetoes the red tier."""
    pairs = list_arena_pairs()
    assert len(pairs) == 9900
    reds = [p for p in pairs if p.get("viability_level") == "red"]
    greens = [p for p in pairs if p.get("viability_level") == "green"]
    assert reds, "no red-viability pairs — MD's hard veto has nothing to avoid"
    assert greens, "no green-viability pairs — ladder has nothing safe to prefer"
    # At least one accretive deal carries a non-green (red/yellow) viability — the
    # high-EPS-but-risky combination Intern is drawn to and MD discounts. This is
    # what makes Intern vs MD pick materially different deals.
    weak_accretive = [
        p for p in pairs
        if p.get("is_accretive") and p.get("viability_level") in {"red", "yellow"}
    ]
    assert weak_accretive, "no high-EPS weaker-viability pairs — ladder is flat"


def test_robot_added_from_is_light_field_only():
    """Robot queue source is a short string like `robot_md`; the V5.8 sanitize
    keeps only the whitelist, so no full result / source_meta can ride along."""
    play = _r(_PLAY_JS)
    assert "`robot_${robotResult.difficulty}`" in play
    # added_from is part of the queue whitelist (asserted in the V5.8 module).
    queue_js = _r(_ROOT / "static" / "modeling" / "js" / "deal_queue.js")
    assert '"added_from"' in queue_js


# ── EPS consistency for robot-selected deals ────────────────────────────────

def test_robot_selected_deal_eps_consistent_light_equals_calculate():
    """Whatever directed pair the robot picks, its light EPS (PAIRS_INDEX lookup)
    equals the calculate full result — robot adds no new economics."""
    client = app.test_client()
    for acq, tgt in [("aapl", "msft"), ("nvda", "avgo"), ("dis", "hd"), ("msft", "aapl")]:
        light = get_arena_pair(acq, tgt)
        full = client.post(
            "/api/modeling/ma/calculate", json=build_pair_payload(acq, tgt)
        ).get_json()["result"]
        assert light["accretion_dilution_pct"] == full["accretion_dilution"]


# ── Backend contract unchanged ──────────────────────────────────────────────

def test_calculate_and_pairs_contract_unchanged():
    client = app.test_client()
    r = client.post("/api/modeling/ma/calculate", json=build_pair_payload("aapl", "msft")).get_json()
    assert r["status"] == "ok" and "boards" not in r
    pairs = client.get("/api/modeling/ma/arena/pairs").get_json()
    assert pairs["pair_count"] == 9900 and "boards" in pairs


def test_play_route_serves_with_robot_script():
    client = app.test_client()
    html = client.get("/modeling/ma/arena/play").get_data(as_text=True)
    assert "robot_opponent.js" in html
    assert "Robot Opponent" in html
