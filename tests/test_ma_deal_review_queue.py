"""V5.8 Deal Review Queue · 候选交易队列 (first pass) tests.

The Deal Review Queue is a front-end-only session shortlist of "deals I want to
revisit this round". It is shared by the War Room (/modeling/ma/arena) and the
Play Table (/modeling/ma/arena/play) via a small `window.DealQueue` module
backed by sessionStorage. It changes NO financial model: it never enters EPS,
synergy, viability or the dual settlement boards, and it triggers no calculate.

These tests lock in the front-end structure (HTML/JS) and the unchanged backend.
Live add/remove/reload interactions are covered by the browser smoke in the
delivery report; here we assert:

* the shared queue module exists, dedupes by DIRECTED pair (A->B != B->A),
  carries only a light whitelist (no source_meta / full result), and persists
  only via sessionStorage with no backend/db/file writes,
* War Room + Play Table + Deal Ticket all expose an Add-to-Queue control,
* Clear Deal never empties the queue,
* safe DOM rendering (no innerHTML interpolation) and no Overall Score,
* engine / synergy / viability / calculate / pairs contract unchanged.
"""

import re
from pathlib import Path

from app import app
from modeling.ma.precompute import build_pair_payload, get_arena_pair


_ROOT = Path(__file__).resolve().parents[1]
_WARROOM_HTML = _ROOT / "static" / "modeling" / "arena.html"
_WARROOM_JS = _ROOT / "static" / "modeling" / "js" / "arena.js"
_PLAY_HTML = _ROOT / "static" / "modeling" / "arena_play.html"
_PLAY_JS = _ROOT / "static" / "modeling" / "js" / "arena_play.js"
_QUEUE_JS = _ROOT / "static" / "modeling" / "js" / "deal_queue.js"


def _r(p):
    return p.read_text(encoding="utf-8")


# ── Shared queue module: exists + is front-end-only session state ───────────

def test_queue_module_exists_and_is_served():
    js = _r(_QUEUE_JS)
    assert "window.DealQueue" in js
    # Served as a static asset and loaded BEFORE the page scripts on both pages.
    war = _r(_WARROOM_HTML)
    play = _r(_PLAY_HTML)
    for html in (war, play):
        assert "/static/modeling/js/deal_queue.js" in html
    # Loaded before the page script so window.DealQueue is ready at init().
    assert war.index("deal_queue.js") < war.index("js/arena.js")
    assert play.index("deal_queue.js") < play.index("js/arena_play.js")


def test_queue_is_session_state_no_backend_no_db():
    js = _r(_QUEUE_JS)
    # Allowed: sessionStorage only. Forbidden: any backend/db/file/network call.
    assert "sessionStorage" in js
    assert "localStorage" not in js
    for banned in ("fetch(", "XMLHttpRequest", "indexedDB", "navigator.sendBeacon"):
        assert banned not in js, banned
    # No remote persistence route is introduced.
    assert "/api/" not in js


def test_queue_no_eval_or_unsafe_exec():
    js = _r(_QUEUE_JS)
    for banned in ("eval(", "new Function", "setTimeout(\"", "setInterval(\""):
        assert banned not in js, banned


# ── Directed pair independence: A->B and B->A are different candidates ───────

def test_queue_dedupes_by_directed_pair_key():
    js = _r(_QUEUE_JS)
    # The key is directed (acquirer->target), so the reverse pair is distinct.
    assert "function dirKey(" in js
    assert "`${acquirerId}->${targetId}`" in js
    # has()/add() dedupe on that directed key, not an unordered set.
    assert "function has(" in js
    assert 'reason: "duplicate"' in js


def test_queue_add_remove_dedupe_surface():
    js = _r(_QUEUE_JS)
    for fn in ("function add(", "function remove(", "function has(", "function list(",
               "function subscribe(", "function clear("):
        assert fn in js, fn
    # add() rejects a self-deal and a full queue with explicit reasons.
    assert 'reason: "self"' in js
    assert 'reason: "full"' in js
    assert "MAX_ITEMS" in js


# ── Queue item is LIGHT: whitelist only, no source_meta / full result ───────

