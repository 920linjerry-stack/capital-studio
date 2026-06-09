from types import SimpleNamespace

from app import (
    _finalize_dcf_market_status,
    _resolve_currency_translation,
    _translate_dcf_currency_outputs,
)


def _out(iv):
    return SimpleNamespace(
        intrinsic_per_share=iv,
        equity_value=(iv * 1000) if iv is not None else None,
        ev=(iv * 1200) if iv is not None else None,
    )


def _finalize(symbol, reporting, trading, iv, price):
    tx = _resolve_currency_translation(
        symbol,
        reporting_currency=reporting,
        trading_currency=trading,
        reporting_currency_source="test",
        trading_currency_source="test",
    )
    outputs = _translate_dcf_currency_outputs(_out(iv), tx)
    return _finalize_dcf_market_status(price, tx, outputs, [])


def test_1299_like_missing_quote_and_iv_is_not_clean():
    result = _finalize("1299.HK", "USD", "HKD", None, None)

    assert result["currency_translation"]["currency_translation_status"] != "Clean"
    assert result["currency_translation"]["market_comparison_allowed"] is False
    assert result["valuation_status"] == "unavailable"
    assert result["market_comparison_status"] == "unavailable"
    assert result["comparison_iv"] is None
    assert result["upside_pct"] is None
    assert "Current price unavailable; upside/downside comparison blocked." in result["warnings"]
    assert "Intrinsic value unavailable; valuation output not clean." in result["warnings"]


def test_same_currency_valid_iv_missing_price_blocks_market_comparison_without_high_review():
    result = _finalize("AAPL", "USD", "USD", 100.0, None)

    assert result["currency_translation"]["currency_translation_status"] == "Review"
    assert result["valuation_status"] == "available"
    assert result["market_comparison_status"] == "unavailable"
    assert result["comparison_iv"] == 100.0
    assert result["upside_pct"] is None


def test_reporting_trading_mismatch_missing_fx_is_high_review_and_no_trading_iv():
    result = _finalize("TEST.HK", "CNY", "USD", 100.0, 50.0)

    assert result["currency_translation"]["currency_translation_status"] == "High Review"
    assert result["currency_translation"]["market_comparison_allowed"] is False
    assert result["currency_outputs"]["intrinsic_value_per_share_trading_currency"] is None
    assert result["comparison_iv"] is None
    assert result["upside_pct"] is None
    assert "FX translation unavailable; market comparison blocked." in result["warnings"]


def test_missing_iv_with_valid_price_marks_valuation_unavailable():
    result = _finalize("AAPL", "USD", "USD", None, 50.0)

    assert result["currency_translation"]["currency_translation_status"] == "Review"
    assert result["valuation_status"] == "unavailable"
    assert result["market_comparison_status"] == "unavailable"
    assert result["comparison_iv"] is None
    assert result["upside_pct"] is None
    assert "Intrinsic value unavailable; valuation output not clean." in result["warnings"]


def test_valid_same_currency_iv_and_price_remains_clean():
    result = _finalize("AAPL", "USD", "USD", 100.0, 50.0)

    assert result["currency_translation"]["currency_translation_status"] == "Clean"
    assert result["currency_translation"]["market_comparison_allowed"] is True
    assert result["valuation_status"] == "available"
    assert result["market_comparison_status"] == "available"
    assert result["comparison_iv"] == 100.0
    assert result["upside_pct"] == 100.0
    assert result["warnings"] == []
