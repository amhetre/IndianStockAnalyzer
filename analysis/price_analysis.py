"""CMP, 52-week range, moving averages, trend and RSI – with plain-English explanation."""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from data_providers.models import CompanyData
from utils.data_validation import price_staleness
from utils.financial_utils import fmt_inr, fmt_pct, is_num, num, pct_change, safe_div


def rsi(close: pd.Series, period: int = 14) -> Optional[float]:
    if close is None or len(close) < period + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain.iloc[-1] / loss.iloc[-1] if loss.iloc[-1] != 0 else np.inf
    return float(100 - 100 / (1 + rs))


def analyse_price(data: CompanyData, profit_growth_ttm: Optional[float] = None,
                  revenue_growth_ttm: Optional[float] = None) -> dict:
    q = data.quote
    h = data.price_history
    price = num(q.get("price"))
    prev = num(q.get("prev_close"))
    out: dict = {"source": q.get("source", ""), "price_note": q.get("price_note", "")}
    out["price"] = price
    out["prev_close"] = prev
    out["day_change"] = (price - prev) if is_num(price) and is_num(prev) else None
    out["day_change_pct"] = pct_change(price, prev)
    out["high_52w"], out["low_52w"] = num(q.get("high_52w")), num(q.get("low_52w"))
    out["dist_from_high_pct"] = (safe_div(price - out["high_52w"], out["high_52w"]) * 100
                                 if is_num(price) and is_num(out["high_52w"]) and out["high_52w"] else None)
    out["dist_from_low_pct"] = (safe_div(price - out["low_52w"], out["low_52w"]) * 100
                                if is_num(price) and is_num(out["low_52w"]) and out["low_52w"] else None)
    out["market_cap_cr"] = num(q.get("market_cap_cr"))
    out["volume"] = num(q.get("volume"))
    out["avg_volume"] = num(q.get("avg_volume"))
    out["last_price_date"] = q.get("last_price_date")
    out["staleness"] = price_staleness(q.get("last_price_date"))

    closes = h["Close"] if h is not None and not h.empty else pd.Series(dtype=float)
    out["dma50"] = float(closes.iloc[-50:].mean()) if len(closes) >= 50 else None
    out["dma200"] = float(closes.iloc[-200:].mean()) if len(closes) >= 200 else None
    out["rsi14"] = rsi(closes)
    out["ret_1m"] = pct_change(closes.iloc[-1], closes.iloc[-22]) if len(closes) > 22 else None
    out["ret_3m"] = pct_change(closes.iloc[-1], closes.iloc[-64]) if len(closes) > 64 else None
    out["ret_1y"] = pct_change(closes.iloc[-1], closes.iloc[-249]) if len(closes) > 249 else None
    # 50-DMA slope over last 20 sessions
    if len(closes) >= 70:
        d_now = closes.iloc[-50:].mean()
        d_prev = closes.iloc[-70:-20].mean()
        out["dma50_slope_pct"] = pct_change(d_now, d_prev)
    else:
        out["dma50_slope_pct"] = None
    out["chart"] = pd.DataFrame({
        "Close": closes,
        "DMA50": closes.rolling(50).mean(),
        "DMA200": closes.rolling(200).mean(),
    }).iloc[-750:] if len(closes) else pd.DataFrame()
    out["explanation"] = explain_price(out, profit_growth_ttm, revenue_growth_ttm)
    return out


