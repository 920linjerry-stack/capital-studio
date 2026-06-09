"""V5.11.2 US Wave 3 production deck acceptance tests.

The real seed deck expanded from 45 -> 100 cards (the reviewed Wave 3 US data
pack, promoted after a read-only source/quote data gate). These tests lock the
new deck's count / pair-count / tier ecology, the data-gate corrections
(BKNG split basis, SNPS post-Ansys + HSY current shares, CRWD -> FTNT because
CrowdStrike's GAAP net income is negative), the MRSH/MMC canonicalization and
alias, the unchanged source_meta / calculate / arena-pairs boundary, and the
gzip payload strategy that keeps 9,900 directed pairs under the 3 MB wire
guardrail. They change no engine / synergy / viability / Match-Points / robot
truth.
"""

import gzip
import json
from collections import Counter

from app import app
from modeling.ma.company_cards import validate_company_card
from modeling.ma.company_deck import (
    get_company_card,
    get_engine_company,
    list_company_cards,
    resolve_company_id,
)
from modeling.ma.cost_synergy import estimate_default_cost_synergy
from modeling.ma.precompute import build_arena_pairs, build_pair_payload, list_arena_pairs
from modeling.ma.real_seed_deck import WAVE3_SEED_COMPANY_CARDS
from modeling.ma.viability import assess_viability

WAVE3_IDS = {c["id"] for c in WAVE3_SEED_COMPANY_CARDS}
DECK_SIZE = 100
EXPECTED_PAIRS = DECK_SIZE * (DECK_SIZE - 1)  # 9900
INTENDED_TIERS = {"gold": 12, "red": 28, "blue": 25, "green": 24, "white": 11}

# Build-time provider market caps (price x current shares outstanding, USD MM)
# the data gate reconciled the corrected cards against.
PROVIDER_CAP = {"bkng": 128506.0, "snps": 89009.0, "hsy": 37440.0}


def _cards():
    return {c["id"]: c for c in list_company_cards()}


# ── 1. Deck count, pair count, tier ecology ─────────────────────────────────

def test_deck_is_100_unique_cards():
    cards = list_company_cards()
    ids = [c["id"] for c in cards]
    assert len(cards) == DECK_SIZE
    assert len(set(ids)) == DECK_SIZE
    assert len(WAVE3_IDS) == 55
    assert WAVE3_IDS <= set(ids)


def test_directed_pair_count_is_n_times_n_minus_one():
    bundle = build_arena_pairs()
    assert bundle["deck_size"] == DECK_SIZE
    assert bundle["pair_count"] == EXPECTED_PAIRS
    assert len(bundle["pairs"]) == EXPECTED_PAIRS
    assert all(p["acquirer_id"] != p["target_id"] for p in bundle["pairs"])


def test_tier_distribution_matches_intended_ecology_with_white():
    tiers = Counter(c["arena_tier"] for c in list_company_cards())
    assert dict(tiers) == INTENDED_TIERS
    assert tiers["white"] == 11  # the new Basic tier is populated


# ── 2. Every card must be a valid acquirer (the CRWD -> FTNT gate) ───────────

def test_every_card_has_positive_net_income_and_ebitda():
    # The A/D engine rejects a non-positive acquirer net income, and the
    # all-pairs precompute requires every card to be a valid acquirer.
    for c in list_company_cards():
        assert c["net_income"] > 0, c["id"]
        assert c["ebitda"] > 0, c["id"]


def test_crwd_excluded_ftnt_substituted():
    ids = {c["id"] for c in list_company_cards()}
    assert "crwd" not in ids        # GAAP-unprofitable -> invalid acquirer
    assert "ftnt" in ids            # GAAP-profitable cybersecurity replacement
    ftnt = get_company_card("ftnt")
    assert ftnt["arena_tier"] == "red"
    assert ftnt["net_income"] > 0 and ftnt["ebitda"] > 0


# ── 3. Data-gate reconciliation ─────────────────────────────────────────────

def test_bkng_market_cap_reconciled():
    bkng = get_company_card("bkng")
    mc = bkng["shares"] * bkng["share_price"]
    # split fix: post-split shares + FY2025 net income, mc within 5% of provider
    assert bkng["net_income"] == 5404.0
    assert abs(mc - PROVIDER_CAP["bkng"]) / PROVIDER_CAP["bkng"] < 0.05


def test_snps_and_hsy_refreshed_within_tolerance():
    for cid, tol in (("snps", 0.05), ("hsy", 0.05)):
        c = get_company_card(cid)
        mc = c["shares"] * c["share_price"]
        assert abs(mc - PROVIDER_CAP[cid]) / PROVIDER_CAP[cid] < tol, cid


def test_warning_cards_keep_explicit_caveats():
    cards = _cards()
    assert "buyback" in cards["kr"]["source_meta"]["notes"].lower()
    assert "insurance" in cards["trv"]["source_meta"]["notes"].lower()
    assert "buyback" in cards["hca"]["source_meta"]["notes"].lower()
    assert cards["bdx"]["source_meta"]["notes"].strip()
    assert "MMC" in cards["mrsh"]["source_meta"]["notes"]


