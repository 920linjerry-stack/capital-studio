"""V5.0 Deal Studio API contract tests (Segment 2 acceptance)."""

from app import app


def _payload(**deal_overrides):
    deal = {
        "deal_type": "full_acquisition",
        "premium": 0.30,
        "cash_pct": 0.5,
        "stock_pct": 0.5,
        "financing_cost": 0.05,
        "tax_rate": 0.25,
        "synergy": 0.0,
    }
    deal.update(deal_overrides)
    return {
        "acquirer": {"name": "Acq", "net_income": 4000.0, "shares": 1000.0, "share_price": 200.0},
        "target": {"name": "Tgt", "net_income": 1000.0, "shares": 500.0, "share_price": 80.0},
        "deal": deal,
        "currency": "USD",
    }


def test_samples_endpoint():
    client = app.test_client()
    resp = client.get("/api/modeling/ma/samples")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    expected_tickers = {
        "AAPL",
        "MSFT",
        "GOOGL",
        "AMZN",
        "META",
        "NVDA",
        "DIS",
        "HD",
        "AVGO",
        "ORCL",
        "CRM",
        "COST",
        "CAT",
        "XOM",
        "V",
        "MA",
        "ADBE",
        "NOW",
        "PANW",
        "AMD",
        "QCOM",
        "AMAT",
        "TMO",
        "ABT",
        "LLY",
        "KO",
        "PG",
        "MCD",
        "RTX",
        "NFLX",
        "WMT",
        "PEP",
        "JNJ",
        "PFE",
        "SBUX",
        "NKE",
        "ISRG",
        "DHR",
        "AMGN",
        "INTU",
        "TXN",
        "LRCX",
        "MU",
        "UPS",
        "LMT",
    }
    assert len(data["companies"]) == 100
    # V5.11.2: the deck expanded to 100; the original tickers are now a subset.
    assert expected_tickers <= {card["ticker"] for card in data["companies"]}
    assert {"id", "name", "net_income", "shares", "share_price", "revenue", "tags", "source_meta"} <= set(data["companies"][0])
    assert not (
        {card["ticker"] for card in data["companies"]}
        & {"SNOW", "PLTR", "DDOG", "JPM", "BAC", "BLK", "AXP", "BA"}
    )


def test_valid_payload_returns_full_result():
    client = app.test_client()
    resp = client.post("/api/modeling/ma/calculate", json=_payload())
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    r = data["result"]
    for key in [
        "offer_value", "cash_consideration", "stock_consideration", "new_shares_issued",
        "pro_forma_net_income", "pro_forma_shares", "pro_forma_eps",
        "accretion_dilution", "break_even_synergy", "synergy_status", "synergy_status_label",
        "synergy_context",
    ]:
        assert key in r, key


def test_pre_ppa_chip_present_and_no_internal_field_names():
    client = app.test_client()
    resp = client.post("/api/modeling/ma/calculate", json=_payload())
    r = resp.get_json()["result"]
    assert r["pre_ppa_chip"]["label"] == "Pre-PPA"
    assert r["pre_ppa_chip"]["detail"]
    # internal boundary field names must not leak into the API surface
    assert "ppa_amortization_modeled" not in r
    assert "pre_ppa" not in r
    assert "pre_ppa_detail" not in r


def test_response_exposes_only_viability_context_not_legacy_placeholder():
    """V5.3.1: the engine's legacy result['viability'] placeholder must be
    dropped; viability_context is the single outward viability field."""
    client = app.test_client()
    payload = {
        "acquirer": {"sample_id": "googl"},
        "target": {"sample_id": "meta"},
        "deal": {"premium": 0.30, "cash_pct": 0.5, "stock_pct": 0.5,
                 "financing_cost": 0.05, "tax_rate": 0.25, "synergy_mode": "default"},
    }
    r = client.post("/api/modeling/ma/calculate", json=payload).get_json()["result"]
    assert "viability" not in r
    assert "viability_context" in r
    assert r["viability_context"]["viability_level"] in {"green", "yellow", "red"}


