"""
Screener.in public company pages (no login).

Parses: company identity (NSE/BSE codes, sector), top ratios, quarterly results,
annual P&L, balance sheet, cash flow, ratios, quarterly shareholding pattern and
the peer list. Optionally requests the public "schedules" breakdown used by the
page's expand (+) buttons to obtain cash, short/long-term borrowings and capex.

All Screener figures are in ₹ crore. Access is rate-limited and cached; if
Screener refuses access (403/429/CAPTCHA) nothing is bypassed – the provider
reports the failure and the manager falls back to other sources.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import quote_plus

import pandas as pd
from bs4 import BeautifulSoup

from data_providers.models import finalize_statement
from utils.financial_utils import is_num
from utils.http_client import AccessRestricted, FetchError, HttpClient
from utils.logger import get_logger

log = get_logger(__name__)

BASE = "https://www.screener.in"
SOURCE = "Screener.in"

PL_MAP = {
    "revenue": ["sales", "revenue"],
    "expenses": ["expenses"],
    "operating_profit": ["operating profit", "financing profit"],
    "other_income": ["other income"],
    "interest": ["interest"],
    "depreciation": ["depreciation"],
    "pbt": ["profit before tax"],
    "tax_pct": ["tax %"],
    "net_income": ["net profit"],
    "eps_basic": ["eps in rs", "eps"],
    "dividend_payout_pct": ["dividend payout %"],
    "gnpa_pct": ["gross npa %"],
    "nnpa_pct": ["net npa %"],
}
BS_MAP = {
    "equity_capital": ["equity capital", "share capital"],
    "reserves": ["reserves"],
    "deposits": ["deposits"],
    "total_debt": ["borrowings", "borrowing"],
    "other_liabilities": ["other liabilities"],
    "total_liabilities": ["total liabilities"],
    "fixed_assets": ["fixed assets", "net block"],
    "cwip": ["cwip", "capital work in progress"],
    "investments": ["investments"],
    "other_assets": ["other assets"],
    "total_assets": ["total assets"],
}
CF_MAP = {
    "cfo": ["cash from operating activity", "cash from operating activities"],
    "cfi": ["cash from investing activity", "cash from investing activities"],
    "cff": ["cash from financing activity", "cash from financing activities"],
    "net_cash_flow": ["net cash flow"],
}
SHP_MAP = {
    "promoters": ["promoters", "promoter"],
    "fii": ["fiis", "fii"],
    "dii": ["diis", "dii"],
    "government": ["government"],
    "public": ["public"],
    "others": ["others"],
    "num_shareholders": ["no. of shareholders"],
}


def _clean_label(text: str) -> str:
    t = (text or "").replace("\xa0", " ").replace("+", "").strip()
    return re.sub(r"\s+", " ", t)


def _parse_number(text: str) -> Optional[float]:
    t = (text or "").replace(",", "").replace("%", "").replace("\xa0", "").strip()
    if t in ("", "-", "--", "NA", "N/A"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _parse_period(label: str) -> Optional[pd.Timestamp]:
    try:
        ts = pd.to_datetime(label.strip(), format="%b %Y")
        return ts + pd.offsets.MonthEnd(0)
    except (ValueError, TypeError):
        return None


def parse_table(table) -> tuple[pd.DataFrame, dict]:
    """Return (DataFrame[label x period], ttm_values) from a Screener data-table."""
    if table is None:
        return pd.DataFrame(), {}
    head = table.find("thead")
    headers = [th.get_text(" ", strip=True) for th in (head.find_all("th") if head else [])]
    rows = {}
    ttm = {}
    body = table.find("tbody") or table
    for tr in body.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        label = _clean_label(cells[0].get_text(" ", strip=True))
        if not label:
            continue
        values = {}
        for i, c in enumerate(cells[1:], start=1):
            if i >= len(headers):
                break
            h = headers[i]
            v = _parse_number(c.get_text(" ", strip=True))
            if h.upper() == "TTM":
                ttm[label] = v
                continue
            ts = _parse_period(h)
            if ts is not None:
                values[ts] = v
        rows[label] = values
    df = pd.DataFrame(rows).T
    if not df.empty:
        df = df.reindex(sorted(df.columns), axis=1)
    return df, ttm


def _map_rows(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    out = {}
    if df.empty:
        return pd.DataFrame()
    labels = {lbl.lower(): lbl for lbl in df.index}
    for item, candidates in mapping.items():
        for cand in candidates:
            match = next((orig for low, orig in labels.items() if low == cand), None)
            if match is None:
                match = next((orig for low, orig in labels.items() if low.startswith(cand)), None)
            if match is not None:
                out[item] = pd.to_numeric(df.loc[match], errors="coerce")
                break
    return pd.DataFrame(out).T if out else pd.DataFrame()


def _map_ttm(ttm: dict, mapping: dict) -> dict:
    res = {}
    low = {k.lower(): v for k, v in ttm.items()}
    for item, cands in mapping.items():
        for c in cands:
            key = next((k for k in low if k == c or k.startswith(c)), None)
            if key is not None:
                res[item] = low[key]
                break
    return res


class ScreenerProvider:
    name = SOURCE

    def __init__(self):
        self.http = HttpClient({"Referer": BASE + "/"})

    # ------------------------------------------------------------------ search
    def search(self, query: str) -> list[dict]:
        try:
            data = self.http.get(f"{BASE}/api/company/search/",
                                 params={"q": query, "v": 3, "fts": 1}, as_json=True, ttl_hours=24)
        except (AccessRestricted, FetchError) as exc:
            log.info("Screener search failed for %r: %s", query, exc)
            return []
        out = []
        for row in data or []:
            url = row.get("url") or ""
            m = re.match(r"^/company/([^/]+)/", url)
            if not m:
                continue
            code = m.group(1)
            out.append({
                "name": row.get("name", code),
                "screener_url": BASE + url,
                "nse_symbol": None if code.isdigit() else code,
                "bse_code": code if code.isdigit() else None,
                "source": SOURCE,
            })
        return out

    # ------------------------------------------------------------------ company page
    def fetch_company(self, code: str, prefer_consolidated: bool = True) -> dict:
        """Fetch & parse the company page. `code` = NSE symbol or BSE code."""
        code = code.strip().upper()
        urls = ([f"{BASE}/company/{quote_plus(code)}/consolidated/", f"{BASE}/company/{quote_plus(code)}/"]
                if prefer_consolidated else
                [f"{BASE}/company/{quote_plus(code)}/", f"{BASE}/company/{quote_plus(code)}/consolidated/"])
        last_err = None
        for url in urls:
            try:
                html = self.http.get(url, ttl_hours=24)
            except AccessRestricted:
                raise
            except FetchError as exc:
                last_err = exc
                continue
            parsed = self.parse_company_html(html, url)
            if parsed.get("annual") is not None and not parsed["annual"].empty:
                return parsed
            last_err = FetchError(f"No financial tables found at {url}")
        raise FetchError(str(last_err) if last_err else f"Screener page not found for {code}")

    def parse_company_html(self, html: str, url: str) -> dict:
        soup = BeautifulSoup(html, "lxml")
        res: dict = {"url": url, "basis": "Consolidated" if "/consolidated/" in url else "Standalone"}
        h1 = soup.find("h1")
        res["name"] = h1.get_text(strip=True) if h1 else None
        info = soup.find(id="company-info")
        if info is not None:
            res["company_id"] = info.get("data-company-id")
            res["warehouse_id"] = info.get("data-warehouse-id")
        # Exchange codes from outbound links
        for a in soup.find_all("a", href=True):
            txt = a.get_text(" ", strip=True)
            if "bseindia.com" in a["href"] and "BSE" in txt:
                m = re.search(r"BSE:\s*([0-9A-Z]+)", txt)
                if m:
                    res["bse_code"] = m.group(1)
            if "nseindia.com" in a["href"] and "NSE" in txt:
                m = re.search(r"NSE:\s*([A-Z0-9&\-_.]+)", txt)
                if m:
                    res["nse_symbol"] = m.group(1)
        # Sector / industry breadcrumbs in peers section
        for a in soup.select("a[title]"):
            title = (a.get("title") or "").strip().lower()
            if title in ("sector", "broad sector", "industry", "broad industry"):
                res.setdefault(title.replace(" ", "_"), a.get_text(strip=True))
        # Top ratios
        top = {}
        for li in soup.select("#top-ratios li"):
            name_el = li.find(class_="name")
            val_el = li.find(class_="value") or li.find(class_="number")
            if not name_el or not val_el:
                continue
            nm = name_el.get_text(" ", strip=True)
            nums = [n.get_text(strip=True) for n in li.select(".number")]
            if nm.lower().startswith("high / low") and len(nums) >= 2:
                top["high_52w"], top["low_52w"] = _parse_number(nums[0]), _parse_number(nums[1])
            else:
                top[nm] = _parse_number(nums[0]) if nums else _parse_number(val_el.get_text(" ", strip=True))
        res["top_ratios"] = top

        def section_table(sec_id, inner_id=None):
            sec = soup.find(id=sec_id)
            if sec is None:
                return None
            if inner_id:
                inner = sec.find(id=inner_id)
                if inner is not None:
                    return inner.find("table")
            return sec.find("table")

        q_df, q_ttm = parse_table(section_table("quarters"))
        pl_df, pl_ttm = parse_table(section_table("profit-loss"))
        bs_df, _ = parse_table(section_table("balance-sheet"))
        cf_df, _ = parse_table(section_table("cash-flow"))
        ratio_df, _ = parse_table(section_table("ratios"))
        shp_df, _ = parse_table(section_table("shareholding", "quarterly-shp"))
        res["raw"] = {"quarters": q_df, "profit_loss": pl_df, "balance_sheet": bs_df,
                      "cash_flow": cf_df, "ratios": ratio_df, "shareholding": shp_df}

        item_sources: dict = {}
        annual = pd.concat([_map_rows(pl_df, PL_MAP), _map_rows(bs_df, BS_MAP), _map_rows(cf_df, CF_MAP)])
        quarterly = _map_rows(q_df, PL_MAP)
        for df_, label in ((annual, "annual"), (quarterly, "quarterly")):
            if df_.empty:
                continue
            # Tax amount from PBT x Tax %
            if "pbt" in df_.index and "tax_pct" in df_.index:
                df_.loc["tax"] = df_.loc["pbt"] * df_.loc["tax_pct"] / 100.0
                item_sources[f"{label}:tax"] = "Derived: Tax = Profit before tax x Tax % (Screener)"
        if not annual.empty and "equity_capital" in annual.index and "reserves" in annual.index:
            annual.loc["total_equity"] = annual.loc["equity_capital"] + annual.loc["reserves"]
            item_sources["annual:total_equity"] = "Derived: Equity capital + Reserves (Screener)"
        res["annual"] = finalize_statement(annual, item_sources, "annual")
        res["quarterly"] = finalize_statement(quarterly, item_sources, "quarterly")
        res["item_sources"] = item_sources
        res["ttm"] = _map_ttm(pl_ttm, PL_MAP) or _map_ttm(q_ttm, PL_MAP)
        res["ratios"] = ratio_df
        # Shareholding (%)
        shp = _map_rows(shp_df, SHP_MAP)
        res["shareholding"] = shp.T.sort_index() if not shp.empty else pd.DataFrame()
        # Bank asset quality (quarterly)
        bank_rows = [r for r in ("gnpa_pct", "nnpa_pct") if not quarterly.empty and r in quarterly.index]
        res["bank_metrics"] = quarterly.loc[bank_rows].T.sort_index() if bank_rows else pd.DataFrame()
        return res

    # ------------------------------------------------------------------ schedules (+ breakdowns)
    def fetch_schedule(self, company_id: str, parent: str, section: str, consolidated: bool) -> pd.DataFrame:
        """Breakdown rows behind a '+' button. Returns DataFrame[label x period] or empty."""
        if not company_id:
            return pd.DataFrame()
        url = f"{BASE}/api/company/{company_id}/schedules/"
        for cons in (("true", "") if consolidated else ("",)):
            try:
                data = self.http.get(url, params={"parent": parent, "section": section, "consolidated": cons},
                                     as_json=True, ttl_hours=24)
            except (AccessRestricted, FetchError) as exc:
                log.info("Screener schedule %s/%s failed: %s", section, parent, exc)
                continue
            if not isinstance(data, dict) or not data:
                continue
            rows = {}
            for label, vals in data.items():
                if not isinstance(vals, dict):
                    continue
                parsed = {}
                for k, v in vals.items():
                    ts = _parse_period(k)
                    if ts is not None:
                        parsed[ts] = _parse_number(str(v))
                if parsed:
                    rows[_clean_label(label)] = parsed
            if rows:
                return pd.DataFrame(rows).T.reindex(sorted({c for r in rows.values() for c in r}), axis=1)
        return pd.DataFrame()

    def enrich_with_schedules(self, parsed: dict) -> None:
        """Add cash, short/long-term debt and capex from schedules when obtainable."""
        cid = parsed.get("company_id")
        consolidated = parsed.get("basis") == "Consolidated"
        annual: pd.DataFrame = parsed.get("annual")
        if not cid or annual is None or annual.empty:
            return
        srcs = parsed.setdefault("item_sources", {})

        def put(item, s, note):
            s = s.reindex(annual.columns)
            if s.notna().any():
                annual.loc[item] = s
                srcs[f"annual:{item}"] = note

        def find(df, *keys):
            for lbl in df.index:
                low = lbl.lower()
                if all(k in low for k in keys):
                    return pd.to_numeric(df.loc[lbl], errors="coerce")
            return None

        oa = self.fetch_schedule(cid, "Other Assets", "balance-sheet", consolidated)
        if not oa.empty:
            s = find(oa, "cash")
            if s is not None:
                put("cash", s, "Screener schedule: Other Assets > Cash Equivalents")
        br = self.fetch_schedule(cid, "Borrowings", "balance-sheet", consolidated)
        if not br.empty:
            lt = find(br, "long term")
            st = find(br, "short term")
            ls = find(br, "lease")
            if lt is not None:
                put("long_term_debt", lt, "Screener schedule: Borrowings > Long term")
            if st is not None:
                put("short_term_debt", st, "Screener schedule: Borrowings > Short term")
            if ls is not None:
                put("lease_liabilities", ls, "Screener schedule: Borrowings > Lease liabilities")
        ci = self.fetch_schedule(cid, "Cash from Investing Activity", "cash-flow", consolidated)
        if not ci.empty:
            capex = find(ci, "fixed assets purchased")
            if capex is not None:
                put("capex", capex.abs(), "Screener schedule: Investing > Fixed assets purchased")
        parsed["annual"] = finalize_statement(annual, srcs, "annual")

    # ------------------------------------------------------------------ peers
    def fetch_peers(self, warehouse_id: str, self_symbol: Optional[str]) -> list[dict]:
        if not warehouse_id:
            return []
        try:
            html = self.http.get(f"{BASE}/api/company/{warehouse_id}/peers/", ttl_hours=24)
        except (AccessRestricted, FetchError) as exc:
            log.info("Screener peers failed: %s", exc)
            return []
        soup = BeautifulSoup(html, "lxml")
        peers = []
        for a in soup.select("table a[href^='/company/']"):
            m = re.match(r"^/company/([^/]+)/", a["href"])
            if not m:
                continue
            code = m.group(1).upper()
            if self_symbol and code == self_symbol.upper():
                continue
            if any(p["symbol"] == code for p in peers):
                continue
            peers.append({"name": a.get_text(strip=True), "symbol": code, "source": "Screener.in peer list"})
        return peers

    @staticmethod
    def top_ratio(parsed: dict, *names: str) -> Optional[float]:
        top = parsed.get("top_ratios", {})
        for n in names:
            for k, v in top.items():
                if k.lower().startswith(n.lower()) and is_num(v):
                    return float(v)
        return None
