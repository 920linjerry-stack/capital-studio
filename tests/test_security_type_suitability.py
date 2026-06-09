from app import app, detect_security_type


def _payload(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "company": symbol,
        "price": 100.0,
        "revenue": 1000.0,
        "ebit": 250.0,
        "da": 40.0,
        "capex": 50.0,
        "wc_change": 0.0,
        "tax_rate": 0.21,
        "net_debt": 0.0,
        "shares": 100.0,
        "revenue_growth": 0.03,
        "ebit_margin": 0.25,
        "da_pct_revenue": 0.04,
        "capex_pct_revenue": 0.05,
        "wc_change_pct_revenue": 0.0,
        "wacc": 0.10,
        "beta": 1.0,
        "terminal_g": 0.02,
        "exit_multiple": 12.0,
        "forecast_years": 5,
        "tv_method": "average",
        "currency": "USD",
    }


def _post(symbol: str) -> dict:
    with app.test_client() as client:
        resp = client.post("/api/modeling/dcf", json=_payload(symbol))
        assert resp.status_code == 200
        return resp.get_json()


def test_index_pattern_blocks_dcf():
    detected = detect_security_type("^GSPC", {}, "US")
    assert detected["security_type"] == "index"
    assert detected["dcf_suitability"] == "unsuitable"

    result = _post("^GSPC")
    assert result["valuation_status"] == "model_unsuitable"
    assert result["intrinsic_per_share"] is None
    assert result["upside_pct"] is None


def test_common_us_etfs_block_dcf():
    for symbol in ["SPY", "QQQ"]:
        detected = detect_security_type(symbol, {}, "US")
        assert detected["security_type"] == "etf"
        assert detected["dcf_suitability"] == "unsuitable"
        result = _post(symbol)
        assert result["model_unsuitable"] is True
        assert result["intrinsic_per_share"] is None
        assert "NAV" in result["recommended_methods"]
        assert "holdings look-through" in result["recommended_methods"]


def test_hk_and_cn_known_etfs_block_dcf():
    for symbol in ["2800.HK", "510300.SS"]:
        detected = detect_security_type(symbol, {}, "HK" if symbol.endswith(".HK") else "CN")
        assert detected["security_type"] == "etf"
        assert detected["dcf_suitability"] == "unsuitable"
        result = _post(symbol)
        assert result["valuation_status"] == "model_unsuitable"
        assert result["market_comparison_status"] == "unavailable"


def test_cn_uncertain_fund_ranges_are_review_not_hard_blocked():
    detected = detect_security_type("510999.SS", {}, "CN")
    assert detected["security_type"] == "fund"
    assert detected["dcf_suitability"] == "review"


def test_operating_companies_not_blocked_by_security_type_gate():
    for symbol in ["AAPL", "2359.HK"]:
        detected = detect_security_type(symbol, {}, "US" if symbol == "AAPL" else "HK")
        assert detected["security_type"] == "operating_company"
        assert detected["dcf_suitability"] == "suitable"
        result = _post(symbol)
        assert result["valuation_status"] != "model_unsuitable"
        assert result["model_unsuitable"] is False
        assert result["intrinsic_per_share"] is not None


def test_reit_sample_is_not_clean_operating_company_dcf():
    detected = detect_security_type("O", {"name": "Realty Income Corporation"}, "US")
    assert detected["security_type"] == "reit"
    assert detected["dcf_suitability"] == "unsuitable"

    result = _post("O")
    assert result["valuation_status"] == "model_unsuitable"
    assert result["intrinsic_per_share"] is None
    assert "AFFO" in result["recommended_methods"]
