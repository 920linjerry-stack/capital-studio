"""V5.1 company card schema and seed deck tests."""

from modeling.ma.company_cards import (
    ARENA_TIER_VALUES,
    COMPANY_CARD_SCHEMA_VERSION,
    card_to_engine_company,
    validate_company_card,
)
from modeling.ma.company_deck import (
    get_company_card,
    get_engine_company,
    list_company_cards,
    list_fictional_company_cards,
)
from modeling.ma.real_seed_deck import WAVE2_DEFERRED_CANDIDATES, WAVE3_SEED_COMPANY_CARDS


OLD_REAL_SEED_IDS = {
    "aapl",
    "msft",
    "googl",
    "amzn",
    "meta",
    "nvda",
    "dis",
    "hd",
    "avgo",
    "orcl",
    "crm",
    "cost",
    "cat",
    "xom",
    "v",
    "ma",
    "adbe",
    "now",
    "panw",
    "amd",
    "qcom",
    "amat",
    "tmo",
    "abt",
    "lly",
    "ko",
    "pg",
    "mcd",
    "rtx",
    "nflx",
}
NEW_V591_IDS = {
    "wmt", "pep", "jnj", "pfe", "sbux", "nke", "isrg", "dhr",
    "amgn", "intu", "txn", "lrcx", "mu", "ups", "lmt",
}
# V5.11.2 US Wave 3: 55 cards (CRWD replaced by FTNT at the data gate).
NEW_V5112_IDS = {c["id"] for c in WAVE3_SEED_COMPANY_CARDS}
REAL_SEED_IDS = OLD_REAL_SEED_IDS | NEW_V591_IDS | NEW_V5112_IDS
NEW_V513_IDS = {"avgo", "orcl", "crm", "cost", "cat", "xom"}
NEW_V571_IDS = {
    "v", "ma", "adbe", "now", "panw", "amd", "qcom", "amat",
    "tmo", "abt", "lly", "ko", "pg", "mcd", "rtx", "nflx",
}
# Deferred / complex candidates: not permanently rejected, just held back
# pending a dedicated financial-services or program-accounting card treatment.
DEFERRED_OR_COMPLEX_CANDIDATES = {"JPM", "BAC", "BA"}
DISALLOWED_INDUSTRY_GROUP_TOKENS = ("mega", "global leader", "large cap", "large-cap")


def test_seed_deck_cards_validate_and_have_schema_fields():
    cards = list_company_cards()
    assert len(cards) == 100
    for card in cards:
        assert validate_company_card(card) == []
        assert card["schema_version"] == COMPANY_CARD_SCHEMA_VERSION
        assert card["revenue"] > 0
        assert card["net_income"] > 0
        assert card["shares"] > 0
        assert card["share_price"] > 0
        assert card["arena_tier"] in ARENA_TIER_VALUES
        assert "market_cap" not in card
        assert isinstance(card["tags"]["strategic_tags"], list)
        assert isinstance(card["tags"]["sensitive_sectors"], list)
        assert {
            "source",
            "source_document_or_provider",
            "fiscal_period_or_as_of_date",
            "as_of_date",
            "notes",
            "confidence",
        } <= set(card["source_meta"])


def test_real_seed_deck_contains_only_freeze_shortlist():
    ids = {card["id"] for card in list_company_cards()}
    tickers = {card["ticker"] for card in list_company_cards()}
    assert ids == REAL_SEED_IDS
    assert OLD_REAL_SEED_IDS <= ids
    assert NEW_V591_IDS <= ids
    assert not (tickers & DEFERRED_OR_COMPLEX_CANDIDATES)


def test_v591_candidate_rejection_list_is_recorded_and_excluded():
    tickers = {card["ticker"] for card in list_company_cards()}
    assert {"SNOW", "PLTR", "DDOG", "JPM", "BAC", "BLK", "AXP", "BA"} <= set(
        WAVE2_DEFERRED_CANDIDATES
    )
    assert not (tickers & set(WAVE2_DEFERRED_CANDIDATES))
    assert all(str(reason).startswith("Deferred:") for reason in WAVE2_DEFERRED_CANDIDATES.values())


