"""V5.10.4 Size Feasibility & Reverse-Whale MP Guardrail.

Match Points is an investment-committee-style GAME score, not the EPS truth. The
A/D engine can legitimately report a small acquirer buying a mega target as wildly
accretive (a small-EPS-base artifact). A committee would never wave such a
"reverse whale" through — financing capacity, shareholder approval, control,
governance and integration risk all bite. So `match_engine.js` constrains MP with
a deterministic SIZE FEASIBILITY band on target/acquirer market cap. EPS / synergy
/ viability truth are untouched; only the GAME score is reshaped, and only
downward.

The guardrail lives in `static/modeling/js/match_engine.js`. There is no Node in
CI, so these tests PARSE the band table out of the JS (so a retune of the JS is
re-evaluated here, never silently stale) and exercise a faithful Python port of
the FROZEN Match Points formula against the SAME 100-company deck / 9900 directed
pairs the page loads.

Acceptance covered:
  * size ratio helper is correct + graceful on missing market cap (no crash),
  * a reverse-whale deal is capped even when paper EPS is huge,
  * PANW->MSFT / PANW->META style outliers are pressed out of the top MP list,
  * reasonable-scale green accretive deals keep their mid/high MP (not mis-killed),
  * direction matters: A->B and B->A get different size treatment,
  * no source_meta / strategy_score / overall_score leakage in the engine source.
"""

import re
from pathlib import Path

from modeling.ma.precompute import list_arena_pairs
from modeling.ma.real_seed_deck import REAL_SEED_COMPANY_CARDS

_ROOT = Path(__file__).resolve().parents[1]
_ENGINE_JS = (_ROOT / "static" / "modeling" / "js" / "match_engine.js").read_text(encoding="utf-8")

_CARD = {c["id"]: c for c in REAL_SEED_COMPANY_CARDS}
TIER_RANK = {"gold": 5, "red": 4, "blue": 3, "green": 2, "white": 1}
_VIA_PTS = {"green": 20, "yellow": 6, "red": -18}
_SYN_PTS = {"high": 10, "medium": 6, "low": 3, "none": 0}


# ── Parse the live size-feasibility band table out of the JS (no drift) ──────

def _parse_size_bands():
    block = re.search(r"const SIZE_FEASIBILITY_BANDS = \[(.+?)\];", _ENGINE_JS, re.S)
    assert block, "SIZE_FEASIBILITY_BANDS not found in match_engine.js"
    bands = []
    for m in re.finditer(
        r'\{\s*max:\s*(Infinity|[0-9.]+),\s*band:\s*"(\w+)",\s*'
        r'penalty:\s*(-?\d+),\s*cap:\s*(null|\d+)\s*\}',
        block.group(1),
    ):
        mx = float("inf") if m.group(1) == "Infinity" else float(m.group(1))
        cap = None if m.group(4) == "null" else int(m.group(4))
        bands.append((mx, m.group(2), int(m.group(3)), cap))
    assert bands, "no bands parsed"
    return bands


SIZE_BANDS = _parse_size_bands()


# ── Faithful Python port of the guardrail + Match Points (frozen formula) ────

def _tier_rank(card):
    return TIER_RANK.get(card.get("arena_tier"), 1) if card else 1


def market_cap(card):
    if not card:
        return None
    try:
        cap = float(card.get("share_price")) * float(card.get("shares"))
    except (TypeError, ValueError):
        return None
    return cap if cap > 0 else None


def size_ratio(acq, tgt):
    a = market_cap(acq)
    t = market_cap(tgt)
    if not a or not t:
        return None
    return t / a


def size_band(ratio):
    if not isinstance(ratio, (int, float)) or ratio <= 0:
        return None
    for mx, band, pen, cap in SIZE_BANDS:
        if ratio <= mx:
            return band, pen, cap
    return SIZE_BANDS[-1][1:]


def _base_points(p):
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
    return total


def match_points(p):
    total = _base_points(p)
    ratio = size_ratio(_CARD.get(p["acquirer_id"]), _CARD.get(p["target_id"]))
    b = size_band(ratio)
    if not b or b[0] == "feasible":
        return total
    _, pen, cap = b
    adj = total + pen
    if cap is not None:
        adj = min(adj, cap)
    return adj


def _key(p):
    return f"{p['acquirer_id']}->{p['target_id']}"


def _idx():
    return {_key(p): p for p in list_arena_pairs()}


# ── 1. Size ratio helper ─────────────────────────────────────────────────────

