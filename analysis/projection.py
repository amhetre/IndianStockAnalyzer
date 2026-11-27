"""
Chart-based price projection (technical analysis).

Reads the daily OHLCV chart and answers "is this stock more likely to rise or
fall from here?" in three layers:

1. Indicator signals - trend (DMA 20/50/200, EMA cross, Supertrend, ADX),
   momentum (RSI, MACD, rate of change), volatility (Bollinger position) and
   volume (OBV, volume on up vs down days).
2. Chart patterns - swing structure (higher highs / higher lows), support and
   resistance from pivot points, breakouts / breakdowns, golden / death cross,
   regression trend channel, and candlestick patterns on the latest bars.
3. A statistical projection - the composite score tilts a log-normal drift;
   recent volatility sets the width of the likely-price cone for 1 week,
   1 month and 3 months, with the probability of finishing higher.

The indicator score is also back-tested on the stock's own history so the
user can see how often this signal was right in the past.

This is a probabilistic, educational read of the chart, not a guarantee and
not investment advice.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd

HORIZONS = [("1W", 5), ("1M", 21), ("3M", 63)]
BACKTEST_H = 21


# ---------------------------------------------------------------- indicators
def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def _rsi(c: pd.Series, n: int = 14) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100)


def _atr(h: pd.Series, l: pd.Series, c: pd.Series, n: int = 14) -> pd.Series:
    pc = c.shift()
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def _adx(h: pd.Series, l: pd.Series, c: pd.Series, n: int = 14):
    upm, dnm = h.diff(), -l.diff()
    pdm = upm.where((upm > dnm) & (upm > 0), 0.0)
    ndm = dnm.where((dnm > upm) & (dnm > 0), 0.0)
    atr = _atr(h, l, c, n).replace(0, np.nan)
    pdi = 100 * pdm.ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / atr
    ndi = 100 * ndm.ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / atr
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False, min_periods=n).mean(), pdi, ndi


def _supertrend(h, l, c, n=10, m=3.0) -> pd.Series:
    atr = _atr(h, l, c, n).to_numpy()
    hv, lv, cv = h.to_numpy(), l.to_numpy(), c.to_numpy()
    trend = np.zeros(len(cv))
    fu = fl = None
    t = 1
    for i in range(len(cv)):
        if np.isnan(atr[i]):
            continue
        hl2 = (hv[i] + lv[i]) / 2
        bu, bl = hl2 + m * atr[i], hl2 - m * atr[i]
        pc = cv[i - 1] if i else cv[i]
        fu = bu if fu is None or bu < fu or pc > fu else fu
        fl = bl if fl is None or bl > fl or pc < fl else fl
        if t == 1 and cv[i] < fl:
            t = -1
        elif t == -1 and cv[i] > fu:
            t = 1
        trend[i] = t
    return pd.Series(trend, index=c.index)


def _frame(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise to Open/High/Low/Close/Volume; fill missing OHLC from Close."""
    d = df.copy()
    d.columns = [str(x).title() for x in d.columns]
    d = d[~d.index.duplicated()].sort_index()
    d["Close"] = pd.to_numeric(d["Close"], errors="coerce")
    for col in ("Open", "High", "Low"):
        d[col] = pd.to_numeric(d[col], errors="coerce") if col in d else d["Close"]
        d[col] = d[col].fillna(d["Close"])
    d["Volume"] = pd.to_numeric(d["Volume"], errors="coerce").fillna(0) if "Volume" in d else 0.0
    return d.dropna(subset=["Close"])


