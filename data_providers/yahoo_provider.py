"""
Yahoo Finance provider (via the free `yfinance` library).

Provides: ticker search, CMP/quote, 10-year daily price history, benchmark
(NIFTY 50) history, and annual/quarterly financial statements (converted to ₹ crore).
Yahoo usually reports Indian companies on a consolidated basis but does not
label it explicitly – reports show basis as "Consolidated (as reported by Yahoo)".
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from config import NETWORK
from data_providers.models import finalize_statement
from utils.financial_utils import CRORE, is_num, num
from utils.http_client import CACHE, HttpClient, AccessRestricted, FetchError
from utils.logger import get_logger

log = get_logger(__name__)

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None

SOURCE = "Yahoo Finance (yfinance)"

# Canonical item -> candidate Yahoo row names (first match wins)
INCOME_MAP = {
    "revenue": ["Total Revenue", "Operating Revenue"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "ebit": ["EBIT"],
    "depreciation": ["Reconciled Depreciation", "Depreciation And Amortization In Income Statement",
                     "Depreciation And Amortization", "Depreciation Amortization Depletion"],
    "interest": ["Interest Expense", "Interest Expense Non Operating"],
    "pbt": ["Pretax Income"],
    "tax": ["Tax Provision"],
    "net_income": ["Net Income Common Stockholders", "Net Income",
                   "Net Income From Continuing Operation Net Minority Interest"],
    "other_income": ["Other Non Operating Income Expenses", "Other Income Expense"],
}
EPS_MAP = {"eps_basic": ["Basic EPS"], "eps_diluted": ["Diluted EPS"]}
BALANCE_MAP = {
    "total_assets": ["Total Assets"],
    "current_liabilities": ["Current Liabilities"],
    "total_equity": ["Stockholders Equity", "Common Stock Equity"],
    "total_debt": ["Total Debt"],
    "short_term_debt": ["Current Debt", "Current Debt And Capital Lease Obligation"],
    "long_term_debt": ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"],
    "lease_liabilities": ["Capital Lease Obligations"],
    "cash": ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"],
}
CASHFLOW_MAP = {
    "cfo": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
    "cfi": ["Investing Cash Flow"],
    "cff": ["Financing Cash Flow"],
    "capex": ["Capital Expenditure"],
    "fcf": ["Free Cash Flow"],
}


def _pick(df: pd.DataFrame, names: list[str]) -> Optional[pd.Series]:
    if df is None or df.empty:
        return None
    for n in names:
        if n in df.index:
            s = pd.to_numeric(df.loc[n], errors="coerce")
            if isinstance(s, pd.DataFrame):
                s = s.iloc[0]
            if s.notna().any():
                return s
    return None


def _to_canonical(frames: list[tuple[pd.DataFrame, dict, bool]]) -> pd.DataFrame:
    """frames: (yahoo_df, mapping, convert_to_crore)"""
    rows = {}
    for df, mapping, to_cr in frames:
        for item, names in mapping.items():
            s = _pick(df, names)
            if s is None:
                continue
            if to_cr:
                s = s / CRORE
            rows[item] = s
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows).T
    out.columns = pd.to_datetime(out.columns, errors="coerce")
    out = out.loc[:, out.columns.notna()]
    out = out.reindex(sorted(out.columns), axis=1)
    if "interest" in out.index:
        out.loc["interest"] = out.loc["interest"].abs()
    if "capex" in out.index:
        out.loc["capex"] = out.loc["capex"].abs()
    return out


class YahooProvider:
    name = SOURCE

    def __init__(self):
        self.http = HttpClient()
        if yf is None:
            log.error("yfinance is not installed; Yahoo provider disabled")

    @property
    def available(self) -> bool:
        return yf is not None

    # ------------------------------------------------------------------ search
    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Return Indian-listed matches: [{name, yahoo_ticker, exchange, nse_symbol}]"""
        results: list[dict] = []
        quotes = []
        if yf is not None and hasattr(yf, "Search"):
            try:
                quotes = CACHE.cached(f"yf_search:{query.lower()}", 24,
                                      lambda: yf.Search(query, max_results=limit, news_count=0).quotes)
            except Exception as exc:  # noqa: BLE001
                log.info("yfinance Search failed for %r: %s", query, exc)
        if not quotes:
            try:
                data = self.http.get("https://query2.finance.yahoo.com/v1/finance/search",
                                     params={"q": query, "quotesCount": limit, "newsCount": 0},
                                     as_json=True, ttl_hours=24)
                quotes = data.get("quotes", []) if isinstance(data, dict) else []
            except (AccessRestricted, FetchError) as exc:
                log.info("Yahoo search endpoint failed for %r: %s", query, exc)
        for q in quotes or []:
            sym = q.get("symbol", "")
            if not (sym.endswith(".NS") or sym.endswith(".BO")):
                continue
            results.append({
                "name": q.get("longname") or q.get("shortname") or sym,
                "yahoo_ticker": sym,
                "exchange": "NSE" if sym.endswith(".NS") else "BSE",
                "nse_symbol": sym[:-3] if sym.endswith(".NS") else None,
                "bse_code": sym[:-3] if sym.endswith(".BO") and sym[:-3].isdigit() else None,
                "source": SOURCE,
            })
        return results

    # ------------------------------------------------------------------ quote/info
    def get_info(self, ticker: str) -> dict:
        if yf is None:
            return {}

        def produce():
            t = yf.Ticker(ticker)
            info = {}
            try:
                info = dict(t.info or {})
            except Exception as exc:  # noqa: BLE001
                log.info("Yahoo info failed for %s: %s", ticker, exc)
            try:
                fi = t.fast_info
                for k in ("last_price", "previous_close", "year_high", "year_low", "market_cap",
                          "shares", "last_volume", "currency", "exchange"):
                    try:
                        info.setdefault("fast_" + k, fi[k])
                    except Exception:  # noqa: BLE001
                        pass
            except Exception:  # noqa: BLE001
                pass
            try:
                isin = t.isin
                if isin and isin != "-":
                    info["isin"] = isin
            except Exception:  # noqa: BLE001
                pass
            return info or None

        return CACHE.cached(f"yf_info:{ticker}", NETWORK.cache_ttl_prices_hours, produce) or {}

    def get_history(self, ticker: str, period: str = "10y") -> pd.DataFrame:
        if yf is None:
            return pd.DataFrame()

        def produce():
            try:
                h = yf.Ticker(ticker).history(period=period, auto_adjust=False, actions=False)
            except Exception as exc:  # noqa: BLE001
                log.warning("Yahoo history failed for %s: %s", ticker, exc)
                return None
            if h is None or h.empty:
                return None
            h = h[[c for c in ("Close", "Volume", "High", "Low") if c in h.columns]].copy()
            idx = pd.to_datetime(h.index)
            if getattr(idx, "tz", None) is not None:
                idx = idx.tz_localize(None)
            h.index = idx.normalize()
            return h.dropna(subset=["Close"])

        out = CACHE.cached(f"yf_hist:{ticker}:{period}", NETWORK.cache_ttl_prices_hours, produce)
        return out if out is not None else pd.DataFrame()

    def build_quote(self, ticker: str, info: dict, hist: pd.DataFrame) -> dict:
        """Assemble quote fields. Price-derived fields fall back to history (labelled)."""
        q: dict = {"source": SOURCE, "ticker": ticker}
        price = num(info.get("currentPrice")) or num(info.get("regularMarketPrice")) or num(info.get("fast_last_price"))
        last_date = None
        if not hist.empty:
            last_date = hist.index[-1]
            if price is None:
                price = float(hist["Close"].iloc[-1])
                q["price_note"] = "CMP taken from last daily close in price history"
        q["price"] = price
        q["last_price_date"] = last_date
        prev = num(info.get("previousClose")) or num(info.get("regularMarketPreviousClose")) or num(info.get("fast_previous_close"))
        if prev is None and len(hist) >= 2:
            prev = float(hist["Close"].iloc[-2])
        q["prev_close"] = prev
        q["volume"] = num(info.get("volume")) or num(info.get("regularMarketVolume")) or num(info.get("fast_last_volume"))
        if q["volume"] is None and not hist.empty and "Volume" in hist:
            q["volume"] = num(hist["Volume"].iloc[-1])
        q["avg_volume"] = num(info.get("averageVolume"))
        hi = num(info.get("fiftyTwoWeekHigh")) or num(info.get("fast_year_high"))
        lo = num(info.get("fiftyTwoWeekLow")) or num(info.get("fast_year_low"))
        if (hi is None or lo is None) and not hist.empty and last_date is not None:
            win = hist.loc[hist.index >= last_date - pd.Timedelta(days=365)]
            hi_col = "High" if "High" in win else "Close"
            lo_col = "Low" if "Low" in win else "Close"
            hi = hi if hi is not None else float(win[hi_col].max())
            lo = lo if lo is not None else float(win[lo_col].min())
        q["high_52w"], q["low_52w"] = hi, lo
        mcap = num(info.get("marketCap")) or num(info.get("fast_market_cap"))
        q["market_cap_cr"] = mcap / CRORE if mcap else None
        q["shares_outstanding"] = num(info.get("sharesOutstanding")) or num(info.get("fast_shares"))
        q["beta"] = num(info.get("beta"))
        q["book_value_per_share"] = num(info.get("bookValue"))
        q["trailing_eps"] = num(info.get("trailingEps"))
        q["trailing_pe_source"] = num(info.get("trailingPE"))
        q["price_to_book_source"] = num(info.get("priceToBook"))
        q["enterprise_value_cr"] = num(info.get("enterpriseValue")) / CRORE if num(info.get("enterpriseValue")) else None
        q["currency"] = info.get("currency") or info.get("fast_currency") or "INR"
        q["financial_currency"] = info.get("financialCurrency") or q["currency"]
        return q

    # ------------------------------------------------------------------ statements
    def get_statements(self, ticker: str) -> dict:
        """Return {'annual': df, 'quarterly': df, 'item_sources': {...}} in ₹ crore."""
        if yf is None:
            return {}

        def produce():
            t = yf.Ticker(ticker)
            out = {}
            for attr in ("income_stmt", "quarterly_income_stmt", "balance_sheet",
                         "quarterly_balance_sheet", "cashflow", "quarterly_cashflow"):
                try:
                    df = getattr(t, attr)
                    out[attr] = df if isinstance(df, pd.DataFrame) else pd.DataFrame()
                except Exception as exc:  # noqa: BLE001
                    log.info("Yahoo %s failed for %s: %s", attr, ticker, exc)
                    out[attr] = pd.DataFrame()
            return out if any(not v.empty for v in out.values()) else None

        raw = CACHE.cached(f"yf_stmts:{ticker}", NETWORK.cache_ttl_fundamentals_hours, produce)
        if not raw:
            return {}
        item_sources: dict = {}
        annual = _to_canonical([
            (raw.get("income_stmt"), INCOME_MAP, True),
            (raw.get("income_stmt"), EPS_MAP, False),
            (raw.get("balance_sheet"), BALANCE_MAP, True),
            (raw.get("cashflow"), CASHFLOW_MAP, True),
        ])
        quarterly = _to_canonical([
            (raw.get("quarterly_income_stmt"), INCOME_MAP, True),
            (raw.get("quarterly_income_stmt"), EPS_MAP, False),
            (raw.get("quarterly_balance_sheet"), BALANCE_MAP, True),
            (raw.get("quarterly_cashflow"), CASHFLOW_MAP, True),
        ])
        annual = finalize_statement(annual, item_sources, "annual")
        quarterly = finalize_statement(quarterly, item_sources, "quarterly")
        return {"annual": annual, "quarterly": quarterly, "item_sources": item_sources}
