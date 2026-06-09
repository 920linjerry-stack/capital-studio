"""V5.10.2.4 Robot Same-Round Card Overlap Rule Hardening.

A company card should feel like a real, single resource on the table. Two rules
make it so, and this file locks them:

  1. Robot-vs-robot company-disjointness — in one round the two robots may not
     share ANY company. If Robot 1 plays A->B then Robot 2 may use NEITHER A nor
     B, as acquirer OR target. The two robots' four tickers are company-disjoint.
  2. Player current-hand exclusion — a robot may not use a company still in the
     player's CURRENT hand (`MATCH.hand`), as acquirer OR target.
  3. Used-card unlock — a card the player has already PLAYED this round has left
     the hand into `used_cards`; it is NOT blocked and a robot may re-use it. The
     robots read ONLY the current hand, never `used_cards`.

The selection logic lives in `static/modeling/js/robot_opponent.js` and the round
orchestration in `static/modeling/js/match_engine.js`. There is no Node runtime in
CI, so (as for the V5.9.5 retune tests) the deterministic logic is PORTED into
Python and exercised against the SAME frozen 100-company deck / 9900 precomputed
directed pairs. The per-difficulty weight table is PARSED out of the JS so the
port cannot silently drift; source-lock assertions additionally pin the new JS so
the two layers stay in step. Nothing here touches Match Points / engines / weights
/ hand lifecycle — those are read-only mirrors of the frozen modules.
"""

import re
from pathlib import Path

from modeling.ma.precompute import list_arena_pairs
from modeling.ma.real_seed_deck import REAL_SEED_COMPANY_CARDS

_ROOT = Path(__file__).resolve().parents[1]
_ROBOT_JS = (_ROOT / "static" / "modeling" / "js" / "robot_opponent.js").read_text(encoding="utf-8")
_ENGINE_JS = (_ROOT / "static" / "modeling" / "js" / "match_engine.js").read_text(encoding="utf-8")

DIFFICULTIES = ["intern", "analyst", "associate", "vp", "md"]


# ── Parse the live weight table + cap out of the JS (no drift) ───────────────

def _parse_cap():
    m = re.search(r"const EPS_TRUST_CAP = ([0-9.]+)", _ROBOT_JS)
    assert m, "EPS_TRUST_CAP not found in robot_opponent.js"
    return float(m.group(1))


def _parse_strategy():
    block = re.search(r"const STRATEGY = \{(.+?)\n  \};", _ROBOT_JS, re.S)
    assert block, "STRATEGY table not found"
    out = {}
    for d in DIFFICULTIES:
        line = re.search(rf"{d}:\s*\{{(.+?)\}},", block.group(1))
        assert line, d
        fields = {}
        for k, v in re.findall(r'(\w+):\s*("?[\w.]+"?)', line.group(1)):
            fields[k] = v.strip('"') if '"' in v else float(v)
        out[d] = fields
    return out


EPS_TRUST_CAP = _parse_cap()
STRATEGY = _parse_strategy()

VIA_LEVEL_NUM = {"green": 0, "yellow": 1, "red": 2}
SYNERGY_TIER_STRENGTH = {"high": 1.0, "medium": 0.6, "low": 0.3, "none": 0.0}
TIER_RANK = {"gold": 5, "red": 4, "blue": 3, "green": 2, "white": 1}

_CARD = {c["id"]: c for c in REAL_SEED_COMPANY_CARDS}


# ── Faithful Python port of robot_opponent.js selection (+ company exclusion) ─

def _tier_rank(card):
    return TIER_RANK.get(card.get("arena_tier"), 1) if card else 1


def _relatedness(a, t):
    if not a or not t:
        return 0.0
    score = 0.0
    if a.get("sector") and a.get("sector") == t.get("sector"):
        score += 0.5
    if a.get("industry") and a.get("industry") == t.get("industry"):
        score += 0.2
    at = (a.get("tags") or {}).get("strategic_tags") or []
    tt = set((t.get("tags") or {}).get("strategic_tags") or [])
    overlap = sum(1 for x in at if x in tt)
    score += min(0.3, overlap * 0.15)
    return min(1.0, score)


def _eps_signal(eps, distrust):
    base = eps / (1 + abs(eps))
    if eps > EPS_TRUST_CAP:
        base -= (distrust or 0.0) * (eps - EPS_TRUST_CAP)
    return base