def _indicators(d: pd.DataFrame) -> pd.DataFrame:
    c, h, l, v = d["Close"], d["High"], d["Low"], d["Volume"]
    x = pd.DataFrame(index=d.index)
    x["close"] = c
    for n in (20, 50, 200):
        x[f"sma{n}"] = c.rolling(n).mean()
    x["ema9"], x["ema21"] = _ema(c, 9), _ema(c, 21)
    x["rsi"] = _rsi(c)
    macd = _ema(c, 12) - _ema(c, 26)
    x["macd"], x["macd_sig"] = macd, _ema(macd, 9)
    x["macd_hist"] = macd - x["macd_sig"]
    mid, sd = c.rolling(20).mean(), c.rolling(20).std(ddof=0)
    x["bb_up"], x["bb_lo"], x["bb_mid"] = mid + 2 * sd, mid - 2 * sd, mid
    x["atr"] = _atr(h, l, c)
    x["adx"], x["pdi"], x["ndi"] = _adx(h, l, c)
    x["st"] = _supertrend(h, l, c)
    x["roc20"] = c.pct_change(20) * 100
    obv = (np.sign(c.diff()).fillna(0) * v).cumsum()
    x["obv_slope"] = (obv - obv.shift(20)) / (v.rolling(20).mean() * 20).replace(0, np.nan)
    upv = v.where(c.diff() > 0, 0).rolling(20).sum()
    dnv = v.where(c.diff() < 0, 0).rolling(20).sum()
    x["updown_vol"] = upv / dnv.replace(0, np.nan)
    return x


# ---------------------------------------------------------------- vectorised core score (also back-tested)
def _core_components(x: pd.DataFrame) -> pd.DataFrame:
    """Each component in [-1, 1]; positive = bullish. Same rules for every day."""
    c = x["close"]
    comp = pd.DataFrame(index=x.index)
    comp["above_dma50"] = np.sign(c - x["sma50"])
    comp["above_dma200"] = np.sign(c - x["sma200"])
    comp["dma50_vs_200"] = np.sign(x["sma50"] - x["sma200"])
    comp["ema_cross"] = np.sign(x["ema9"] - x["ema21"])
    comp["supertrend"] = x["st"].replace(0, np.nan)
    # ADX: directional strength only counts when a trend exists
    adx_w = ((x["adx"] - 15) / 15).clip(0, 1)
    comp["adx_dir"] = np.sign(x["pdi"] - x["ndi"]) * adx_w
    r = x["rsi"]
    # RSI: 50-70 bullish momentum, >75 stretched, <30 oversold bounce potential
    comp["rsi"] = np.select(
        [r >= 75, r >= 55, r > 45, r > 30, r <= 30],
        [-0.3, 0.7, 0.0, -0.7, 0.3], default=0.0)
    comp["macd"] = np.sign(x["macd_hist"]) * 0.5 + np.sign(x["macd"]) * 0.5
    comp["roc20"] = (x["roc20"] / 10).clip(-1, 1)
    bbpos = (c - x["bb_lo"]) / (x["bb_up"] - x["bb_lo"]).replace(0, np.nan)
    comp["bollinger"] = np.select([bbpos > 1, bbpos > 0.6, bbpos < 0, bbpos < 0.4], [-0.3, 0.4, 0.3, -0.4], 0.0)
    comp["obv"] = x["obv_slope"].clip(-1, 1)
    comp["updown_vol"] = np.log(x["updown_vol"].clip(0.25, 4)) / math.log(4)
    return comp


CORE_WEIGHTS = {
    "above_dma50": 1.0, "above_dma200": 1.2, "dma50_vs_200": 1.0, "ema_cross": 0.8, "supertrend": 1.0,
    "adx_dir": 0.8, "rsi": 0.8, "macd": 0.9, "roc20": 0.7, "bollinger": 0.4, "obv": 0.6, "updown_vol": 0.5,
}


def _core_score(comp: pd.DataFrame) -> pd.Series:
    w = pd.Series(CORE_WEIGHTS)
    cols = list(w.index)
    vals = comp[cols]
    mask = vals.notna()
    num = (vals.fillna(0) * w).sum(axis=1)
    den = (mask * w).sum(axis=1).replace(0, np.nan)
    return (num / den * 100).clip(-100, 100)


# ---------------------------------------------------------------- chart patterns (latest bar only)
def _pivots(d: pd.DataFrame, k: int = 5):
    h, l = d["High"].to_numpy(), d["Low"].to_numpy()
    highs, lows = [], []
    for i in range(k, len(d) - k):
        if h[i] == h[i - k:i + k + 1].max():
            highs.append((i, float(h[i])))
        if l[i] == l[i - k:i + k + 1].min():
            lows.append((i, float(l[i])))
    return highs, lows


