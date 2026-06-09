"""V5.9.6.1 Legendary Border State Fix tests.

Bug: a gold/Legendary hand card showed a blue border when it was selected as the
acquirer (and amber when target) in its NON-hover state, then "recovered" to gold
only on hover. Root cause was CSS selector order/specificity: the selected-state
rule `.pcard.arena-tier.sel-acq` (specificity 0,3,0) set `border-color: var(--accent)`
which beat the base tier rule `.pcard.arena-tier` (0,2,0) in the resting state,
while the hover rule `.pcard-shell:hover .pcard.arena-tier` (0,4,0) restored the
tier color — producing the hover-only "gold flicker".

Fix: the selected state keeps `border-color: var(--tier-color)` and conveys the
acquirer/target role through the box-shadow ring only. So the border reads the SAME
tier color across normal / hover / selected for all five tiers, and is never
overwritten by a generic blue/amber border.

No Node runtime in CI, so the CSS is parsed from source and asserted statically; the
live render is covered by the documented browser smoke. The tier SURFACE / wash,
Chinese localization, and retain-chip treatment are covered by
test_ma_card_localization.py and are not changed here.
"""

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_ARENA_HTML = _ROOT / "static" / "modeling" / "arena.html"
_MATCH_HTML = _ROOT / "static" / "modeling" / "arena_match.html"
_PLAY_HTML = _ROOT / "static" / "modeling" / "arena_play.html"

# (file, selector substring that introduces the selected tier rule).
_SELECTED_RULES = [
    (_MATCH_HTML, ".pcard.arena-tier.sel-acq"),
    (_MATCH_HTML, ".pcard.arena-tier.sel-tgt"),
    (_PLAY_HTML, ".pcard.arena-tier.sel-acq"),
    (_PLAY_HTML, ".pcard.arena-tier.sel-tgt"),
    (_ARENA_HTML, ".hand-card.arena-tier.sel-acq"),
    (_ARENA_HTML, ".hand-card.arena-tier.sel-tgt"),
]


def _r(p):
    return p.read_text(encoding="utf-8")


def _rule_body(text, selector):
    """Return the declaration block for the FIRST rule whose selector list contains
    `selector`. Tolerant of multi-selector / multi-line CSS."""
    idx = text.find(selector)
    assert idx != -1, f"selector {selector!r} not found"
    open_brace = text.find("{", idx)
    close_brace = text.find("}", open_brace)
    assert open_brace != -1 and close_brace != -1
    return text[open_brace + 1:close_brace]


def test_selected_tier_card_keeps_tier_border_not_generic_color():
    """Selected acquirer/target tier cards must border with --tier-color, never a
    generic accent-blue or amber that would mask the tier."""
    for html, selector in _SELECTED_RULES:
        body = _rule_body(_r(html), selector)
        assert "border-color: var(--tier-color)" in body, f"{html.name} {selector}"
        # The generic role color must NOT live on the border anymore.
        assert "border-color: var(--accent)" not in body, f"{html.name} {selector}"
        assert "border-color: #d29922" not in body, f"{html.name} {selector}"


def test_selected_tier_card_still_signals_role_via_ring():
    """Role is still readable: acquirer shows an accent ring, target an amber ring,
    via box-shadow (not the border)."""
    for html in (_MATCH_HTML, _PLAY_HTML):
        text = _r(html)
        acq = _rule_body(text, ".pcard.arena-tier.sel-acq")
        tgt = _rule_body(text, ".pcard.arena-tier.sel-tgt")
        assert "0 0 0 1px var(--accent)" in acq, html.name
        assert "0 0 0 1px #d29922" in tgt, html.name
        # The inset tier bar survives so the tier reads top-and-edge.
        assert "inset 0 4px 0 var(--tier-color)" in acq, html.name
        assert "inset 0 4px 0 var(--tier-color)" in tgt, html.name
    arena = _r(_ARENA_HTML)
    acq = _rule_body(arena, ".hand-card.arena-tier.sel-acq")
    tgt = _rule_body(arena, ".hand-card.arena-tier.sel-tgt")
    assert "0 0 0 1px var(--accent)" in acq
    assert "0 0 0 1px #d29922" in tgt
    assert "inset 0 3px 0 var(--tier-color)" in acq
    assert "inset 0 3px 0 var(--tier-color)" in tgt


def test_hover_tier_rule_uses_tier_border_on_match_and_play():
    """The hover state already used the tier color; assert it stays so the resting
    and hover borders agree (no gold flicker)."""
    for html in (_MATCH_HTML, _PLAY_HTML):
        text = _r(html)
        body = _rule_body(text, ".pcard-shell:hover .pcard.arena-tier")
        assert "border-color: var(--tier-color)" in body, html.name


def test_base_tier_rule_borders_from_tier_color():
    """The resting tier rule derives its border from --tier-color (color-mix), so a
    non-selected gold card already shows gold at rest."""
    for html in (_MATCH_HTML, _PLAY_HTML):
        text = _r(html)
        body = _rule_body(text, ".pcard.arena-tier")
        assert "color-mix(in srgb, var(--tier-color)" in body, html.name
    arena = _r(_ARENA_HTML)
    body = _rule_body(arena, ".co-card.arena-tier, .hand-card.arena-tier")
    assert "color-mix(in srgb, var(--tier-color)" in body
