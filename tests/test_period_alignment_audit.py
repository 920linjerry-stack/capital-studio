from modeling.data_quality import build_period_alignment_audit


def test_all_periods_same_clean():
    audit = build_period_alignment_audit({
        "revenue": 100,
        "income_statement_period": "2025-12-31",
        "cash_flow_period": "2025-12-31",
        "balance_sheet_period": "2025-12-31",
    })
    assert audit["status"] == "Clean"


def test_missing_bs_period_review():
    audit = build_period_alignment_audit({
        "revenue": 100,
        "income_statement_period": "2025-12-31",
        "cash_flow_period": "2025-12-31",
    })
    assert audit["status"] == "Review"
    assert "missing" in audit["warning"].lower()


def test_mismatched_periods_high_review():
    audit = build_period_alignment_audit({
        "revenue": 100,
        "income_statement_period": "2025-12-31",
        "cash_flow_period": "2024-12-31",
        "balance_sheet_period": "2025-12-31",
    })
    assert audit["status"] == "High Review"


def test_no_period_data_review_or_unavailable():
    audit = build_period_alignment_audit({"revenue": 100})
    assert audit["status"] in {"Review", "Unavailable"}


def test_aapl_unavailable_metadata_not_high_review():
    audit = build_period_alignment_audit({"revenue": 416161, "ebit": 133050})
    assert audit["status"] != "High Review"