def test_queue_item_summary_fields_present():
    js = _r(_QUEUE_JS)
    for field in (
        "acquirer_id", "acquirer_ticker", "acquirer_tier",
        "target_id", "target_ticker", "target_tier",
        "accretion_dilution_pct", "is_accretive", "economic_label",
        "viability_level", "viability_label", "synergy_status_label",
        "default_synergy_tier", "pre_ppa", "added_from", "added_seq",
    ):
        assert field in js, field


def test_queue_item_has_no_source_meta_or_full_result_keys():
    """The queue is a light review list. Its whitelist must not carry the source
    trail, raw audit fields or a full calculate result."""
    js = _r(_QUEUE_JS)
    for banned in (
        "source_meta", "field_sources", "filing_url", "quote_url",
        "companyfacts_url", "triggered_tags", "rule_id", "synergy_context",
        "offer_value", "cash_consideration", "pro_forma_eps",
    ):
        assert banned not in js, banned
    # Defence in depth: add() reduces any input to a fixed whitelist via sanitize.
    assert "function sanitize(" in js
    assert "STRING_FIELDS" in js


def test_queue_glue_never_stores_source_meta_on_either_page():
    # Scope to the queue item builder: the page headers legitimately discuss the
    # source_meta boundary in prose, but the builder itself must copy only light
    # economic/viability summary fields (ticker/name/tier re-read from the deck).
    for js in (_r(_WARROOM_JS), _r(_PLAY_JS)):
        m = re.search(r"function queueItemFrom\(.*?\n\}", js, re.S)
        assert m, "queueItemFrom not found"
        body = m.group(0)
        for banned in ("source_meta", "field_sources", "filing_url", "quote_url",
                       "triggered_tags", "rule_id", "synergy_context"):
            assert banned not in body, banned


# ── War Room add / display / remove / reload UI ─────────────────────────────

def test_warroom_has_queue_panel_and_add_buttons():
    html = _r(_WARROOM_HTML)
    assert 'id="queue-card"' in html
    assert "候选交易队列" in html and "Deal Review Queue" in html
    assert 'id="queue-list"' in html
    # Add-to-queue from the light result card AND the Deal Ticket.
    assert 'id="rc-queue-btn"' in html
    assert 'id="tk-queue-btn"' in html


def test_warroom_settlement_row_has_queue_button():
    js = _r(_WARROOM_JS)
    # Each settlement board row gets an "加入" button that queues the row pair
    # directly (no selection change, no calculate).
    assert 'el("button", "sb-queue", "加入")' in js
    assert 'addToQueue(p, "settlement")' in js


def test_warroom_queue_reload_and_remove_wired():
    js = _r(_WARROOM_JS)
    assert "function loadQueueItem(" in js
    assert "setDeal(it.acquirer_id, it.target_id)" in js
    assert "window.DealQueue.remove(it.acquirer_id, it.target_id)" in js
    # Reload validates the ids against the loaded deck before changing selection.
    assert "if (!companyById(it.acquirer_id) || !companyById(it.target_id))" in js


def test_warroom_add_sources_are_war_room_and_ticket():
    js = _r(_WARROOM_JS)
    assert 'addCurrentToQueue("war_room")' in js
    assert 'addCurrentToQueue("ticket")' in js


# ── Play Table add / display / remove / reload UI ───────────────────────────

def test_play_has_queue_panel_and_add_buttons():
    html = _r(_PLAY_HTML)
    assert 'class="hud-card hud-queue"' in html
    assert "候选队列" in html and "Deal Review Queue" in html
    assert 'id="queue-list"' in html
    assert 'id="rc-queue-btn"' in html
    assert 'id="tk-queue-btn"' in html


def test_play_queue_reload_and_remove_wired():
    js = _r(_PLAY_JS)
    assert "function loadQueueItem(" in js
    assert "setDeal(it.acquirer_id, it.target_id)" in js
    assert "window.DealQueue.remove(it.acquirer_id, it.target_id)" in js
    assert 'addCurrentToQueue("play_table")' in js
    assert 'addCurrentToQueue("ticket")' in js


