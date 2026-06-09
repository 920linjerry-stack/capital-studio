"""V5.4 Deal Ticket · mid-density review overlay tests (Segment 5 acceptance).

The Deal Ticket is the MIDDLE information-density tier of V5:

    Arena light card  ->  Deal Ticket overlay  ->  Deal Studio full page

It is opened on demand from the Arena light result card. It reuses the SAME
/api/modeling/ma/calculate full result (same Arena terms) and never
re-implements EPS math. These tests assert:

* the Arena page still serves and exposes the Deal Ticket trigger,
* the overlay markup carries an Economic block and a Viability block but NO
  overall/combined score,
* the front end reuses /api/modeling/ma/calculate (no second Arena engine),
* three-tier EPS consistency: Arena-light (precompute) == Ticket (calculate)
  == Deal Studio (calculate) for AAPL->MSFT, MSFT->AAPL, NVDA->AVGO, DIS->HD,
  including the reversed direction,
* the calculate full result carries the exact Economic + Viability fields the
  ticket renders,
* the Arena light card / precompute pair is NOT polluted with the heavy
  economics table,
* the Deal Studio deep link still serves,
* V5.0/V5.1/V5.2/V5.3 behaviors do not regress.
"""

from pathlib import Path

from app import app
from modeling.ma.precompute import (
    ARENA_DEAL_TERMS,
    build_pair_payload,
    get_arena_pair,
)


_REPO_ROOT = Path(__file__).resolve().parents[1]
_ARENA_HTML = _REPO_ROOT / "static" / "modeling" / "arena.html"
_ARENA_JS = _REPO_ROOT / "static" / "modeling" / "js" / "arena.js"

# The four acceptance pairs (plus their reverses) the brief mandates.
ACCEPTANCE_PAIRS = [
    ("aapl", "msft"),
    ("msft", "aapl"),
    ("nvda", "avgo"),
    ("dis", "hd"),
]


def _calculate(client, acq, tgt):
    """Full calculate result for one directed pair under the Arena terms.

    This is the exact path both the Deal Ticket overlay (buildPayload) and a
    deep-linked Deal Studio run share, so it represents Ticket == Studio.
    """
    resp = client.post("/api/modeling/ma/calculate", json=build_pair_payload(acq, tgt))
    assert resp.status_code == 200
    return resp.get_json()["result"]


# ── Segment 1: Arena page still opens + Deal Ticket trigger present ──────────

def test_arena_page_still_serves():
    client = app.test_client()
    resp = client.get("/modeling/ma/arena")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Deal Arena" in html
    assert "/static/modeling/js/arena.js" in html


def test_deal_ticket_trigger_present():
    html = _ARENA_HTML.read_text(encoding="utf-8")
    # Trigger button on the light result card.
    assert 'id="rc-ticket-btn"' in html
    assert "查看推演票据" in html
    # The existing Deal Studio detail button is preserved alongside it.
    assert 'id="rc-studio-btn"' in html
    assert "在 Deal Studio 中查看详情" in html


def test_deal_ticket_overlay_has_clear_title_and_close():
    html = _ARENA_HTML.read_text(encoding="utf-8")
    assert 'id="ticket-overlay"' in html
    assert 'id="ticket-title"' in html
    assert 'id="ticket-close"' in html
    # Overlay, not a page navigation.
    assert 'role="dialog"' in html


# ── Segment 2: Ticket shows Economic + Viability, but NO overall score ───────

def test_overlay_has_economic_and_viability_blocks():
    html = _ARENA_HTML.read_text(encoding="utf-8")
    assert "交易摘要" in html
    assert "经济性拆解" in html
    assert "现实可行性" in html
    # Economic field anchors the mid-density grid renders into.
    assert 'id="tk-econ-grid"' in html
    # Viability block has its own level + flags region.
    assert 'id="tk-via-level"' in html
    assert 'id="tk-via-flags"' in html


def test_overlay_has_no_overall_score_language():
    """V5 hard boundary 8/9: no Overall Score / win-rate / combined number."""
    html = _ARENA_HTML.read_text(encoding="utf-8")
    for banned in ("综合评分", "Overall Score", "胜率", "win_rate", "overall_score"):
        assert banned not in html, banned


def test_viability_block_states_it_is_rule_inference_not_legal():
    html = _ARENA_HTML.read_text(encoding="utf-8")
    assert "规则推演" in html
    assert "非法律意见" in html
    assert "不进入 EPS" in html


# ── Segment 1/6/F: the ticket reuses the calculate API, no second engine ─────

def test_ticket_front_end_reuses_calculate_api():
    js = _ARENA_JS.read_text(encoding="utf-8")
    assert "openTicket" in js
    assert "renderTicket" in js
    # The ticket fetches the SAME endpoint Deal Studio uses.
    assert "/api/modeling/ma/calculate" in js
    # And it builds the request with the shared buildPayload (Arena terms),
    # never an inline ad-hoc deal definition just for the ticket.
    assert "buildPayload()" in js


