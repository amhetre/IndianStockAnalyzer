"""
Indian market news from public RSS feeds (Economic Times, Mint, Business Standard)
and per-company news from Google News search.

Only headline, source, time, thumbnail and a short teaser are shown; every item
links to the publisher's own article.
"""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import quote_plus, urlparse

import requests

from server.market import _cached
from utils.logger import get_logger

log = get_logger("server.news")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36", "Accept": "application/rss+xml, application/xml, text/xml"}

FEEDS = {
    "et_markets": ("Economic Times", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    "et_stocks": ("Economic Times", "https://economictimes.indiatimes.com/markets/stocks/news/rssfeeds/2146842.cms"),
    "et_ipo": ("Economic Times", "https://economictimes.indiatimes.com/markets/ipos/fpos/rssfeeds/14655708.cms"),
    "et_economy": ("Economic Times", "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms"),
    "mint_markets": ("Mint", "https://www.livemint.com/rss/markets"),
    "mint_companies": ("Mint", "https://www.livemint.com/rss/companies"),
    "bs_markets": ("Business Standard", "https://www.business-standard.com/rss/markets-106.rss"),
}

CATEGORIES = {
    "markets": ("Markets", ["et_markets", "mint_markets", "bs_markets"]),
    "stocks": ("Stocks & companies", ["et_stocks", "mint_companies"]),
    "ipo": ("IPOs", ["et_ipo"]),
    "economy": ("Economy", ["et_economy"]),
}

_TAG = re.compile(r"<[^>]+>")


def _text(s: Optional[str], limit: int = 0) -> str:
    t = html.unescape(_TAG.sub(" ", html.unescape(s or "")))
    t = re.sub(r"\s+", " ", t).strip()
    if limit and len(t) > limit:
        t = t[:limit].rsplit(" ", 1)[0] + "…"
    return t


def _image(item: ET.Element) -> Optional[str]:
    for el in item.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        url = el.get("url")
        if tag in ("content", "thumbnail") and url:
            return url
        if tag == "enclosure" and url and (el.get("type") or "image").startswith("image"):
            return url
    m = re.search(r'<img[^>]+src="([^"]+)"', html.unescape(item.findtext("description") or ""))
    return m.group(1) if m else None


def _ts(s: Optional[str]) -> Optional[float]:
    try:
        return parsedate_to_datetime(s).timestamp() if s else None
    except (TypeError, ValueError):
        return None


def _parse(content: bytes, source: Optional[str], google: bool = False) -> list[dict]:
    out = []
    for it in ET.fromstring(content).iter("item"):
        title, link = _text(it.findtext("title")), (it.findtext("link") or "").strip()
        if not title or not link.startswith("http"):
            continue
        src = source
        if google:  # "Headline - Publisher"
            src = _text(it.findtext("source")) or None
            if src and title.endswith(f" - {src}"):
                title = title[: -len(src) - 3]
        out.append({
            "title": title,
            "link": link,
            "source": src or urlparse(link).netloc.removeprefix("www."),
            "published": _ts(it.findtext("pubDate")),
            "summary": "" if google else _text(it.findtext("description"), 220),
            "image": None if google else _image(it),
        })
    return out


def _fetch(url: str, source: Optional[str], google: bool = False) -> list[dict]:
    try:
        r = requests.get(url, headers=UA, timeout=12)
        r.raise_for_status()
        return _parse(r.content, source, google)
    except Exception as exc:  # noqa: BLE001 - one bad feed must not break the page
        log.info("news feed failed %s: %s", url, exc)
        return []


def _feed(key: str) -> list[dict]:
    source, url = FEEDS[key]
    return _cached(f"news:{key}", 600, lambda: _fetch(url, source))


def _merge(lists: list[list[dict]], limit: int) -> list[dict]:
    seen, out = set(), []
    for n in sorted((n for lst in lists for n in lst), key=lambda n: n["published"] or 0, reverse=True):
        key = re.sub(r"\W+", "", n["title"].lower())[:60]
        if key in seen:
            continue
        seen.add(key)
        out.append(n)
    return out[:limit]


def get_news(category: str = "markets", limit: int = 40) -> dict:
    if category == "all":
        keys = list(FEEDS)
    elif category in CATEGORIES:
        keys = CATEGORIES[category][1]
    else:
        raise KeyError(category)
    with ThreadPoolExecutor(max_workers=len(keys)) as ex:
        lists = list(ex.map(_feed, keys))
    return {
        "category": category,
        "categories": [{"key": k, "label": v[0]} for k, v in CATEGORIES.items()],
        "items": _merge(lists, limit),
    }


def company_news(name: str, symbol: Optional[str] = None, limit: int = 20) -> dict:
    """Recent news about one company from Google News (India edition)."""
    clean = re.sub(r"\b(ltd|limited|ltd\.)\b\.?", "", name or "", flags=re.I).strip(" .") or symbol or ""
    if not clean:
        return {"query": "", "items": []}
    q = f'"{clean}" (share OR stock OR NSE OR BSE OR Sensex OR Nifty) -NYSE -Nasdaq'
    url = f"https://news.google.com/rss/search?q={quote_plus(q)}&hl=en-IN&gl=IN&ceid=IN:en"
    items = _cached(f"cnews:{clean.lower()}", 900, lambda: _fetch(url, None, google=True))
    return {"query": clean, "items": _merge([items], limit)}
