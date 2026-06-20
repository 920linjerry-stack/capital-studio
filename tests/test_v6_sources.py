"""V6 -- source adapter parsing + registry tests (no live network)."""

from modeling.v6.sources.base import parse_feed, raw_to_event, RawItem
from modeling.v6.sources.registry import (
    ingest_events, get_source_status, overall_data_mode, SOURCE_REGISTRY,
)
from modeling.v6.sources.adapters import YahooFinanceRSS, SecEdgar, FredCalendar

# Saved sample feeds (no network) -------------------------------------------
_RSS = """<?xml version='1.0'?>
<rss version='2.0'><channel>
  <item><title>Apple beats earnings estimates</title>
    <link>http://example.com/a</link>
    <pubDate>Sat, 20 Jun 2026 10:00:00 GMT</pubDate>
    <description>Apple topped estimates.</description></item>
  <item><title>Fed cuts rates 25bp</title>
    <link>http://example.com/b</link>
    <pubDate>Sat, 20 Jun 2026 11:00:00 GMT</pubDate>
    <description>Dovish cut.</description></item>
</channel></rss>"""

_ATOM = """<?xml version='1.0'?>
<feed xmlns='http://www.w3.org/2005/Atom'>
  <entry><title>Nvidia AI chip demand surges</title>
    <link href='http://example.com/c'/>
    <updated>2026-06-20T09:00:00Z</updated>
    <summary>Strong demand.</summary></entry>
</feed>"""


def test_parse_rss_items():
    items = parse_feed(_RSS)
    assert len(items) == 2
    assert items[0]["title"] == "Apple beats earnings estimates"
    assert items[0]["link"] == "http://example.com/a"


def test_parse_atom_items():
    items = parse_feed(_ATOM)
    assert len(items) == 1
    assert items[0]["title"].startswith("Nvidia")
    assert items[0]["link"] == "http://example.com/c"   # href attribute


def test_parse_garbage_is_empty_not_error():
    assert parse_feed("not xml at all <<<") == []


def test_raw_to_event_classifies_via_rules():
    item = RawItem(title="Fed cuts rates 25bp", source="Test", source_type="macro")
    ev = raw_to_event(item, 0, data_mode="fixture")
    assert ev.event_type == "rate_cut"
    assert ev.direction == 1
    assert ev.data_mode == "fixture"
    assert ev.event_id.startswith("src-")


def test_registry_fixture_mode_is_offline_and_labeled():
    events, statuses = ingest_events(allow_network=False)
    assert len(statuses) == len(SOURCE_REGISTRY)
    assert all(s["mode"] in ("fixture", "unavailable") for s in statuses)
    assert events  # fixture items produce some events


def test_fred_and_analyst_are_fixture_only():
    fred = FredCalendar().fetch(allow_network=True)
    assert fred.mode == "fixture"   # key required -> never live


def test_yahoo_fixture_when_network_disabled():
    res = YahooFinanceRSS().fetch(tickers=["AAPL"], allow_network=False)
    assert res.mode == "fixture"
    assert res.items and res.items[0].related_tickers == ["AAPL"]


def test_sec_edgar_unknown_ticker_is_unavailable_when_live():
    res = SecEdgar().fetch(tickers=["ZZZZ"], allow_network=True)
    assert res.mode == "unavailable"   # no CIK, but no crash


def test_overall_mode_rollup():
    assert overall_data_mode([{"mode": "fixture"}, {"mode": "fixture"}]) == "fixture"
    assert overall_data_mode([{"mode": "live"}, {"mode": "live-partial"}]) == "live"
    assert overall_data_mode([{"mode": "live"}, {"mode": "fixture"}]) == "live-partial"


def test_get_source_status_shape():
    statuses = get_source_status(allow_network=False)
    for s in statuses:
        assert {"source_id", "source_name", "mode", "item_count", "error"} <= set(s)
