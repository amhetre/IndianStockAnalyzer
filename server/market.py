"""
Live market overview: NIFTY 50 / SENSEX quotes and intraday charts, NIFTY 50
top gainers / losers, and current + upcoming IPOs.

NSE's public website JSON is tried first (it is what nseindia.com itself uses);
Yahoo Finance (yfinance) is the fallback for prices. Results are kept in a
short in-memory cache so the home page can poll without hammering sources.
"""
from __future__ import annotations

import math
import re
import threading
import time
from typing import Any, Callable, Optional

from utils.http_client import AccessRestricted, FetchError, HttpClient
from utils.logger import get_logger

log = get_logger("server.market")

try:
    import yfinance as yf
except Exception:  # noqa: BLE001
    yf = None

NSE = "https://www.nseindia.com"

INDICES = {
    "NIFTY": {"name": "NIFTY 50", "yahoo": "^NSEI"},
    "SENSEX": {"name": "SENSEX", "yahoo": "^BSESN"},
}

# Fallback constituent list used only when NSE's live index API is unreachable.
NIFTY50_FALLBACK = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO", "BAJFINANCE",
    "BAJAJFINSV", "BEL", "BHARTIARTL", "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
    "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO", "HINDUNILVR", "ICICIBANK", "INDIGO",
    "INFY", "ITC", "JIOFIN", "JSWSTEEL", "KOTAKBANK", "LT", "M&M", "MARUTI", "MAXHEALTH",
    "NESTLEIND", "NTPC", "ONGC", "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", "SHRIRAMFIN",
    "SUNPHARMA", "TATACONSUM", "TMPV", "TATASTEEL", "TCS", "TECHM", "TITAN", "TRENT",
    "ULTRACEMCO", "WIPRO",
]

_cache: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()


def _cached(key: str, ttl: float, producer: Callable[[], Any]) -> Any:
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    value = producer()
    with _lock:
        _cache[key] = (now, value)
    return value


def _f(x) -> Optional[float]:
    try:
        v = float(str(x).replace(",", ""))
        return None if math.isnan(v) or math.isinf(v) else v
    except (TypeError, ValueError):
        return None


class _NSE:
    """Minimal NSE JSON client with session cookies and no disk cache."""

    def __init__(self):
        self.http = HttpClient({"Referer": NSE + "/", "Accept": "application/json, text/plain, */*"})
        self._warmed_at = 0.0

    def get(self, path: str, params: Optional[dict] = None) -> Optional[Any]:
        try:
            if time.time() - self._warmed_at > 600:
                self.http.get(NSE, use_cache=False)
                self._warmed_at = time.time()
            return self.http.get(NSE + path, params=params, as_json=True, use_cache=False)
        except (AccessRestricted, FetchError) as exc:
            log.info("NSE %s failed: %s", path, exc)
            self._warmed_at = 0.0
            return None


_nse = _NSE()


# ---------------------------------------------------------------- indices
def _index_from_yahoo(key: str) -> dict:
    meta = INDICES[key]
    out = {"key": key, "name": meta["name"], "last": None, "change": None, "pct": None,
           "prev_close": None, "open": None, "high": None, "low": None, "points": [], "source": "Yahoo Finance"}
    if yf is None:
        return out
    t = yf.Ticker(meta["yahoo"])
    try:
        hist = t.history(period="1d", interval="2m")
        if hist.empty:  # market holiday / pre-open: show last session
            hist = t.history(period="5d", interval="5m")
            if not hist.empty:
                last_day = hist.index[-1].date()
                hist = hist[hist.index.date == last_day]
        out["points"] = [{"t": ts.isoformat(), "v": round(float(v), 2)} for ts, v in hist["Close"].items()
                         if _f(v) is not None]
        if not hist.empty:
            out["open"] = _f(hist["Open"].iloc[0])
            out["high"] = _f(hist["High"].max())
            out["low"] = _f(hist["Low"].min())
            out["last"] = _f(hist["Close"].iloc[-1])
    except Exception as exc:  # noqa: BLE001
        log.info("Yahoo intraday failed for %s: %s", key, exc)
    try:
        daily = t.history(period="10d", interval="1d")
        if len(daily) >= 2:
            last_day = out["points"][-1]["t"][:10] if out["points"] else None
            closes = daily["Close"]
            # previous close = close of the session before the one we're charting
            prev_idx = -2 if (last_day is None or str(closes.index[-1].date()) == last_day) else -1
            out["prev_close"] = _f(closes.iloc[prev_idx])
            if out["last"] is None:
                out["last"] = _f(closes.iloc[-1])
    except Exception as exc:  # noqa: BLE001
        log.info("Yahoo daily failed for %s: %s", key, exc)
    if out["last"] is not None and out["prev_close"]:
        out["change"] = round(out["last"] - out["prev_close"], 2)
        out["pct"] = round(out["change"] / out["prev_close"] * 100, 2)
    return out


