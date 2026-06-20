"""V6 -- event de-duplication tests."""

from modeling.v6.schemas import MarketEvent, DIRECTION_BULLISH
from modeling.v6.dedupe import dedupe_events, event_signature


def _ev(eid, title, conf, src, ticker="AAPL", etype="guidance_raise"):
    return MarketEvent(event_id=eid, title=title, event_type=etype,
                       direction=DIRECTION_BULLISH, magnitude=4.0, confidence=conf,
                       related_tickers=[ticker], source=src,
                       timestamp="2026-06-20T10:00:00Z", effective_at="2026-06-20T10:00:00Z")


def test_near_duplicate_headlines_merge():
    evs = [
        _ev("a", "Apple raises full-year guidance on services strength", 0.7, "Fixture News"),
        _ev("b", "Apple lifts full year guidance; services strong", 0.8, "Yahoo"),
    ]
    out, rep = dedupe_events(evs)
    assert len(out) == 1
    assert rep["merged_count"] == 1
    assert out[0].source_count == 2
    assert set(out[0].source_list) == {"Fixture News", "Yahoo"}


def test_distinct_events_not_merged():
    evs = [
        _ev("a", "Apple raises guidance", 0.7, "Fixture News", ticker="AAPL"),
        _ev("b", "Nvidia chip demand surges", 0.6, "GS", ticker="NVDA", etype="ai_capex_semis"),
    ]
    out, rep = dedupe_events(evs)
    assert len(out) == 2
    assert rep["merged_count"] == 0


def test_representative_keeps_highest_confidence():
    evs = [
        _ev("a", "Apple raises full-year guidance", 0.6, "Fixture News"),
        _ev("b", "Apple raises full-year guidance", 0.9, "Yahoo"),
    ]
    out, _ = dedupe_events(evs)
    # confidence is the higher one (0.9) plus a small capped boost
    assert out[0].confidence >= 0.9


def test_confidence_boost_is_capped():
    evs = [_ev(str(i), "Apple raises full-year guidance", 0.5, f"S{i}") for i in range(20)]
    out, _ = dedupe_events(evs)
    assert len(out) == 1
    assert out[0].confidence <= 0.5 + 0.10 + 1e-9   # cap is +0.10
    assert out[0].source_count == 20


def test_signature_is_deterministic():
    e = _ev("a", "Apple raises guidance", 0.7, "Fixture News")
    assert event_signature(e) == event_signature(e)
