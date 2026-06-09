"""V5.9.6.2 Match Start State Isolation & Seeded Opening Hand tests.

Two narrow gameplay fixes, ZERO financial-truth change (engine / synergy /
viability / calculate / pairs payload / Match Points / robot strategy / deck data
/ source_meta / precompute all untouched):

  1. State isolation — Start Match is a fresh game with a CLEAN deal table. The
     Match no longer deep-links a deal from the URL, so the War Room's current
     acquirer/target selection never seats the Match table. The Deal Review Queue
     still persists across pages, but a queued deal is preview/load only.
  2. Seeded opening hand — each new match gets a fresh `match_seed`; the deck is
     laid out by a deterministic mulberry32 + Fisher-Yates shuffle (`draw_order`),
     so the opening hand varies between matches yet is replayable/restorable
     within a match. The seed feeds the card SHUFFLE only — never any result.

There is no Node runtime in CI, so the shuffle is PORTED to Python (faithful
mulberry32 over uint32) and exercised against the real frozen deck to prove
variability + determinism; the rest is static-source / contract assertions, with
the live flow covered by the documented browser smoke.
"""

import re
from pathlib import Path

from app import app
from modeling.ma.real_seed_deck import REAL_SEED_COMPANY_CARDS
from modeling.ma.precompute import build_pair_payload

_ROOT = Path(__file__).resolve().parents[1]
_MATCH_JS = _ROOT / "static" / "modeling" / "js" / "arena_match.js"
_ENGINE_JS = _ROOT / "static" / "modeling" / "js" / "match_engine.js"
_SETUP_JS = _ROOT / "static" / "modeling" / "js" / "match_setup.js"

DECK_IDS = [c["id"] for c in REAL_SEED_COMPANY_CARDS]


def _r(p):
    return p.read_text(encoding="utf-8")


# ── Faithful Python port of match_engine.js mulberry32 + seededShuffle ───────

def _imul(a, b):
    return (a * b) & 0xFFFFFFFF


def _mulberry32(seed):
    a = seed & 0xFFFFFFFF or 1

    def rng():
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = _imul(a ^ (a >> 15), 1 | a)
        t = (((t + _imul(t ^ (t >> 7), 61 | t)) & 0xFFFFFFFF) ^ t) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

    return rng


def _seeded_shuffle(ids, seed):
    arr = list(ids)
    rand = _mulberry32(seed & 0xFFFFFFFF)
    for i in range(len(arr) - 1, 0, -1):
        j = int(rand() * (i + 1))
        arr[i], arr[j] = arr[j], arr[i]
    return arr


def _opening_hand(seed, n=7):
    return _seeded_shuffle(DECK_IDS, seed)[:n]


# ── 1. State isolation: Match never seats from the War Room / URL ────────────

def test_match_does_not_deep_link_a_deal_from_url():
    js = _r(_MATCH_JS)
    # The deep-link seat function and its call are gone; init must not call it.
    assert "function deepLinkInit(" not in js
    assert "deepLinkInit()" not in js
    # init explicitly clears the table selection (ignore any URL ?acq/?tgt).
    assert "selected = { acq: null, tgt: null }; // clean deal table" in js


def test_setup_does_not_forward_acq_tgt_to_match():
    js = _r(_SETUP_JS)
    assert "passthroughQuery" not in js
    # Start Match navigates to the clean match URL (no query string).
    assert 'window.location.href = "/modeling/ma/arena/match/play"' in js


def test_new_match_starts_clean_via_start_new_match():
    js = _r(_MATCH_JS)
    assert "function startNewMatch(" in js
    body = js[js.index("function startNewMatch("):js.index("function startNewMatch(") + 600]
    # A fresh match: clean engine state + fresh seed + empty order/cursor/used pile.
    assert "window.MatchEngine.createMatch(config)" in body
    assert "m.match_seed = freshSeed();" in body
    assert "m.draw_order = [];" in body
    assert "m.deck_cursor = 0;" in body
    assert "m.used_cards = [];" in body
    # Used by BOTH the initial build and Play Again.
    assert "restoreMatchState(MATCH_CONFIG) || startNewMatch(MATCH_CONFIG)" in js
    assert "MATCH = startNewMatch(MATCH_CONFIG)" in js  # playAgain


def test_queue_persists_but_is_load_only_not_auto_seated():
    js = _r(_MATCH_JS)
    # The queue is still subscribed/rendered on the Match page (persists across
    # pages) ...
    assert "window.DealQueue.subscribe(renderQueue)" in js
    # ... but a queued row only LOADS as a preview selection on click; it is never
    # auto-applied at init (loadQueueItem is an explicit click handler).
    assert "function loadQueueItem(" in js
    init_body = js[js.index("async function init("):]
    assert "loadQueueItem(" not in init_body


# ── 2. Seeded opening hand: variability + determinism (ported shuffle) ───────

def test_opening_hand_is_deterministic_for_a_seed():
    assert _opening_hand(12345) == _opening_hand(12345)
    assert _seeded_shuffle(DECK_IDS, 999) == _seeded_shuffle(DECK_IDS, 999)