def get_indices() -> list[dict]:
    return _cached("indices", 60, lambda: [_index_from_yahoo(k) for k in INDICES])


# ---------------------------------------------------------------- movers
def _movers_from_nse() -> Optional[list[dict]]:
    data = _nse.get("/api/equity-stockIndices", {"index": "NIFTY 50"})
    if not isinstance(data, dict) or not data.get("data"):
        return None
    rows = []
    for r in data["data"]:
        sym = r.get("symbol")
        if not sym or sym == "NIFTY 50" or r.get("priority") == 1:
            continue
        rows.append({
            "symbol": sym,
            "name": (r.get("meta") or {}).get("companyName") or sym,
            "last": _f(r.get("lastPrice")), "change": _f(r.get("change")), "pct": _f(r.get("pChange")),
            "volume": _f(r.get("totalTradedVolume")),
        })
    return rows or None


def _movers_from_yahoo() -> list[dict]:
    if yf is None:
        return []
    tickers = [f"{s}.NS" for s in NIFTY50_FALLBACK]
    try:
        df = yf.download(tickers, period="5d", interval="1d", progress=False, group_by="ticker",
                         auto_adjust=False, threads=True)
    except Exception as exc:  # noqa: BLE001
        log.info("Yahoo movers download failed: %s", exc)
        return []
    rows = []
    for sym, tk in zip(NIFTY50_FALLBACK, tickers):
        try:
            closes = df[tk]["Close"].dropna()
            if len(closes) < 2:
                continue
            last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
            vol = _f(df[tk]["Volume"].dropna().iloc[-1])
            rows.append({"symbol": sym, "name": sym, "last": round(last, 2),
                         "change": round(last - prev, 2), "pct": round((last - prev) / prev * 100, 2),
                         "volume": vol})
        except Exception:  # noqa: BLE001
            continue
    return rows


def get_movers(n: int = 10) -> dict:
    def produce():
        rows = _movers_from_nse()
        source = "NSE India"
        if not rows:
            rows, source = _movers_from_yahoo(), "Yahoo Finance"
        rows = [r for r in rows if r["pct"] is not None]
        rows.sort(key=lambda r: r["pct"], reverse=True)
        adv = sum(1 for r in rows if r["pct"] > 0)
        dec = sum(1 for r in rows if r["pct"] < 0)
        return {"source": source, "gainers": rows[:n],
                "losers": sorted(rows, key=lambda r: r["pct"])[:n],
                "advances": adv, "declines": dec, "unchanged": len(rows) - adv - dec}
    return _cached("movers", 60, produce)


# ---------------------------------------------------------------- IPOs
def _norm_ipo(r: dict, status: str) -> dict:
    return {
        "symbol": r.get("symbol"),
        "name": r.get("companyName") or r.get("symbol"),
        "series": r.get("series"),
        "start": r.get("issueStartDate"),
        "end": r.get("issueEndDate"),
        "price_band": r.get("issuePrice") or r.get("priceBand"),
        "issue_size": r.get("issueSize"),
        "subscription": r.get("noOfTime") or r.get("noOfTimesSubscribed"),
        "status": status,
        "is_sme": (r.get("series") or "").upper() == "SME",
    }


GMP_URL = "https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/"
GMP_SOURCE = "IPO Watch (ipowatch.in)"
_gmp_http = HttpClient()


def _ipo_key(name: str) -> str:
    n = re.sub(r"\b(limited|ltd|ipo|india|the)\b|[^a-z0-9]", " ", (name or "").lower())
    return " ".join(n.split()[:2])


def _rupees(text: str) -> Optional[float]:
    m = re.search(r"([-+]?)\s*₹?\s*([\d,]+(?:\.\d+)?)", text or "")
    if not m:
        return None
    v = float(m.group(2).replace(",", ""))
    return -v if m.group(1) == "-" else v


def _band_top(text: str) -> Optional[float]:
    nums = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", text or "")]
    return max(nums) if nums else None


def _trend(sym: str) -> str:
    return {"↑": "up", "↓": "down"}.get((sym or "").strip(), "flat")


