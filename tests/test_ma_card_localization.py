"""V5.9.6 Card Localization & Visual Readability tests.

Company cards now show a player-friendly Chinese name + Chinese sector (ticker
kept) and a per-tier card SURFACE so Legendary/Elite/Core/Specialist/Basic differ
across the whole face, not just the border. The display mapping is a deterministic
front-end module `static/modeling/js/card_localization.js` (window.CardLocalization)
— it changes NO truth: financial fields, source_meta, the pairs payload,
precompute, the engine, Match Points and the robot strategy are untouched.

There is no Node runtime in CI, so the JS mapping is PARSED from source and checked
against the real frozen deck (so a future deck card that misses a Chinese field is
caught), plus static assertions that the renderers read the shared helpers and that
the tier surface CSS exists. The live render is covered by the documented browser
smoke. They assert:
  * every real-deck ticker has a non-empty Chinese name + sector (no undefined/blank),
  * every real-deck English sector has a Chinese fallback,
  * the renderers (deck / hand / slot / retain) use the localization helpers and
    keep ticker + Chinese name + Chinese sector, via safe DOM only,
  * each tier (gold/red/blue/green/white) has a card-surface treatment, not only a
    border, on every card-bearing page,
  * the module is loaded before the page scripts and leaks no truth.
"""

import re
from pathlib import Path

from modeling.ma.real_seed_deck import REAL_SEED_COMPANY_CARDS

_ROOT = Path(__file__).resolve().parents[1]
_LOC_JS = _ROOT / "static" / "modeling" / "js" / "card_localization.js"
_ARENA_JS = _ROOT / "static" / "modeling" / "js" / "arena.js"
_MATCH_JS = _ROOT / "static" / "modeling" / "js" / "arena_match.js"
_PLAY_JS = _ROOT / "static" / "modeling" / "js" / "arena_play.js"
_ARENA_HTML = _ROOT / "static" / "modeling" / "arena.html"
_MATCH_HTML = _ROOT / "static" / "modeling" / "arena_match.html"
_PLAY_HTML = _ROOT / "static" / "modeling" / "arena_play.html"

_TIERS = ("gold", "red", "blue", "green", "white")


def _r(p):
    return p.read_text(encoding="utf-8")


# ── Parse the display mapping out of the JS ──────────────────────────────────

def _parse_company_cn():
    js = _r(_LOC_JS)
    block = re.search(r"const COMPANY_CN = \{(.+?)\n  \};", js, re.S)
    assert block, "COMPANY_CN table not found"
    out = {}
    for tk, name, sector in re.findall(
        r'(\w+):\s*\{\s*name:\s*"([^"]*)",\s*sector:\s*"([^"]*)"\s*\}', block.group(1)
    ):
        out[tk] = {"name": name, "sector": sector}
    return out


def _parse_sector_cn():
    js = _r(_LOC_JS)
    block = re.search(r"const SECTOR_CN = \{(.+?)\n  \};", js, re.S)
    assert block, "SECTOR_CN table not found"
    return dict(re.findall(r'"([^"]+)":\s*"([^"]+)"', block.group(1)))


COMPANY_CN = _parse_company_cn()
SECTOR_CN = _parse_sector_cn()
DECK_TICKERS = [c["ticker"].upper() for c in REAL_SEED_COMPANY_CARDS]
DECK_SECTORS = sorted({c["sector"] for c in REAL_SEED_COMPANY_CARDS})


# ── 1. Coverage: every real-deck ticker localized, non-empty ────────────────

def test_every_deck_ticker_has_chinese_name_and_sector():
    missing = [t for t in DECK_TICKERS if t not in COMPANY_CN]
    assert not missing, f"deck tickers missing localization: {missing}"
    for t in DECK_TICKERS:
        entry = COMPANY_CN[t]
        assert entry["name"].strip(), f"{t} has empty name"
        assert entry["sector"].strip(), f"{t} has empty sector"
        # No literal undefined/null leaking as a display string.
        assert entry["name"] not in ("undefined", "null", "-")
        assert entry["sector"] not in ("undefined", "null", "-")


def test_localization_count_matches_deck_size():
    # The map may carry a couple of extra/legacy keys, but it must AT LEAST cover
    # the whole current deck (45) and not be a tiny sample.
    assert len(DECK_TICKERS) == 100
    assert len(COMPANY_CN) >= 100


def test_sample_tickers_have_expected_chinese_names():
    expected = {"AAPL": "苹果", "MSFT": "微软", "NVDA": "英伟达", "XOM": "埃克森美孚", "MCD": "麦当劳"}
    for t, name in expected.items():
        assert COMPANY_CN[t]["name"] == name, t
    # NVDA reads as 半导体, not just 科技 — a player-readable industry label.
    assert COMPANY_CN["NVDA"]["sector"] == "半导体"
    assert COMPANY_CN["MCD"]["sector"] == "餐饮"


# ── 2. Fallback: every English sector has a Chinese mapping ──────────────────

def test_every_deck_sector_has_chinese_fallback():
    missing = [s for s in DECK_SECTORS if s not in SECTOR_CN]
    assert not missing, f"deck sectors missing Chinese fallback: {missing}"


def test_helpers_have_graceful_fallback_chain():
    js = _r(_LOC_JS)
    # nameCn: map -> deck name -> ticker -> dash.
    assert "if (e && e.name) return e.name;" in js
    assert "if (card && card.name) return String(card.name);" in js
    # sectorCn: map -> english-sector map -> raw -> dash.
    assert "if (e && e.sector) return e.sector;" in js
    assert "SECTOR_CN[raw]" in js
    # Never throws on a null card.
    assert "if (!card) return" in js


