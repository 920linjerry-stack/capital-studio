from types import SimpleNamespace

from app import (
    _currency_translation_from_payload,
    _resolve_currency_translation,
    _translate_dcf_currency_outputs,
)


def _out(iv):
    return SimpleNamespace(
        intrinsic_per_share=iv,
        equity_value=iv * 1000,
        ev=iv * 1200,
    )


def test_aapl_usd_to_usd_clean_no_conversion():
    tx = _resolve_currency_translation(
        "AAPL",
        reporting_currency="USD",
        trading_currency="USD",
        reporting_currency_source="yfinance",
        trading_currency_source="quote",
    )

    assert tx["currency_translation_status"] == "Clean"
    assert tx["fx_rate_reporting_to_trading"] == 1.0
    assert tx["fx_rate_source"] == "same_currency"
    assert _translate_dcf_currency_outputs(_out(202.77), tx)["intrinsic_value_per_share_trading_currency"] == 202.77


def test_maotai_cny_to_cny_clean_no_conversion():
    tx = _resolve_currency_translation(
        "600519.SS",
        reporting_currency="CNY",
        trading_currency="CNY",
        reporting_currency_source="akshare",
        trading_currency_source="quote",
    )

    assert tx["currency_translation_status"] == "Clean"
    assert tx["fx_rate_reporting_to_trading"] == 1.0
    assert _translate_dcf_currency_outputs(_out(100), tx)["intrinsic_value_per_share_trading_currency"] == 100


def test_2359_cny_reporting_to_hkd_trading_static_review():
    tx = _resolve_currency_translation(
        "2359.HK",
        reporting_currency="CNY",
        trading_currency="HKD",
        reporting_currency_source="probe_confirmed",
        trading_currency_source="quote",
    )
    translated = _translate_dcf_currency_outputs(_out(100), tx)

    assert tx["currency_translation_status"] == "Review"
    assert tx["fx_rate_reporting_to_trading"] == 1.08
    assert tx["fx_rate_source"] == "static_fallback_review_required"
    assert translated["intrinsic_value_per_share_reporting_currency"] == 100
    assert translated["intrinsic_value_per_share_trading_currency"] == 108


def test_2359_default_hkd_unverified_is_reclassified_to_cny_review():
    tx = _resolve_currency_translation(
        "2359.HK",
        reporting_currency="HKD",
        trading_currency="HKD",
        reporting_currency_source="default_hkd_unverified",
        trading_currency_source="quote",
    )

    assert tx["reporting_currency"] == "CNY"
    assert tx["trading_currency"] == "HKD"
    assert tx["currency_translation_status"] == "Review"


def test_0005_usd_reporting_to_hkd_trading_static_review():
    tx = _resolve_currency_translation(
        "0005.HK",
        reporting_currency="USD",
        trading_currency="HKD",
        reporting_currency_source="hk_reporting_currency_whitelist",
        trading_currency_source="quote",
    )
    translated = _translate_dcf_currency_outputs(_out(10), tx)

    assert tx["currency_translation_status"] == "Review"
    assert tx["fx_rate_reporting_to_trading"] == 7.80
    assert translated["intrinsic_value_per_share_trading_currency"] == 78


def test_0005_default_hkd_unverified_is_reclassified_to_usd_review():
    tx = _resolve_currency_translation(
        "0005.HK",
        reporting_currency="HKD",
        trading_currency="HKD",
        reporting_currency_source="default_hkd_unverified",
        trading_currency_source="quote",
    )

    assert tx["reporting_currency"] == "USD"
    assert tx["trading_currency"] == "HKD"
    assert tx["fx_rate_reporting_to_trading"] == 7.80
    assert tx["currency_translation_status"] == "Review"


def test_missing_reporting_currency_blocks_market_comparison():
    tx = _resolve_currency_translation(
        "9999.HK",
        reporting_currency=None,
        trading_currency="HKD",
        reporting_currency_source="unknown",
        trading_currency_source="quote",
    )
    translated = _translate_dcf_currency_outputs(_out(100), tx)

    assert tx["currency_translation_status"] == "High Review"
    assert tx["market_comparison_allowed"] is False
    assert translated["intrinsic_value_per_share_trading_currency"] is None


def test_hk_unknown_payload_without_reporting_currency_blocks_market_comparison():
    tx = _currency_translation_from_payload(
        {"symbol": "9999.HK", "currency": "HKD"},
        SimpleNamespace(symbol="9999.HK", market="HK", currency="HKD"),
    )

    assert tx["currency_translation_status"] == "High Review"
    assert tx["market_comparison_allowed"] is False
