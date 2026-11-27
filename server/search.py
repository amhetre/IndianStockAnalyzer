"""
Fast type-ahead search for the web UI.

Queries Screener.in and Yahoo Finance in parallel with short timeouts and no
per-host throttling (the analysis pipeline keeps its polite throttled client).
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, wait

import requests

from config import NETWORK
from utils.logger import get_logger

log = get_logger("server.search")

_session = requests.Session()
_session.headers.update({"User-Agent": NETWORK.user_agent, "Accept-Language": "en-IN,en;q=0.9"})
_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="search")
TIMEOUT = 4
NON_EQUITY = re.compile(r"\bETF\b|BEES\b|IETF$|\bIndex Fund\b|\bFund of Fund", re.I)


def _screener(q: str) -> list[dict]:
    r = _session.get("https://www.screener.in/api/company/search/", params={"q": q, "v": 3, "fts": 1},
                     headers={"Referer": "https://www.screener.in/"}, timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for row in r.json() or []:
        m = re.match(r"^/company/([^/]+)/", row.get("url") or "")
        if not m:
            continue
        code = m.group(1)
        out.append({"name": row.get("name", code), "screener_url": "https://www.screener.in" + row["url"],
                    "nse_symbol": None if code.isdigit() else code,
                    "bse_code": code if code.isdigit() else None})
    return out


def _yahoo(q: str) -> list[dict]:
    r = _session.get("https://query2.finance.yahoo.com/v1/finance/search",
                     params={"q": q, "quotesCount": 10, "newsCount": 0}, timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for x in r.json().get("quotes", []):
        sym = x.get("symbol", "")
        if not sym.endswith((".NS", ".BO")) or x.get("quoteType") not in (None, "EQUITY"):
            continue
        base = sym[:-3]
        out.append({"name": x.get("longname") or x.get("shortname") or sym, "yahoo_ticker": sym,
                    "nse_symbol": base if sym.endswith(".NS") else None,
                    "bse_code": base if sym.endswith(".BO") and base.isdigit() else None,
                    "exchange": "NSE" if sym.endswith(".NS") else "BSE"})
    return out


def search(q: str, limit: int = 10) -> list[dict]:
    futs = {_pool.submit(fn, q): name for fn, name in ((_screener, "screener"), (_yahoo, "yahoo"))}
    done, _ = wait(futs, timeout=TIMEOUT + 1)
    merged: dict[str, dict] = {}
    order: list[str] = []
    # Screener first: its names and symbols are the cleanest for Indian equities.
    for fut in sorted(done, key=lambda f: futs[f] != "screener"):
        try:
            rows = fut.result()
        except Exception as exc:  # noqa: BLE001
            log.info("%s search failed for %r: %s", futs[fut], q, exc)
            continue
        for c in rows:
            # Yahoo BSE rows with a text symbol duplicate the NSE listing – skip them
            if c.get("yahoo_ticker", "").endswith(".BO") and not c.get("bse_code"):
                key = c["yahoo_ticker"][:-3].upper()
                if key in merged:
                    continue
            key = (c.get("nse_symbol") or c.get("bse_code") or c.get("yahoo_ticker") or c["name"]).upper()
            if key in merged:
                for k, v in c.items():
                    if v and not merged[key].get(k):
                        merged[key][k] = v
            else:
                merged[key] = dict(c)
                order.append(key)
    # Stocks only: drop ETFs / index funds / gold & silver BeES etc.
    out = [merged[k] for k in order if not NON_EQUITY.search(merged[k]["name"])
           and not NON_EQUITY.search(merged[k].get("nse_symbol") or "")]
    for c in out:
        if not c.get("yahoo_ticker"):
            c["yahoo_ticker"] = f"{c['nse_symbol']}.NS" if c.get("nse_symbol") else (
                f"{c['bse_code']}.BO" if c.get("bse_code") else None)
        c.setdefault("exchange", "NSE" if c.get("nse_symbol") else "BSE")
    return out[:limit]