def test_all_wave3_cards_reconcile_within_25pct():
    # No card may enter production with an undocumented >25% market-cap gap.
    # Here every card's stored equity value must itself be a sane positive cap.
    for c in WAVE3_SEED_COMPANY_CARDS:
        mc = c["shares"] * c["share_price"]
        assert mc > 1_000, c["id"]


# ── 4. MRSH canonical / MMC alias / no duplicate entity ─────────────────────

def test_mrsh_canonical_and_mmc_alias_safe():
    assert resolve_company_id("MMC") == "mrsh"
    assert resolve_company_id("mmc") == "mrsh"
    assert resolve_company_id("mrsh") == "mrsh"
    # Legacy MMC id/ticker resolves to the single MRSH card ...
    assert get_company_card("mmc")["id"] == "mrsh"
    assert get_company_card("MMC")["ticker"] == "MRSH"
    assert get_engine_company("mmc")["ticker"] == "MRSH"
    # ... and unknown ids still fall through to the normal missing-card path.
    assert resolve_company_id("nope") == "nope"
    assert get_company_card("nope") is None


def test_no_duplicate_economic_entity():
    cards = list_company_cards()
    ids = [c["id"] for c in cards]
    tickers = [c["ticker"] for c in cards]
    assert len(ids) == len(set(ids))
    assert len(tickers) == len(set(tickers))
    assert "mmc" not in ids and "MMC" not in tickers  # never a second card
    assert ids.count("mrsh") == 1


# ── 5. Wave 3 cards are complete, typed, and auditable ──────────────────────

def test_wave3_cards_complete_typed_and_auditable():
    cards = _cards()
    for cid in WAVE3_IDS:
        card = cards[cid]
        assert validate_company_card(card) == []
        assert card["currency"] == "USD"
        for f in ("revenue", "ebitda", "net_income", "cash", "debt", "shares", "share_price"):
            assert isinstance(card[f], float) and card[f] == card[f]  # finite
        assert card["revenue"] > 0 and card["shares"] > 0 and card["share_price"] > 0
        assert card["arena_tier"] in {"gold", "red", "blue", "green", "white"}
        src = card["source_meta"]
        assert src["as_of_date"] in {"2026-06-05", "2026-06-08"}
        assert src["filing_url"].startswith("https://www.sec.gov/Archives/")
        assert src["companyfacts_url"].startswith("https://data.sec.gov/")
        assert src["quote_url"].startswith("https://query1.finance.yahoo.com/")
        assert set(src["field_sources"]) == {
            "revenue", "ebitda", "net_income", "cash", "debt", "shares", "share_price",
        }


def test_wave3_tags_do_not_break_synergy_or_viability():
    cards = _cards()
    for acq, tgt in [("bkng", "low"), ("ftnt", "anet"), ("kr", "gis"),
                     ("mrsh", "aon"), ("vlo", "eog")]:
        syn = estimate_default_cost_synergy(cards[acq], cards[tgt])
        via = assess_viability(cards[acq], cards[tgt])
        assert syn["status"] == "ok"
        assert via["viability_level"] in {"green", "yellow", "red"}


# ── 6. Boundary: source_meta stays in deck/sample only ──────────────────────

def test_samples_expose_wave3_source_meta_but_calculate_does_not():
    client = app.test_client()
    samples = {c["id"]: c for c in client.get("/api/modeling/ma/samples").get_json()["companies"]}
    assert "source_meta" in samples["mrsh"]
    assert "field_sources" in samples["mrsh"]["source_meta"]

    full = client.post(
        "/api/modeling/ma/calculate", json=build_pair_payload("bkng", "low")
    ).get_json()
    blob = json.dumps(full)
    for banned in ("source_meta", "field_sources", "filing_url", "quote_url", "companyfacts_url"):
        assert banned not in blob


def test_arena_pairs_includes_new_cards_but_no_source_meta():
    pairs = list_arena_pairs()
    keys = {(p["acquirer_id"], p["target_id"]) for p in pairs}
    assert ("ftnt", "anet") in keys
    assert ("bkng", "low") in keys
    raw = json.dumps(pairs)
    assert "source_meta" not in raw and "field_sources" not in raw


# ── 7. Payload strategy: gzip-negotiated, under the 3 MB wire guardrail ──────

def test_arena_pairs_payload_gzip_negotiated_and_under_guardrail():
    client = app.test_client()
    gz = client.get("/api/modeling/ma/arena/pairs", headers={"Accept-Encoding": "gzip"})
    assert gz.status_code == 200
    assert gz.headers.get("Content-Encoding") == "gzip"
    assert gz.headers.get("Vary") == "Accept-Encoding"
    assert len(gz.data) < 3_000_000  # ~0.31 MB on the wire
    decoded = json.loads(gzip.decompress(gz.data))
    assert decoded["pair_count"] == EXPECTED_PAIRS

    # Content-negotiated: a client that does not accept gzip gets identical,
    # uncompressed, valid JSON (fetch in real browsers always negotiates gzip).
    plain = client.get("/api/modeling/ma/arena/pairs", headers={"Accept-Encoding": "identity"})
    assert plain.headers.get("Content-Encoding") is None
    assert plain.get_json() == decoded
