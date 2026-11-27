import { useEffect, useMemo, useRef, useState } from "react";
import { createChart, CrosshairMode } from "lightweight-charts";
import { abbr, api, fmt, marketStatus } from "../api.js";
import { themeTokens, useTheme } from "../theme.js";
import { bollinger, ema, heikinAshi, macd, rsi, sma, supertrend, vwap } from "../indicators.js";

// Timeframes and the candle intervals that make sense for each (Yahoo limits intraday history).
const RANGES = {
  "1D": { iv: ["1m", "5m", "15m", "30m", "1h"], def: "5m" },
  "5D": { iv: ["1m", "5m", "15m", "30m", "1h"], def: "15m" },
  "1M": { iv: ["5m", "15m", "30m", "1h", "1D"], def: "1h" },
  "3M": { iv: ["1h", "1D", "1W"], def: "1D" },
  "6M": { iv: ["1h", "1D", "1W"], def: "1D" },
  "1Y": { iv: ["1h", "1D", "1W"], def: "1D" },
  "3Y": { iv: ["1D", "1W", "1M"], def: "1D" },
  "5Y": { iv: ["1D", "1W", "1M"], def: "1W" },
  MAX: { iv: ["1D", "1W", "1M"], def: "1M" },
};
const IV_LABEL = { "1m": "1 min", "5m": "5 min", "15m": "15 min", "30m": "30 min", "1h": "1 hour", "1D": "1 day", "1W": "1 week", "1M": "1 month" };

const TYPES = [
  ["candles", "Candles"],
  ["heikin", "Heikin Ashi"],
  ["bars", "Bars (OHLC)"],
  ["line", "Line"],
  ["area", "Area"],
  ["baseline", "Baseline"],
];

const IND = [
  ["vol", "Volume", "Traded shares per candle"],
  ["dma20", "DMA 20", "20-period simple moving average"],
  ["dma50", "DMA 50", "50-period simple moving average"],
  ["dma200", "DMA 200", "200-period simple moving average (long-term trend)"],
  ["ema", "EMA 9 / 21", "Exponential moving averages – react faster than DMA"],
  ["bb", "Bollinger Bands", "20-period SMA ± 2 standard deviations"],
  ["vwap", "VWAP", "Volume-weighted average price, resets daily (intraday)"],
  ["st", "Supertrend", "ATR-based trend line (10, 3)"],
  ["rsi", "RSI (14)", "Momentum 0–100; >70 overbought, <30 oversold"],
  ["macd", "MACD", "12/26 EMA difference with 9-period signal"],
];
const DEFAULT_IND = { vol: true, dma50: true, dma200: true };
// Indicator line colours come from the theme's chart tokens (see styles.css).
const SERIES_TOKEN = { dma20: "chart-3", dma50: "chart-1", dma200: "chart-2", ema9: "chart-4", ema21: "chart-5", bb: "chart-7", vwap: "chart-6", rsi: "chart-7", macd: "chart-1", signal: "chart-6" };
const COLORS = Object.fromEntries(Object.entries(SERIES_TOKEN).map(([k, t]) => [k, `var(--${t})`])); // for CSS legends
const seriesColors = () => {
  const t = themeTokens(...new Set(Object.values(SERIES_TOKEN)));
  return Object.fromEntries(Object.entries(SERIES_TOKEN).map(([k, n]) => [k, t[n]]));
};

function load(key, fallback) {
  try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; } catch { return fallback; }
}
function save(key, v) { try { localStorage.setItem(key, JSON.stringify(v)); } catch { /* storage blocked */ } }

function themeColors() {
  const t = themeTokens("muted-foreground", "chart-grid", "card", "success", "danger", "primary");
  return { text: t["muted-foreground"], grid: t["chart-grid"], bg: t.card, up: t.success, down: t.danger, accent: t.primary };
}

const fmtTime = (t, intraday) => {
  const d = new Date(t * 1000); // already IST-shifted → read as UTC
  const o = { timeZone: "UTC", day: "2-digit", month: "short", year: intraday ? undefined : "numeric" };
  const s = d.toLocaleDateString("en-IN", o);
  return intraday ? `${s} ${d.toLocaleTimeString("en-IN", { timeZone: "UTC", hour: "2-digit", minute: "2-digit", hour12: false })}` : s;
};

