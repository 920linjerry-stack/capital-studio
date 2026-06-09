"""V5.9.1 formal US deck expansion acceptance tests."""

import json
import math

from app import app
from modeling.ma.company_cards import ARENA_TIER_VALUES, validate_company_card
from modeling.ma.company_deck import get_company_card, list_company_cards
from modeling.ma.cost_synergy import estimate_default_cost_synergy
from modeling.ma.precompute import (
    build_arena_pairs,
    build_pair_payload,
    build_settlement_boards,
    get_arena_pair,
    list_arena_pairs,
)
from modeling.ma.real_seed_deck import WAVE2_DEFERRED_CANDIDATES
from modeling.ma.viability import assess_viability


OLD_IDS = {
    "aapl", "msft", "googl", "amzn", "meta", "nvda", "dis", "hd",
    "avgo", "orcl", "crm", "cost", "cat", "xom", "v", "ma", "adbe",
    "now", "panw", "amd", "qcom", "amat", "tmo", "abt", "lly", "ko",
    "pg", "mcd", "rtx", "nflx",
}
NEW_IDS = {
    "wmt", "pep", "jnj", "pfe", "sbux", "nke", "isrg", "dhr",
    "amgn", "intu", "txn", "lrcx", "mu", "ups", "lmt",
}
EXPECTED_PAIRS = 100 * 99


def test_wave2_deck_count_old_cards_and_new_cards():
    cards = list_company_cards()
    ids = {card["id"] for card in cards}
    assert len(cards) == 100
    assert OLD_IDS <= ids
    assert NEW_IDS <= ids
    # V5.11.2: the deck expanded to 100; the Wave 2 milestone set (45) is now a
    # subset rather than the whole deck.
    assert (OLD_IDS | NEW_IDS) <= ids


def test_wave2_cards_are_complete_typed_and_auditable():
    cards = {card["id"]: card for card in list_company_cards()}
    for company_id in NEW_IDS:
        card = cards[company_id]
        assert validate_company_card(card) == []
        assert card["market"] in {"NYSE", "NASDAQ"}
        assert card["currency"] == "USD"
        for field in ("revenue", "ebitda", "net_income", "cash", "debt", "shares", "share_price"):
            assert isinstance(card[field], float)
            assert math.isfinite(card[field])
        assert card["revenue"] > 0
        assert card["ebitda"] > 0
        assert card["net_income"] > 0
        assert card["cash"] >= 0
        assert card["debt"] >= 0
        assert card["shares"] > 0
        assert card["share_price"] > 0
        assert card["shares"] * card["share_price"] > 1_000
        assert card["tags"]["industry_group"]
        assert card["tags"]["strategic_tags"]
        assert card["tags"]["jurisdiction"] == "US"
        assert card["arena_tier"] in ARENA_TIER_VALUES
        assert card["arena_tier_reason"]
        source = card["source_meta"]
        assert source["as_of_date"] == "2026-06-04"
        assert source["filing_url"].startswith("https://www.sec.gov/Archives/")
        assert source["companyfacts_url"].startswith("https://data.sec.gov/")
        assert source["quote_url"].startswith("https://query1.finance.yahoo.com/")
        assert set(source["field_sources"]) == {
            "revenue", "ebitda", "net_income", "cash", "debt", "shares", "share_price",
        }


def test_wave2_dirty_or_complex_candidates_remain_deferred():
    tickers = {card["ticker"] for card in list_company_cards()}
    assert not (tickers & set(WAVE2_DEFERRED_CANDIDATES))
    assert {"SNOW", "PLTR", "DDOG", "JPM", "BAC", "BLK", "AXP", "BA"} <= set(
        WAVE2_DEFERRED_CANDIDATES
    )


def test_wave2_source_meta_is_defensively_copied():
    first = get_company_card("wmt")
    baseline = dict(first["source_meta"]["field_sources"])
    first["source_meta"]["field_sources"]["revenue"] = "TAMPERED"
    first["source_meta"]["notes"] = "TAMPERED"
    second = get_company_card("wmt")
    assert second["source_meta"]["field_sources"] == baseline
    assert second["source_meta"]["notes"] != "TAMPERED"


def test_new_tags_do_not_break_default_synergy_or_viability():
    cards = {card["id"]: card for card in list_company_cards()}
    for acquirer_id, target_id in [
        ("wmt", "pep"),
        ("jnj", "isrg"),
        ("intu", "txn"),
        ("lrcx", "mu"),
        ("ups", "lmt"),
    ]:
        synergy = estimate_default_cost_synergy(cards[acquirer_id], cards[target_id])
        viability = assess_viability(cards[acquirer_id], cards[target_id])
        assert synergy["status"] == "ok"
        assert synergy["result"]["synergy_tier"] in {"high", "medium", "low", "none"}
        assert viability["viability_level"] in {"green", "yellow", "red"}