def test_unexpected_exception_returns_fixed_error_without_leak(monkeypatch):
    """V5.3.1: an unexpected error returns a fixed structured 500 and never
    leaks the raw exception (paths / stack / token)."""
    import app as app_module

    secret = "INTERNAL_TRACE C:/secret/app.py line 99 token=zzz999"

    def boom(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(app_module, "build_ma_response", boom)
    resp = app_module.app.test_client().post("/api/modeling/ma/calculate", json=_payload())
    assert resp.status_code == 500
    body = resp.get_json()
    assert body["status"] == "error" and body["result"] is None
    assert body["flags"][0]["code"] == "MA_CALCULATION_UNAVAILABLE"
    assert body["flags"][0]["message"] == "M&A calculation is temporarily unavailable."
    raw = resp.get_data(as_text=True)
    for leak in (secret, "INTERNAL_TRACE", "app.py", "token=zzz999", "RuntimeError"):
        assert leak not in raw


def test_validation_errors_stay_4xx_not_500():
    """Normal user-input errors must remain structured 4xx, not be swallowed
    into the generic 500 path."""
    client = app.test_client()
    # missing financing cost on an all-cash deal
    p = _payload(cash_pct=1.0, stock_pct=0.0)
    del p["deal"]["financing_cost"]
    resp = client.post("/api/modeling/ma/calculate", json=p)
    assert resp.status_code == 400
    codes = {f["code"] for f in resp.get_json()["flags"]}
    assert "FINANCING_COST_REQUIRED" in codes
    assert "MA_CALCULATION_UNAVAILABLE" not in codes


def test_sample_id_resolution():
    client = app.test_client()
    payload = {
        "acquirer": {"sample_id": "atlas_software"},
        "target": {"sample_id": "fulton_media"},
        "deal": {"premium": 0.25, "cash_pct": 0.0, "stock_pct": 1.0,
                 "financing_cost": 0.0, "tax_rate": 0.25, "synergy": 0.0},
    }
    resp = client.post("/api/modeling/ma/calculate", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["result"]["acquirer"]["name"] == "Atlas Software"
    assert data["result"]["target"]["name"] == "Fulton Media"
    assert data["result"]["target"]["revenue"] > 0


def test_missing_core_field_returns_4xx_structured_error():
    client = app.test_client()
    payload = _payload()
    del payload["acquirer"]["net_income"]
    resp = client.post("/api/modeling/ma/calculate", json=payload)
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["status"] == "error"
    assert data["result"] is None
    assert any(f["code"] == "ACQUIRER_NET_INCOME_REQUIRED" for f in data["flags"])


def test_missing_company_returns_4xx():
    client = app.test_client()
    payload = {"target": _payload()["target"], "deal": _payload()["deal"]}
    resp = client.post("/api/modeling/ma/calculate", json=payload)
    assert resp.status_code == 400
    assert any(f["code"] == "ACQUIRER_REQUIRED" for f in resp.get_json()["flags"])


def test_no_silent_zero_fallback_on_bad_mix():
    client = app.test_client()
    resp = client.post("/api/modeling/ma/calculate", json=_payload(cash_pct=0.8, stock_pct=0.8))
    assert resp.status_code == 400
    assert any(f["code"] == "CONSIDERATION_MIX_INVALID" for f in resp.get_json()["flags"])


def test_all_cash_missing_financing_cost_returns_4xx():
    client = app.test_client()
    payload = _payload(cash_pct=1.0, stock_pct=0.0)
    del payload["deal"]["financing_cost"]
    resp = client.post("/api/modeling/ma/calculate", json=payload)
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["status"] == "error"
    assert data["result"] is None
    assert any(f["code"] == "FINANCING_COST_REQUIRED" for f in data["flags"])


def test_all_stock_missing_financing_cost_ok():
    client = app.test_client()
    payload = _payload(cash_pct=0.0, stock_pct=1.0)
    del payload["deal"]["financing_cost"]
    resp = client.post("/api/modeling/ma/calculate", json=payload)
    assert resp.status_code == 200
    assert resp.get_json()["result"]["after_tax_financing_cost"] == 0.0


def test_market_cap_only_returns_4xx_with_clear_message():
    client = app.test_client()
    payload = _payload()
    payload["target"] = {"name": "Tgt", "net_income": 1000.0, "market_cap": 40000.0}
    resp = client.post("/api/modeling/ma/calculate", json=payload)
    assert resp.status_code == 400
    data = resp.get_json()
    codes = {f["code"] for f in data["flags"]}
    assert "TARGET_SHARES_REQUIRED" in codes
    assert "TARGET_PRICE_REQUIRED" in codes
    text = " ".join(f["message"] for f in data["flags"]).lower()
    assert "shares" in text and "price" in text


def test_default_mode_market_cap_only_prioritizes_core_schema_errors():
    client = app.test_client()
    payload = _payload(synergy_mode="default")
    payload["target"] = {"name": "Tgt", "net_income": 1000.0, "market_cap": 40000.0}
    resp = client.post("/api/modeling/ma/calculate", json=payload)
    assert resp.status_code == 400
    data = resp.get_json()
    codes = {f["code"] for f in data["flags"]}
    assert "TARGET_SHARES_REQUIRED" in codes
    assert "TARGET_PRICE_REQUIRED" in codes
    assert "TARGET_REVENUE_REQUIRED" not in codes
    assert "DEFAULT_COST_SYNERGY_UNAVAILABLE" not in codes


def test_default_cost_synergy_mode_uses_rule_based_amount():
    client = app.test_client()
    payload = {
        "acquirer": {"sample_id": "atlas_software"},
        "target": {"sample_id": "beacon_payments"},
        "deal": {"premium": 0.25, "cash_pct": 0.5, "stock_pct": 0.5,
                 "financing_cost": 0.05, "tax_rate": 0.25, "synergy_mode": "default"},
    }
    resp = client.post("/api/modeling/ma/calculate", json=payload)
    assert resp.status_code == 200
    r = resp.get_json()["result"]
    default = r["synergy_context"]["default_cost_synergy"]
    assert default["synergy_tier"] == "medium"
    assert default["synergy_type"] == "cost_only"
    assert default["illustrative"] is True
    assert r["synergy"] == default["synergy_amount"]
    assert r["synergy_context"]["zero_synergy_result"]["synergy"] == 0.0


def test_real_seed_deck_sample_ids_calculate_with_default_synergy():
    client = app.test_client()
    payload = {
        "acquirer": {"sample_id": "aapl"},
        "target": {"sample_id": "msft"},
        "deal": {"premium": 0.20, "cash_pct": 0.5, "stock_pct": 0.5,
                 "financing_cost": 0.05, "tax_rate": 0.25, "synergy_mode": "default"},
    }
    resp = client.post("/api/modeling/ma/calculate", json=payload)
    assert resp.status_code == 200
    r = resp.get_json()["result"]
    assert r["acquirer"]["ticker"] == "AAPL"
    assert r["target"]["ticker"] == "MSFT"
    assert r["synergy_context"]["default_cost_synergy"]["synergy_tier"] != "high"
    assert r["synergy_context"]["zero_synergy_result"]["synergy"] == 0.0


def test_zero_synergy_mode_forces_zero_even_when_default_exists():
    client = app.test_client()
    payload = {
        "acquirer": {"sample_id": "atlas_software"},
        "target": {"sample_id": "beacon_payments"},
        "deal": {"premium": 0.25, "cash_pct": 0.5, "stock_pct": 0.5,
                 "financing_cost": 0.05, "tax_rate": 0.25,
                 "synergy_mode": "zero", "synergy": 999.0},
    }
    resp = client.post("/api/modeling/ma/calculate", json=payload)
    assert resp.status_code == 200
    r = resp.get_json()["result"]
    assert r["synergy"] == 0.0
    assert r["synergy_context"]["zero_synergy_selected"] is True


def test_manual_synergy_override_takes_priority():
    client = app.test_client()
    payload = {
        "acquirer": {"sample_id": "atlas_software"},
        "target": {"sample_id": "beacon_payments"},
        "deal": {"premium": 0.25, "cash_pct": 0.5, "stock_pct": 0.5,
                 "financing_cost": 0.05, "tax_rate": 0.25,
                 "synergy_mode": "manual", "synergy": 123.0},
    }
    resp = client.post("/api/modeling/ma/calculate", json=payload)
    assert resp.status_code == 200
    r = resp.get_json()["result"]
    assert r["synergy"] == 123.0
    assert r["synergy_context"]["manual_override"] is True
    assert r["synergy_context"]["default_cost_synergy"]["synergy_amount"] != 123.0


def test_default_synergy_requires_target_revenue_for_inline_payload():
    client = app.test_client()
    payload = _payload(synergy_mode="default")
    resp = client.post("/api/modeling/ma/calculate", json=payload)
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["status"] == "error"
    codes = {flag["code"] for flag in data["flags"]}
    assert "TARGET_REVENUE_REQUIRED" in codes
    assert "DEFAULT_COST_SYNERGY_UNAVAILABLE" in codes


def test_manual_and_zero_modes_preserve_core_market_cap_rejection():
    client = app.test_client()
    for mode in ("manual", "zero"):
        payload = _payload(synergy_mode=mode)
        payload["target"] = {"name": "Tgt", "net_income": 1000.0, "market_cap": 40000.0}
        resp = client.post("/api/modeling/ma/calculate", json=payload)
        assert resp.status_code == 400
        codes = {f["code"] for f in resp.get_json()["flags"]}
        assert "TARGET_SHARES_REQUIRED" in codes
        assert "TARGET_PRICE_REQUIRED" in codes


def test_default_mode_financing_cost_validation_still_precedes_synergy_rules():
    client = app.test_client()
    payload = {
        "acquirer": {"sample_id": "atlas_software"},
        "target": {"sample_id": "beacon_payments"},
        "deal": {"premium": 0.25, "cash_pct": 1.0, "stock_pct": 0.0,
                 "tax_rate": 0.25, "synergy_mode": "default"},
    }
    resp = client.post("/api/modeling/ma/calculate", json=payload)
    assert resp.status_code == 400
    codes = {f["code"] for f in resp.get_json()["flags"]}
    assert "FINANCING_COST_REQUIRED" in codes
    assert "DEFAULT_COST_SYNERGY_UNAVAILABLE" not in codes