def _levels(highs, lows, price: float, atr: float):
    """Cluster pivot prices into support / resistance zones near the current price."""
    pts = sorted([p for _, p in highs[-40:]] + [p for _, p in lows[-40:]])
    if not pts:
        return [], []
    tol = max(atr * 0.8, price * 0.01)
    clusters: list[list[float]] = [[pts[0]]]
    for p in pts[1:]:
        if p - clusters[-1][-1] <= tol:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    zones = [(float(np.mean(cl)), len(cl)) for cl in clusters]
    sup = sorted([z for z in zones if z[0] < price * 0.995], key=lambda z: -z[0])[:3]
    res = sorted([z for z in zones if z[0] > price * 1.005], key=lambda z: z[0])[:3]
    fmt = lambda zs: [{"price": round(p, 2), "touches": n, "dist_pct": round((p / price - 1) * 100, 2)} for p, n in zs]  # noqa: E731
    return fmt(sup), fmt(res)


def _candles(d: pd.DataFrame) -> list[dict]:
    out = []
    if len(d) < 3:
        return out
    o, h, l, c = (d[k].to_numpy()[-3:] for k in ("Open", "High", "Low", "Close"))
    if np.allclose(o, c) and np.allclose(h, c):
        return out  # close-only data, no candle shapes
    body = abs(c[-1] - o[-1])
    rng = max(h[-1] - l[-1], 1e-9)
    upper, lower = h[-1] - max(o[-1], c[-1]), min(o[-1], c[-1]) - l[-1]
    pbody_lo, pbody_hi = min(o[-2], c[-2]), max(o[-2], c[-2])
    if c[-2] < o[-2] and c[-1] > o[-1] and o[-1] <= pbody_lo and c[-1] >= pbody_hi:
        out.append(("Bullish engulfing", 1, "Today's green candle fully swallowed yesterday's red one - buyers took control."))
    if c[-2] > o[-2] and c[-1] < o[-1] and o[-1] >= pbody_hi and c[-1] <= pbody_lo:
        out.append(("Bearish engulfing", -1, "Today's red candle fully swallowed yesterday's green one - sellers took control."))
    if lower >= 2 * body and upper <= body and body / rng < 0.35 and c[-1] < c[-3]:
        out.append(("Hammer", 1, "Long lower wick after a dip: sellers pushed price down but buyers pulled it back up."))
    if upper >= 2 * body and lower <= body and body / rng < 0.35 and c[-1] > c[-3]:
        out.append(("Shooting star", -1, "Long upper wick after a rise: buyers pushed up but sellers pulled it back down."))
    if body / rng < 0.1 and not out:
        out.append(("Doji", 0, "Open and close almost equal - indecision; the next candle usually decides direction."))
    return [{"name": n, "bias": b, "text": t} for n, b, t in out]