def test_opening_hand_varies_by_seed():
    seeds = [1, 2, 7, 42, 1000, 2_000_000, 4_000_000_000]
    hands = {tuple(_opening_hand(s)) for s in seeds}
    # Distinct seeds overwhelmingly give distinct opening hands (not one fixed set).
    assert len(hands) >= len(seeds) - 1
    # And not the unshuffled deck head (AAPL/MSFT/GOOGL/AMZN/META/NVDA/DIS).
    default_head = DECK_IDS[:7]
    differing = [s for s in seeds if _opening_hand(s) != default_head]
    assert len(differing) >= len(seeds) - 1


def test_seeded_shuffle_is_a_permutation_no_loss_no_dupes():
    for s in (0, 1, 123, 7777, 4_294_967_295):
        order = _seeded_shuffle(DECK_IDS, s)
        assert sorted(order) == sorted(DECK_IDS)
        assert len(set(order)) == len(DECK_IDS)


# ── 3. Engine exposes pure shuffle helpers; stays finance-deterministic ──────

def test_engine_exposes_pure_seeded_shuffle_helpers():
    js = _r(_ENGINE_JS)
    assert "function mulberry32(" in js
    assert "function seededShuffle(" in js
    assert "function buildDrawOrder(" in js
    for name in ("mulberry32", "seededShuffle", "buildDrawOrder"):
        assert re.search(rf"\n    {name},", js), name
    # The shuffle is the ONLY entropy; the engine carries no Math.random and the
    # seed is documented as a GAME shuffle, never a financial input.
    assert "Math.random" not in js


def test_seed_is_game_only_not_in_match_points_or_robot():
    # Match Points + robot strategy must not read the seed/draw order.
    eng = _r(_ENGINE_JS)
    mp = eng[eng.index("function matchPointsBreakdown("):eng.index("function matchPoints(")]
    for tok in ("match_seed", "draw_order", "deck_cursor", "seededShuffle"):
        assert tok not in mp, tok
    robot = _r(_ROOT / "static" / "modeling" / "js" / "robot_opponent.js")
    for tok in ("match_seed", "draw_order", "deck_cursor"):
        assert tok not in robot, tok


# ── 4. Seeded draw pool drives draw / reshuffle / retain refresh ─────────────

def test_draw_pool_uses_seeded_order_and_excludes_used():
    js = _r(_MATCH_JS)
    assert "function drawPool(" in js
    pool = js[js.index("function drawPool("):js.index("function drawEligible(")]
    assert "window.MatchEngine.buildDrawOrder(seed, CARDS.map((c) => c.id))" in pool
    # draw uses the seeded pool, still skipping used + in-hand ids.
    draw = js[js.index("function drawEligible("):js.index("function initialDeal(")]
    assert "const pool = drawPool();" in draw
    assert "if (used.has(id) || inHand.has(id) || ex.has(id) || out.indexOf(id) >= 0) continue;" in draw
    # Draw / Reshuffle / retain-refresh all refill via drawEligible (the seeded pool).
    assert "drawEligible(1)" in js          # Draw
    assert "drawEligible(HAND_SIZE)" in js  # Reshuffle
    assert "drawEligible(need)" in js       # retain refresh


def test_seed_generation_prefers_crypto():
    js = _r(_MATCH_JS)
    body = js[js.index("function freshSeed("):js.index("function startNewMatch(")]
    assert "window.crypto.getRandomValues" in body
    assert "Math.random" not in body  # deterministic-after-pick; no PRNG fallback


# ── 5. Restore keeps the dealt hand (reload does not reshuffle) ──────────────

def test_restore_keeps_hand_no_reshuffle_on_reload():
    js = _r(_MATCH_JS)
    assert "function restoreMatchState(" in js
    # A valid in-progress match is restored as-is (incl. its seed/order/hand);
    # ensureHand keeps the restored hand instead of re-dealing.
    ensure = js[js.index("function ensureHand("):js.index("function drawOne(")]
    assert "if (Array.isArray(MATCH.hand) && MATCH.hand.length)" in ensure
    assert "initialDeal();" in ensure  # only when there is no restored hand


# ── 6. No source_meta / contract regressions ────────────────────────────────

def test_no_source_meta_in_match_state_or_engine():
    for f in (_MATCH_JS, _ENGINE_JS, _SETUP_JS):
        text = _r(f)
        for banned in ("source_meta", "field_sources", "filing_url", "quote_url"):
            assert banned not in text, f"{banned} in {f.name}"


def test_calculate_and_pairs_contract_unchanged():
    client = app.test_client()
    r = client.post("/api/modeling/ma/calculate", json=build_pair_payload("aapl", "msft")).get_json()
    assert r["status"] == "ok"
    s = str(r)
    for banned in ("match_seed", "draw_order", "deck_cursor", "used_cards"):
        assert banned not in s, banned
    pairs = client.get("/api/modeling/ma/arena/pairs").get_json()
    assert pairs["pair_count"] == 9900
    assert "match_seed" not in str(pairs) and "draw_order" not in str(pairs)