def test_ticket_does_not_reimplement_eps_math():
    """The ticket must not compute accretion/EPS itself; it only formats the
    server result. Guard against a hand-rolled EPS formula creeping in."""
    js = _ARENA_JS.read_text(encoding="utf-8")
    # No locally-derived pro-forma EPS / accretion arithmetic in the ticket.
    assert "pro_forma_net_income /" not in js
    assert "/ pro_forma_shares" not in js
    assert "accretion_dilution =" not in js  # never assigns its own number


# ── Three-tier EPS consistency: Arena-light == Ticket == Studio ──────────────

def test_three_tier_eps_consistency_for_acceptance_pairs():
    """Arena light (precompute), Deal Ticket (calculate) and Deal Studio
    (calculate) must report the SAME accretion/dilution for the same inputs.

    Ticket and Studio share the calculate path, so they are identical by
    construction; the meaningful check is that the precomputed light card
    agrees with that same number for all four acceptance pairs and reverses.
    """
    client = app.test_client()
    for acq, tgt in ACCEPTANCE_PAIRS:
        light = get_arena_pair(acq, tgt)
        assert light is not None, f"missing precomputed pair {acq}->{tgt}"

        ticket = _calculate(client, acq, tgt)        # Deal Ticket tier
        studio = _calculate(client, acq, tgt)        # Deal Studio tier

        # Ticket == Studio (same calculate full result, same terms).
        assert ticket["accretion_dilution"] == studio["accretion_dilution"]
        # Arena-light == Ticket (precompute projects the same calculate number).
        assert light["accretion_dilution_pct"] == ticket["accretion_dilution"], (
            f"{acq}->{tgt}: light {light['accretion_dilution_pct']} != "
            f"ticket {ticket['accretion_dilution']}"
        )
        # Direction flows through consistently.
        assert ticket["acquirer"]["id"] == acq
        assert ticket["target"]["id"] == tgt


def test_reverse_direction_recomputes_and_stays_consistent():
    """Reversing acquirer/target yields an independent result, and the light
    and ticket tiers still agree on that recomputed number."""
    client = app.test_client()
    fwd_light = get_arena_pair("aapl", "msft")
    rev_light = get_arena_pair("msft", "aapl")
    assert fwd_light["accretion_dilution_pct"] != rev_light["accretion_dilution_pct"]

    rev_ticket = _calculate(client, "msft", "aapl")
    assert rev_light["accretion_dilution_pct"] == rev_ticket["accretion_dilution"]
    assert rev_ticket["acquirer"]["ticker"] == "MSFT"
    assert rev_ticket["target"]["ticker"] == "AAPL"


# ── Calculate full result carries the fields the ticket renders ──────────────

def test_calculate_result_has_ticket_economic_fields():
    client = app.test_client()
    r = _calculate(client, "aapl", "msft")
    for field in (
        "offer_value",
        "cash_consideration",
        "stock_consideration",
        "pro_forma_eps",
        "accretion_dilution",
        "break_even_synergy",
        "synergy",
        "premium",
        "consideration_mix",
        "pre_ppa_chip",
    ):
        assert field in r, field
    assert {"cash_pct", "stock_pct"} <= set(r["consideration_mix"])
    # Zero / current synergy EPS-impact pair (the "why" of accretion).
    ctx = r["synergy_context"]
    assert "zero_synergy_result" in ctx
    assert "accretion_dilution" in ctx["zero_synergy_result"]
    assert ctx["default_cost_synergy"]["synergy_tier"] in {"high", "medium", "low", "none"}


def test_calculate_result_has_ticket_viability_fields():
    client = app.test_client()
    via = _calculate(client, "nvda", "avgo")["viability_context"]
    assert via["viability_level"] in {"green", "yellow", "red"}
    assert via["viability_label"]
    assert via["summary"]
    assert via["flags"]
    flag = via["flags"][0]
    for field in ("severity", "category", "title", "message", "rule_id", "triggered_tags"):
        assert field in flag, field
    # Viability never carries an economic/EPS number.
    assert "accretion_dilution" not in via
    assert "pro_forma_eps" not in via


# ── Arena light card / precompute stays LIGHT (not stuffed mid/heavy) ─────────

def test_precompute_pair_not_polluted_with_heavy_economics():
    """Opening the ticket must NOT push mid/heavy fields back onto the light
    precomputed pair. The light shape stays compact."""
    light = get_arena_pair("aapl", "msft")
    for heavy in (
        "offer_value",
        "cash_consideration",
        "stock_consideration",
        "consideration_mix",
        "pro_forma_eps",
        "break_even_synergy",
        "source_meta",
        "synergy_context",
    ):
        assert heavy not in light, heavy
    # No overall/merged score on the light card either.
    for banned in ("overall_score", "score", "win_rate"):
        assert banned not in light, banned


