"""
Fast snapshot for the stock page: live quote, key stats and price history.

This is what renders immediately when a stock is opened; the full fundamental
report keeps building in the background (server/reports.py).
"""
from __future__ import annotations

from typing import Optional

from server.market import _cached, _f, yf
from utils.logger import get_logger

log = get_logger("server.quote")

RANGES = {
    "1D": ("1d", "2m"),
    "5D": ("5d", "15m"),
    "1M": ("1mo", "1d"),
    "6M": ("6mo", "1d"),
    "1Y": ("1y", "1d"),
    "5Y": ("5y", "1wk"),
    "MAX": ("max", "1mo"),
}


def ticker_for(nse: Optional[str], bse: Optional[str], yt: Optional[str]) -> Optional[str]:
    if yt:
        return yt.upper()
    if nse:
        return f"{nse.upper()}.NS"
    if bse:
        return f"{bse}.BO"
    return None


def _info(tk: str) -> dict:
    t = yf.Ticker(tk)
    info: dict = {}
    try:
        info = t.info or {}
    except Exception as exc:  # noqa: BLE001
        log.info("yfinance info failed for %s: %s", tk, exc)
    if not info.get("regularMarketPrice") and not info.get("currentPrice"):
        try:
            fi = t.fast_info
            info.setdefault("currentPrice", fi.get("lastPrice"))
            info.setdefault("previousClose", fi.get("previousClose"))
            info.setdefault("marketCap", fi.get("marketCap"))
            info.setdefault("fiftyTwoWeekHigh", fi.get("yearHigh"))
            info.setdefault("fiftyTwoWeekLow", fi.get("yearLow"))
        except Exception:  # noqa: BLE001
            pass
    return info


def get_quote(tk: str) -> dict:
    def produce():
        if yf is None:
            return {"ticker": tk, "available": False}
        i = _info(tk)
        price = _f(i.get("currentPrice")) or _f(i.get("regularMarketPrice"))
        prev = _f(i.get("previousClose")) or _f(i.get("regularMarketPreviousClose"))
        chg = round(price - prev, 2) if price is not None and prev else None
        mcap = _f(i.get("marketCap"))
        dy = _f(i.get("dividendYield"))
        return {
            "ticker": tk,
            "available": price is not None,
            "name": i.get("longName") or i.get("shortName"),
            "exchange": "NSE" if tk.endswith(".NS") else "BSE",
            "sector": i.get("sector"), "industry": i.get("industry"),
            "website": i.get("website"),
            "summary": i.get("longBusinessSummary"),
            "price": price, "prev_close": prev, "change": chg,
            "pct": round(chg / prev * 100, 2) if chg is not None and prev else None,
            "open": _f(i.get("open")) or _f(i.get("regularMarketOpen")),
            "day_high": _f(i.get("dayHigh")), "day_low": _f(i.get("dayLow")),
            "high_52w": _f(i.get("fiftyTwoWeekHigh")), "low_52w": _f(i.get("fiftyTwoWeekLow")),
            "volume": _f(i.get("regularMarketVolume")) or _f(i.get("volume")),
            "market_state": i.get("marketState"),          # REGULAR | CLOSED | PRE | POST …
            "market_time": i.get("regularMarketTime"),     # epoch seconds of the last trade
            "avg_volume": _f(i.get("averageVolume")),
            "market_cap_cr": round(mcap / 1e7, 0) if mcap else None,
            "pe": _f(i.get("trailingPE")), "forward_pe": _f(i.get("forwardPE")),
            "pb": _f(i.get("priceToBook")), "eps": _f(i.get("trailingEps")),
            "book_value": _f(i.get("bookValue")),
            # yfinance ≥0.2.5x reports dividendYield already in percent
            "dividend_yield": dy if dy is None or yf_pct_yield() else round(dy * 100, 2),
            "roe": round(_f(i.get("returnOnEquity")) * 100, 2) if _f(i.get("returnOnEquity")) is not None else None,
            "debt_to_equity": _f(i.get("debtToEquity")),
            "beta": _f(i.get("beta")),
            "face_value": None,
        }
    return _cached(f"quote:{tk}", 15, produce)


def get_history(tk: str, rng: str) -> dict:
    period, interval = RANGES.get(rng.upper(), RANGES["1Y"])

    def produce():
        if yf is None:
            return {"ticker": tk, "range": rng, "points": []}
        try:
            h = yf.Ticker(tk).history(period=period, interval=interval, auto_adjust=False)
        except Exception as exc:  # noqa: BLE001
            log.info("history failed for %s %s: %s", tk, rng, exc)
            h = None
        if rng.upper() == "1D" and (h is None or h.empty):  # holiday / pre-open → last session
            try:
                h = yf.Ticker(tk).history(period="5d", interval="5m", auto_adjust=False)
                if not h.empty:
                    h = h[h.index.date == h.index[-1].date()]
            except Exception:  # noqa: BLE001
                h = None
        pts = []
        if h is not None and not h.empty:
            for ts, row in h.iterrows():
                c = _f(row["Close"])
                if c is not None:
                    pts.append({"t": ts.isoformat(), "v": round(c, 2), "vol": _f(row.get("Volume"))})
        return {"ticker": tk, "range": rng.upper(), "intraday": interval.endswith("m"), "points": pts}
    return _cached(f"hist:{tk}:{rng.upper()}", 60 if interval.endswith("m") else 900, produce)


