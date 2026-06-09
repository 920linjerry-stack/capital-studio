"""V5.9.5 Robot Retune under Hand Lifecycle · behavioral difficulty-ladder tests.

The player now has a hand lifecycle (play consumes two company cards, used cards
do not return, retain 4 / refresh-to-7). Robots stay hand-agnostic, so the old
"strongest-global-deal" picker felt unfair to beginners — in particular the
Intern, whose pure-EPS chase happened to land the single global Match-Points
optimum (`panw->dis`, +418% EPS, green viability) every match.

The selection logic lives in `static/modeling/js/robot_opponent.js`. There is no
Node runtime in CI, so these tests PORT that deterministic logic into Python and
exercise it against the SAME frozen 100-company deck / 9900 precomputed directed
pairs the page loads. To stop the port from silently drifting, the per-difficulty
weight table and EPS_TRUST_CAP are PARSED out of the JS source — if someone
retunes the JS, this test re-evaluates the real numbers. The Match Points mirror
reflects the FROZEN `match_engine.js` formula (read-only here; never modified).

They assert the V5.9.5 acceptance criteria:
  * Intern no longer lands the global optimum / a near-optimal deal,
  * the five rungs stay differentiated (no collapse) and the ladder ascends,
  * MD/VP keep their strong, green, risk-aware picks (not weakened),
  * selection is fully deterministic (same inputs -> same output),
  * no Overall Score / strategy rank / source_meta leaks anywhere.
"""

import re
from pathlib import Path

from modeling.ma.precompute import list_arena_pairs
from modeling.ma.real_seed_deck import REAL_SEED_COMPANY_CARDS

_ROOT = Path(__file__).resolve().parents[1]
_ROBOT_JS = (_ROOT / "static" / "modeling" / "js" / "robot_opponent.js").read_text(encoding="utf-8")

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


# ── Faithful Python port of robot_opponent.js selection ─────────────────────

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


def select(diff, pairs, exclude):
    w = STRATEGY[diff]
    scored = []
    for p in pairs:
        if p["acquirer_id"] == p["target_id"]:
            continue
        k = _key(p)
        if k in exclude:
            continue
        s = _score(p, w)
        if s is None:
            continue
        scored.append((s, k, p))
    if not scored:
        return None
    scored.sort(key=lambda x: (-x[0], x[1]))
    skip = max(0, int(w.get("rankSkip", 0)))
    return scored[min(skip, len(scored) - 1)]


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
    syn = _SYN_PTS.get(p.get("default_synergy_tier"), 0)
    total += syn
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


def _five_round_picks(diff, pairs):
    """One seat of `diff` plays five rounds, excluding its own prior picks
    (mirrors robotRecentKeys / playedKeys exclusion)."""
    exclude, picks = set(), []
    for _ in range(5):
        b = select(diff, pairs, exclude)
        if not b:
            break
        exclude.add(b[1])
        picks.append(b[2])
    return picks


# ── Tests ───────────────────────────────────────────────────────────────────

def test_parsed_strategy_complete():
    for d in DIFFICULTIES:
        for k in ("eps", "viaPenalty", "softRedPenalty", "outlierDistrust", "rankSkip", "redVeto"):
            assert k in STRATEGY[d], (d, k)


def test_intern_does_not_land_global_optimum_or_near_optimal():
    """The headline retune: Intern's first pick must NOT be the global
    Match-Points optimum (it was `panw->dis` MP#1 before) nor anywhere near the
    top — it lands a 'good but not top' deal."""
    pairs = list_arena_pairs()
    by_mp = sorted(pairs, key=lambda p: -match_points(p))
    mp_rank = {_key(p): i for i, p in enumerate(by_mp)}

    intern_first = select("intern", pairs, set())[2]
    rank = mp_rank[_key(intern_first)]
    assert rank >= 50, f"Intern first pick MP-rank #{rank+1} is still near-optimal"

    # And not the raw global EPS argmax either (the +418% outlier).
    eps_argmax = max(
        (p for p in pairs if isinstance(p.get("accretion_dilution_pct"), (int, float))),
        key=lambda p: p["accretion_dilution_pct"],
    )
    assert _key(intern_first) != _key(eps_argmax)