def test_v513_new_seed_deck_cards_have_required_fields_and_source_notes():
    notes = {
        "avgo": "FY2025 SEC facts tie out clean; EBITDA is operating income plus depreciation and acquired-intangible amortization; debt uses short-term debt plus long-term debt carrying amount, excluding lease obligations.",
        "orcl": "FY2025 core fields tie out; cash excludes marketable securities; debt is notes payable and other borrowings current plus non-current, with finance lease liabilities excluded.",
        "crm": "FY2026 revenue/net income/diluted shares tie out; cash excludes marketable securities; EBITDA is operating income plus D&A, with Informatica acquisition noted for comparability.",
        "cost": "FY2025 SEC facts tie out clean; EBITDA is operating income plus D&A; debt is current plus noncurrent long-term debt and excludes finance lease liabilities.",
        "cat": "FY2025 revenue/net income/shares/cash tie out; EBITDA is operating income plus D&A; debt should be read with note that Caterpillar has machinery and financial-products debt presentation.",
        "xom": "FY2025 revenue/net income/cash/share count tie out; EBITDA is derived from income before tax plus interest expense plus depreciation/depletion, not operating income plus D&A; debt includes current debt plus long-term debt.",
    }
    cards = {card["id"]: card for card in list_company_cards()}
    assert set(cards) >= NEW_V513_IDS
    for company_id in NEW_V513_IDS:
        card = cards[company_id]
        assert validate_company_card(card) == []
        assert card["source_meta"]["source"] == "SEC EDGAR + Stooq"
        assert "SEC companyfacts" in card["source_meta"]["source_document_or_provider"]
        assert "Stooq quote" in card["source_meta"]["source_document_or_provider"]
        assert "price snapshot 2026-06-04" in card["source_meta"]["fiscal_period_or_as_of_date"]
        assert card["source_meta"]["as_of_date"] == "2026-06-04"
        assert card["source_meta"]["notes"] == notes[company_id]
        assert card["source_meta"]["confidence"] in {"high", "medium", "low"}


def test_real_seed_deck_source_meta_is_build_time_snapshot():
    for card in list_company_cards():
        source_meta = card["source_meta"]
        assert source_meta["source"] in {"SEC EDGAR + Stooq", "SEC EDGAR + Yahoo Finance"}
        assert "SEC companyfacts" in source_meta["source_document_or_provider"]
        assert (
            "Stooq quote" in source_meta["source_document_or_provider"]
            or "Yahoo Finance chart" in source_meta["source_document_or_provider"]
        )
        assert "FY ended" in source_meta["fiscal_period_or_as_of_date"]
        # V5.11.2: the deck spans two snapshot dates (Wave 1/2 06-04, Wave 3 06-05,
        # plus the FTNT replacement sourced 06-08).
        assert "price snapshot 2026-06-0" in source_meta["fiscal_period_or_as_of_date"]
        assert source_meta["notes"]
        assert source_meta["confidence"] in {"high", "medium", "low"}


def test_v571_wave1_cards_have_field_level_source_trails():
    cards = {card["id"]: card for card in list_company_cards()}
    assert set(cards) >= NEW_V571_IDS
    for company_id in NEW_V571_IDS:
        card = cards[company_id]
        source_meta = card["source_meta"]
        assert source_meta["source"] == "SEC EDGAR + Yahoo Finance"
        assert source_meta["filing_url"].startswith("https://www.sec.gov/Archives/edgar/data/")
        assert source_meta["companyfacts_url"].startswith("https://data.sec.gov/api/xbrl/companyfacts/")
        assert source_meta["quote_url"].startswith("https://query1.finance.yahoo.com/v8/finance/chart/")
        assert set(source_meta["field_sources"]) == {
            "revenue", "ebitda", "net_income", "cash", "debt", "shares", "share_price",
        }
        assert all(str(value).strip() for value in source_meta["field_sources"].values())


def test_v591_wave2_cards_have_complete_field_level_source_trails():
    cards = {card["id"]: card for card in list_company_cards()}
    for company_id in NEW_V591_IDS:
        card = cards[company_id]
        source_meta = card["source_meta"]
        assert source_meta["source"] == "SEC EDGAR + Yahoo Finance"
        assert source_meta["filing_url"].startswith("https://www.sec.gov/Archives/edgar/data/")
        assert source_meta["companyfacts_url"].startswith("https://data.sec.gov/api/xbrl/companyfacts/")
        assert source_meta["quote_url"].startswith("https://query1.finance.yahoo.com/v8/finance/chart/")
        assert set(source_meta["field_sources"]) == {
            "revenue", "ebitda", "net_income", "cash", "debt", "shares", "share_price",
        }
        assert all(str(value).strip() for value in source_meta["field_sources"].values())
        assert source_meta["confidence"] in {"high", "medium"}
        assert "FY2025" in source_meta["notes"] or "FY2026" in source_meta["notes"]