# ── 3. Render: deck / hand / slot / retain read the shared helpers ──────────

def test_arena_renderers_use_localization_helpers():
    js = _r(_ARENA_JS)
    # Deck/hand card: Chinese name + Chinese sector via helpers (not raw c.name).
    assert 'el("div", "co-name", cnName(c))' in js
    assert 'el("div", "co-sub", cnSector(c))' in js
    assert 'el("div", "co-en", en)' in js
    # War Room deal-table slot.
    assert 'el("div", "slot-name", cnName(c))' in js
    assert 'el("div", "slot-sub", cnSector(c))' in js


def test_match_renderers_use_localization_helpers():
    js = _r(_MATCH_JS)
    assert 'el("div", "pcard-name", cnName(c))' in js
    assert 'el("div", "pcard-sub", cnSector(c))' in js
    assert 'el("div", "pslot-name", cnName(c))' in js
    assert 'el("div", "pslot-sub", cnSector(c))' in js
    # Retain modal chip carries the Chinese name.
    assert 'el("span", "rc-nm", cnName(c))' in js


def test_play_renderers_use_localization_helpers():
    js = _r(_PLAY_JS)
    assert 'el("div", "pcard-name", cnName(c))' in js
    assert 'el("div", "pcard-sub", cnSector(c))' in js
    assert 'el("div", "pslot-name", cnName(c))' in js
    assert 'el("div", "pslot-sub", cnSector(c))' in js


def test_helper_fallbacks_present_in_each_renderer():
    for js in (_r(_ARENA_JS), _r(_MATCH_JS), _r(_PLAY_JS)):
        assert "window.CardLocalization && window.CardLocalization.nameCn(c)" in js
        assert "window.CardLocalization && window.CardLocalization.sectorCn(c)" in js


# ── 4. Tier visual surface (not just border) on every card page ─────────────

def test_tier_color_tokens_defined_on_every_card_page():
    for html in (_ARENA_HTML, _MATCH_HTML, _PLAY_HTML):
        text = _r(html)
        for tier in _TIERS:
            assert re.search(rf"\.tier-{tier}\s*\{{[^}}]*--tier-color", text), f"{tier} in {html.name}"


def test_card_surface_uses_tier_wash_not_only_border():
    # War Room deck/hand cards get a tier-tinted background gradient.
    arena = _r(_ARENA_HTML)
    m = re.search(r"\.co-card\.arena-tier,\s*\.hand-card\.arena-tier\s*\{(.+?)\}", arena, re.S)
    assert m and "background:" in m.group(1) and "var(--tier-color)" in m.group(1)
    assert "color-mix(in srgb, var(--tier-color)" in m.group(1)
    # Match + sandbox hand cards: the fixed blue face is replaced by a tier wash.
    for html in (_MATCH_HTML, _PLAY_HTML):
        text = _r(html)
        m = re.search(r"\.pcard\.arena-tier\s*\{(.+?)\}", text, re.S)
        assert m, html.name
        body = m.group(1)
        assert "background:" in body and "var(--tier-color)" in body, html.name


def test_filled_slot_has_tier_surface():
    arena = _r(_ARENA_HTML)
    assert re.search(r"\.dt-slot\.arena-tier\.filled\s*\{[^}]*background:[^}]*var\(--tier-color\)", arena, re.S)
    for html in (_MATCH_HTML, _PLAY_HTML):
        text = _r(html)
        assert re.search(r"\.pslot\.arena-tier\.filled\s*\{[^}]*background:[^}]*var\(--tier-color\)", text, re.S), html.name


def test_retain_chip_keeps_tier_color_and_surface():
    match = _r(_MATCH_HTML)
    m = re.search(r"\.retain-chip\.arena-tier\s*\{(.+?)\}", match, re.S)
    assert m and "background:" in m.group(1) and "var(--tier-color)" in m.group(1)


# ── 5/6. Safe DOM — no innerHTML interpolation of card text ──────────────────

def _strip_comments(js):
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    js = re.sub(r"//[^\n]*", "", js)
    return js


def test_localization_module_is_safe_and_leaks_no_truth():
    # Scan CODE only — the header comment legitimately names these tokens in prose.
    code = _strip_comments(_r(_LOC_JS))
    for banned in ("innerHTML", "fetch(", "XMLHttpRequest", "Math.random", "eval(",
                   "source_meta", "field_sources", "accretion", "match_points"):
        assert banned not in code, banned


def test_renderers_have_no_innerhtml_interpolation_of_card_fields():
    for js in (_r(_ARENA_JS), _r(_MATCH_JS), _r(_PLAY_JS)):
        for m in re.finditer(r"\.innerHTML\s*=\s*(.+)", js):
            rhs = m.group(1).strip()
            assert rhs.startswith('""') or rhs.startswith("''"), rhs


# ── 7. Module load order + presence ─────────────────────────────────────────

def test_localization_loaded_before_page_scripts():
    pairs = [
        (_ARENA_HTML, "js/arena.js"),
        (_MATCH_HTML, "js/arena_match.js"),
        (_PLAY_HTML, "js/arena_play.js"),
    ]
    for html, page_script in pairs:
        text = _r(html)
        assert "card_localization.js" in text, html.name
        assert text.index("card_localization.js") < text.index(page_script), html.name
