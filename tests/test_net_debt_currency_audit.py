from modeling.data_quality import build_net_debt_currency_audit


def test_aapl_usd_usd_clean():
    audit = build_net_debt_currency_audit(
        "AAPL",
        {"currency": "USD", "net_debt_currency": "USD"},
        {"reporting_currency": "USD", "trading_currency": "USD", "fx_rate_reporting_to_trading": 1.0},
    )
    assert audit["status"] == "Clean"


def test_2359_cny_hkd_reporting_bridge_clean_or_review():
    audit = build_net_debt_currency_audit(
        "2359.HK",
        {"currency": "CNY", "net_debt_currency": "CNY"},
        {"reporting_currency": "CNY", "trading_currency": "HKD", "fx_rate_reporting_to_trading": 1.08},
    )
    assert audit["status"] in {"Clean", "Review"}
    assert audit["final_iv_conversion"] == "after_equity_value_per_share"


def test_0883_usd_hkd_clean_if_net_debt_usd():
    audit = build_net_debt_currency_audit(
        "0883.HK",
        {"currency": "USD", "net_debt_currency": "USD"},
        {"reporting_currency": "USD", "trading_currency": "HKD", "fx_rate_reporting_to_trading": 7.8},
    )
    assert audit["status"] == "Clean"


def test_unknown_net_debt_currency_mismatch_review():
    audit = build_net_debt_currency_audit(
        "0005.HK",
        {"currency": "USD"},
        {"reporting_currency": "USD", "trading_currency": "HKD", "fx_rate_reporting_to_trading": 7.8},
    )
    assert audit["status"] == "Review"


def test_explicit_mixed_currency_high_review():
    audit = build_net_debt_currency_audit(
        "0883.HK",
        {"currency": "USD", "net_debt_currency": "HKD"},
        {"reporting_currency": "USD", "trading_currency": "HKD", "fx_rate_reporting_to_trading": 7.8},
    )
    assert audit["status"] == "High Review"