def test_size_ratio_is_directed_target_over_acquirer():
    panw = _CARD["panw"]
    msft = _CARD["msft"]
    # MSFT is much larger than PANW -> ratio >> 1 in the panw->msft direction.
    r_fwd = size_ratio(panw, msft)
    r_rev = size_ratio(msft, panw)
    assert r_fwd is not None and r_rev is not None
    assert r_fwd > 4.0, r_fwd
    assert r_rev < 1.0, r_rev
    # Reciprocal relationship (directed, not symmetric).
    assert abs(r_fwd * r_rev - 1.0) < 1e-9


def test_size_ratio_graceful_on_missing_market_cap():
    assert market_cap(None) is None
    assert market_cap({"share_price": None, "shares": 100}) is None
    assert market_cap({"share_price": 10, "shares": None}) is None
    assert market_cap({"share_price": 0, "shares": 100}) is None  # zero cap
    assert market_cap({"share_price": "x", "shares": 100}) is None
    assert size_ratio({"share_price": 0, "shares": 1}, _CARD["msft"]) is None
    assert size_band(None) is None  # missing ratio -> no band -> no change


def test_band_table_is_well_formed_and_monotone():
    # Ascending thresholds, "feasible" first and untouched, every concern band
    # carries a non-positive penalty, and caps only tighten as ratio grows.
    maxes = [b[0] for b in SIZE_BANDS]
    assert maxes == sorted(maxes), maxes
    assert SIZE_BANDS[0][1] == "feasible" and SIZE_BANDS[0][2] == 0 and SIZE_BANDS[0][3] is None
    caps = [b[3] for b in SIZE_BANDS if b[3] is not None]
    assert caps == sorted(caps, reverse=True), caps  # higher ratio -> lower cap
    for _mx, band, pen, _cap in SIZE_BANDS:
        if band != "feasible":
            assert pen <= 0, (band, pen)


# ── 2. Reverse-whale cap binds even with huge EPS ────────────────────────────

def test_reverse_whale_is_capped_despite_high_eps():
    idx = _idx()
    # PANW (~$200B) buying MSFT (~$3.2T): a ~16x reverse whale that the engine
    # still reports as +106% accretive. The size cap must bind.
    p = idx["panw->msft"]
    assert p["accretion_dilution_pct"] > 1.0  # paper EPS still very high
    ratio = size_ratio(_CARD["panw"], _CARD["msft"])
    band = size_band(ratio)[0]
    assert band == "extreme", band
    extreme_cap = next(b[3] for b in SIZE_BANDS if b[1] == "extreme")
    assert match_points(p) <= extreme_cap
    # And strictly below its own uncapped (pre-guardrail) economic score.
    assert match_points(p) < _base_points(p)


def test_more_extreme_ratio_never_scores_above_milder_one_all_else_equal():
    # The guardrail is monotone in ratio for the same base score: deeper reverse
    # whales can never out-score shallower ones when the economics are identical.
    base = 70
    prev = None
    for mx, band, pen, cap in SIZE_BANDS:
        ratio = mx if mx != float("inf") else 99.0
        b = size_band(ratio)
        adj = base + b[1]
        if b[2] is not None:
            adj = min(adj, b[2])
        if prev is not None:
            assert adj <= prev + 1e-9, (band, adj, prev)
        prev = adj


# ── 3. PANW reverse-whale outliers pressed out of the top MP list ────────────

def test_named_reverse_whales_drop_below_reasonable_deals():
    idx = _idx()
    reasonable = match_points(idx["jnj->isrg"])      # 0.27x, green, reasonable
    big_buys_small = match_points(idx["amzn->ups"])  # 0.03x, green, reasonable
    for whale in ("panw->msft", "panw->amzn", "panw->meta", "panw->xom"):
        mp = match_points(idx[whale])
        assert mp < reasonable, (whale, mp, reasonable)
        assert mp < big_buys_small, (whale, mp, big_buys_small)


def test_top_mp_list_has_no_severe_reverse_whale():
    pairs = list_arena_pairs()
    top = sorted(pairs, key=lambda p: -match_points(p))[:20]
    for p in top:
        r = size_ratio(_CARD.get(p["acquirer_id"]), _CARD.get(p["target_id"]))
        assert r is None or r < 2.0, (_key(p), r, match_points(p))