def test_intern_still_picks_a_plausible_accretive_deal():
    """Weaker, not sabotaged: Intern still chases EPS — its pick is strongly
    accretive (it just doesn't scrutinise viability)."""
    pairs = list_arena_pairs()
    intern_first = select("intern", pairs, set())[2]
    assert intern_first["is_accretive"] is True
    assert intern_first["accretion_dilution_pct"] > 0.30  # clearly accretive, "looks good"


def test_intern_walks_into_risk_elites_avoid():
    """Across five rounds the Intern lands real weaker-viability (non-green)
    deals — exactly the risk the careful rungs price in and it doesn't. The
    invariant is relative (deck-size robust): the Intern walks into strictly more
    risk than the green-only elites, who hold a hard red veto + high viability
    weight."""
    pairs = list_arena_pairs()
    intern = _five_round_picks("intern", pairs)
    md = _five_round_picks("md", pairs)
    assert len(intern) == 5
    intern_risk = sum(1 for p in intern if p.get("viability_level") != "green")
    md_risk = sum(1 for p in md if p.get("viability_level") != "green")
    assert intern_risk >= 2, [p.get("viability_level") for p in intern]
    assert intern_risk > md_risk, (intern_risk, md_risk)


def test_difficulty_ladder_ascends_in_match_points():
    """Aggregate five-round Match Points must ascend out of the Intern: it is
    strictly the weakest, and Analyst is clearly stronger. The elite rungs form a
    strong cluster above both."""
    pairs = list_arena_pairs()
    totals = {d: sum(match_points(p) for p in _five_round_picks(d, pairs)) for d in DIFFICULTIES}
    assert totals["intern"] < totals["analyst"], totals
    assert totals["analyst"] < totals["associate"], totals
    # Intern is strictly the weakest of all five rungs.
    assert totals["intern"] == min(totals.values()), totals
    # And clearly so (not a marginal gap) — a beginner game is now winnable.
    assert totals["analyst"] - totals["intern"] >= 40, totals


def test_difficulties_do_not_collapse():
    """Five rungs must produce differentiated choices (not five copies of one
    rule). At least three distinct first picks, and the VP/MD five-round paths
    diverge even where they share a first pick."""
    pairs = list_arena_pairs()
    firsts = {d: _key(select(d, pairs, set())[2]) for d in DIFFICULTIES}
    assert len(set(firsts.values())) >= 3, firsts
    assert firsts["intern"] != firsts["md"], firsts
    vp_seq = [_key(p) for p in _five_round_picks("vp", pairs)]
    md_seq = [_key(p) for p in _five_round_picks("md", pairs)]
    assert vp_seq != md_seq


def test_md_and_vp_not_weakened_stay_green_and_risk_aware():
    """The strong rungs keep choosing clean, accretive, green deals (hard red
    veto holds): high quality, never a regulatory dead-end."""
    pairs = list_arena_pairs()
    for diff in ("vp", "md"):
        picks = _five_round_picks(diff, pairs)
        assert len(picks) == 5
        assert all(p.get("viability_level") == "green" for p in picks), diff
        assert all(p.get("is_accretive") for p in picks), diff


def test_selection_is_fully_deterministic():
    """Same deck / round / difficulty -> identical pick, every time, for every
    rung (no randomness anywhere)."""
    pairs = list_arena_pairs()
    for d in DIFFICULTIES:
        a = [_key(p) for p in _five_round_picks(d, pairs)]
        b = [_key(p) for p in _five_round_picks(d, pairs)]
        assert a == b, d


def test_two_intern_seats_never_duplicate_in_a_round():
    """In an Intern+Intern match robot_2 excludes robot_1's pick, so the two
    seats never play the same directed pair in one round (mirrors robotsPlay)."""
    pairs = list_arena_pairs()
    exclude = set()
    for _ in range(5):
        b1 = select("intern", pairs, exclude)
        exclude.add(b1[1])
        b2 = select("intern", pairs, exclude)
        exclude.add(b2[1])
        assert b1[1] != b2[1]


def test_no_overall_score_or_internal_signal_leak_in_source():
    """strategy_rank / rank-window internals must never be relabelled as an
    Overall Score, and no source_meta rides along."""
    for banned in ("综合评分", "Overall Score", "胜率", "win_rate", "overall_score",
                   "source_meta", "field_sources"):
        assert banned not in _ROBOT_JS, banned
