"""
Provider manager: resolves the company and assembles a single, consistent
CompanyData object from the available providers.

Source priority (each dataset comes from ONE primary source so figures are not mixed):
* Price / CMP / history / beta inputs : Yahoo Finance -> NSE quote (fallback)
* Financial statements               : Screener.in (consolidated preferred) -> Yahoo Finance
* Shareholding pattern               : Screener.in quarterly -> NSE shareholding master
* Promoter pledge                    : NSE pledge data
* Peers                              : Screener.in peer list -> configured fallback list

New providers can be added by implementing the same small method set
(search / get_info / statements ...) and registering them here.
"""
from __future__ import annotations

import re
import sys
from typing import Optional

import pandas as pd

from config import FALLBACK_PEER_KEYWORDS, FALLBACK_PEERS, SECTOR_KEYWORDS, SETTINGS
from data_providers.models import CompanyData, CompanyIdentity, finalize_statement
from data_providers.nse_provider import NSEProvider
from data_providers.screener_provider import ScreenerProvider
from data_providers.yahoo_provider import YahooProvider
from utils.financial_utils import is_num, num
from utils.http_client import AccessRestricted, FetchError
from utils.logger import get_logger

log = get_logger(__name__)


class AmbiguousCompany(Exception):
    def __init__(self, query: str, candidates: list[dict]):
        super().__init__(f"Multiple companies match '{query}'")
        self.query = query
        self.candidates = candidates


class CompanyNotFound(Exception):
    pass


def classify_sector(*texts: Optional[str]) -> str:
    blob = " | ".join(t.lower() for t in texts if t)
    if not blob:
        return "other"
    order = ["insurance", "bank", "nbfc", "it_services", "real_estate", "infrastructure", "manufacturing"]
    for cls in order:
        for kw in SECTOR_KEYWORDS[cls]:
            if kw in blob:
                if cls == "bank" and ("investment bank" in blob):
                    continue
                return cls
    return "other"