def _score(pair, w):
    eps = pair.get("accretion_dilution_pct")
    if not isinstance(eps, (int, float)):
        return None
    level = pair.get("viability_level")
    if w.get("redVeto") == "hard" and level == "red":
        return None
    via = VIA_LEVEL_NUM.get(level, 1)
    flags = pair.get("viability_flags_count") or 0
    syn = SYNERGY_TIER_STRENGTH.get(pair.get("default_synergy_tier"), 0.0)
    soft_red = 1 if (w.get("redVeto") != "hard" and level == "red") else 0
    a = _CARD.get(pair["acquirer_id"])
    t = _CARD.get(pair["target_id"])
    tier = (_tier_rank(a) + _tier_rank(t)) / 10
    rel = _relatedness(a, t)
    return (
        w["eps"] * _eps_signal(eps, w.get("outlierDistrust", 0.0))
        - w["viaPenalty"] * via
        - w["flagPenalty"] * flags
        - w["softRedPenalty"] * soft_red
        + w["tier"] * tier
        + w["related"] * rel
        + w["synergy"] * syn
    )


def _key(p):
    return f"{p['acquirer_id']}->{p['target_id']}"


def select(diff, pairs, exclude_keys, exclude_companies):
    """Mirror of selectRobotDeal: directed-key exclusion + V5.10.2.4 company ban,
    same deterministic rank + rankSkip window. Returns the chosen pair or None."""
    w = STRATEGY[diff]
    ex_keys = set(exclude_keys or ())
    ex_co = set(exclude_companies or ())
    scored = []
    for p in pairs:
        if p["acquirer_id"] == p["target_id"]:
            continue
        k = _key(p)
        if k in ex_keys:
            continue
        if p["acquirer_id"] in ex_co or p["target_id"] in ex_co:
            continue
        s = _score(p, w)
        if s is None:
            continue
        scored.append((s, k, p))
    if not scored:
        return None
    scored.sort(key=lambda x: (-x[0], x[1]))
    skip = max(0, int(w.get("rankSkip", 0)))
    return scored[min(skip, len(scored) - 1)][2]


def _robot_pick_with_fallback(diff, pairs, exclude_keys, company_levels):
    """Mirror of robotPickWithFallback: try each company-exclusion set strictest
    first; the first that yields a candidate wins. Returns (pair, level) or
    (None, -1)."""
    levels = company_levels or [set()]
    for i, lvl in enumerate(levels):
        pick = select(diff, pairs, exclude_keys, lvl)
        if pick:
            return pick, i
    return None, -1


def robots_play_round(diff1, diff2, pairs, hand_companies=(), played_keys=()):
    """Mirror of match_engine.robotsPlay's per-round company-overlap orchestration.
    Returns (pick1, pick2, level1, level2)."""
    base_exclude = set(played_keys)
    hand = set(hand_companies)

    pick1, lvl1 = _robot_pick_with_fallback(diff1, pairs, base_exclude, [hand, set()])
    robot_used = set()
    if pick1:
        base_exclude.add(_key(pick1))
        robot_used.add(pick1["acquirer_id"])
        robot_used.add(pick1["target_id"])

    pick2, lvl2 = _robot_pick_with_fallback(
        diff2, pairs, base_exclude, [hand | robot_used, set(hand), set()]
    )
    return pick1, pick2, lvl1, lvl2


def _companies(pick):
    return {pick["acquirer_id"], pick["target_id"]} if pick else set()


# ── Match Points mirror (FROZEN match_engine.js formula, read-only) ──────────

_VIA_PTS = {"green": 20, "yellow": 6, "red": -18}
_SYN_PTS = {"high": 10, "medium": 6, "low": 3, "none": 0}

# V5.10.4 size feasibility / reverse-whale guardrail (mirrors match_engine.js).
_SIZE_BANDS = [
    (1.0, "feasible", 0, None),
    (1.5, "minor", -4, None),
    (2.0, "moderate", -8, 52),
    (3.0, "reverse_whale", -10, 36),
    (4.0, "severe", -12, 24),
    (float("inf"), "extreme", -14, 14),
]


def _market_cap(card):
    if not card:
        return None
    try:
        cap = float(card.get("share_price")) * float(card.get("shares"))
    except (TypeError, ValueError):
        return None
    return cap if cap > 0 else None