def test_real_seed_deck_industry_groups_are_specific_not_size_labels():
    expected = {
        "aapl": "consumer_electronics_ecosystem",
        "msft": "enterprise_software_cloud",
        "googl": "search_ads_cloud",
        "amzn": "ecommerce_cloud_logistics",
        "meta": "social_ads_platform",
        "nvda": "semiconductors_ai_accelerators",
        "dis": "media_entertainment_content",
        "hd": "home_improvement_retail",
        "avgo": "semiconductor_networking_infrastructure",
        "orcl": "database_enterprise_cloud_infrastructure",
        "crm": "enterprise_saas_customer_platform",
        "cost": "membership_warehouse_retail",
        "cat": "industrial_machinery_equipment",
        "xom": "integrated_oil_gas_energy",
        "v": "payments_networks",
        "ma": "payments_networks",
        "adbe": "creative_document_software",
        "now": "enterprise_workflow_platform",
        "panw": "cybersecurity_platform",
        "amd": "semiconductor_design_compute",
        "qcom": "semiconductor_wireless_ip",
        "amat": "semiconductor_equipment",
        "tmo": "healthcare_tools_life_sciences",
        "abt": "medical_devices_diagnostics",
        "lly": "innovative_pharma",
        "ko": "consumer_staples_beverages",
        "pg": "consumer_staples_brands",
        "mcd": "quick_service_restaurants",
        "rtx": "aerospace_defense",
        "nflx": "streaming_content_platform",
        "wmt": "big_box_retail",
        "pep": "consumer_staples_beverages_snacks",
        "jnj": "healthcare_pharma_medtech",
        "pfe": "pharma_innovative",
        "sbux": "coffeehouse_retail",
        "nke": "athletic_footwear_apparel",
        "isrg": "medical_devices_robotics",
        "dhr": "healthcare_tools_diagnostics",
        "amgn": "biotech_innovative",
        "intu": "enterprise_tax_finance_software",
        "txn": "semiconductor_analog",
        "lrcx": "semiconductor_equipment",
        "mu": "semiconductor_memory",
        "ups": "logistics_parcel_network",
        "lmt": "aerospace_defense",
    }
    for card in list_company_cards():
        group = card["tags"]["industry_group"]
        # Wave 1/2 cards keep their exact specific industry_group; every card
        # (including the 55 Wave 3 additions) must still be a specific token, not
        # a size / market-position label.
        if card["id"] in expected:
            assert group == expected[card["id"]]
        assert group, card["id"]
        lowered = group.lower()
        assert not any(token in lowered for token in DISALLOWED_INDUSTRY_GROUP_TOKENS)


def test_loader_returns_copies_not_mutable_globals():
    first = get_company_card("atlas_software")
    assert first is not None
    first["name"] = "Mutated"
    second = get_company_card("atlas_software")
    assert second["name"] == "Atlas Software"


def test_engine_projection_preserves_ad_fields_and_revenue_tags():
    company = get_engine_company("beacon_payments")
    assert company is not None
    assert company["net_income"] > 0
    assert company["shares"] > 0
    assert company["share_price"] > 0
    assert company["revenue"] > 0
    assert company["tags"]["industry_group"] == "fintech_payments"


def test_fictional_seed_deck_remains_available_as_dev_fallback():
    fictional = list_fictional_company_cards()
    assert any(card["id"] == "atlas_software" for card in fictional)
    assert get_engine_company("atlas_software")["name"] == "Atlas Software"


def test_invalid_card_missing_revenue_flags():
    card = get_company_card("atlas_software")
    del card["revenue"]
    flags = validate_company_card(card)
    assert any(flag["code"] == "COMPANY_CARD_FIELD_REQUIRED" and "revenue" in flag["message"] for flag in flags)


def test_card_to_engine_company_rejects_invalid_card():
    card = get_company_card("atlas_software")
    card["shares"] = 0
    try:
        card_to_engine_company(card)
    except ValueError as exc:
        assert "Invalid company card" in str(exc)
    else:
        raise AssertionError("Expected invalid company card to raise")