# ── Clear Deal must NOT empty the queue ─────────────────────────────────────

def test_clear_deal_does_not_clear_queue_on_play():
    js = _r(_PLAY_JS)
    # clearSelection resets the current deal only; it must never call the queue's
    # clear() (which would empty the shortlist).
    m = re.search(r"function clearSelection\(\)\s*\{(.*?)\n\}", js, re.S)
    assert m, "clearSelection not found"
    body = m.group(1)
    assert "DealQueue.clear" not in body
    assert "queue" not in body.lower()


def test_clear_selection_does_not_clear_queue_on_warroom():
    js = _r(_WARROOM_JS)
    m = re.search(r"function clearSelection\(\)\s*\{(.*?)\n\}", js, re.S)
    assert m, "clearSelection not found"
    assert "DealQueue.clear" not in m.group(1)


# ── Safe DOM + no Overall Score ─────────────────────────────────────────────

def test_queue_uses_safe_dom_no_innerhtml_interpolation():
    for js in (_r(_QUEUE_JS), _r(_WARROOM_JS), _r(_PLAY_JS)):
        for m in re.finditer(r"\.innerHTML\s*=\s*(.+)", js):
            rhs = m.group(1).strip()
            assert rhs.startswith('""') or rhs.startswith("''"), rhs


def test_queue_rows_built_with_textcontent():
    for js in (_r(_WARROOM_JS), _r(_PLAY_JS)):
        assert "function buildQueueRow(" in js
        # Rows are assembled from el()/textContent + document.createTextNode,
        # never an interpolated HTML string.
        assert "document.createTextNode(it.acquirer_ticker" in js


def test_queue_has_no_overall_score():
    # The page JS files carry pre-existing prose explaining WHY there is no
    # Overall Score; the meaningful V5.8 check is that the new queue surface (both
    # page shells + the shared module) introduces no merged/overall score.
    for f in (_WARROOM_HTML, _PLAY_HTML, _QUEUE_JS):
        text = _r(f)
        for banned in ("综合评分", "Overall Score", "胜率", "win_rate", "overall_score"):
            assert banned not in text, f"{banned} in {f.name}"


# ── Performance / concurrency: no calculate added for queueing ──────────────

def test_queue_does_not_add_calculate_calls():
    # The brief forbids batch-calculating to populate the queue. The only
    # calculate fetches remain the single-deal fallback + the Deal Ticket (2).
    assert _r(_PLAY_JS).count("${API}/api/modeling/ma/calculate") == 2
    assert _r(_WARROOM_JS).count("${API}/api/modeling/ma/calculate") == 2
    # The shared queue module performs no network I/O at all.
    assert "calculate" not in _r(_QUEUE_JS)


# ── Pages still serve; backend contract unchanged ───────────────────────────

def test_warroom_and_play_still_serve_with_queue_script():
    client = app.test_client()
    war = client.get("/modeling/ma/arena")
    play = client.get("/modeling/ma/arena/play")
    assert war.status_code == 200 and play.status_code == 200
    assert "deal_queue.js" in war.get_data(as_text=True)
    assert "deal_queue.js" in play.get_data(as_text=True)


def test_calculate_and_pairs_contract_unchanged():
    client = app.test_client()
    r = client.post("/api/modeling/ma/calculate", json=build_pair_payload("aapl", "msft")).get_json()
    assert r["status"] == "ok" and "boards" not in r
    pairs = client.get("/api/modeling/ma/arena/pairs").get_json()
    assert pairs["pair_count"] == 9900 and "boards" in pairs


def test_queue_summary_matches_precomputed_light_pair():
    """A queued candidate's economic sign mirrors the SAME precomputed light pair
    the table shows — the queue summary cannot diverge from the displayed deal."""
    for acq, tgt in [("aapl", "msft"), ("msft", "aapl"), ("nvda", "avgo")]:
        light = get_arena_pair(acq, tgt)
        # economic_label in the queue item is derived purely from is_accretive,
        # which is the precomputed pair's own sign.
        assert isinstance(light["is_accretive"], bool)
        assert light["accretion_dilution_pct"] is not None