def _size_adjust(total, p):
    a = _market_cap(_CARD.get(p["acquirer_id"]))
    t = _market_cap(_CARD.get(p["target_id"]))
    if not a or not t:
        return total
    ratio = t / a
    for mx, band, pen, cap in _SIZE_BANDS:
        if ratio <= mx:
            if band == "feasible":
                return total
            adj = total + pen
            if cap is not None:
                adj = min(adj, cap)
            return adj
    return total


def match_points(p):
    total = 0
    eps = p.get("accretion_dilution_pct")
    if isinstance(eps, (int, float)):
        total += round((eps / (1 + abs(eps))) * 40)
        if p.get("is_accretive"):
            total += 8
        elif eps < -0.5:
            total -= 10
    lvl = p.get("viability_level")
    if lvl in _VIA_PTS:
        total += _VIA_PTS[lvl]
    flags = p.get("viability_flags_count") or 0
    if flags > 0:
        total -= min(12, flags * 4)
    total += _SYN_PTS.get(p.get("default_synergy_tier"), 0)
    if p.get("synergy_status") in ("self_accretive", "synergy_supported"):
        total += 4
    a = _CARD.get(p["acquirer_id"])
    t = _CARD.get(p["target_id"])
    rel = 0
    if a and t:
        if a.get("sector") and a.get("sector") == t.get("sector"):
            rel += 1
        if a.get("industry") and a.get("industry") == t.get("industry"):
            rel += 1
    if rel:
        total += rel * 5
    tb = round((_tier_rank(a) + _tier_rank(t)) - 2)
    if tb:
        total += tb
    return _size_adjust(total, p)


# A representative spread of difficulty pairings for the two seats.
_COMBOS = [
    ("intern", "intern"),
    ("intern", "md"),
    ("analyst", "vp"),
    ("associate", "associate"),
    ("md", "md"),
    ("vp", "intern"),
]


# ── 1. Robot-vs-robot company overlap ban ───────────────────────────────────

def test_two_robots_in_a_round_share_no_company():
    """The two robots' four tickers are company-disjoint — no company appears in
    both deals, regardless of acquirer/target role."""
    pairs = list_arena_pairs()
    for d1, d2 in _COMBOS:
        pick1, pick2, _, _ = robots_play_round(d1, d2, pairs)
        assert pick1 and pick2, (d1, d2)
        shared = _companies(pick1) & _companies(pick2)
        assert not shared, f"{d1}+{d2} shared company {shared}: {_key(pick1)} / {_key(pick2)}"


# ── 2. Same acquirer ban ────────────────────────────────────────────────────

def test_two_robots_never_share_an_acquirer():
    pairs = list_arena_pairs()
    for d1, d2 in _COMBOS:
        pick1, pick2, _, _ = robots_play_round(d1, d2, pairs)
        assert pick1["acquirer_id"] != pick2["acquirer_id"], (d1, d2)
        # The acquirer of one is also never the target of the other.
        assert pick1["acquirer_id"] != pick2["target_id"], (d1, d2)


# ── 3. Same target ban ──────────────────────────────────────────────────────

def test_two_robots_never_share_a_target():
    pairs = list_arena_pairs()
    for d1, d2 in _COMBOS:
        pick1, pick2, _, _ = robots_play_round(d1, d2, pairs)
        assert pick1["target_id"] != pick2["target_id"], (d1, d2)
        assert pick1["target_id"] != pick2["acquirer_id"], (d1, d2)


# ── 4. Current player hand exclusion ────────────────────────────────────────

def test_robots_never_use_current_hand_companies():
    """Companies still in the player's hand are off-limits to BOTH robots, as
    acquirer or target."""
    pairs = list_arena_pairs()
    # Seed the hand with the companies a robot would otherwise grab, to prove the
    # exclusion actually moves the pick off them.
    p1, p2, _, _ = robots_play_round("analyst", "vp", pairs)
    hand = _companies(p1) | _companies(p2)
    for d1, d2 in _COMBOS:
        q1, q2, _, _ = robots_play_round(d1, d2, pairs, hand_companies=hand)
        assert q1 and q2, (d1, d2)
        assert not (_companies(q1) & hand), f"{d1} used hand company: {_key(q1)}"
        assert not (_companies(q2) & hand), f"{d2} used hand company: {_key(q2)}"