def test_expanded_precompute_count_directionality_and_determinism():
    first = build_arena_pairs()
    second = build_arena_pairs()
    assert first["deck_size"] == 100
    assert first["pair_count"] == EXPECTED_PAIRS
    assert len(first["pairs"]) == EXPECTED_PAIRS
    assert first["pairs"] == second["pairs"]
    assert all(pair["acquirer_id"] != pair["target_id"] for pair in first["pairs"])
    forward = get_arena_pair("wmt", "pep")
    reverse = get_arena_pair("pep", "wmt")
    assert forward["acquirer_id"] == "wmt"
    assert reverse["acquirer_id"] == "pep"
    assert forward["accretion_dilution_pct"] != reverse["accretion_dilution_pct"]


def test_expanded_pairs_payload_is_compact_and_source_isolated():
    import gzip
    response = app.test_client().get(
        "/api/modeling/ma/arena/pairs", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert response.headers.get("Content-Encoding") == "gzip"
    raw = gzip.decompress(response.data).decode("utf-8")
    body = json.loads(raw)
    assert body["pair_count"] == EXPECTED_PAIRS
    # gzip wire size guardrail (9900 pairs compress to ~0.31 MB).
    assert len(response.data) < 3_000_000
    for banned in ("source_meta", "field_sources", "filing_url", "quote_url", "companyfacts_url"):
        assert banned not in raw


def test_new_company_light_ticket_and_calculate_eps_are_consistent():
    client = app.test_client()
    for acquirer_id, target_id in [
        ("wmt", "pep"),
        ("isrg", "dhr"),
        ("txn", "lrcx"),
        ("ups", "lmt"),
        ("intu", "nke"),
    ]:
        light = get_arena_pair(acquirer_id, target_id)
        full = client.post(
            "/api/modeling/ma/calculate",
            json=build_pair_payload(acquirer_id, target_id),
        ).get_json()["result"]
        assert light["accretion_dilution_pct"] == full["accretion_dilution"]
        assert "source_meta" not in json.dumps(full)


def test_ups_debt_is_not_double_counted_with_current_maturities():
    # V5.9.1.1: LongTermDebt (23,585) already includes current maturities, so the
    # old 24,193 value (23,585 + 608 DebtCurrent) double-counted them and pulled
    # in finance-lease amounts the lease-exclusion convention is supposed to drop.
    ups = get_company_card("ups")
    long_term_debt = 23585.0
    debt_current = 608.0
    assert ups["debt"] != long_term_debt + debt_current  # no double-count
    assert ups["debt"] == long_term_debt  # disclosed non-lease total long-term debt


def test_ups_debt_caveat_and_field_sources_are_internally_consistent():
    ups = get_company_card("ups")
    source = ups["source_meta"]
    notes = source["notes"]
    debt_source = source["field_sources"]["debt"]
    # Caveat must not still claim the old "plus current debt" summation.
    assert "plus current debt" not in notes
    # Caveat and field_sources must both rest on LongTermDebt and the lease exclusion.
    assert "LongTermDebt" in debt_source
    assert "lease" in notes.lower()
    assert "lease" in debt_source.lower()
    # DebtCurrent may only survive as a caveat-only reference, not as a summed source.
    assert "plus us-gaap:DebtCurrent" not in debt_source
    assert "LongTermDebt plus" not in debt_source


def test_settlement_boards_remain_deterministic_on_expanded_deck():
    first = build_settlement_boards()
    second = build_settlement_boards()
    assert first == second
    assert first["pair_count"] == EXPECTED_PAIRS


def test_robot_all_difficulties_have_valid_candidate_universes():
    pairs = list_arena_pairs()
    valid_keys = {
        (pair["acquirer_id"], pair["target_id"])
        for pair in pairs
    }
    assert len(valid_keys) == EXPECTED_PAIRS
    assert all(acquirer_id != target_id for acquirer_id, target_id in valid_keys)
    for difficulty in ("intern", "analyst", "associate"):
        eligible = pairs
        assert eligible, difficulty
    for difficulty in ("vp", "md"):
        eligible = [pair for pair in pairs if pair["viability_level"] != "red"]
        assert eligible, difficulty
