"""V5.7 deterministic Arena card-tier visual system tests."""

from copy import deepcopy
from pathlib import Path

from app import app
from modeling.ma.company_cards import ARENA_TIER_FIELDS, ARENA_TIER_VALUES, card_to_engine_company
from modeling.ma.company_deck import get_company_card, list_company_cards
from modeling.ma.cost_synergy import estimate_default_cost_synergy
from modeling.ma.precompute import build_pair_payload
from modeling.ma.viability import assess_viability


_ROOT = Path(__file__).resolve().parents[1]
_WARROOM_HTML = _ROOT / "static" / "modeling" / "arena.html"
_WARROOM_JS = _ROOT / "static" / "modeling" / "js" / "arena.js"
_PLAY_HTML = _ROOT / "static" / "modeling" / "arena_play.html"
_PLAY_JS = _ROOT / "static" / "modeling" / "js" / "arena_play.js"

EXPECTED_TIERS = {
    "aapl": "gold",
    "msft": "gold",
    "nvda": "gold",
    "googl": "gold",
    "amzn": "gold",
    "meta": "gold",
    "avgo": "red",
    "orcl": "red",
    "cost": "red",
    "xom": "red",
    "crm": "blue",
    "hd": "blue",
    "cat": "blue",
    "dis": "blue",
    "v": "gold",
    "ma": "gold",
    "adbe": "red",
    "now": "red",
    "panw": "red",
    "amd": "red",
    "qcom": "blue",
    "amat": "green",
    "tmo": "red",
    "abt": "blue",
    "lly": "red",
    "ko": "red",
    "pg": "red",
    "mcd": "red",
    "rtx": "red",
    "nflx": "gold",
    "wmt": "gold",
    "pep": "red",
    "jnj": "gold",
    "pfe": "red",
    "sbux": "red",
    "nke": "gold",
    "isrg": "red",
    "dhr": "red",
    "amgn": "red",
    "intu": "red",
    "txn": "blue",
    "lrcx": "green",
    "mu": "red",
    "ups": "red",
    "lmt": "red",
    # V5.11.2 US Wave 3 (55 cards). CRWD was replaced by FTNT at the data gate
    # (CrowdStrike GAAP net income / EBITDA are negative -> invalid acquirer).
    "uber": "red", "vrt": "red", "ftnt": "red", "anet": "red",
    "bkng": "blue", "low": "blue", "tjx": "blue", "cmg": "blue", "cl": "blue",
    "spgi": "blue", "ice": "blue", "cme": "blue", "adp": "blue", "tt": "blue",
    "fdx": "blue", "csco": "blue", "klac": "blue", "cdns": "blue", "snps": "blue",
    "hca": "blue", "syk": "blue", "mdt": "blue",
    "yum": "green", "rost": "green", "tgt": "green", "kr": "green", "gis": "green",
    "kmb": "green", "hsy": "green", "mrsh": "green", "aon": "green", "ajg": "green",
    "fis": "green", "payx": "green", "gww": "green", "fast": "green", "uri": "green",
    "carr": "green", "ph": "green", "odfl": "green", "lh": "green", "bdx": "green",
    "vlo": "green", "eog": "green",
    "mkc": "white", "clx": "white", "hrl": "white", "chd": "white", "trv": "white",
    "jbht": "white", "dgx": "white", "dri": "white", "cpb": "white", "akam": "white",
    "cah": "white",
}


def _read(path):
    return path.read_text(encoding="utf-8")


def _without_tier(card):
    stripped = deepcopy(card)
    for field in ARENA_TIER_FIELDS:
        stripped.pop(field, None)
    stripped.pop("schema_version", None)
    return stripped


def test_real_seed_deck_has_complete_legal_deterministic_tiers():
    cards = {card["id"]: card for card in list_company_cards()}
    assert {company_id: card["arena_tier"] for company_id, card in cards.items()} == EXPECTED_TIERS
    assert ARENA_TIER_VALUES == {"gold", "red", "blue", "green", "white"}
    for card in cards.values():
        assert set(ARENA_TIER_FIELDS) <= set(card)
        assert card["arena_tier"] in ARENA_TIER_VALUES
        assert card["arena_tier_label"] in {"Legendary", "Elite", "Core", "Specialist", "Basic"}
        assert card["arena_tier_name_cn"]
        assert card["arena_tier_reason"]


def test_tier_fields_do_not_enter_strict_engine_projection():
    for card in list_company_cards():
        projected = card_to_engine_company(card)
        assert not (set(ARENA_TIER_FIELDS) & set(projected))
        assert projected == card_to_engine_company(_without_tier(card))


def test_tier_metadata_does_not_change_synergy_or_viability():
    acquirer = get_company_card("nvda")
    target = get_company_card("avgo")
    stripped_acquirer = _without_tier(acquirer)
    stripped_target = _without_tier(target)
    assert estimate_default_cost_synergy(acquirer, target) == estimate_default_cost_synergy(
        stripped_acquirer, stripped_target
    )
    assert assess_viability(acquirer, target) == assess_viability(stripped_acquirer, stripped_target)


def test_samples_adds_tier_but_calculate_and_pairs_stay_light():
    client = app.test_client()
    samples = client.get("/api/modeling/ma/samples").get_json()["companies"]
    assert len(samples) == 100
    assert all(card["arena_tier"] in ARENA_TIER_VALUES for card in samples)

    calculated = client.post(
        "/api/modeling/ma/calculate", json=build_pair_payload("aapl", "msft")
    ).get_json()
    assert calculated["status"] == "ok"
    assert "arena_tier" not in str(calculated)

    pairs = client.get("/api/modeling/ma/arena/pairs").get_json()
    assert pairs["pair_count"] == 9900
    assert "arena_tier" not in str(pairs)


def test_warroom_renders_tier_cards_slots_rows_and_legend():
    html = _read(_WARROOM_HTML)
    js = _read(_WARROOM_JS)
    assert 'id="tier-legend"' in html
    assert "不是投资评级，也不进入 EPS 或 Viability 计算" in html
    assert "function arenaTierBadge(" in js
    assert 'arenaTierBadge(c, "co-tier")' in js
    assert 'arenaTierBadge(c, "slot-tier")' in js
    assert "tier-pip arena-tier tier-" in js
    assert "tier-text" in js


def test_play_renders_tier_hand_slots_pile_hud_board_and_legend():
    html = _read(_PLAY_HTML)
    js = _read(_PLAY_JS)
    assert "play-tier-legend" in html
    assert "不是投资评级，也不进入 EPS 或 Viability" in html
    assert 'arenaTierBadge(c, "pcard-tier")' in js
    assert 'arenaTierBadge(c, "slot-tier")' in js
    assert "function refreshPileTier(" in js
    assert "tier-pip arena-tier tier-" in js
    assert "tier-text" in js


def test_tier_copy_is_not_an_investment_recommendation_or_score():
    visible_sources = "\n".join((_read(_WARROOM_HTML), _read(_PLAY_HTML)))
    lowered = visible_sources.lower()
    for banned in ("quality score", "stock recommendation", "buy rating", "sell rating"):
        assert banned not in lowered