export default function TradingChart({ company, prevClose }) {
  const [range, setRange] = useState(() => load("tc.range", "1D"));
  const [interval, setIntervalV] = useState(() => load("tc.iv", RANGES[load("tc.range", "1D")]?.def || "5m"));
  const [type, setType] = useState(() => load("tc.type", "candles"));
  const [ind, setInd] = useState(() => load("tc.ind", DEFAULT_IND));
  const [menu, setMenu] = useState(false);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [hover, setHover] = useState(null);
  const theme = useTheme();

  const mainEl = useRef(null), rsiEl = useRef(null), macdEl = useRef(null);
  const rangeRef = useRef(null); // keep zoom when only styling/indicators change

  useEffect(() => save("tc.range", range), [range]);
  useEffect(() => save("tc.iv", interval), [interval]);
  useEffect(() => save("tc.type", type), [type]);
  useEffect(() => save("tc.ind", ind), [ind]);

  useEffect(() => {
    if (!menu) return;
    const k = (e) => e.key === "Escape" && setMenu(false);
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [menu]);

  const pickRange = (r) => {
    setRange(r);
    if (!RANGES[r].iv.includes(interval)) setIntervalV(RANGES[r].def);
  };
  const iv = RANGES[range].iv.includes(interval) ? interval : RANGES[range].def;

  // Fetch candles; refresh intraday candles every 30 s while the market is open
  useEffect(() => {
    let alive = true;
    rangeRef.current = null;
    setLoading(true);
    const get = () => api.candles(company, range, iv)
      .then((d) => alive && setData(d))
      .catch(() => alive && setData({ candles: [] }))
      .finally(() => alive && setLoading(false));
    get();
    const intraday = iv.endsWith("m") || iv === "1h";
    const t = setInterval(() => {
      if (intraday && marketStatus().open && document.visibilityState === "visible") get();
    }, 30_000);
    return () => { alive = false; clearInterval(t); };
  }, [company, range, iv]);

  const bars = useMemo(() => {
    const c = data?.candles || [];
    return type === "heikin" ? heikinAshi(c) : c;
  }, [data, type]);

  // Build / rebuild charts
  useEffect(() => {
    if (!mainEl.current || bars.length < 2) return;
    const col = themeColors();
    const SC = seriesColors();
    const intraday = !!data?.intraday;
    const base = (el, h) => createChart(el, {
      height: h, autoSize: true,
      layout: { background: { color: "transparent" }, textColor: col.text, fontSize: 11, fontFamily: "inherit" },
      grid: { vertLines: { color: col.grid, style: 1 }, horzLines: { color: col.grid, style: 1 } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, timeVisible: intraday, secondsVisible: false, rightOffset: 4 },
      crosshair: { mode: CrosshairMode.Normal },
      localization: { priceFormatter: (p) => p.toLocaleString("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 }) },
    });
    const raw = data.candles;
    const charts = [];
    const main = base(mainEl.current, mainEl.current.clientHeight || 400);
    charts.push(main);

    const upC = col.up, dnC = col.down;
    let price;
    if (type === "candles" || type === "heikin") {
      price = main.addCandlestickSeries({ upColor: upC, downColor: dnC, borderUpColor: upC, borderDownColor: dnC, wickUpColor: upC, wickDownColor: dnC });
      price.setData(bars);
    } else if (type === "bars") {
      price = main.addBarSeries({ upColor: upC, downColor: dnC, thinBars: false });
      price.setData(bars);
    } else if (type === "line") {
      price = main.addLineSeries({ color: col.accent, lineWidth: 2 });
      price.setData(bars.map((b) => ({ time: b.time, value: b.close })));
    } else if (type === "area") {
      price = main.addAreaSeries({ lineColor: col.accent, topColor: col.accent + "55", bottomColor: col.accent + "05", lineWidth: 2 });
      price.setData(bars.map((b) => ({ time: b.time, value: b.close })));
    } else {
      const bv = range === "1D" && prevClose ? prevClose : raw[0].close;
      price = main.addBaselineSeries({ baseValue: { type: "price", price: bv }, topLineColor: upC, bottomLineColor: dnC,
        topFillColor1: upC + "40", topFillColor2: upC + "05", bottomFillColor1: dnC + "05", bottomFillColor2: dnC + "40", lineWidth: 2 });
      price.setData(bars.map((b) => ({ time: b.time, value: b.close })));
    }
    if (range === "1D" && prevClose) {
      price.createPriceLine({ price: prevClose, color: col.text, lineStyle: 2, lineWidth: 1, axisLabelVisible: true, title: "Prev close" });
    }

    const line = (d, color, w = 1.5, extra = {}) => {
      const s = main.addLineSeries({ color, lineWidth: w, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, ...extra });
      s.setData(d);
      return s;
    };
    if (ind.dma20) line(sma(raw, 20), SC.dma20);
    if (ind.dma50) line(sma(raw, 50), SC.dma50);
    if (ind.dma200) line(sma(raw, 200), SC.dma200, 2);
    if (ind.ema) { line(ema(raw, 9), SC.ema9); line(ema(raw, 21), SC.ema21); }
    if (ind.bb) {
      const b = bollinger(raw);
      line(b.upper, SC.bb, 1); line(b.lower, SC.bb, 1); line(b.mid, SC.bb, 1, { lineStyle: 2 });
    }
    if (ind.vwap && intraday) line(vwap(raw), SC.vwap, 2);
    if (ind.st) { const s = supertrend(raw); line(s.up, upC, 2); line(s.down, dnC, 2); }
    if (ind.vol) {
      const v = main.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false });
      main.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
      v.setData(raw.map((b) => ({ time: b.time, value: b.volume, color: (b.close >= b.open ? upC : dnC) + "66" })));
    }
    main.priceScale("right").applyOptions({ scaleMargins: { top: 0.08, bottom: ind.vol ? 0.22 : 0.08 } });

    // Lower panes share the main time axis via a whitespace series covering every bar
    const pane = (el) => {
      const c = base(el, el.clientHeight || 130);
      c.addLineSeries({ visible: false }).setData(raw.map((b) => ({ time: b.time })));
      charts.push(c);
      return c;
    };
    if (ind.rsi && rsiEl.current) {
      const c = pane(rsiEl.current);
      const s = c.addLineSeries({ color: SC.rsi, lineWidth: 1.5, priceLineVisible: false });
      s.setData(rsi(raw));
      [70, 30].forEach((p) => s.createPriceLine({ price: p, color: col.text, lineStyle: 2, lineWidth: 1, axisLabelVisible: false }));
    }
    if (ind.macd && macdEl.current) {
      const c = pane(macdEl.current);
      const m = macd(raw);
      c.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false })
        .setData(m.hist.map((p) => ({ ...p, color: (p.value >= 0 ? upC : dnC) + "99" })));
      c.addLineSeries({ color: SC.macd, lineWidth: 1.5, priceLineVisible: false }).setData(m.macd);
      c.addLineSeries({ color: SC.signal, lineWidth: 1.5, priceLineVisible: false }).setData(m.signal);
    }

    // Sync zoom/scroll across panes
    let syncing = false;
    charts.forEach((c) => c.timeScale().subscribeVisibleLogicalRangeChange((r) => {
      if (syncing || !r) return;
      syncing = true;
      charts.forEach((o) => o !== c && o.timeScale().setVisibleLogicalRange(r));
      syncing = false;
      if (c === main) rangeRef.current = r;
    }));

    if (rangeRef.current) main.timeScale().setVisibleLogicalRange(rangeRef.current);
    else if (data.from) main.timeScale().setVisibleRange({ from: data.from, to: raw[raw.length - 1].time });
    else main.timeScale().fitContent();

    main.subscribeCrosshairMove((p) => {
      if (!p?.time) { setHover(null); return; }
      const i = raw.findIndex((b) => b.time === p.time);
      if (i >= 0) setHover(i);
    });
    return () => charts.forEach((c) => c.remove());
  }, [bars, data, type, ind, theme, range, prevClose]);

  const raw = data?.candles || [];
  const hi = hover != null && raw[hover] ? hover : raw.length - 1;
  const bar = raw[hi];
  const prev = hi > 0 ? raw[hi - 1].close : null;
  const chg = bar && prev ? bar.close - prev : null;

  // Change over the visible timeframe
  const fromIdx = data?.from ? Math.max(0, raw.findIndex((b) => b.time >= data.from)) : 0;
  const baseP = range === "1D" && prevClose ? prevClose : raw[fromIdx]?.close;
  const last = raw[raw.length - 1]?.close;
  const rchg = last != null && baseP ? last - baseP : null;

  return (
    <section className="card tchart">
      <div className="tc-bar">
        <div className="range-tabs" role="tablist" aria-label="Timeframe">
          {Object.keys(RANGES).map((r) => (
            <button key={r} className={r === range ? "on" : ""} onClick={() => pickRange(r)}>{r}</button>
          ))}
        </div>
        <div className="tc-controls">
          <label className="tc-select" title="Candle interval">
            <select value={iv} onChange={(e) => setIntervalV(e.target.value)}>
              {RANGES[range].iv.map((i) => <option key={i} value={i}>{IV_LABEL[i]}</option>)}
            </select>
          </label>
          <label className="tc-select" title="Chart type">
            <select value={type} onChange={(e) => setType(e.target.value)}>
              {TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </label>
          <div className="tc-menu-wrap">
            <button className={`tc-btn ${menu ? "on" : ""}`} onClick={() => setMenu(!menu)} aria-expanded={menu}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M3 17l6-6 4 4 8-8" /></svg>
              Indicators{Object.values(ind).filter(Boolean).length ? ` · ${Object.values(ind).filter(Boolean).length}` : ""}
            </button>
            {menu && (
              <>
                <div className="tc-scrim" onClick={() => setMenu(false)} />
                <div className="tc-menu" role="menu">
                  {IND.map(([k, l, d]) => (
                    <label key={k} className="tc-opt">
                      <input type="checkbox" checked={!!ind[k]} onChange={(e) => setInd({ ...ind, [k]: e.target.checked })} />
                      <span><b>{l}</b><small>{k === "vwap" && !data?.intraday ? "Intraday intervals only" : d}</small></span>
                    </label>
                  ))}
                  <button className="link-btn" onClick={() => setInd(DEFAULT_IND)}>Reset to default</button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      <div className="tc-legend">
        {bar ? (
          <>
            <span className="muted">{fmtTime(bar.time, data?.intraday)}</span>
            <span>O <b>{fmt(bar.open)}</b></span>
            <span>H <b>{fmt(bar.high)}</b></span>
            <span>L <b>{fmt(bar.low)}</b></span>
            <span>C <b className={chg == null ? "" : chg >= 0 ? "up" : "down"}>{fmt(bar.close)}</b></span>
            <span>Vol <b>{abbr(bar.volume)}</b></span>
            {hover == null && rchg != null && (
              <span className={rchg >= 0 ? "up" : "down"}>
                {rchg >= 0 ? "+" : ""}{fmt(rchg)} ({rchg >= 0 ? "+" : ""}{((rchg / baseP) * 100).toFixed(2)}%) · {range}
              </span>
            )}
          </>
        ) : <span className="muted">&nbsp;</span>}
        <span className="tc-keys">
          {ind.dma20 && <i style={{ "--c": COLORS.dma20 }}>DMA 20</i>}
          {ind.dma50 && <i style={{ "--c": COLORS.dma50 }}>DMA 50</i>}
          {ind.dma200 && <i style={{ "--c": COLORS.dma200 }}>DMA 200</i>}
          {ind.ema && <><i style={{ "--c": COLORS.ema9 }}>EMA 9</i><i style={{ "--c": COLORS.ema21 }}>EMA 21</i></>}
          {ind.bb && <i style={{ "--c": COLORS.bb }}>BB 20,2</i>}
          {ind.vwap && data?.intraday && <i style={{ "--c": COLORS.vwap }}>VWAP</i>}
          {ind.st && <i style={{ "--c": "var(--up)" }}>Supertrend 10,3</i>}
        </span>
      </div>

      <div className={`tc-body ${loading ? "dim" : ""}`}>
        {raw.length > 1 ? (
          <>
            <div ref={mainEl} className="tc-main" />
            {ind.rsi && <div className="tc-pane"><span className="tc-pane-label">RSI 14</span><div ref={rsiEl} className="tc-sub" /></div>}
            {ind.macd && <div className="tc-pane"><span className="tc-pane-label">MACD 12,26,9</span><div ref={macdEl} className="tc-sub" /></div>}
          </>
        ) : (
          <div className="empty tc-main">{loading ? <span className="spinner" /> : "No price data for this timeframe"}</div>
        )}
      </div>
    </section>
  );
}