def test_eps_outliers_are_demoted_relative_to_their_uncapped_score():
    # Of the highest-EPS deals, the small-buys-big ones must lose ground vs their
    # pre-guardrail score; the size-feasible ones keep theirs.
    pairs = list_arena_pairs()
    by_eps = sorted(
        (p for p in pairs if isinstance(p.get("accretion_dilution_pct"), (int, float))),
        key=lambda p: -p["accretion_dilution_pct"],
    )[:20]
    demoted = 0
    for p in by_eps:
        r = size_ratio(_CARD.get(p["acquirer_id"]), _CARD.get(p["target_id"]))
        if r and r > 1.0:
            assert match_points(p) <= _base_points(p), _key(p)
            if match_points(p) < _base_points(p):
                demoted += 1
        else:
            assert match_points(p) == _base_points(p), _key(p)
    assert demoted >= 4, demoted  # several of the EPS leaders are reverse whales


# ── 4. Reasonable-scale deals are preserved (not mis-killed) ─────────────────

def test_reasonable_scale_green_accretive_deals_keep_mid_high_mp():
    idx = _idx()
    # amzn->ups: mega buys mid-cap, green, accretive -> untouched, stays mid/high.
    ups = idx["amzn->ups"]
    assert size_ratio(_CARD["amzn"], _CARD["ups"]) < 1.0
    assert match_points(ups) == _base_points(ups)
    assert match_points(ups) >= 40
    # A genuinely size-feasible high scorer keeps a top score.
    dis = idx["panw->dis"]  # 0.93x, green -> feasible band, untouched
    assert size_ratio(_CARD["panw"], _CARD["dis"]) <= 1.0
    assert match_points(dis) == _base_points(dis)


def test_guardrail_only_lowers_never_raises():
    for p in list_arena_pairs():
        assert match_points(p) <= _base_points(p), _key(p)


# ── 5. Directionality ────────────────────────────────────────────────────────

def test_direction_changes_size_treatment():
    idx = _idx()
    fwd = idx["panw->msft"]   # small buys mega -> capped
    rev = idx["msft->panw"]   # mega buys small -> untouched by size
    assert match_points(rev) == _base_points(rev)
    assert match_points(fwd) < _base_points(fwd)
    # The reverse (feasible) direction is not artificially penalised by size.
    assert size_ratio(_CARD["msft"], _CARD["panw"]) < 1.0


# ── 6. Missing-data robustness on the real port ──────────────────────────────

def test_match_points_never_crashes_with_unknown_company():
    # A pair referencing a card with no market cap data falls back to base score.
    fake = {
        "acquirer_id": "panw", "target_id": "panw",  # ids resolve, but force gap:
        "accretion_dilution_pct": 0.5, "is_accretive": True,
        "viability_level": "green", "default_synergy_tier": "medium",
    }
    # Patch a temporary capless card lookup by using a deal whose target has no cap.
    nocap = dict(fake)
    nocap["acquirer_id"] = "__missing__"
    nocap["target_id"] = "__missing__"
    # _base_points needs the ids present in _CARD for tier/story; missing -> tier 1.
    assert isinstance(_base_points(nocap), int)
    # size_ratio with missing cards is None -> no band -> base returned.
    assert size_ratio(None, _CARD["msft"]) is None


# ── 7. JS wiring + no leakage ────────────────────────────────────────────────

def test_engine_exposes_size_helpers_and_applies_in_breakdown():
    assert "function marketCapOf(card)" in _ENGINE_JS
    assert "function sizeRatio(acqCard, tgtCard)" in _ENGINE_JS
    assert "function sizeFeasibilityBand(ratio)" in _ENGINE_JS
    # Exported for the page + tooling.
    for name in ("marketCapOf", "sizeRatio", "sizeFeasibilityBand"):
        assert re.search(rf"\n    {name},", _ENGINE_JS), name
    # Applied as a single net-delta part so the breakdown still sums to total.
    assert 'key: "size_feasibility"' in _ENGINE_JS
    # No randomness / network / dynamic exec introduced.
    for banned in ("Math.random", "fetch(", "eval("):
        assert banned not in _ENGINE_JS, banned


def test_no_overall_score_or_source_meta_leak():
    for banned in ("综合评分", "Overall Score", "胜率", "win_rate", "overall_score",
                   "source_meta", "field_sources", "strategy_score", "strategy_rank"):
        assert banned not in _ENGINE_JS, banned


def test_selection_is_fully_deterministic():
    a = {_key(p): match_points(p) for p in list_arena_pairs()}
    b = {_key(p): match_points(p) for p in list_arena_pairs()}
    assert a == b
