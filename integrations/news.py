"""Headlines via RSS.

RSS over a news API on purpose: no key, no quota, no per-request billing, and
the publishers have every incentive to keep the feeds up. Parsed with stdlib
ElementTree rather than pulling in feedparser for what amounts to two XPaths.
"""
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

import requests

TIMEOUT = 15
HEADERS = {"User-Agent": "JARVIS personal assistant"}
ATOM = "{http://www.w3.org/2005/Atom}"


@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    topic: str


FEEDS = [
    Feed("BBC", "https://feeds.bbci.co.uk/news/rss.xml", "world"),
    Feed("NPR", "https://feeds.npr.org/1001/rss.xml", "world"),
    Feed("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", "tech"),
    Feed("Hacker News", "https://hnrss.org/frontpage", "tech"),
]


def fetch(feed: Feed, limit: int = 10) -> list[dict[str, Any]]:
    """Headlines from one feed. Raises so the poller can record the failure."""
    r = requests.get(feed.url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    root = ET.fromstring(r.content)

    # RSS 2.0 puts items at channel/item; Atom uses a namespaced <entry>.
    items = root.findall(".//item") or root.findall(f".//{ATOM}entry")
    headlines = []
    for item in items[:limit]:
        title = _text(item, "title") or _text(item, f"{ATOM}title")
        if not title:
            continue
        headlines.append({
            "title": title,
            "link": _text(item, "link") or _link_atom(item),
            "published": _text(item, "pubDate") or _text(item, f"{ATOM}updated"),
            "source": feed.name,
            "topic": feed.topic,
        })
    return headlines


def fetch_all(feeds: list[Feed] | None = None, per_feed: int = 8) -> list[dict[str, Any]]:
    """Every feed, with per-feed failures tolerated.

    One publisher being down shouldn't cost the whole briefing its news section,
    so this only raises when nothing at all came back.
    """
    feeds = feeds or FEEDS
    headlines: list[dict[str, Any]] = []
    errors: list[str] = []
    for feed in feeds:
        try:
            headlines.extend(fetch(feed, limit=per_feed))
        except Exception as e:
            errors.append(f"{feed.name}: {type(e).__name__}")
    if not headlines:
        raise RuntimeError(f"all feeds failed ({'; '.join(errors)})")
    return headlines


def _text(item: ET.Element, tag: str) -> str:
    node = item.find(tag)
    return (node.text or "").strip() if node is not None and node.text else ""


def _link_atom(item: ET.Element) -> str:
    node = item.find(f"{ATOM}link")
    return node.get("href", "") if node is not None else ""