def _patterns(d: pd.DataFrame, x: pd.DataFrame) -> tuple[list[dict], dict]:
    sig: list[dict] = []
    c = d["Close"]
    price = float(c.iloc[-1])
    atr = float(x["atr"].iloc[-1]) if pd.notna(x["atr"].iloc[-1]) else price * 0.02

    # Swing structure from the last pivots
    highs, lows = _pivots(d.iloc[-260:])
    if len(highs) >= 2 and len(lows) >= 2:
        hh, hl = highs[-1][1] > highs[-2][1], lows[-1][1] > lows[-2][1]
        if hh and hl:
            sig.append(_s("Swing structure", "Higher highs & higher lows", 1.0, 1.2, "Pattern",
                          "Each rally peaks higher and each dip stops higher - the textbook definition of an uptrend."))
        elif not hh and not hl:
            sig.append(_s("Swing structure", "Lower highs & lower lows", -1.0, 1.2, "Pattern",
                          "Each rally fails lower and each dip goes deeper - the textbook definition of a downtrend."))
        else:
            sig.append(_s("Swing structure", "Mixed (range / triangle)", 0.0, 1.2, "Pattern",
                          "Peaks and troughs are not lining up in one direction - price is consolidating."))

    support, resistance = _levels(highs, lows, price, atr)

    # Breakout / breakdown of the 55-day range, confirmed by volume
    if len(d) > 60:
        hi55, lo55 = float(d["High"].iloc[-56:-1].max()), float(d["Low"].iloc[-56:-1].min())
        v = d["Volume"]
        vol_ratio = float(v.iloc[-5:].mean() / v.iloc[-60:-5].mean()) if v.iloc[-60:-5].mean() > 0 else 1.0
        conf = " on rising volume" if vol_ratio > 1.2 else ""
        if price > hi55:
            sig.append(_s("55-day breakout", f"Closed above ₹{hi55:,.2f}{conf}", 1.0 if conf else 0.7, 1.3, "Pattern",
                          "Price broke above its 11-week high. Breakouts often attract momentum buyers, especially with volume."))
        elif price < lo55:
            sig.append(_s("55-day breakdown", f"Closed below ₹{lo55:,.2f}{conf}", -1.0 if conf else -0.7, 1.3, "Pattern",
                          "Price fell below its 11-week low. Breakdowns often trigger stop-loss selling."))
        else:
            pos = (price - lo55) / (hi55 - lo55) if hi55 > lo55 else 0.5
            sig.append(_s("55-day range", f"{pos * 100:.0f}% of the way from low to high", (pos - 0.5) * 0.6, 0.6, "Pattern",
                          f"Trading inside its 11-week range of ₹{lo55:,.2f} – ₹{hi55:,.2f}."))

    # Golden / death cross within the last 30 bars
    s50, s200 = x["sma50"], x["sma200"]
    diff = np.sign(s50 - s200).dropna()
    if len(diff) > 30:
        flips = diff.iloc[-30:].diff().fillna(0)
        if (flips > 0).any():
            sig.append(_s("Golden cross", "50-DMA crossed above 200-DMA recently", 1.0, 1.0, "Pattern",
                          "A widely watched long-term bullish signal: the medium-term average moved above the long-term one."))
        elif (flips < 0).any():
            sig.append(_s("Death cross", "50-DMA crossed below 200-DMA recently", -1.0, 1.0, "Pattern",
                          "A widely watched long-term bearish signal: the medium-term average fell below the long-term one."))

    # Linear-regression trend channel over ~6 months (log price)
    n = min(126, len(c))
    y = np.log(c.iloc[-n:].to_numpy())
    t = np.arange(n)
    slope, icpt = np.polyfit(t, y, 1)
    fit = icpt + slope * t
    resid = y - fit
    r2 = 1 - resid.var() / y.var() if y.var() > 0 else 0
    sd = resid.std()
    z = resid[-1] / sd if sd > 0 else 0
    ann = (math.exp(slope * 252) - 1) * 100
    bias = float(np.clip(slope * 252 / 0.4, -1, 1) * min(1, r2 / 0.5))
    where = "upper edge" if z > 1 else "lower edge" if z < -1 else "middle"
    sig.append(_s("6-month trend channel", f"{ann:+.0f}%/yr pace, R² {r2:.2f}, price at {where}", bias, 1.1, "Pattern",
                  "A best-fit line through the last six months. A steep, tight channel (high R²) means a steady trend; "
                  "price at the upper edge is stretched, at the lower edge it is near channel support."))
    channel = {"slope_daily": float(slope), "r2": float(r2), "z": float(z), "sd": float(sd),
               "fit_now": float(math.exp(fit[-1])), "n": n}

    # Candlesticks on the last bar
    for cd in _candles(d):
        sig.append(_s(f"Candle: {cd['name']}", "Latest session", cd["bias"] * 0.8, 0.5, "Pattern", cd["text"]))

    # Distance to nearest levels
    if support:
        sig.append(_s("Nearest support", f"₹{support[0]['price']:,.2f} ({support[0]['dist_pct']:+.1f}%)",
                      0.3 if support[0]["dist_pct"] > -3 else 0.0, 0.4, "Pattern",
                      "A price zone where buyers stepped in before. Close support limits downside if it holds."))
    if resistance:
        sig.append(_s("Nearest resistance", f"₹{resistance[0]['price']:,.2f} ({resistance[0]['dist_pct']:+.1f}%)",
                      -0.3 if resistance[0]["dist_pct"] < 3 else 0.0, 0.4, "Pattern",
                      "A price zone where sellers appeared before. Close resistance can cap a rally until it breaks."))

    return sig, {"support": support, "resistance": resistance, "channel": channel}