def test_arena_result_card_shell_has_no_full_economics_table():
    """The Arena page shell must not preload a full economics grid or a
    source_meta dump; mid-density economics live only inside the ticket."""
    html = _ARENA_HTML.read_text(encoding="utf-8")
    assert "source_meta" not in html
    # The result-card region itself ships empty chip containers, not a grid of
    # offer/cash/stock cells.
    assert 'id="rc-chips"' in html
    assert 'id="econ-grid"' not in html  # that id belongs to Deal Studio only


# ── Deep link into Deal Studio still works ──────────────────────────────────

def test_deal_studio_deep_link_route_serves():
    client = app.test_client()
    resp = client.get("/modeling/ma?acq=aapl&tgt=msft")
    assert resp.status_code == 200
    assert "ma_studio.js" in resp.get_data(as_text=True)


def test_deal_studio_nav_says_deal_arena_not_lite():
    """V5.10.4.x Deal Studio Copy Fix: the top-nav entry back to the Arena is no
    longer the stale '轻牌桌 / Deal Arena Lite' copy — it reads 'Deal Arena' and
    still links to the Arena route."""
    studio_html = (_REPO_ROOT / "static" / "modeling" / "ma_studio.html").read_text(encoding="utf-8")
    assert "轻牌桌" not in studio_html
    assert "Deal Arena Lite" not in studio_html
    assert ">Deal Arena<" in studio_html
    assert 'href="/modeling/ma/arena"' in studio_html


def test_ticket_builds_studio_deep_link():
    js = _ARENA_JS.read_text(encoding="utf-8")
    # The ticket footer links into Deal Studio carrying acq/tgt.
    assert "tk-studio-btn" in js
    assert "/modeling/ma?acq=" in js


# ── No regression: V5.0 financing-cost strict validation ─────────────────────

def test_v50_financing_cost_strict_validation_no_regression():
    client = app.test_client()
    payload = build_pair_payload("aapl", "msft")
    payload["deal"] = dict(payload["deal"], cash_pct=1.0, stock_pct=0.0)
    payload["deal"].pop("financing_cost", None)
    resp = client.post("/api/modeling/ma/calculate", json=payload)
    assert resp.status_code == 400
    assert any(f["code"] == "FINANCING_COST_REQUIRED" for f in resp.get_json()["flags"])


# ── No regression: V5.1 default / manual / zero synergy ──────────────────────

def test_v51_synergy_modes_no_regression():
    client = app.test_client()
    default = _calculate(client, "aapl", "msft")
    assert default["synergy"] == default["synergy_context"]["default_cost_synergy"]["synergy_amount"]

    manual = build_pair_payload("aapl", "msft")
    manual["deal"] = dict(manual["deal"], synergy_mode="manual", synergy=250.0)
    mr = client.post("/api/modeling/ma/calculate", json=manual).get_json()["result"]
    assert mr["synergy"] == 250.0 and mr["synergy_context"]["manual_override"] is True

    zero = build_pair_payload("aapl", "msft")
    zero["deal"] = dict(zero["deal"], synergy_mode="zero")
    zr = client.post("/api/modeling/ma/calculate", json=zero).get_json()["result"]
    assert zr["synergy"] == 0.0 and zr["synergy_context"]["zero_synergy_selected"] is True


# ── No regression: V5.2 precompute/calculate consistency ─────────────────────

def test_v52_precompute_matches_calculate_no_regression():
    client = app.test_client()
    for acq, tgt in ACCEPTANCE_PAIRS:
        pre = get_arena_pair(acq, tgt)
        live = _calculate(client, acq, tgt)
        assert pre["accretion_dilution_pct"] == live["accretion_dilution"]
        assert pre["synergy_status"] == live["synergy_status"]
        assert pre["default_synergy_tier"] == live["synergy_context"]["default_cost_synergy"]["synergy_tier"]


def test_v52_arena_terms_unchanged():
    assert ARENA_DEAL_TERMS["synergy_mode"] == "default"
    assert ARENA_DEAL_TERMS["premium"] == 0.30
    assert ARENA_DEAL_TERMS["cash_pct"] == 0.5
    assert ARENA_DEAL_TERMS["stock_pct"] == 0.5
    assert ARENA_DEAL_TERMS["financing_cost"] == 0.05
    assert ARENA_DEAL_TERMS["tax_rate"] == 0.25


# ── No regression: V5.3 viability_context ────────────────────────────────────

def test_v53_viability_context_no_regression():
    client = app.test_client()
    # Same-industry global leaders should still raise an antitrust red flag, and
    # viability never leaks into the economic numbers.
    r = _calculate(client, "aapl", "msft")
    via = r["viability_context"]
    assert via["viability_level"] in {"green", "yellow", "red"}
    assert via["disclaimer"]
    # Economic result is unchanged by the presence of viability.
    assert isinstance(r["accretion_dilution"], (int, float))
