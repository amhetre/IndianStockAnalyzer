// Technical indicators on candles [{time, open, high, low, close, volume}].
// Each returns [{time, value}] (or several such series) aligned to the input bars.

const pts = (bars, vals) => bars.map((b, i) => ({ time: b.time, value: vals[i] })).filter((p) => p.value != null && Number.isFinite(p.value));

function smaArr(v, n) {
  const out = new Array(v.length).fill(null);
  let s = 0;
  for (let i = 0; i < v.length; i++) {
    s += v[i];
    if (i >= n) s -= v[i - n];
    if (i >= n - 1) out[i] = s / n;
  }
  return out;
}

function emaArr(v, n) {
  const out = new Array(v.length).fill(null);
  const k = 2 / (n + 1);
  let e = null;
  for (let i = 0; i < v.length; i++) {
    if (v[i] == null) continue;
    if (e == null) {
      if (i >= n - 1) {
        let s = 0, c = 0;
        for (let j = i - n + 1; j <= i; j++) if (v[j] != null) { s += v[j]; c++; }
        if (c === n) e = s / n;
      }
    } else e = v[i] * k + e * (1 - k);
    out[i] = e;
  }
  return out;
}

export const sma = (bars, n) => pts(bars, smaArr(bars.map((b) => b.close), n));
export const ema = (bars, n) => pts(bars, emaArr(bars.map((b) => b.close), n));

export function rsi(bars, n = 14) {
  const c = bars.map((b) => b.close);
  const out = new Array(c.length).fill(null);
  let g = 0, l = 0;
  for (let i = 1; i < c.length; i++) {
    const d = c[i] - c[i - 1];
    const up = Math.max(d, 0), dn = Math.max(-d, 0);
    if (i <= n) {
      g += up; l += dn;
      if (i === n) { g /= n; l /= n; out[i] = l === 0 ? 100 : 100 - 100 / (1 + g / l); }
    } else {
      g = (g * (n - 1) + up) / n;
      l = (l * (n - 1) + dn) / n;
      out[i] = l === 0 ? 100 : 100 - 100 / (1 + g / l);
    }
  }
  return pts(bars, out);
}

export function macd(bars, f = 12, s = 26, sig = 9) {
  const c = bars.map((b) => b.close);
  const ef = emaArr(c, f), es = emaArr(c, s);
  const line = c.map((_, i) => (ef[i] != null && es[i] != null ? ef[i] - es[i] : null));
  const signal = emaArr(line, sig);
  const hist = line.map((v, i) => (v != null && signal[i] != null ? v - signal[i] : null));
  return { macd: pts(bars, line), signal: pts(bars, signal), hist: pts(bars, hist) };
}

export function bollinger(bars, n = 20, k = 2) {
  const c = bars.map((b) => b.close);
  const mid = smaArr(c, n);
  const up = [], lo = [];
  for (let i = 0; i < c.length; i++) {
    if (mid[i] == null) { up.push(null); lo.push(null); continue; }
    let v = 0;
    for (let j = i - n + 1; j <= i; j++) v += (c[j] - mid[i]) ** 2;
    const sd = Math.sqrt(v / n);
    up.push(mid[i] + k * sd);
    lo.push(mid[i] - k * sd);
  }
  return { mid: pts(bars, mid), upper: pts(bars, up), lower: pts(bars, lo) };
}

// VWAP resets every trading day (bar times are IST-shifted epoch seconds).
export function vwap(bars) {
  let day = null, pv = 0, vv = 0;
  return pts(bars, bars.map((b) => {
    const d = Math.floor(b.time / 86400);
    if (d !== day) { day = d; pv = 0; vv = 0; }
    const tp = (b.high + b.low + b.close) / 3;
    pv += tp * (b.volume || 0);
    vv += b.volume || 0;
    return vv ? pv / vv : null;
  }));
}

function atrArr(bars, n) {
  const tr = bars.map((b, i) => (i === 0 ? b.high - b.low
    : Math.max(b.high - b.low, Math.abs(b.high - bars[i - 1].close), Math.abs(b.low - bars[i - 1].close))));
  const out = new Array(bars.length).fill(null);
  let a = null;
  for (let i = 0; i < tr.length; i++) {
    if (i === n - 1) a = tr.slice(0, n).reduce((x, y) => x + y, 0) / n;
    else if (i >= n) a = (a * (n - 1) + tr[i]) / n;
    out[i] = a;
  }
  return out;
}

// Supertrend (ATR period, multiplier) → separate up-trend (green) and down-trend (red) segments.
export function supertrend(bars, n = 10, m = 3) {
  const atr = atrArr(bars, n);
  const up = [], dn = [];
  let fu = null, fl = null, trend = 1;
  for (let i = 0; i < bars.length; i++) {
    const b = bars[i];
    if (atr[i] == null) { up.push(null); dn.push(null); continue; }
    const hl2 = (b.high + b.low) / 2;
    const bu = hl2 + m * atr[i], bl = hl2 - m * atr[i];
    const pc = i ? bars[i - 1].close : b.close;
    fu = fu == null || bu < fu || pc > fu ? bu : fu;
    fl = fl == null || bl > fl || pc < fl ? bl : fl;
    if (trend === 1 && b.close < fl) trend = -1;
    else if (trend === -1 && b.close > fu) trend = 1;
    up.push(trend === 1 ? fl : null);
    dn.push(trend === -1 ? fu : null);
  }
  // whitespace points break the line between trend flips
  const ws = (vals) => bars.map((b, i) => (vals[i] == null ? { time: b.time } : { time: b.time, value: vals[i] }));
  return { up: ws(up), down: ws(dn) };
}

export function heikinAshi(bars) {
  const out = [];
  bars.forEach((b, i) => {
    const close = (b.open + b.high + b.low + b.close) / 4;
    const open = i === 0 ? (b.open + b.close) / 2 : (out[i - 1].open + out[i - 1].close) / 2;
    out.push({ time: b.time, open, close, high: Math.max(b.high, open, close), low: Math.min(b.low, open, close), volume: b.volume });
  });
  return out;
}
