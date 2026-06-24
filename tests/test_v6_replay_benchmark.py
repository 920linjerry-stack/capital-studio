"""Internal-only benchmark integrity, evaluation, and diagnostic tests."""

from dataclasses import replace

from modeling.v6.replay import to_market_event
from modeling.v6.replay_benchmark import (
    ERROR_REASONS,
    VALID_SPLITS,
    benchmark_integrity,
    error_taxonomy,
    evaluate_benchmark,
    load_benchmark_events,
    run_benchmark,
)
from modeling.v6.templates import contains_banned_phrase


REQUIRED_TICKERS = {
    "AAPL", "MSFT", "NVDA", "AMD", "TSLA", "META", "GOOGL", "AMZN",
    "AVGO", "TSM", "ASML", "JPM", "BAC", "GS", "XOM", "CVX", "UNH",
    "LLY", "NVO", "QQQ", "TQQQ", "SPY", "SGOV", "GLD", "USO", "IWM",
    "XLF", "XLK", "XLV", "XLE",
}


def test_benchmark_integrity_schema_and_size():
    events = load_benchmark_events()
    integrity = benchmark_integrity(events)
    assert 50 <= len(events) <= 200
    assert integrity["duplicate_event_ids"] == []
    assert integrity["invalid_splits"] == []
    assert integrity["invalid_return_statuses"] == []
    assert integrity["missing_provenance"] == []
    assert integrity["missing_tickers"] == []
    assert integrity["missing_label_confidence"] == []


def test_benchmark_all_events_pass_no_lookahead():
    events = load_benchmark_events()
    assert all(event.no_lookahead_flag for event in events)
    assert all(event.lookahead_ok() for event in events)


def test_benchmark_has_frozen_seed_dev_holdout_partitions():
    events = load_benchmark_events()
    splits = {event.split for event in events}
    assert splits == VALID_SPLITS
    assert sum(event.split == "seed" for event in events) == 10
    assert sum(event.split == "dev" for event in events) >= 20
    assert sum(event.split == "holdout" for event in events) >= 10


def test_benchmark_category_and_asset_coverage():
    events = load_benchmark_events()
    categories = {event.category for event in events}
    assert {
        "macro_rates_inflation", "company_earnings_guidance",
        "institutional_analyst", "official_filing", "regulatory_policy",
        "sentiment_reflexivity", "sector_specific_shock",
        "breaking_news_shock",
    } <= categories
    tickers = {ticker for event in events for ticker in event.affected_tickers}
    assert REQUIRED_TICKERS <= tickers


def test_benchmark_conversion_uses_existing_market_event_path():
    event = next(e for e in load_benchmark_events() if e.split == "dev")
    converted = to_market_event(event.to_historical_event(event.affected_tickers[0]))
    assert converted.event_id.startswith("replay-")
    assert not hasattr(converted, "fixture_returns")
    assert converted.timestamp == event.event_time


def test_benchmark_missing_returns_are_safe():
    source = next(e for e in load_benchmark_events() if e.split == "dev")
    event = replace(
        source,
        return_status="missing",
        fixture_returns_by_ticker={},
        fixture_benchmark_returns={},
    )
    rows = run_benchmark([event])
    assert rows
    assert all(row["result"] in {"no_data", "no_call"} for row in rows)


def test_benchmark_metrics_shape_and_holdout_separation():
    results = run_benchmark(load_benchmark_events())
    metrics = evaluate_benchmark(results)
    assert set(metrics["by_split"]) == VALID_SPLITS
    assert metrics["holdout"] == metrics["by_split"]["holdout"]
    assert set(metrics["by_window"]) == {"1", "3", "5", "10"}
    assert "directional_hit_rate" in metrics["overall"]
    assert "agreement_rate" in metrics["expected_label_diagnostic"]
    assert set(metrics["impact_score_calibration"]) == {"low", "medium", "high"}
    assert set(metrics["confidence_calibration"]) == {"low", "medium", "high"}


def test_benchmark_error_taxonomy_shape():
    taxonomy = error_taxonomy(run_benchmark(load_benchmark_events()))
    assert set(taxonomy["counts"]) == set(ERROR_REASONS)
    assert set(taxonomy["examples"]) == set(ERROR_REASONS)
    assert taxonomy["classified_rows"] >= 0


def test_holdout_can_be_run_without_dev_rows():
    events = load_benchmark_events()
    holdout = run_benchmark(events, splits={"holdout"})
    dev = run_benchmark(events, splits={"dev"})
    assert holdout and dev
    assert all(row["split"] == "holdout" for row in holdout)
    assert all(row["split"] == "dev" for row in dev)
    assert {row["event_id"] for row in holdout}.isdisjoint(
        {row["event_id"] for row in dev}
    )


def test_benchmark_is_internal_only_and_has_no_advice_wording():
    from app import app

    client = app.test_client()
    assert client.get("/modeling/v6/replay").status_code == 404
    assert client.get("/api/modeling/v6/replay").status_code == 404
    for row in run_benchmark(load_benchmark_events()):
        assert contains_banned_phrase(row["conclusion"], ignore_quoted=True) is None
        assert contains_banned_phrase(row.get("notes", "") or "") is None
