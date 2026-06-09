import datetime

import pandas as pd
import pytest

from data_fetcher_akshare import _filter_hk_future_periods, _hk_pivot_latest


def _row(period, item, amount):
    return {"REPORT_DATE": period, "STD_ITEM_NAME": item, "AMOUNT": amount}


def test_hk_future_period_filter_keeps_past_period_and_drops_true_future():
    df = pd.DataFrame(
        [
            _row("2024-12-31", "营业额", 200.0),
            _row("2025-12-31", "营业额", 300.0),
            _row("2026-12-31", "营业额", 400.0),
        ]
    )

    filtered = _filter_hk_future_periods(
        df,
        "REPORT_DATE",
        ticker="02359",
        today=datetime.date(2026, 5, 26),
    )

    assert filtered["REPORT_DATE"].dt.strftime("%Y-%m-%d").tolist() == [
        "2024-12-31",
        "2025-12-31",
    ]
    assert filtered["REPORT_DATE"].max().strftime("%Y-%m-%d") == "2025-12-31"
    assert filtered.attrs["hk_period_policy_audit"]["dropped_future_period_count"] == 1


def test_hk_pivot_latest_raises_when_all_periods_are_future(monkeypatch):
    class MockDate(datetime.date):
        @classmethod
        def today(cls):
            return cls(2026, 5, 26)

    class MockDateTimeModule:
        date = MockDate

    df = pd.DataFrame([_row("2026-12-31", "营业额", 400.0)])
    monkeypatch.setattr("data_fetcher_akshare.datetime", MockDateTimeModule)

    with pytest.raises(ValueError, match="no HK financial rows remain"):
        _hk_pivot_latest(df, date_col="REPORT_DATE", ticker="02359")


def test_hk_pivot_latest_excludes_period_after_today_but_keeps_prior(monkeypatch):
    class MockDate(datetime.date):
        @classmethod
        def today(cls):
            return cls(2025, 6, 1)

    class MockDateTimeModule:
        date = MockDate

    df = pd.DataFrame(
        [
            _row("2024-12-31", "营业额", 200.0),
            _row("2024-12-31", "经营溢利", 20.0),
            _row("2025-12-31", "营业额", 300.0),
            _row("2025-12-31", "经营溢利", 30.0),
        ]
    )
    monkeypatch.setattr("data_fetcher_akshare.datetime", MockDateTimeModule)

    latest = _hk_pivot_latest(df, date_col="REPORT_DATE", ticker="02359")

    assert latest["营业额"] == 200.0
    assert latest["经营溢利"] == 20.0
    audit = latest["_period_policy_audit"]
    assert audit["selected_period_end"].strftime("%Y-%m-%d") == "2024-12-31"
    assert audit["dropped_future_period_count"] == 2
    assert audit["period_policy"] == "latest_non_future_period"