def _norm_name(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\b(limited|ltd|ltd\.|the|inc|co|company|corporation|corp)\b", " ", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def _month_end(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    df = df.copy()
    df.columns = [pd.Timestamp(c) + pd.offsets.MonthEnd(0) for c in df.columns]
    df = df.loc[:, ~pd.Index(df.columns).duplicated(keep="last")]
    return df.reindex(sorted(df.columns), axis=1)


def _drop_interim_annual_columns(data: CompanyData) -> pd.DataFrame:
    """Remove trailing annual columns that carry no revenue and no net profit.

    Screener/Yahoo sometimes append a half-year balance sheet (e.g. Sep 2026) to the
    annual statements. Treating it as the latest financial year makes every
    income-based ratio (ROE, ROCE, margins, EPS growth) 'Unavailable'.
    """
    a = data.annual
    income_rows = [r for r in ("revenue", "net_income") if r in a.index]
    if not income_rows:
        return a
    has_income = a.loc[income_rows].apply(pd.to_numeric, errors="coerce").notna().any(axis=0)
    dropped = []
    while len(a.columns) > 1 and not has_income[a.columns[-1]]:
        dropped.append(a.columns[-1])
        a = a.iloc[:, :-1]
    if dropped:
        labels = ", ".join(str(pd.Timestamp(c).date()) for c in dropped)
        data.warn(f"Interim balance-sheet-only period(s) {labels} excluded from annual statements; "
                  f"ratios use the latest full financial year ({pd.Timestamp(a.columns[-1]).date()}).")
    return a


class ProviderManager:
    def __init__(self, yahoo: Optional[YahooProvider] = None, screener: Optional[ScreenerProvider] = None,
                 nse: Optional[NSEProvider] = None, use_nse: bool = True, use_screener: bool = True):
        self.yahoo = yahoo or YahooProvider()
        self.screener = screener if screener is not None else (ScreenerProvider() if use_screener else None)
        self.nse = nse if nse is not None else (NSEProvider() if use_nse else None)

    # ================================================================== resolution
    def resolve(self, query: str, exchange: Optional[str] = None) -> CompanyIdentity:
        q = query.strip()
        if not q:
            raise CompanyNotFound("Empty company name / symbol")
        exchange = (exchange or "").upper() or None

        # 1. Explicit Yahoo ticker
        if q.upper().endswith((".NS", ".BO")):
            ident = self._identity_from_ticker(q.upper(), "Yahoo ticker supplied")
            if ident:
                return ident
            raise CompanyNotFound(f"Yahoo ticker {q} returned no data")

        # 2. Symbol-like input (no spaces): try exact NSE symbol / BSE code first
        if re.fullmatch(r"[A-Za-z0-9&\-_.]{1,20}", q):
            sym = q.upper()
            tickers = []
            if sym.isdigit():
                tickers = [f"{sym}.BO"]
            elif exchange == "BSE":
                tickers = [f"{sym}.BO", f"{sym}.NS"]
            else:
                tickers = [f"{sym}.NS", f"{sym}.BO"]
            for t in tickers:
                ident = self._identity_from_ticker(t, "Exact exchange symbol")
                if ident:
                    return ident
            # Screener exact code (works even if Yahoo is down)
            if self.screener is not None:
                try:
                    parsed = self.screener.fetch_company(sym, SETTINGS.prefer_consolidated)
                    return CompanyIdentity(
                        name=parsed.get("name") or sym,
                        nse_symbol=parsed.get("nse_symbol") or (None if sym.isdigit() else sym),
                        bse_code=parsed.get("bse_code") or (sym if sym.isdigit() else None),
                        yahoo_ticker=(f"{parsed['nse_symbol']}.NS" if parsed.get("nse_symbol") else
                                      (f"{parsed['bse_code']}.BO" if parsed.get("bse_code") else None)),
                        exchange="NSE" if parsed.get("nse_symbol") else "BSE",
                        screener_url=parsed.get("url"), resolved_by="Exact Screener code")
                except (AccessRestricted, FetchError) as exc:
                    log.info("Screener exact lookup failed for %s: %s", sym, exc)

        # 3. Name search across providers
        candidates = self.search_candidates(q)
        if exchange == "NSE":
            candidates = [c for c in candidates if c.get("nse_symbol")] or candidates
        elif exchange == "BSE":
            candidates = [c for c in candidates if c.get("bse_code") or (c.get("yahoo_ticker") or "").endswith(".BO")] or candidates
        if not candidates:
            raise CompanyNotFound(
                f"No Indian listed company found for '{q}'. Check spelling, or pass the NSE symbol "
                f"(e.g. RELIANCE) or Yahoo ticker (e.g. RELIANCE.NS). Data sources may also be unreachable – see logs/analyzer.log.")
        nq = _norm_name(q)
        exact = [c for c in candidates if _norm_name(c["name"]) == nq or (c.get("nse_symbol") or "").upper() == q.upper()]
        if len(exact) == 1:
            return self._identity_from_candidate(exact[0], "Exact name match")
        if len(candidates) == 1:
            return self._identity_from_candidate(candidates[0], "Single search match")
        raise AmbiguousCompany(q, candidates[:10])

    def search_candidates(self, q: str) -> list[dict]:
        merged: dict[str, dict] = {}

        def add(c: dict):
            key = (c.get("nse_symbol") or c.get("bse_code") or c.get("yahoo_ticker") or c["name"]).upper()
            if key in merged:
                for k, v in c.items():
                    if v and not merged[key].get(k):
                        merged[key][k] = v
            else:
                merged[key] = dict(c)

        providers = [self.screener, self.yahoo, self.nse]
        for p in providers:
            if p is None:
                continue
            try:
                for c in p.search(q):
                    add(c)
            except Exception as exc:  # noqa: BLE001 – a failed provider must not stop resolution
                log.info("Search failed in %s: %s", getattr(p, "name", p), exc)
        return list(merged.values())

    def _identity_from_ticker(self, ticker: str, how: str) -> Optional[CompanyIdentity]:
        if not self.yahoo.available:
            return None
        info = self.yahoo.get_info(ticker)
        name = info.get("longName") or info.get("shortName")
        price = num(info.get("currentPrice")) or num(info.get("regularMarketPrice")) or num(info.get("fast_last_price"))
        if not name and price is None:
            return None
        base = ticker[:-3]
        return CompanyIdentity(
            name=name or base,
            nse_symbol=base if ticker.endswith(".NS") else None,
            bse_code=base if ticker.endswith(".BO") and base.isdigit() else None,
            yahoo_ticker=ticker,
            isin=info.get("isin"),
            sector=info.get("sector"), industry=info.get("industry"),
            exchange="NSE" if ticker.endswith(".NS") else "BSE",
            currency=info.get("currency") or "INR",
            resolved_by=how,
        )

    def _identity_from_candidate(self, c: dict, how: str) -> CompanyIdentity:
        ticker = c.get("yahoo_ticker") or (f"{c['nse_symbol']}.NS" if c.get("nse_symbol") else
                                           (f"{c['bse_code']}.BO" if c.get("bse_code") else None))
        return CompanyIdentity(
            name=c["name"], nse_symbol=c.get("nse_symbol"), bse_code=c.get("bse_code"),
            yahoo_ticker=ticker, exchange="NSE" if c.get("nse_symbol") else "BSE",
            screener_url=c.get("screener_url"), resolved_by=how)

    @staticmethod
    def choose_interactively(err: AmbiguousCompany) -> Optional[dict]:
        print(f"\nMultiple companies match '{err.query}':")
        for i, c in enumerate(err.candidates, 1):
            codes = ", ".join(x for x in [f"NSE: {c['nse_symbol']}" if c.get("nse_symbol") else "",
                                          f"BSE: {c['bse_code']}" if c.get("bse_code") else "",
                                          c.get("yahoo_ticker") or ""] if x)
            print(f"  {i}. {c['name']}  ({codes})")
        if not sys.stdin.isatty():
            print("Non-interactive session: re-run with the exact NSE symbol, or use --choice N.")
            return None
        while True:
            ans = input("Select a number (or press Enter to cancel): ").strip()
            if not ans:
                return None
            if ans.isdigit() and 1 <= int(ans) <= len(err.candidates):
                return err.candidates[int(ans) - 1]
            print("Invalid choice.")

    # ================================================================== loading
    def load(self, ident: CompanyIdentity, with_peers: bool = True, light: bool = False) -> CompanyData:
        data = CompanyData(identity=ident)
        ticker = ident.yahoo_ticker or (f"{ident.nse_symbol}.NS" if ident.nse_symbol else
                                        (f"{ident.bse_code}.BO" if ident.bse_code else None))
        ident.yahoo_ticker = ticker

        # ---------------- price / quote (Yahoo)
        info, hist = {}, pd.DataFrame()
        if ticker and self.yahoo.available:
            info = self.yahoo.get_info(ticker)
            hist = self.yahoo.get_history(ticker, "2y" if light else "10y")
            if not hist.empty or info:
                data.quote = self.yahoo.build_quote(ticker, info, hist)
                data.price_history = hist
                data.add_source("CMP & price history", self.yahoo.name,
                                f"https://finance.yahoo.com/quote/{ticker}",
                                hist.index[-1].date() if not hist.empty else "",
                                "OK" if not hist.empty else "Partial")
            else:
                data.add_source("CMP & price history", self.yahoo.name, "", "", "Failed",
                                "No data returned (network/rate-limit/unknown ticker)")
            ident.sector = ident.sector or info.get("sector")
            ident.industry = ident.industry or info.get("industry")
            ident.isin = ident.isin or info.get("isin")
            if not ident.name or ident.name == ident.nse_symbol:
                ident.name = info.get("longName") or ident.name
            ident.currency = info.get("currency") or ident.currency
            if not light:
                bench = self.yahoo.get_history("^NSEI", "5y")
                if not bench.empty:
                    data.benchmark_history = bench["Close"]
                    data.add_source("Benchmark (NIFTY 50) history", self.yahoo.name,
                                    "https://finance.yahoo.com/quote/%5ENSEI", bench.index[-1].date())

        # ---------------- Screener
        parsed = None
        code = ident.nse_symbol or ident.bse_code
        if self.screener is not None and code:
            try:
                parsed = self.screener.fetch_company(code, SETTINGS.prefer_consolidated)
                if not light:
                    try:
                        self.screener.enrich_with_schedules(parsed)
                    except Exception as exc:  # noqa: BLE001
                        log.info("Screener schedules failed: %s", exc)
                ident.screener_url = parsed.get("url")
                ident.screener_company_id = parsed.get("company_id")
                ident.screener_warehouse_id = parsed.get("warehouse_id")
                ident.bse_code = ident.bse_code or parsed.get("bse_code")
                ident.nse_symbol = ident.nse_symbol or parsed.get("nse_symbol")
                ident.sector = ident.sector or parsed.get("sector") or parsed.get("broad_sector")
                ident.industry = ident.industry or parsed.get("industry") or parsed.get("broad_industry")
                if not ident.name or ident.name.upper() == code.upper():
                    ident.name = parsed.get("name") or code
                data.source_ratios = dict(parsed.get("top_ratios", {}))
                data.source_ratios["_screener_industry"] = parsed.get("industry")
                data.source_ratios["_screener_sector"] = parsed.get("sector")
            except AccessRestricted as exc:
                data.add_source("Financial statements", "Screener.in", "", "", "Restricted", str(exc))
                log.warning("Screener access restricted: %s", exc)
            except FetchError as exc:
                data.add_source("Financial statements", "Screener.in", "", "", "Failed", str(exc))
                log.warning("Screener fetch failed: %s", exc)

        # ---------------- NSE metadata
        nse_q = {}
        if self.nse is not None and ident.nse_symbol and not light:
            nse_q = self.nse.quote(ident.nse_symbol)
            if nse_q:
                ident.isin = ident.isin or nse_q.get("isin")
                ident.industry = ident.industry or nse_q.get("industry")
                ident.sector = ident.sector or nse_q.get("sector")
                data.add_source("Company metadata (ISIN, industry)", self.nse.name,
                                f"https://www.nseindia.com/get-quotes/equity?symbol={ident.nse_symbol}",
                                nse_q.get("last_update", ""))
            else:
                data.add_source("Company metadata (ISIN, industry)", self.nse.name, "", "",
                                "Restricted" if self.nse.restricted else "Failed",
                                "NSE did not return data (access restricted or unavailable)")

        # Quote fallbacks
        if not is_num(data.quote.get("price")):
            fallback_price = nse_q.get("price") if nse_q else None
            src = self.nse.name if fallback_price else None
            if fallback_price is None and parsed:
                fallback_price = ScreenerProvider.top_ratio(parsed, "Current Price")
                src = "Screener.in (top ratios)"
            if fallback_price is not None:
                data.quote.update({"price": fallback_price, "source": src,
                                   "price_note": f"CMP from {src} because Yahoo was unavailable",
                                   "last_price_date": pd.to_datetime(nse_q.get("last_update"), errors="coerce") if nse_q.get("last_update") else None})
                for k in ("prev_close", "high_52w", "low_52w"):
                    if nse_q.get(k) is not None:
                        data.quote.setdefault(k, nse_q.get(k))
                if parsed:
                    data.quote.setdefault("high_52w", parsed.get("top_ratios", {}).get("high_52w"))
                    data.quote.setdefault("low_52w", parsed.get("top_ratios", {}).get("low_52w"))
                data.add_source("CMP (fallback)", src, ident.screener_url or "", "", "Partial")
        if not is_num(data.quote.get("market_cap_cr")):
            mc = ScreenerProvider.top_ratio(parsed, "Market Cap") if parsed else None
            if mc is None and is_num(data.quote.get("price")) and nse_q.get("issued_size"):
                mc = data.quote["price"] * nse_q["issued_size"] / 1e7
            data.quote["market_cap_cr"] = mc

        # ---------------- statements (single primary source)
        y_st = {}
        if parsed is not None and parsed.get("annual") is not None and not parsed["annual"].empty:
            data.annual = parsed["annual"]
            data.quarterly = parsed.get("quarterly", pd.DataFrame())
            data.statement_source = "Screener.in"
            data.statement_basis = parsed.get("basis", "Unknown")
            data.item_sources = dict(parsed.get("item_sources", {}))
            data.ttm = parsed.get("ttm", {})
            data.add_source(f"Financial statements ({data.statement_basis}, ₹ crore)", "Screener.in",
                            parsed.get("url", ""), str(data.annual.columns[-1].date()))
            # Supplement only missing line items from Yahoo for the SAME period-ends,
            # and only when both are consolidated (Yahoo reports consolidated for Indian cos).
            if data.statement_basis == "Consolidated" and ticker and self.yahoo.available and not light:
                y_st = self.yahoo.get_statements(ticker)
                self._supplement(data, y_st.get("annual"), ["current_liabilities", "cash", "capex",
                                                            "short_term_debt", "long_term_debt",
                                                            "eps_diluted"])
        elif ticker and self.yahoo.available:
            y_st = self.yahoo.get_statements(ticker)
            if y_st and not y_st.get("annual", pd.DataFrame()).empty:
                data.annual = _month_end(y_st["annual"])
                data.quarterly = _month_end(y_st.get("quarterly", pd.DataFrame()))
                data.statement_source = "Yahoo Finance"
                data.statement_basis = "Consolidated (as reported by Yahoo)"
                data.item_sources = dict(y_st.get("item_sources", {}))
                data.add_source("Financial statements (₹ crore, converted from ₹)", self.yahoo.name,
                                f"https://finance.yahoo.com/quote/{ticker}/financials",
                                str(data.annual.columns[-1].date()), "Partial",
                                "Yahoo typically provides only ~4 annual and ~5 quarterly periods")
        if not data.annual.empty:
            data.annual = _drop_interim_annual_columns(data)
        if data.annual.empty:
            data.add_source("Financial statements", "All providers", "", "", "Failed",
                            "No financial statements could be retrieved")
            data.warn("No financial statements could be retrieved; fundamental metrics are unavailable.")

        # ---------------- shareholding
        if not light:
            if parsed is not None and not parsed.get("shareholding", pd.DataFrame()).empty:
                data.shareholding = parsed["shareholding"]
                data.shareholding_source = "Screener.in (quarterly shareholding pattern)"
                data.add_source("Shareholding pattern (quarterly)", "Screener.in",
                                (parsed.get("url") or "") + "#shareholding",
                                str(data.shareholding.index[-1].date()))
            elif self.nse is not None and ident.nse_symbol:
                shp = self.nse.shareholding_master(ident.nse_symbol)
                if not shp.empty:
                    data.shareholding = shp
                    data.shareholding_source = "NSE shareholding master (promoter / public only)"
                    data.add_source("Shareholding pattern (quarterly)", self.nse.name,
                                    f"https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern?symbol={ident.nse_symbol}",
                                    str(shp.index[-1].date()), "Partial", "FII/DII split not provided by this endpoint")
            if data.shareholding.empty:
                data.add_source("Shareholding pattern (quarterly)", "Screener.in / NSE", "", "", "Failed",
                                "Shareholding data could not be retrieved")
            if self.nse is not None and ident.nse_symbol:
                pl = self.nse.pledge(ident.nse_symbol)
                if not pl.empty:
                    data.pledge = pl
                    data.pledge_source = self.nse.name
                    data.add_source("Promoter pledge data", self.nse.name,
                                    f"https://www.nseindia.com/companies-listing/corporate-filings-pledged-data?symbol={ident.nse_symbol}",
                                    str(pl.index[-1].date()))
                else:
                    data.add_source("Promoter pledge data", self.nse.name, "", "",
                                    "Restricted" if self.nse.restricted else "Failed",
                                    "Pledge data unavailable from NSE")
            if parsed is not None and not parsed.get("bank_metrics", pd.DataFrame()).empty:
                data.bank_metrics = parsed["bank_metrics"]

        # ---------------- sector class
        ident.sector_class = classify_sector(ident.industry, ident.sector,
                                             data.source_ratios.get("_screener_industry"))
        if data.statement_source == "Screener.in" and "deposits" in data.annual.index \
                and data.annual.loc["deposits"].notna().any() and ident.sector_class not in ("bank",):
            ident.sector_class = "bank"  # Screener bank-format balance sheet

        # ---------------- peers
        if with_peers and not light:
            peers = []
            if parsed is not None and self.screener is not None:
                peers = self.screener.fetch_peers(parsed.get("warehouse_id"), ident.nse_symbol or ident.bse_code)
            if not peers:
                key = self._fallback_peer_key(ident)
                if key:
                    peers = [{"name": s, "symbol": s, "source": "Configured fallback peer list (config.py)"}
                             for s in FALLBACK_PEERS[key] if s != (ident.nse_symbol or "")]
            data.peers = peers[: SETTINGS.max_peers]
        return data

    @staticmethod
    def _fallback_peer_key(ident: CompanyIdentity) -> Optional[str]:
        if ident.sector_class in FALLBACK_PEERS:
            return ident.sector_class
        blob = f"{ident.industry or ''} {ident.sector or ''}".lower()
        for key, kws in FALLBACK_PEER_KEYWORDS.items():
            if any(k in blob for k in kws):
                return key
        for key, syms in FALLBACK_PEERS.items():
            if ident.nse_symbol in syms:
                return key
        return None

    @staticmethod
    def _supplement(data: CompanyData, other: Optional[pd.DataFrame], items: list[str]) -> None:
        if other is None or other.empty or data.annual.empty:
            return
        other = _month_end(other)
        ann = data.annual
        common = [c for c in ann.columns if c in other.columns]
        if not common:
            return
        changed = False
        for item in items:
            if item not in other.index:
                continue
            existing = ann.loc[item] if item in ann.index else pd.Series(float("nan"), index=ann.columns)
            if existing.notna().any():
                continue
            vals = other.loc[item].reindex(ann.columns)
            vals[[c for c in ann.columns if c not in common]] = float("nan")
            if vals.notna().any():
                ann.loc[item] = vals
                data.item_sources[f"annual:{item}"] = ("Yahoo Finance (same period-end, consolidated) – "
                                                       "supplements an item Screener does not show")
                changed = True
        if changed:
            data.annual = finalize_statement(ann, data.item_sources, "annual")

    # ================================================================== peers
    def load_peer(self, symbol: str) -> Optional[CompanyData]:
        try:
            if symbol.isdigit():
                ident = CompanyIdentity(name=symbol, bse_code=symbol, yahoo_ticker=f"{symbol}.BO")
            else:
                ident = CompanyIdentity(name=symbol, nse_symbol=symbol, yahoo_ticker=f"{symbol}.NS")
            d = self.load(ident, with_peers=False, light=True)
            if d.annual.empty and not is_num(d.quote.get("price")):
                return None
            return d
        except Exception as exc:  # noqa: BLE001
            log.warning("Peer %s failed: %s", symbol, exc)
            return None
