"""
NSE India public website endpoints (no login).

Used for: symbol autocomplete, quote metadata (ISIN, industry), shareholding
master (promoter vs public %) and promoter pledge data.

NSE protects its site with cookies/anti-bot checks. This provider performs only
a normal homepage visit to obtain session cookies (what any browser does) and
never attempts to defeat bot protection. If NSE refuses the request, the data is
reported as unavailable from NSE.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from utils.financial_utils import num
from utils.http_client import AccessRestricted, FetchError, HttpClient
from utils.logger import get_logger

log = get_logger(__name__)

BASE = "https://www.nseindia.com"
SOURCE = "NSE India (nseindia.com)"


class NSEProvider:
    name = SOURCE

    def __init__(self):
        self.http = HttpClient({"Referer": BASE + "/", "Accept": "application/json, text/plain, */*"})
        self._warmed = False
        self.restricted = False

    def _warm(self) -> None:
        if self._warmed or self.restricted:
            return
        try:
            self.http.get(BASE, use_cache=False)
            self._warmed = True
        except AccessRestricted as exc:
            self.restricted = True
            log.info("NSE access restricted: %s", exc)
        except FetchError as exc:
            log.info("NSE homepage failed: %s", exc)

    def _api(self, path: str, params: dict, ttl: float = 12) -> Optional[object]:
        if self.restricted:
            return None
        self._warm()
        if self.restricted:
            return None
        try:
            return self.http.get(BASE + path, params=params, as_json=True, ttl_hours=ttl)
        except AccessRestricted as exc:
            self.restricted = True
            log.info("NSE API restricted (%s): %s", path, exc)
        except FetchError as exc:
            log.info("NSE API failed (%s): %s", path, exc)
        return None

    def search(self, query: str) -> list[dict]:
        data = self._api("/api/search/autocomplete", {"q": query}, ttl=24)
        out = []
        for s in (data or {}).get("symbols", []) if isinstance(data, dict) else []:
            if s.get("result_sub_type") not in (None, "equity") and s.get("activeSeries") is None:
                continue
            sym = s.get("symbol")
            if not sym:
                continue
            out.append({"name": s.get("symbol_info") or sym, "nse_symbol": sym, "source": SOURCE})
        return out

    def quote(self, symbol: str) -> dict:
        data = self._api("/api/quote-equity", {"symbol": symbol}, ttl=4)
        if not isinstance(data, dict) or "info" not in data:
            return {}
        info = data.get("info", {})
        ind = data.get("industryInfo", {}) or {}
        meta = data.get("metadata", {}) or {}
        pi = data.get("priceInfo", {}) or {}
        whl = pi.get("weekHighLow", {}) or {}
        return {
            "name": info.get("companyName"),
            "isin": info.get("isin") or meta.get("isin"),
            "sector": ind.get("sector") or ind.get("macro"),
            "industry": ind.get("basicIndustry") or ind.get("industry") or meta.get("industry"),
            "price": num(pi.get("lastPrice")),
            "prev_close": num(pi.get("previousClose")),
            "high_52w": num(whl.get("max")),
            "low_52w": num(whl.get("min")),
            "last_update": meta.get("lastUpdateTime"),
            "issued_size": num((data.get("securityInfo") or {}).get("issuedSize")),
        }

    def shareholding_master(self, symbol: str) -> pd.DataFrame:
        """Quarterly promoter & public % from NSE shareholding master."""
        data = self._api("/api/corporate-share-holdings-master", {"index": "equities", "symbol": symbol})
        rows = []
        for r in data if isinstance(data, list) else []:
            d = pd.to_datetime(r.get("date"), errors="coerce", dayfirst=True)
            if pd.isna(d):
                continue
            rows.append({"date": d, "promoters": num(r.get("pr_and_prgrp")),
                         "public": num(r.get("public_val")),
                         "employee_trusts": num(r.get("employeeTrusts"))})
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows).drop_duplicates("date").set_index("date").sort_index()
        return df

    def pledge(self, symbol: str) -> pd.DataFrame:
        """Promoter pledge history: pledged % of promoter holding and of total shares."""
        data = self._api("/api/corporate-pledgedata", {"index": "equities", "symbol": symbol})
        recs = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        rows = []
        for r in recs:
            if not isinstance(r, dict):
                continue
            date_val = r.get("shp") or r.get("date") or r.get("broadcastDt")
            d = pd.to_datetime(date_val, errors="coerce", dayfirst=True)
            if pd.isna(d):
                continue
            rows.append({
                "date": d,
                "pledged_pct_of_promoter": num(r.get("percPromoterShares")),
                "pledged_pct_of_total": num(r.get("percTotShares")),
                "promoter_holding_pct": num(r.get("percPromoterHolding")),
            })
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows).sort_values("date").drop_duplicates("date", keep="last").set_index("date")
        return df