def _s(name, value, bias, weight, group, text) -> dict:
    b = float(np.clip(bias, -1, 1))
    return {"name": name, "value": value, "bias": round(b, 2), "weight": weight, "group": group, "text": text,
            "view": "Bullish" if b > 0.15 else "Bearish" if b < -0.15 else "Neutral"}


def _indicator_signals(x: pd.DataFrame, comp: pd.DataFrame) -> list[dict]:
    last, cl = x.iloc[-1], comp.iloc[-1]
    p = last["close"]
    out = []

    def add(key, name, value, group, text):
        v = cl.get(key)
        if pd.notna(v):
            out.append(_s(name, value, v, CORE_WEIGHTS[key], group, text))

    def pct(a, b):
        return f"{(a / b - 1) * 100:+.1f}%" if pd.notna(b) and b else "n/a"

    add("above_dma50", "Price vs 50-DMA", f"₹{p:,.2f} vs ₹{last['sma50']:,.2f} ({pct(p, last['sma50'])})", "Trend",
        "Above the 50-day average means the medium-term trend is up.")
    add("above_dma200", "Price vs 200-DMA", f"₹{p:,.2f} vs ₹{last['sma200']:,.2f} ({pct(p, last['sma200'])})", "Trend",
        "The 200-day average is the most-watched long-term trend line.")
    add("dma50_vs_200", "50-DMA vs 200-DMA", "50 above 200" if last["sma50"] > last["sma200"] else "50 below 200", "Trend",
        "When the faster average is above the slower one the long-term trend is bullish.")
    add("ema_cross", "EMA 9 / 21", "9 above 21" if last["ema9"] > last["ema21"] else "9 below 21", "Trend",
        "Short-term trend: fast EMA above slow EMA means recent buying pressure.")
    add("supertrend", "Supertrend (10, 3)", "Up-trend" if last["st"] > 0 else "Down-trend", "Trend",
        "ATR-based trailing line; flips only when price moves decisively.")
    add("adx_dir", "ADX trend strength", f"ADX {last['adx']:.0f}, +DI {last['pdi']:.0f} / -DI {last['ndi']:.0f}", "Trend",
        "ADX above 25 means a strong trend; +DI vs -DI tells its direction. Below 20 the market is range-bound.")
    add("rsi", "RSI (14)", f"{last['rsi']:.1f}", "Momentum",
        "55-70 = healthy bullish momentum, above 75 = overbought (pullback risk), below 30 = oversold (bounce potential).")
    add("macd", "MACD (12, 26, 9)", f"MACD {last['macd']:.2f}, histogram {last['macd_hist']:+.2f}", "Momentum",
        "MACD above its signal line (positive histogram) shows momentum is improving.")
    add("roc20", "20-day rate of change", f"{last['roc20']:+.1f}%", "Momentum",
        "How much the price moved in the last month.")
    add("bollinger", "Bollinger Bands (20, 2)", f"₹{last['bb_lo']:,.2f} – ₹{last['bb_up']:,.2f}", "Volatility",
        "Riding the upper half is bullish; closing outside a band is stretched and often snaps back.")
    add("obv", "On-balance volume (20d)", f"{last['obv_slope']:+.2f}", "Volume",
        "Rising OBV means more volume on up days - buyers are accumulating.")
    add("updown_vol", "Up-day vs down-day volume", f"{last['updown_vol']:.2f}x" if pd.notna(last["updown_vol"]) else "n/a",
        "Volume", "Above 1x: more shares change hands on rising days than falling days.")
    return out