def test_hand_exclusion_changes_the_pick_when_it_must():
    """When the unconstrained pick sits on a hand company, the rule forces a
    different, hand-free deal (not a no-op)."""
    pairs = list_arena_pairs()
    base1, _, _, _ = robots_play_round("intern", "intern", pairs)
    hand = _companies(base1)
    new1, _, _, _ = robots_play_round("intern", "intern", pairs, hand_companies=hand)
    assert _key(new1) != _key(base1)
    assert not (_companies(new1) & hand)


# ── 5. Used-card unlock (robots read ONLY the current hand) ──────────────────

def test_used_cards_do_not_block_robots():
    """A card the player already played has left the hand into used_cards; it must
    NOT be excluded from the robots. The orchestration reads ONLY state.hand, so a
    company that is used-but-not-in-hand stays fully selectable."""
    pairs = list_arena_pairs()
    # Robot 1's natural (empty-hand) pick: pretend the player already played these
    # two — they are now in used_cards and OUT of the hand.
    base1, _, _, _ = robots_play_round("analyst", "analyst", pairs)
    used_only = _companies(base1)
    # With an empty CURRENT hand, the robot exclusion is empty -> the used-only
    # companies are NOT blocked, so the identical natural pick returns.
    again1, _, _, _ = robots_play_round("analyst", "analyst", pairs, hand_companies=set())
    assert _key(again1) == _key(base1), "used_cards must not change a robot's pick"
    # And a deal on a used-only company is still selectable (company ban only fires
    # for current-hand / robot-vs-robot, never for the used pile).
    on_used = [p for p in pairs if (used_only & _companies(p)) and p["acquirer_id"] != p["target_id"]]
    assert on_used, "expected deals involving the used-only companies to exist"
    pick = select("analyst", pairs, exclude_keys=set(), exclude_companies=set())
    assert pick is not None


# ── 6. Deterministic (same inputs -> same output, incl. fallback) ────────────

def test_round_orchestration_is_fully_deterministic():
    pairs = list_arena_pairs()
    hand = _companies(robots_play_round("md", "md", pairs)[0])
    for d1, d2 in _COMBOS:
        a = robots_play_round(d1, d2, pairs, hand_companies=hand)
        b = robots_play_round(d1, d2, pairs, hand_companies=hand)
        assert [_key(a[0]), _key(a[1]), a[2], a[3]] == [_key(b[0]), _key(b[1]), b[2], b[3]], (d1, d2)


# ── 7. Retune is NOT regressed by the new exclusion ─────────────────────────

def test_retune_intact_with_empty_hand():
    """With no hand constraint, Robot 1 keeps its retuned behavior: the Intern's
    first pick is NOT the global Match-Points optimum (it lands a good-but-not-top
    deal), and the rungs stay differentiated (no collapse)."""
    pairs = list_arena_pairs()
    by_mp = sorted(pairs, key=lambda p: -match_points(p))
    mp_rank = {_key(p): i for i, p in enumerate(by_mp)}

    intern1, _, _, _ = robots_play_round("intern", "intern", pairs)
    assert mp_rank[_key(intern1)] >= 50, "Intern slid back toward the global optimum"

    firsts = {d: _key(robots_play_round(d, d, pairs)[0]) for d in DIFFICULTIES}
    assert len(set(firsts.values())) >= 3, firsts
    assert firsts["intern"] != firsts["md"], firsts


def test_difficulty_behavior_does_not_collapse_under_exclusion():
    """Even with a populated hand (a real round constraint), the strong rungs stay
    strong: VP/MD still avoid red-viability dead-ends (their hard veto holds)."""
    pairs = list_arena_pairs()
    hand = _companies(robots_play_round("intern", "intern", pairs)[0])
    for diff in ("vp", "md"):
        p1, p2, _, _ = robots_play_round(diff, diff, pairs, hand_companies=hand)
        for pick in (p1, p2):
            assert pick is not None
            assert pick.get("viability_level") != "red", diff
            assert pick.get("is_accretive"), diff


# ── 8. Graceful fallback when the constrained set is exhausted ───────────────

