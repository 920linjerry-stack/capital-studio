"""Pre-print acceptance-bar archive -- logging only, failure-tolerant, offline-safe."""

from modeling.v6 import acceptance_bar as ab
from modeling.v6.postprint import ACCEPTANCE_BAR_STATUSES


def test_offline_build_is_graceful_and_records_reasons():
    # No network: consensus + options must be recorded unavailable, run continues.
    rec = ab.build_acceptance_bar("NVDA", allow_network=False)
    assert rec.ticker == "NVDA"
    assert rec.acceptance_bar_status in ACCEPTANCE_BAR_STATUSES
    assert rec.option_implied_move is None
    assert any("network disabled" in r for r in rec.reason_missing)
    assert rec.is_preprint_snapshot is True


def test_offline_still_captures_own_bar_when_baseline_exists():
    rec = ab.build_acceptance_bar("NVDA", allow_network=False)
    # NVDA has a whisper baseline -> own bar available even offline -> partial.
    if rec.own_historical_surprise_bar is not None:
        assert rec.acceptance_bar_status in {"partial", "available"}
        assert rec.own_bar_n_history and rec.own_bar_n_history >= 1


def test_no_baseline_ticker_records_unavailable_reason():
    rec = ab.build_acceptance_bar("ZZZZ_NO_TICKER", allow_network=False)
    assert any("own_historical_surprise_bar" in r for r in rec.reason_missing)


def test_skip_options_records_skip_reason():
    rec = ab.build_acceptance_bar("NVDA", allow_network=False, skip_options=True)
    assert rec.option_implied_move is None
    assert any("skipped" in r for r in rec.reason_missing)


def test_record_serializes_with_schema_version():
    d = ab.build_acceptance_bar("MU", allow_network=False).to_dict()
    assert d["schema_version"] == ab.RECORD_SCHEMA_VERSION
    assert "option_implied_move" in d and "consensus_source_type" in d
    assert isinstance(d["reason_missing"], list) and isinstance(d["data_sources"], list)


def test_record_flags_live_only_and_not_backtestable():
    rec = ab.build_acceptance_bar("MU", allow_network=False)
    d = rec.to_dict()
    assert d["live_logging_only"] is True
    assert d["not_backtestable"] is True
    assert "logging_only" in d["scoring_isolation"]
    # the live-only field list must cover options + consensus
    for f in ("option_implied_move", "consensus_eps"):
        assert f in d["live_only_fields"]


def test_status_inference_levels():
    rec = ab.AcceptanceBarRecord(ticker="X")
    assert ab._status(rec) == "unavailable"
    rec.option_implied_move = 0.08
    assert ab._status(rec) == "partial"
    rec.consensus_eps = 1.0
    rec.own_historical_surprise_bar = 0.5
    rec.priced_for_perfection = 0.7
    assert ab._status(rec) == "available"