# ---------------------------------------------------------------- back-test
def _backtest(score: pd.Series, close: pd.Series, h: int = BACKTEST_H, thr: float = 20) -> dict:
    fwd = close.shift(-h) / close - 1
    df = pd.DataFrame({"s": score, "f": fwd}).dropna()
    df = df.iloc[::5]  # weekly sampling to reduce overlap
    bull, bear = df[df.s >= thr], df[df.s <= -thr]
    hits = int((bull.f > 0).sum() + (bear.f < 0).sum())
    n = len(bull) + len(bear)
    base_up = float((df.f > 0).mean() * 100) if len(df) else None
    return {
        "horizon_days": h, "threshold": thr, "signals": n,
        "hit_rate": round(hits / n * 100, 1) if n else None,
        "bull_signals": len(bull), "bull_hit": round(float((bull.f > 0).mean() * 100), 1) if len(bull) else None,
        "bull_avg_ret": round(float(bull.f.mean() * 100), 2) if len(bull) else None,
        "bear_signals": len(bear), "bear_hit": round(float((bear.f < 0).mean() * 100), 1) if len(bear) else None,
        "bear_avg_ret": round(float(bear.f.mean() * 100), 2) if len(bear) else None,
        "base_up_rate": round(base_up, 1) if base_up is not None else None,
    }