def explain_price(p: dict, profit_growth: Optional[float], revenue_growth: Optional[float]) -> list[dict]:
    qa = []
    price, hi, lo = p.get("price"), p.get("high_52w"), p.get("low_52w")
    # 1. near high or low?
    if is_num(price) and is_num(hi) and is_num(lo) and hi > lo:
        pos = (price - lo) / (hi - lo) * 100
        if pos >= 85:
            where = "close to its 52-week HIGH"
        elif pos <= 15:
            where = "close to its 52-week LOW"
        else:
            where = "in the middle part of its 52-week range"
        a = (f"The share at {fmt_inr(price)} is {where} (52-week range {fmt_inr(lo)} – {fmt_inr(hi)}; it sits at "
             f"{pos:.0f}% of that range). It is {fmt_pct(abs(p['dist_from_high_pct']))} below the high and "
             f"{fmt_pct(p['dist_from_low_pct'])} above the low.")
    else:
        a = "52-week range data is not available."
    qa.append({"q": "Is the current price near its 52-week high or low?", "a": a})
    # 2. rising or falling?
    r3, r1y, slope = p.get("ret_3m"), p.get("ret_1y"), p.get("dma50_slope_pct")
    parts = []
    if is_num(r3):
        parts.append(f"{'up' if r3 >= 0 else 'down'} {abs(r3):.1f}% over about 3 months")
    if is_num(r1y):
        parts.append(f"{'up' if r1y >= 0 else 'down'} {abs(r1y):.1f}% over about 1 year")
    trend = ("rising" if is_num(slope) and slope > 1 else "falling" if is_num(slope) and slope < -1
             else "moving sideways" if is_num(slope) else "unclear")
    a = (f"The price is {', and '.join(parts)}. The short-term trend (direction of the 50-day average) looks {trend}."
         if parts else "Not enough price history to judge the trend.")
    qa.append({"q": "Is the share price rising or falling?", "a": a})
    # 3. vs moving averages
    d50, d200 = p.get("dma50"), p.get("dma200")
    if is_num(price) and is_num(d50) and is_num(d200):
        a = (f"It is trading {'ABOVE' if price > d50 else 'BELOW'} its 50-day average ({fmt_inr(d50)}) and "
             f"{'ABOVE' if price > d200 else 'BELOW'} its 200-day average ({fmt_inr(d200)}).")
        if d50 > d200:
            a += " The 50-day average is above the 200-day average, which traders read as a positive medium-term trend."
        else:
            a += " The 50-day average is below the 200-day average, which traders read as a weak medium-term trend."
    else:
        a = "Moving averages need at least 200 trading days of price history, which is not available."
    qa.append({"q": "Is it trading above or below its 50-day and 200-day moving averages?", "a": a})
    # 4. what does it indicate
    if is_num(price) and is_num(d50) and is_num(d200):
        if price > d50 > d200:
            ind = "Market sentiment is currently positive – buyers have been in control."
        elif price < d50 < d200:
            ind = "Market sentiment is currently negative – sellers have been in control."
        else:
            ind = "Signals are mixed – the price is between its averages, so the trend is not clear."
        rsi_v = p.get("rsi14")
        if is_num(rsi_v):
            ind += (f" RSI(14) is {rsi_v:.0f}" + (" – above 70, the stock may be short-term overbought." if rsi_v > 70
                                                   else " – below 30, the stock may be short-term oversold." if rsi_v < 30
                                                   else " – in the neutral zone."))
        ind += " These are price/sentiment signals only; they say nothing by themselves about whether the business is good or the price is fair."
    else:
        ind = "Insufficient price history for trend signals."
    qa.append({"q": "What does this indicate?", "a": ind})
    # 5. supported by fundamentals?
    if is_num(r1y) and is_num(profit_growth):
        if r1y > 15 and profit_growth > 10:
            a = (f"Partly yes: the price rose {r1y:.1f}% in a year and trailing profit grew {profit_growth:.1f}%. "
                 "Rising profits are supporting the price rise.")
        elif r1y > 15 and profit_growth <= 0:
            a = (f"Not clearly: the price rose {r1y:.1f}% but trailing profit changed {profit_growth:.1f}%. The rise seems "
                 "driven by expectations or sentiment rather than current earnings – this raises valuation risk.")
        elif r1y < -15 and profit_growth > 10:
            a = (f"The price fell {abs(r1y):.1f}% even though trailing profit grew {profit_growth:.1f}%. The market may be "
                 "worried about future growth, sector issues or valuation. This is worth investigating – it is NOT "
                 "automatically a sign of undervaluation.")
        elif r1y < -15 and profit_growth <= 0:
            a = (f"Yes – the price fell {abs(r1y):.1f}% and trailing profit also fell ({profit_growth:.1f}%). The fall is "
                 "consistent with weaker business performance.")
        else:
            a = (f"Price change over 1 year ({r1y:+.1f}%) and trailing profit growth ({profit_growth:+.1f}%) are broadly "
                 "in line; no major disconnect.")
        if is_num(revenue_growth):
            a += f" Revenue growth over the same trailing period was {revenue_growth:+.1f}%."
    else:
        a = "Cannot compare – 1-year price change or trailing profit growth is unavailable."
    a += " Note: a stock near its 52-week low is not automatically cheap, and one near its high is not automatically expensive."
    qa.append({"q": "Does the price movement appear supported by financial performance?", "a": a})
    return qa
