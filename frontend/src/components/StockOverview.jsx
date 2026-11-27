import { useEffect, useState } from "react";
import { Area, AreaChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { abbr, abbrCr, api, fmt } from "../api.js";

const RANGES = ["1D", "5D", "1M", "6M", "1Y", "5Y", "MAX"];

const num = (v, d = 2) => (v == null ? "–" : v.toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d }));
const pct = (v) => (v == null ? "–" : `${num(v)}%`);
const cr = (v) => abbrCr(v);
const vol = (v) => abbr(v);

function tickLabel(iso, range) {
  const d = new Date(iso);
  const o = { timeZone: "Asia/Kolkata" };
  if (range === "1D") return d.toLocaleTimeString("en-IN", { ...o, hour: "2-digit", minute: "2-digit", hour12: false });
  if (range === "5D" || range === "1M") return d.toLocaleDateString("en-IN", { ...o, day: "numeric", month: "short" });
  if (range === "6M" || range === "1Y") return d.toLocaleDateString("en-IN", { ...o, month: "short", year: "2-digit" });
  return d.toLocaleDateString("en-IN", { ...o, year: "numeric" });
}

function Tip({ active, payload, range }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  const d = new Date(p.t);
  const intraday = range === "1D" || range === "5D";
  return (
    <div className="chart-tip">
      <b>₹{fmt(p.v)}</b>
      <span>
        {d.toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric" })}
        {intraday && ` ${d.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false })}`}
      </span>
    </div>
  );
}

export function PriceChart({ company, prevClose }) {
  const [range, setRange] = useState("1D");
  const [hist, setHist] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .history(company, range)
      .then((h) => alive && setHist(h))
      .catch(() => alive && setHist({ points: [] }))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [company, range]);

  const pts = hist?.points || [];
  const first = pts[0]?.v;
  const last = pts[pts.length - 1]?.v;
  const base = range === "1D" && prevClose ? prevClose : first;
  const chg = last != null && base ? last - base : null;
  const up = chg == null || chg >= 0;
  const color = up ? "var(--up)" : "var(--down)";
  const vals = pts.map((p) => p.v).concat(range === "1D" && prevClose ? [prevClose] : []);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = (hi - lo) * 0.08 || 1;

  return (
    <section className="card chart-card">
      <div className="chart-top">
        <div className="range-tabs">
          {RANGES.map((r) => (
            <button key={r} className={r === range ? "on" : ""} onClick={() => setRange(r)}>{r}</button>
          ))}
        </div>
        {chg != null && (
          <span className={`range-chg ${up ? "up" : "down"}`}>
            {up ? "+" : ""}{num(chg)} ({up ? "+" : ""}{num((chg / base) * 100)}%) <span className="muted">{range}</span>
          </span>
        )}
      </div>
      <div className={`chart-body ${loading ? "dim" : ""}`}>
        {pts.length > 1 ? (
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={pts} margin={{ top: 8, right: 4, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="pg" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.25} />
                  <stop offset="100%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="t" tickFormatter={(t) => tickLabel(t, range)} minTickGap={50}
                tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} axisLine={false} tickLine={false} />
              <YAxis domain={[lo - pad, hi + pad]} orientation="right" width={64}
                tickFormatter={(v) => Math.round(v).toLocaleString("en-IN")}
                tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} axisLine={false} tickLine={false} />
              {range === "1D" && prevClose && (
                <ReferenceLine y={prevClose} stroke="var(--muted-foreground)" strokeDasharray="3 4" strokeOpacity={0.7} />
              )}
              <Tooltip content={<Tip range={range} />} cursor={{ stroke: "var(--muted-foreground)", strokeDasharray: "2 3" }} />
              <Area type="monotone" dataKey="v" stroke={color} strokeWidth={2} fill="url(#pg)" isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="empty" style={{ height: 280 }}>{loading ? <span className="spinner" /> : "No price data for this range"}</div>
        )}
      </div>
    </section>
  );
}

function RangeBar({ lo, hi, val }) {
  if (lo == null || hi == null || val == null || hi <= lo) return null;
  const p = Math.min(100, Math.max(0, ((val - lo) / (hi - lo)) * 100));
  return (
    <div className="rangebar">
      <span className="rb-track"><span className="rb-dot" style={{ left: `${p}%` }} /></span>
      <span className="rb-labels"><span>{fmt(lo)}</span><span>{fmt(hi)}</span></span>
    </div>
  );
}

export function KeyStats({ q, live }) {
  const rows = [
    ["Market cap", cr(q.market_cap_cr)],
    ["P/E (TTM)", num(q.pe)],
    ["P/B", num(q.pb)],
    ["EPS (TTM)", q.eps == null ? "–" : `₹${num(q.eps)}`],
    ["Book value", q.book_value == null ? "–" : `₹${num(q.book_value)}`],
    ["Dividend yield", pct(q.dividend_yield)],
    ["ROE", pct(q.roe)],
    ["Debt / Equity", q.debt_to_equity == null ? "–" : num(q.debt_to_equity / 100)],
    ["Beta", num(q.beta)],
    [live ? "Volume (live)" : "Day's volume", vol(q.volume)],
    ["Traded value ≈", q.volume && q.price ? abbr(q.volume * q.price, { rupee: true }) : "–"],
    ["Avg volume", vol(q.avg_volume)],
    ["Open", fmt(q.open)],
    ["Prev close", fmt(q.prev_close)],
  ];
  return (
    <section className="card stats-card">
      <h3 className="section-title">Key stats</h3>
      <div className="range-block">
        <div>
          <span className="muted">Day range</span>
          <RangeBar lo={q.day_low} hi={q.day_high} val={q.price} />
        </div>
        <div>
          <span className="muted">52-week range</span>
          <RangeBar lo={q.low_52w} hi={q.high_52w} val={q.price} />
        </div>
      </div>
      <dl className="kv">
        {rows.map(([k, v]) => (
          <div key={k}><dt>{k}</dt><dd>{v}</dd></div>
        ))}
      </dl>
    </section>
  );
}

export function About({ q }) {
  const [open, setOpen] = useState(false);
  if (!q.summary) return null;
  return (
    <section className="card about">
      <h3 className="section-title">About {q.name}</h3>
      <p className={open ? "" : "clamp"}>{q.summary}</p>
      <button className="link-btn" onClick={() => setOpen(!open)}>{open ? "Show less" : "Read more"}</button>
    </section>
  );
}
