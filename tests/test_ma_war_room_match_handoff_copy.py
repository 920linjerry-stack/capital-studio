"""V5.9.7.1 War Room Match Handoff Copy Fix.

A narrow COPY-ONLY hotfix. After V5.9.6.2 the Match always begins as a clean
game: Start Match opens a fresh five-round match whose deal table starts EMPTY,
and the War Room's current acquirer/target selection is intentionally NOT seated
on the Match table. The Deal Review Queue still persists across pages, but a
queued deal is preview / load / Ticket only and never auto-seats the table.

The War Room intro copy used to claim the opposite ("当前已选的买方/标的会一并带入"),
which is now wrong. These tests lock the corrected wording and guard against the
old claim returning. No state logic, layout, engine, Match Points, seed, Queue,
hand lifecycle, robot or source_meta behaviour is touched by this fix.
"""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_WARROOM_HTML = _ROOT / "static" / "modeling" / "arena.html"
_WARROOM_JS = _ROOT / "static" / "modeling" / "js" / "arena.js"


def _r(p):
    return p.read_text(encoding="utf-8")


# ── Acceptance 1: the old "selection is carried into Match" claim is gone ─────

def test_war_room_no_longer_claims_selection_is_carried_into_match():
    html = _r(_WARROOM_HTML)
    # The exact stale phrasing and any "一并带入" carry claim must be gone.
    assert "当前已选的买方/标的会一并带入" not in html
    assert "一并带入" not in html
    # The misleading dev comment in the handoff JS no longer claims a carry.
    js = _r(_WARROOM_JS)
    assert "carries the same selection into Match Setup" not in js


# ── Acceptance 2: copy states Match is a clean / empty table start ───────────

def test_war_room_copy_states_clean_table_start():
    html = _r(_WARROOM_HTML)
    assert "牌桌将从空桌开始" in html
    assert "不会自动带入 Match" in html


# ── Acceptance 3: copy explains the Queue persists but does not auto-seat ─────

def test_war_room_copy_explains_queue_persists_load_only():
    html = _r(_WARROOM_HTML)
    assert "候选队列 Queue 会保留" in html
    # The path to actually use a deal in the Match is: add to Queue, then load it
    # manually under the in-Match hand rules (never auto-seated).
    assert "请先加入 Queue" in html
    assert "手动" in html


# ── Acceptance 4: this is copy-only — the handoff wiring is unchanged ─────────

def test_handoff_wiring_unchanged_copy_only():
    js = _r(_WARROOM_JS)
    # The Start Match entry and sandbox link ids/targets are untouched.
    assert "start-match-btn" in js and "/modeling/ma/arena/match/setup" in js
    assert "start-tabletop-btn" in js and "/modeling/ma/arena/play" in js
    # The corrected comment now documents the clean-table behaviour.
    assert "Start Match always begins a clean game" in js
    # No source_meta / financial-truth leakage was introduced by the copy fix.
    for banned in ("source_meta", "field_sources", "filing_url"):
        assert banned not in _r(_WARROOM_HTML), banned