# ---------------------------------------------------------------- main entry
def _phi(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def project(df: pd.DataFrame) -> dict:
    """df: daily bars indexed by date with Close (and ideally Open/High/Low/Volume)."""
    d = _frame(df)
    if len(d) < 60:
        return {"available": False, "reason": "Need at least 60 trading days of price history."}

    x = _indicators(d)
    comp = _core_components(x)
    core = _core_score(comp)
    ind_sig = _indicator_signals(x, comp)
    pat_sig, levels = _patterns(d, x)
    signals = ind_sig + pat_sig

    # Composite: indicator score (back-testable) blended with pattern evidence
    pw = sum(s["weight"] for s in pat_sig)
    pat_score = (sum(s["bias"] * s["weight"] for s in pat_sig) / pw * 100) if pw else 0.0
    core_now = float(core.iloc[-1]) if pd.notna(core.iloc[-1]) else 0.0
    score = round(0.65 * core_now + 0.35 * pat_score, 1)

    bulls = sum(1 for s in signals if s["view"] == "Bullish")
    bears = sum(1 for s in signals if s["view"] == "Bearish")
    agree = abs(bulls - bears) / max(1, bulls + bears)
    adx = float(x["adx"].iloc[-1]) if pd.notna(x["adx"].iloc[-1]) else 15
    conf_val = min(1.0, 0.45 * agree + 0.35 * abs(score) / 60 + 0.2 * min(1, adx / 30))
    confidence = "High" if conf_val >= 0.65 else "Medium" if conf_val >= 0.4 else "Low"

    if score >= 40:
        verdict, outlook = "Strong uptrend", "rise"
    elif score >= 15:
        verdict, outlook = "Likely to rise", "rise"
    elif score <= -40:
        verdict, outlook = "Strong downtrend", "fall"
    elif score <= -15:
        verdict, outlook = "Likely to fall", "fall"
    else:
        verdict, outlook = "Sideways / no clear edge", "sideways"

    # Projection cone: log-normal with score-tilted drift
    c = d["Close"]
    price = float(c.iloc[-1])
    lr = np.log(c).diff().dropna()
    sig_d = float(lr.iloc[-60:].ewm(span=30).std().iloc[-1]) if len(lr) >= 30 else float(lr.std())
    sig_d = max(sig_d, 0.004)
    reg_slope = levels["channel"]["slope_daily"] * min(1, levels["channel"]["r2"] / 0.5)
    mu_d = 0.35 * reg_slope + 0.12 * sig_d * (score / 100)
    mu_d = float(np.clip(mu_d, -0.15 * sig_d, 0.15 * sig_d))

    horizons = []
    for label, h in HORIZONS:
        m, s = mu_d * h, sig_d * math.sqrt(h)
        horizons.append({
            "label": label, "days": h,
            "target": round(price * math.exp(m), 2),
            "exp_ret_pct": round((math.exp(m) - 1) * 100, 2),
            "low68": round(price * math.exp(m - s), 2), "high68": round(price * math.exp(m + s), 2),
            "low95": round(price * math.exp(m - 1.96 * s), 2), "high95": round(price * math.exp(m + 1.96 * s), 2),
            "prob_up": round(_phi(m / s) * 100, 1),
        })

    # Path for the chart: last ~6 months of closes + daily cone out to 3 months
    hist_n = 130
    hist = [{"t": ts.strftime("%Y-%m-%d"), "close": round(float(v), 2),
             "sma50": _r(x["sma50"].loc[ts]), "sma200": _r(x["sma200"].loc[ts])}
            for ts, v in c.iloc[-hist_n:].items()]
    future_dates = pd.bdate_range(c.index[-1] + pd.Timedelta(days=1), periods=HORIZONS[-1][1])
    path = [{"t": hist[-1]["t"], "mid": price, "band68": [price, price], "band95": [price, price]}]
    for i, ts in enumerate(future_dates, start=1):
        m, s = mu_d * i, sig_d * math.sqrt(i)
        path.append({"t": ts.strftime("%Y-%m-%d"), "mid": round(price * math.exp(m), 2),
                     "band68": [round(price * math.exp(m - s), 2), round(price * math.exp(m + s), 2)],
                     "band95": [round(price * math.exp(m - 1.96 * s), 2), round(price * math.exp(m + 1.96 * s), 2)]})

    atr = float(x["atr"].iloc[-1]) if pd.notna(x["atr"].iloc[-1]) else price * 0.02
    sup0 = levels["support"][0]["price"] if levels["support"] else None
    res0 = levels["resistance"][0]["price"] if levels["resistance"] else None
    invalidation = (sup0 if sup0 and sup0 > price - 3 * atr else round(price - 2 * atr, 2)) if outlook != "fall" else \
                   (res0 if res0 and res0 < price + 3 * atr else round(price + 2 * atr, 2))

    groups = {}
    for s in signals:
        g = groups.setdefault(s["group"], {"bull": 0, "bear": 0, "neutral": 0})
        g["bull" if s["view"] == "Bullish" else "bear" if s["view"] == "Bearish" else "neutral"] += 1

    return {
        "available": True,
        "as_of": c.index[-1].strftime("%Y-%m-%d"),
        "price": round(price, 2),
        "score": score, "indicator_score": round(core_now, 1), "pattern_score": round(pat_score, 1),
        "verdict": verdict, "outlook": outlook, "confidence": confidence,
        "bullish_count": bulls, "bearish_count": bears, "neutral_count": len(signals) - bulls - bears,
        "groups": groups,
        "daily_vol_pct": round(sig_d * 100, 2), "atr": round(atr, 2),
        "invalidation": invalidation,
        "horizons": horizons,
        "signals": signals,
        "support": levels["support"], "resistance": levels["resistance"],
        "backtest": _backtest(core, c),
        "history": hist, "path": path,
        "summary": _summary(verdict, outlook, score, confidence, bulls, bears, horizons, levels, invalidation),
    }


def _r(v) -> Optional[float]:
    return None if v is None or pd.isna(v) else round(float(v), 2)


def _summary(verdict, outlook, score, confidence, bulls, bears, horizons, levels, inval) -> str:
    m1 = next(h for h in horizons if h["label"] == "1M")
    parts = [f"The chart reads {verdict.lower()} (score {score:+.0f} on a -100 to +100 scale, {confidence.lower()} confidence): "
             f"{bulls} signals bullish vs {bears} bearish."]
    parts.append(f"Over the next month the model's central estimate is ₹{m1['target']:,.2f} ({m1['exp_ret_pct']:+.1f}%), "
                 f"with a 68% range of ₹{m1['low68']:,.2f} – ₹{m1['high68']:,.2f} and a {m1['prob_up']:.0f}% chance of ending higher.")
    if outlook == "rise":
        parts.append(f"The bullish view weakens if price closes below ₹{inval:,.2f}.")
    elif outlook == "fall":
        parts.append(f"The bearish view weakens if price closes above ₹{inval:,.2f}.")
    else:
        r = levels["resistance"][0]["price"] if levels["resistance"] else None
        s = levels["support"][0]["price"] if levels["support"] else None
        if r and s:
            parts.append(f"Watch for a break above ₹{r:,.2f} (bullish) or below ₹{s:,.2f} (bearish).")
    return " ".join(parts)
