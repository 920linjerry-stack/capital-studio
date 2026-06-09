"""V5.7.1.1 · Source-metadata boundary hardening.

Two deterministic QA blockers, fixed without touching deck data / tier / engine
/ synergy / viability / board sorting / UI:

  Blocker 1 — /api/modeling/ma/calculate echoed back the resolved companies WITH
  ``source_meta`` (and its nested ``field_sources`` / filing / quote /
  companyfacts URLs). That source trail belongs to the deck and the /samples
  inspection layer, not to a compute result. It is now stripped from the echo.

  Blocker 2 — normalize_company_card shallow-copied ``source_meta`` only at the
  top level, so the nested ``source_meta.field_sources`` mapping stayed shared
  with the frozen seed object. Mutating one getter result polluted every later
  read. It now defensively deep-copies the whole source_meta subtree.

These tests assert the calculate result is source-trail-free in every branch of
the tree, that nested mutation can no longer leak into later reads, and that the
build-time source trail on the deck / /samples is preserved.
"""

from modeling.ma.api import build_ma_response
from modeling.ma.company_deck import get_company_card, list_company_cards
from modeling.ma.precompute import build_pair_payload, list_arena_pairs

from app import app


EXPECTED_PAIRS = 100 * (100 - 1)  # 9900 directed pairs over the 100-company deck

# Keys that are part of the build-time source trail / audit layer and must never
# appear anywhere inside a /calculate result tree.
_BANNED_SOURCE_KEYS = {
    "source_meta",
    "field_sources",
    "filing_url",
    "quote_url",
    "companyfacts_url",
}


def _walk_keys(obj):
    """Yield every dict key that appears anywhere in a nested JSON structure."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield key
            yield from _walk_keys(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_keys(item)


def _calc_response():
    payload = build_pair_payload("aapl", "msft")
    body, code = build_ma_response(payload)
    assert code == 200, body
    assert body["status"] == "ok"
    return body


# ── Blocker 1 · /calculate carries no source metadata anywhere ───────────────

def test_calculate_result_has_no_source_meta_in_any_branch():
    body = _calc_response()
    keys = set(_walk_keys(body))
    leaked = keys & _BANNED_SOURCE_KEYS
    assert not leaked, f"calculate leaked source-trail keys: {sorted(leaked)}"


def test_calculate_company_echo_keeps_display_fields_but_drops_source_meta():
    body = _calc_response()
    for side in ("acquirer", "target"):
        echo = body["result"][side]
        # The UI still gets what it needs to label the deal ...
        for field in ("id", "ticker", "name", "revenue", "net_income", "shares", "share_price", "tags"):
            assert field in echo, f"{side} echo lost {field}"
        # ... but not the source trail.
        assert "source_meta" not in echo
        assert "field_sources" not in echo


def test_calculate_endpoint_text_has_no_audit_urls():
    client = app.test_client()
    raw = client.post(
        "/api/modeling/ma/calculate", json=build_pair_payload("nvda", "avgo")
    ).get_data(as_text=True)
    assert "source_meta" not in raw
    assert "field_sources" not in raw
    assert "sec.gov/Archives" not in raw          # filing_url
    assert "data.sec.gov/api/xbrl" not in raw     # companyfacts_url
    assert "finance.yahoo.com/v8/finance/chart" not in raw  # quote_url


# ── Blocker 2 · nested field_sources defensive deep copy ─────────────────────

def test_nested_field_sources_mutation_does_not_pollute_later_reads():
    first = get_company_card("v")  # Visa: a V5.7.1 card with a field-level trail
    assert first is not None
    assert "field_sources" in first["source_meta"]
    baseline = dict(first["source_meta"]["field_sources"])

    # Mutate the nested mapping on the returned object in several ways.
    first["source_meta"]["field_sources"]["revenue"] = "TAMPERED"
    first["source_meta"]["field_sources"]["__injected__"] = "x"
    first["source_meta"]["filing_url"] = "https://evil.example/inject"

    second = get_company_card("v")
    assert second["source_meta"]["field_sources"] == baseline
    assert "__injected__" not in second["source_meta"]["field_sources"]
    assert second["source_meta"]["filing_url"].startswith("https://www.sec.gov/")


def test_list_cards_do_not_share_nested_source_meta_references():
    a = {card["id"]: card for card in list_company_cards()}
    b = {card["id"]: card for card in list_company_cards()}
    # Distinct getter calls must not alias the nested field_sources mapping.
    assert a["v"]["source_meta"]["field_sources"] is not b["v"]["source_meta"]["field_sources"]
    a["v"]["source_meta"]["field_sources"]["revenue"] = "TAMPERED"
    assert b["v"]["source_meta"]["field_sources"].get("revenue") != "TAMPERED"


def test_top_level_and_tag_mutations_also_stay_isolated():
    first = get_company_card("aapl")
    first["source_meta"]["notes"] = "TAMPERED"
    first["tags"]["strategic_tags"].append("__injected__")
    first["tags"]["sensitive_sectors"].append("__injected__")
    second = get_company_card("aapl")
    assert second["source_meta"]["notes"] != "TAMPERED"
    assert "__injected__" not in second["tags"]["strategic_tags"]
    assert "__injected__" not in second["tags"]["sensitive_sectors"]


# ── Preserved boundaries · deck / samples source trail intact ────────────────

def test_samples_endpoint_still_exposes_source_meta_trail():
    client = app.test_client()
    cards = client.get("/api/modeling/ma/samples").get_json()["companies"]
    by_id = {c["id"]: c for c in cards}
    assert "source_meta" in by_id["v"]
    assert "field_sources" in by_id["v"]["source_meta"]
    assert by_id["v"]["source_meta"]["filing_url"].startswith("https://www.sec.gov/")


def test_real_seed_deck_source_meta_not_deleted():
    for card in list_company_cards():
        assert "source_meta" in card
        assert card["source_meta"]["source"]
        assert card["source_meta"]["confidence"] in {"high", "medium", "low"}


# ── Preserved boundaries · precompute count, light pairs, EPS consistency ────

def test_precompute_pair_count_matches_expanded_deck():
    pairs = list_arena_pairs()
    assert len(pairs) == EXPECTED_PAIRS


def test_arena_pairs_payload_stays_light_no_source_meta():
    client = app.test_client()
    data = client.get("/api/modeling/ma/arena/pairs")
    assert data.get_json()["pair_count"] == EXPECTED_PAIRS
    raw = data.get_data(as_text=True)
    assert "source_meta" not in raw
    assert "field_sources" not in raw


def test_eps_consistency_calculate_unchanged_after_strip():
    """Stripping source_meta from the echo must not touch the economics: the
    precomputed board number still equals the live calculate accretion."""
    client = app.test_client()
    fwd = client.post(
        "/api/modeling/ma/calculate", json=build_pair_payload("aapl", "msft")
    ).get_json()["result"]
    pair = next(
        p for p in list_arena_pairs()
        if p["acquirer_id"] == "aapl" and p["target_id"] == "msft"
    )
    assert pair["accretion_dilution_pct"] == fwd["accretion_dilution"]


def test_card_tier_not_in_calculate():
    body = _calc_response()
    assert "arena_tier" not in str(body)
