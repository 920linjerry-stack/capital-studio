"""Shared types + HTTP/RSS helpers for V6 source adapters.

Dependency-free: HTTP via ``urllib`` with a short timeout and a declared
User-Agent; feed parsing via the stdlib XML parser. Every adapter is honest
about its ``mode`` (one of :data:`modeling.v6.schemas.DATA_MODES`).
"""

from __future__ import annotations

import os
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree as ET

from modeling.v6.schemas import MarketEvent
from modeling.v6.classifier import classify_text

# A normal browser-ish UA; SEC in particular asks callers to identify. Kept
# generic and keyless.
_USER_AGENT = os.environ.get(
    "V6_PUBLIC_USER_AGENT",
    "stock-dashboard-v6/1.0 (+https://github.com/920linjerry-stack/capital-studio)",
)
DEFAULT_TIMEOUT = 4.0


@dataclass
class RawItem:
    """A normalized raw item from any feed, before classification."""
    title: str
    summary: str = ""
    url: str = ""
    published: str = ""          # ISO-8601 if known, else raw string
    source: str = ""
    source_type: str = "company"
    related_tickers: list[str] = field(default_factory=list)


@dataclass
class FetchResult:
    """One adapter's outcome. ``mode`` tells the UI how real the data is."""
    source_id: str
    source_name: str
    mode: str                    # live / live-partial / fixture / unavailable / error
    items: list[RawItem] = field(default_factory=list)
    error: str = ""

    def to_status(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "mode": self.mode,
            "item_count": len(self.items),
            "error": self.error,
        }


def http_get(url: str, timeout: float = DEFAULT_TIMEOUT) -> str:
    """GET a URL as text with a short timeout. Raises on any failure."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https only by convention)
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def parse_feed(xml_text: str) -> list[dict[str, str]]:
    """Parse an RSS 2.0 or Atom feed into ``[{title, link, published, summary}]``.

    Namespace-agnostic (matches on local tag names) and tolerant of partial
    feeds. Returns an empty list if nothing parseable is found.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    items: list[dict[str, str]] = []
    for el in root.iter():
        name = _localname(el.tag)
        if name not in ("item", "entry"):
            continue
        rec = {"title": "", "link": "", "published": "", "summary": ""}
        for child in el:
            cname = _localname(child.tag)
            text = (child.text or "").strip()
            if cname == "title":
                rec["title"] = text
            elif cname == "link":
                # RSS: text; Atom: href attribute
                rec["link"] = text or child.attrib.get("href", "")
            elif cname in ("pubDate", "published", "updated", "date"):
                rec["published"] = rec["published"] or text
            elif cname in ("description", "summary", "content"):
                rec["summary"] = rec["summary"] or text
        if rec["title"]:
            items.append(rec)
    return items


def raw_to_event(item: RawItem, idx: int, *, data_mode: str = "fixture") -> MarketEvent:
    """Classify a :class:`RawItem` into a structured :class:`MarketEvent`.

    Direction / event_type / tags come from the deterministic classifier (no
    LLM). The event id is derived from the source + index so repeated ingests
    are stable.
    """
    res = classify_text(item.title, item.summary)
    eid = f"src-{item.source.lower().replace(' ', '_')}-{idx}"
    return MarketEvent(
        event_id=eid,
        title=item.title,
        source=item.source,
        source_type=item.source_type,
        timestamp=item.published,
        effective_at=item.published,
        event_type=res["event_type"],
        direction=res["direction"],
        magnitude=res["magnitude"],
        confidence=0.5,                       # headline-derived: medium by default
        affected_tags=res["tags"],
        related_tickers=item.related_tickers,
        summary=item.summary,
        data_mode=data_mode,
        source_list=[item.source] if item.source else [],
        recognized_states=res.get("states", []),
        classification_flags=res.get("flags", []),
        classification_confidence=res.get("confidence_multiplier", 1.0),
    )