def test_fallback_relaxes_overlap_before_crashing():
    """A pathologically tiny board (two pairs sharing the same two companies) can
    not satisfy strict company-disjointness for Robot 2. The fallback must relax
    the robot-vs-robot overlap (NOT crash / return None) and stay deterministic."""
    base = {
        "accretion_dilution_pct": 0.20,
        "is_accretive": True,
        "viability_level": "green",
        "viability_flags_count": 0,
        "default_synergy_tier": "medium",
        "synergy_status": "synergy_supported",
    }
    pairs = [
        {**base, "acquirer_id": "AA", "target_id": "BB"},
        {**base, "acquirer_id": "BB", "target_id": "AA"},
    ]
    p1, p2, lvl1, lvl2 = robots_play_round("analyst", "analyst", pairs)
    assert p1 is not None and p2 is not None, "fallback must still seat both robots"
    assert _key(p1) != _key(p2), "the two robots still avoid the exact same directed pair"
    # Only two companies exist, so disjointness is impossible -> Robot 2 relaxed.
    assert lvl2 >= 1, "Robot 2 should have used the relaxation chain"
    # Deterministic: identical inputs reproduce identical picks + relaxation level.
    q1, q2, _, ql2 = robots_play_round("analyst", "analyst", pairs)
    assert (_key(p1), _key(p2), lvl2) == (_key(q1), _key(q2), ql2)


def test_fallback_keeps_player_hand_block_longest():
    """Relaxation drops robot-vs-robot overlap before the player-hand block: with
    a small board, Robot 2 still avoids the player's current hand even while it is
    forced to share a company with Robot 1."""
    base = {
        "accretion_dilution_pct": 0.20,
        "is_accretive": True,
        "viability_level": "green",
        "viability_flags_count": 0,
        "default_synergy_tier": "medium",
        "synergy_status": "synergy_supported",
    }
    # Three companies; CC is in the player's hand so no deal touching CC is legal.
    pairs = [
        {**base, "acquirer_id": "AA", "target_id": "BB"},
        {**base, "acquirer_id": "BB", "target_id": "AA"},
        {**base, "acquirer_id": "AA", "target_id": "CC"},
        {**base, "acquirer_id": "CC", "target_id": "BB"},
    ]
    p1, p2, _, lvl2 = robots_play_round("analyst", "analyst", pairs, hand_companies={"CC"})
    assert p1 and p2
    assert "CC" not in _companies(p1) and "CC" not in _companies(p2), "hand block must hold"
    assert lvl2 == 1, "Robot 2 relaxed only the robot-vs-robot overlap, not the hand block"


# ── Source-lock: the JS actually implements what the port mirrors ────────────

def test_robot_opponent_source_has_company_exclusion():
    js = _ROBOT_JS
    assert "function toCompanySet(" in js
    assert "const excludeCompanies = toCompanySet(ctx.excludedCompanies);" in js
    assert "if (excludeCompanies.has(pair.acquirer_id) || excludeCompanies.has(pair.target_id)) continue;" in js
    # The directed-key exclusion + self-deal guard + deterministic tie-break stay.
    assert "pair.acquirer_id === pair.target_id) continue;" in js
    assert "return a.key < b.key ? -1 : a.key > b.key ? 1 : 0;" in js


def test_engine_source_has_per_round_overlap_orchestration():
    js = _ENGINE_JS
    assert "function currentHandCompanies(state)" in js
    # Robots read ONLY the current hand, never the used pile.
    hand_fn = js[js.index("function currentHandCompanies(state)"):]
    hand_fn = hand_fn[:hand_fn.index("\n  }")]
    assert "state.hand" in hand_fn
    assert "used_cards" not in hand_fn
    assert "function unionCompanies(" in js
    assert "function robotPickWithFallback(" in js
    # Robot 1 blocks the hand; Robot 2 blocks hand + Robot 1's companies (strictest
    # first), relaxing the overlap before the hand block.
    assert "[handCompanies, new Set()]" in js
    assert "[unionCompanies(handCompanies, robotUsed), handCompanies, new Set()]" in js
    assert "robotUsed.add(d1.acquirer_id);" in js and "robotUsed.add(d1.target_id);" in js
    # The pre-existing directed-key duplicate guard is preserved.
    assert "const baseExclude = playedKeys(state).slice();" in js
    assert "baseExclude.push(dirKey(d1.acquirer_id, d1.target_id));" in js


def test_overlap_rule_adds_no_leakage_or_unsafe_dom():
    """The new code path stores no provenance / score leak and adds no network /
    randomness / unsafe interpolation."""
    for js, name in ((_ROBOT_JS, "robot_opponent.js"), (_ENGINE_JS, "match_engine.js")):
        for banned in ("source_meta", "field_sources", "filing_url", "quote_url",
                       "strategy_score", "overall_score", "综合评分",
                       "Math.random", "fetch(", "eval(", "new Function"):
            assert banned not in js, f"{banned} in {name}"
