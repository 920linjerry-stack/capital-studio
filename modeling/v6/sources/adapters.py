"""Concrete public, keyless source adapters for V6.

Each adapter exposes ``id``, ``name``, ``source_type`` and a ``fetch(...)`` that
returns a :class:`FetchResult`. When ``allow_network`` is False (the safe
default) or a live fetch fails, the adapter returns bundled sample items with an
honest ``mode`` so the page never hangs and never pretends data is live.

Sources:
* YahooFinanceRSS   -- Yahoo Finance headline RSS per ticker (keyless).
* GoogleNewsRSS     -- Google News RSS search per query (keyless).
* SecEdgar          -- SEC EDGAR public submissions JSON (keyless; UA required).
* FredCalendar      -- macro calendar; FRED API needs a key, so this is a
                       skeleton + fixture fallback (mode never "live").
* AnalystHeadlines  -- no reliable keyless analyst feed; interface + fixtures.
"""

from __future__ import annotations

import json
import logging
from urllib.parse import quote_plus

from modeling.v6.sources.base import (
    RawItem, FetchResult, http_get, parse_feed, DEFAULT_TIMEOUT,
    public_error_status,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Yahoo Finance headline RSS (per ticker)
# --------------------------------------------------------------------------
class YahooFinanceRSS:
    id = "yahoo_rss"
    name = "Yahoo Finance RSS"
    source_type = "institutional"
    url_tmpl = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={t}&region=US&lang=en-US"

    def fetch(self, *, tickers=None, keywords=None, timeout=DEFAULT_TIMEOUT,
              allow_network=False) -> FetchResult:
        tickers = [t for t in (tickers or []) if t][:6]
        if not allow_network:
            return FetchResult(self.id, self.name, "fixture", _yahoo_fixture(tickers))
        items: list[RawItem] = []
        ok = False
        for t in tickers:
            try:
                xml = http_get(self.url_tmpl.format(t=quote_plus(t)), timeout)
                for rec in parse_feed(xml):
                    items.append(RawItem(
                        title=rec["title"], summary=rec["summary"], url=rec["link"],
                        published=rec["published"], source=self.name,
                        source_type=self.source_type, related_tickers=[t],
                    ))
                ok = True
            except Exception:  # noqa: BLE001 - one ticker failing must not abort
                continue
        if not ok:
            return FetchResult(self.id, self.name, "unavailable",
                               _yahoo_fixture(tickers), error="all ticker feeds failed")
        mode = "live" if len(items) else "live-partial"
        return FetchResult(self.id, self.name, mode, items)


# --------------------------------------------------------------------------
# Google News RSS search
# --------------------------------------------------------------------------
class GoogleNewsRSS:
    id = "google_news_rss"
    name = "Google News RSS"
    source_type = "company"
    url_tmpl = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"

    def fetch(self, *, tickers=None, keywords=None, timeout=DEFAULT_TIMEOUT,
              allow_network=False) -> FetchResult:
        terms = list(keywords or []) + list(tickers or [])
        query = " OR ".join(terms[:8]) or "stock market"
        if not allow_network:
            return FetchResult(self.id, self.name, "fixture", _google_fixture())
        try:
            xml = http_get(self.url_tmpl.format(q=quote_plus(query)), timeout)
        except Exception as e:  # noqa: BLE001
            # Raw exception kept server-side only; client gets a sanitized status.
            logger.debug("v6 %s fetch failed", self.id, exc_info=True)
            safe = public_error_status(e, source_name=self.name)
            return FetchResult(self.id, self.name, "error", _google_fixture(),
                               error=safe["error"], error_code=safe["error_code"])
        items = [
            RawItem(title=r["title"], summary=r["summary"], url=r["link"],
                    published=r["published"], source=self.name, source_type=self.source_type)
            for r in parse_feed(xml)
        ]
        if not items:
            return FetchResult(self.id, self.name, "unavailable", _google_fixture())
        return FetchResult(self.id, self.name, "live", items)


# --------------------------------------------------------------------------
# SEC EDGAR public submissions
# --------------------------------------------------------------------------
# Minimal ticker -> CIK map for a few covered names (zero-padded to 10 digits).
_CIK = {
    "AAPL": "0000320193", "MSFT": "0000789019", "NVDA": "0001045810",
    "AMD": "0000002488", "TSLA": "0001318605", "META": "0001326801",
    "GOOGL": "0001652044", "JPM": "0000019617", "XOM": "0000034088",
    "UNH": "0000731766",
    # wave-3 coverage
    "AMZN": "0001018724", "AVGO": "0001730168", "ASML": "0000937966",
    "BAC": "0000070858", "GS": "0000886982", "CVX": "0000093410",
    "LLY": "0000059478", "TSM": "0001046179",
}

# Common SEC form types surfaced as official events (for UI labelling).
_FORM_LABELS = {
    "8-K": "重大事项 (8-K)", "10-Q": "季度报告 (10-Q)", "10-K": "年度报告 (10-K)",
    "S-1": "招股说明书 (S-1)", "4": "内部人交易 (Form 4)", "6-K": "外国发行人报告 (6-K)",
    "20-F": "外国年度报告 (20-F)",
}


class SecEdgar:
    id = "sec_edgar"
    name = "SEC EDGAR"
    source_type = "official"
    url_tmpl = "https://data.sec.gov/submissions/CIK{cik}.json"

    def fetch(self, *, tickers=None, keywords=None, timeout=DEFAULT_TIMEOUT,
              allow_network=False) -> FetchResult:
        known = [t for t in (tickers or []) if t.upper() in _CIK][:4]
        if not allow_network:
            return FetchResult(self.id, self.name, "fixture", _edgar_fixture(known or ["AAPL"]))
        if not known:
            return FetchResult(self.id, self.name, "unavailable", [],
                               error="no covered CIK for requested tickers")
        items: list[RawItem] = []
        ok = False
        for t in known:
            try:
                raw = http_get(self.url_tmpl.format(cik=_CIK[t.upper()]), timeout)
                data = json.loads(raw)
                recent = (data.get("filings", {}) or {}).get("recent", {}) or {}
                forms = recent.get("form", [])[:5]
                dates = recent.get("filingDate", [])[:5]
                for form, d in zip(forms, dates):
                    label = _FORM_LABELS.get(form, f"form {form}")
                    items.append(RawItem(
                        title=f"{t} files SEC {form}",
                        summary=f"{t} filed a {label} with the SEC on {d}.",
                        published=d, source=self.name, source_type=self.source_type,
                        related_tickers=[t.upper()],
                    ))
                ok = True
            except Exception:  # noqa: BLE001
                continue
        if not ok:
            return FetchResult(self.id, self.name, "unavailable",
                               _edgar_fixture(known), error="EDGAR fetch failed")
        return FetchResult(self.id, self.name, "live", items)


# --------------------------------------------------------------------------
# FRED / macro calendar (key required -> skeleton + fixtures only)
# --------------------------------------------------------------------------
class FredCalendar:
    id = "fred_calendar"
    name = "Fixture Macro Calendar"
    source_type = "macro"

    def fetch(self, *, tickers=None, keywords=None, timeout=DEFAULT_TIMEOUT,
              allow_network=False) -> FetchResult:
        # The FRED API requires an API key, which violates the keyless boundary,
        # so this adapter is intentionally fixture-only. The interface is ready
        # for a future keyless macro-calendar source.
        return FetchResult(self.id, self.name, "fixture", _macro_calendar_fixture())


# --------------------------------------------------------------------------
# Analyst headlines (no reliable keyless feed -> fixtures)
# --------------------------------------------------------------------------
class AnalystHeadlines:
    id = "analyst_headlines"
    name = "Fixture Analyst Headline"
    source_type = "institutional"

    def fetch(self, *, tickers=None, keywords=None, timeout=DEFAULT_TIMEOUT,
              allow_network=False) -> FetchResult:
        # Public analyst research is paywalled; we only ever use sample headlines
        # and never scrape login/paywalled content.
        return FetchResult(self.id, self.name, "fixture", _analyst_fixture(tickers))


# --- sample-item fixtures (deterministic, mock) ---------------------------
def _yahoo_fixture(tickers) -> list[RawItem]:
    t = (tickers or ["AAPL"])[0]
    return [
        RawItem(title=f"{t} rallies as analysts raise price target on AI momentum",
                summary="Sample public-news headline (fixture).", source="Fixture Public News",
                source_type="institutional", related_tickers=[t]),
    ]


def _google_fixture() -> list[RawItem]:
    return [
        RawItem(title="Treasury yields rise after hotter-than-expected inflation data",
                summary="Sample public-news headline (fixture).", source="Fixture Public News",
                source_type="macro"),
    ]


def _edgar_fixture(tickers) -> list[RawItem]:
    t = (tickers or ["AAPL"])[0].upper()
    return [
        RawItem(title=f"{t} files SEC 8-K",
                summary=f"Sample EDGAR filing item for {t} — {_FORM_LABELS['8-K']} (fixture).",
                source="Fixture Filing Source", source_type="official", related_tickers=[t]),
    ]


def _macro_calendar_fixture() -> list[RawItem]:
    return [
        RawItem(title="FOMC rate decision on the calendar",
                summary="Sample macro-calendar entry (fixture).",
                source="Fixture Macro Calendar", source_type="macro"),
    ]


def _analyst_fixture(tickers) -> list[RawItem]:
    t = (tickers or ["NVDA"])[0]
    return [
        RawItem(title=f"Brokerage upgrades {t} to overweight citing AI capex demand",
                summary="Sample analyst headline (fixture).",
                source="Fixture Analyst Headline", source_type="institutional", related_tickers=[t]),
    ]


ALL_ADAPTERS = [
    YahooFinanceRSS(), GoogleNewsRSS(), SecEdgar(), FredCalendar(), AnalystHeadlines(),
]