# ---------------------------------------------------------------- OHLC candles for the trading chart
IST = 19800  # chart library shows UTC; shift so axis labels read in IST
INTERVALS = {  # ui interval -> (yfinance interval, max days Yahoo serves)
    "1m": ("1m", 7), "5m": ("5m", 59), "15m": ("15m", 59), "30m": ("30m", 59),
    "1h": ("60m", 729), "1D": ("1d", None), "1W": ("1wk", None), "1M": ("1mo", None),
}
RANGE_DAYS = {"1D": 1, "5D": 5, "1M": 31, "3M": 92, "6M": 183, "1Y": 366, "3Y": 1096, "5Y": 1827, "MAX": None}
# Extra history loaded before the visible window so 200-DMA / RSI / MACD are valid from the first bar.
WARMUP_DAYS = {"1m": 4, "5m": 20, "15m": 40, "30m": 58, "1h": 300, "1D": 420, "1W": 1900, "1M": None}


def get_candles(tk: str, rng: str, interval: str) -> dict:
    rng, interval = rng.upper(), interval if interval in INTERVALS else "1D"
    yf_int, max_days = INTERVALS[interval]
    days = RANGE_DAYS.get(rng, 366)

    def produce():
        import pandas as pd
        out = {"ticker": tk, "range": rng, "interval": interval, "candles": [], "from": None}
        if yf is None:
            return out
        warm = WARMUP_DAYS[interval]
        load = None if days is None or warm is None else days + warm + (3 if days <= 5 else 0)
        if load and max_days:
            load = min(load, max_days)
        kw = {"period": "max"} if load is None else {
            "start": (pd.Timestamp.utcnow() - pd.Timedelta(days=load)).strftime("%Y-%m-%d")}
        try:
            h = yf.Ticker(tk).history(interval=yf_int, auto_adjust=False, **kw)
        except Exception as exc:  # noqa: BLE001
            log.info("candles failed for %s %s %s: %s", tk, rng, interval, exc)
            return out
        if h is None or h.empty:
            return out
        h = h.dropna(subset=["Open", "High", "Low", "Close"])
        candles = []
        for ts, r in h.iterrows():
            candles.append({"time": int(ts.timestamp()) + IST, "open": round(float(r["Open"]), 2),
                            "high": round(float(r["High"]), 2), "low": round(float(r["Low"]), 2),
                            "close": round(float(r["Close"]), 2), "volume": _f(r.get("Volume")) or 0})
        out["candles"] = candles
        if candles and days is not None:
            idx = h.index
            if rng in ("1D", "5D"):  # last N trading sessions
                dates = sorted(set(idx.date))
                first = dates[-days] if len(dates) >= days else dates[0]
                start = idx[idx.date >= first][0]
            else:
                start = idx[-1] - pd.Timedelta(days=days)
            out["from"] = int(start.timestamp()) + IST
        out["intraday"] = yf_int.endswith("m")
        return out
    return _cached(f"candles:{tk}:{rng}:{interval}", 30 if yf_int.endswith("m") else 900, produce)


def yf_pct_yield() -> bool:
    """yfinance >= 0.2.51 reports dividendYield already in percent (0.44 means 0.44%)."""
    try:
        parts = [int(x) for x in yf.__version__.split(".")[:3]]
        return parts >= [0, 2, 51]
    except Exception:  # noqa: BLE001
        return True


# ---------------------------------------------------------------- chart-based projection
def get_projection(tk: Optional[str], demo: bool = False) -> dict:
    """Technical read of the daily chart + probabilistic price cone (analysis/projection.py)."""
    from analysis.projection import project

    def produce():
        if demo:
            from data_providers.demo_provider import make_demo_company
            h = make_demo_company(with_peers=False).price_history.iloc[-800:]
        else:
            if yf is None:
                return {"available": False, "reason": "yfinance is not installed"}
            try:
                h = yf.Ticker(tk).history(period="3y", interval="1d", auto_adjust=True)
            except Exception as exc:  # noqa: BLE001
                log.info("projection history failed for %s: %s", tk, exc)
                return {"available": False, "reason": "Could not download price history"}
            if h is None or h.empty:
                return {"available": False, "reason": "No price history from Yahoo Finance"}
            h.index = h.index.tz_localize(None) if h.index.tz is not None else h.index
        try:
            out = project(h)
        except Exception as exc:  # noqa: BLE001
            log.exception("projection failed for %s", tk)
            return {"available": False, "reason": f"Analysis failed: {exc}"}
        out["ticker"] = "DEMO (synthetic)" if demo else tk
        return out
    return _cached(f"proj:{'demo' if demo else tk}", 600, produce)