def _fetch_gmp() -> dict:
    """Grey-market premium table from ipowatch.in (unofficial, informal market)."""
    from bs4 import BeautifulSoup
    try:
        html = _gmp_http.get(GMP_URL, use_cache=False)
    except (AccessRestricted, FetchError) as exc:
        log.info("GMP fetch failed: %s", exc)
        return {"live": [], "listed": [], "ok": False}
    soup = BeautifulSoup(html, "lxml")
    live, listed = [], []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        head = [c.get_text(" ", strip=True).lower() for c in rows[0].find_all(["td", "th"])]
        cells = [[c.get_text(" ", strip=True) for c in r.find_all(["td", "th"])] for r in rows[1:]]
        slugs = []
        for r in rows[1:]:
            a = r.find("a", href=True)
            m = re.match(r"^(?:https?://(?:www\.)?ipowatch\.in)?/([a-z0-9-]+)/?$", a["href"]) if a else None
            slugs.append(m.group(1) if m else None)
        if "ipo gmp" in head and "price band" in head:
            ix = {h: i for i, h in enumerate(head)}
            for c, slug in zip(cells, slugs):
                if len(c) < len(head):
                    continue
                gmp = _rupees(c[ix["ipo gmp"]])
                top = _band_top(c[ix["price band"]])
                live.append({
                    "name": c[ix["ipo name"]], "slug": slug, "gmp": gmp, "price_band": c[ix["price band"]],
                    "gmp_pct": round(gmp / top * 100, 2) if gmp is not None and top else None,
                    "est_listing": (gmp + top) if gmp is not None and top else None,
                    "trend": _trend(c[ix.get("trend", 0)]) if "trend" in ix else "flat",
                    "dates": c[ix.get("date", 0)] if "date" in ix else None,
                    "type": c[ix["type"]] if "type" in ix else None,
                    "status": c[ix["status"]] if "status" in ix else None,
                    "updated": c[ix["last updated"]] if "last updated" in ix else None,
                })
        elif head[:1] == ["ipo name"] and "listing price" in head and "issue price" in head:
            ix = {h: i for i, h in enumerate(head)}
            for c, slug in list(zip(cells, slugs))[:10]:
                if len(c) < len(head):
                    continue
                issue, lp = _rupees(c[ix["issue price"]]), _rupees(c[ix["listing price"]])
                listed.append({
                    "name": c[ix["ipo name"]], "slug": slug, "type": c[ix.get("type", 1)],
                    "issue_price": issue, "gmp": _rupees(c[ix["gmp"]]), "listing_price": lp,
                    "listing_gain_pct": round((lp - issue) / issue * 100, 2) if issue and lp is not None else None,
                })
    return {"live": live, "listed": listed, "ok": bool(live or listed)}


def get_ipos() -> dict:
    def produce():
        current = _nse.get("/api/ipo-current-issue")
        upcoming = _nse.get("/api/all-upcoming-issues", {"category": "ipo"})
        gmp = _fetch_gmp()
        out_current = [_norm_ipo(r, "Open") for r in (current or []) if isinstance(r, dict)] \
            if isinstance(current, list) else []
        out_upcoming = [_norm_ipo(r, "Upcoming") for r in (upcoming or []) if isinstance(r, dict)] \
            if isinstance(upcoming, list) else []
        # NSE sometimes returns open issues inside "upcoming" too – dedupe
        seen = {i["symbol"] for i in out_current}
        out_upcoming = [i for i in out_upcoming if i["symbol"] not in seen]

        # Attach GMP; add IPOs that only the GMP site knows about (e.g. BSE SME, not-yet-on-NSE)
        by_key = {_ipo_key(g["name"]): g for g in gmp["live"]}
        used = set()
        for ipo in out_current + out_upcoming:
            g = by_key.get(_ipo_key(ipo["name"]))
            if g:
                used.add(_ipo_key(g["name"]))
                ipo.update(slug=g["slug"], gmp=g["gmp"], gmp_pct=g["gmp_pct"], est_listing=g["est_listing"],
                           gmp_trend=g["trend"], gmp_updated=g["updated"])
        for k, g in by_key.items():
            if k in used:
                continue
            status = (g["status"] or "").lower()
            if status not in ("open", "upcoming"):
                continue
            start, _, end = (g["dates"] or "").partition(" - ")
            row = {"symbol": None, "slug": g["slug"], "name": g["name"], "series": g["type"], "start": start or None,
                   "end": end or None, "price_band": g["price_band"], "issue_size": None, "subscription": None,
                   "status": status.title(), "is_sme": "main" not in (g["type"] or "").lower(),
                   "exchange": g["type"], "gmp": g["gmp"], "gmp_pct": g["gmp_pct"],
                   "est_listing": g["est_listing"], "gmp_trend": g["trend"], "gmp_updated": g["updated"]}
            (out_current if status == "open" else out_upcoming).append(row)
        ok = current is not None or upcoming is not None or gmp["ok"]
        return {"source": "NSE India", "gmp_source": GMP_SOURCE if gmp["ok"] else None, "available": ok,
                "current": out_current, "upcoming": out_upcoming, "recently_listed": gmp["listed"]}
    return _cached("ipos", 600, produce)
