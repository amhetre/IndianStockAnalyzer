import { useEffect, useMemo, useState } from "react";
import { Area, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, fmt } from "../api.js";

const GROUPS = ["Trend", "Momentum", "Volatility", "Volume", "Pattern"];
const toneOf = (o) => (o === "rise" ? "up" : o === "fall" ? "down" : "mid");
const viewTone = (v) => (v === "Bullish" ? "up" : v === "Bearish" ? "down" : "flat");

function Gauge({ score }) {
  const p = (score + 100) / 2; // 0..100
  return (
    <div className="pj-gauge">
      <div className="pj-gauge-track"><span className="pj-gauge-dot" style={{ left: `${p}%` }} /></div>
      <div className="pj-gauge-labels"><span>Bearish −100</span><span>0</span><span>+100 Bullish</span></div>
    </div>
  );
}

function Tip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  const d = new Date(p.t).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  return (
    <div className="chart-tip">
      <span>{d}{p.mid != null && p.close == null ? " · projected" : ""}</span>
      {p.close != null && <b>₹{fmt(p.close)}</b>}
      {p.mid != null && p.close == null && (
        <>
          <b>₹{fmt(p.mid)} central</b>
          <span>68%: ₹{fmt(p.band68[0])} – ₹{fmt(p.band68[1])}</span>
          <span>95%: ₹{fmt(p.band95[0])} – ₹{fmt(p.band95[1])}</span>
        </>
      )}
    </div>
  );
}

function ConeChart({ r }) {
  const data = useMemo(() => {
    const m = new Map(r.history.map((h) => [h.t, { ...h }]));
    r.path.forEach((p) => m.set(p.t, { ...(m.get(p.t) || {}), ...p }));
    return [...m.values()];
  }, [r]);
  const vals = data.flatMap((d) => [d.close, d.band95?.[0], d.band95?.[1]]).filter((v) => v != null);
  const lo = Math.min(...vals), hi = Math.max(...vals), pad = (hi - lo) * 0.05;
  const color = r.outlook === "rise" ? "var(--up)" : r.outlook === "fall" ? "var(--down)" : "var(--mid)";
  return (
    <ResponsiveContainer width="100%" height={340}>
      <ComposedChart data={data} margin={{ top: 10, right: 4, left: 0, bottom: 0 }}>
        <XAxis dataKey="t" minTickGap={60} tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} axisLine={false} tickLine={false}
          tickFormatter={(t) => new Date(t).toLocaleDateString("en-IN", { month: "short", year: "2-digit" })} />
        <YAxis domain={[lo - pad, hi + pad]} orientation="right" width={64} tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
          axisLine={false} tickLine={false} tickFormatter={(v) => Math.round(v).toLocaleString("en-IN")} />
        <Tooltip content={<Tip />} cursor={{ stroke: "var(--muted-foreground)", strokeDasharray: "2 3" }} />
        <Area dataKey="band95" stroke="none" fill={color} fillOpacity={0.1} isAnimationActive={false} />
        <Area dataKey="band68" stroke="none" fill={color} fillOpacity={0.2} isAnimationActive={false} />
        <Line dataKey="sma50" stroke="var(--chart-1)" strokeWidth={1.2} dot={false} isAnimationActive={false} />
        <Line dataKey="sma200" stroke="var(--chart-2)" strokeWidth={1.2} dot={false} isAnimationActive={false} />
        <Line dataKey="close" stroke="var(--text)" strokeWidth={1.8} dot={false} isAnimationActive={false} />
        <Line dataKey="mid" stroke={color} strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
        {r.support.slice(0, 1).map((s) => (
          <ReferenceLine key="s" y={s.price} stroke="var(--up)" strokeDasharray="2 4"
            label={{ value: `Support ₹${fmt(s.price)}`, position: "insideBottom", fontSize: 11, fill: "var(--up)" }} />
        ))}
        {r.resistance.slice(0, 1).map((s) => (
          <ReferenceLine key="r" y={s.price} stroke="var(--down)" strokeDasharray="2 4"
            label={{ value: `Resistance ₹${fmt(s.price)}`, position: "insideTopLeft", fontSize: 11, fill: "var(--down)" }} />
        ))}
        <ReferenceLine x={r.as_of} stroke="var(--muted-foreground)" strokeDasharray="3 3" />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export default function Projection({ company }) {
  const [r, setR] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let alive = true;
    setR(null); setErr(null);
    api.projection(company).then((x) => alive && setR(x)).catch((e) => alive && setErr(e.message));
    return () => { alive = false; };
  }, [company]);

  if (err) return <div className="card error-box big"><h3>Projection failed</h3><p>{err}</p></div>;
  if (!r) return <div className="card pj-loading"><span className="spinner" /> Reading the chart…</div>;
  if (!r.available) return <div className="card error-box big"><h3>Projection unavailable</h3><p>{r.reason}</p></div>;

  const t = toneOf(r.outlook);
  const bt = r.backtest;
  return (
    <div className="pj">
      <section className={`card pj-hero ${t}`}>
        <div className="pj-verdict">
          <span className="muted">Chart outlook · as of {r.as_of}</span>
          <h2 className={t}>{r.outlook === "rise" ? "▲" : r.outlook === "fall" ? "▼" : "◆"} {r.verdict}</h2>
          <div className="pj-chips">
            <span className="chip">Score {r.score > 0 ? "+" : ""}{r.score}</span>
            <span className="chip">{r.confidence} confidence</span>
            <span className="chip up-chip">{r.bullish_count} bullish</span>
            <span className="chip down-chip">{r.bearish_count} bearish</span>
            <span className="chip">{r.neutral_count} neutral</span>
          </div>
          <Gauge score={r.score} />
        </div>
        <div className="pj-horizons">
          {r.horizons.map((h) => (
            <div key={h.label} className="pj-h">
              <span className="muted">{h.label} target</span>
              <b>₹{fmt(h.target)}</b>
              <small className={h.exp_ret_pct >= 0 ? "up" : "down"}>{h.exp_ret_pct >= 0 ? "+" : ""}{h.exp_ret_pct}%</small>
              <small className="muted">₹{fmt(h.low68)} – ₹{fmt(h.high68)}</small>
              <div className="pj-prob" title="Probability the price ends higher than today">
                <span style={{ width: `${h.prob_up}%` }} />
              </div>
              <small><b className={h.prob_up >= 50 ? "up" : "down"}>{h.prob_up}%</b> chance up</small>
            </div>
          ))}
        </div>
      </section>

      <section className="card pj-summary"><p>{r.summary}</p></section>

      <section className="card pj-chart">
        <div className="pj-chart-head">
          <h3 className="section-title">Projected price cone (next 3 months)</h3>
          <div className="tc-keys">
            <i style={{ "--c": "var(--text)" }}>Close</i>
            <i style={{ "--c": "var(--chart-1)" }}>50-DMA</i>
            <i style={{ "--c": "var(--chart-2)" }}>200-DMA</i>
            <i style={{ "--c": "var(--muted-foreground)" }}>Central path · shaded 68% / 95% range</i>
          </div>
        </div>
        <ConeChart r={r} />
      </section>

      <div className="pj-grid">
        <section className="card pj-signals">
          <h3 className="section-title">What the chart is saying</h3>
          {GROUPS.filter((g) => r.signals.some((s) => s.group === g)).map((g) => (
            <div key={g} className="pj-group">
              <h4>{g === "Pattern" ? "Chart patterns" : g}
                <small className="muted"> · {r.groups[g].bull} bullish / {r.groups[g].bear} bearish</small></h4>
              {r.signals.filter((s) => s.group === g).map((s) => (
                <div key={s.name} className="pj-sig">
                  <span className={`pj-tag ${viewTone(s.view)}`}>{s.view}</span>
                  <div>
                    <b>{s.name}</b> <span className="muted">— {s.value}</span>
                    <p>{s.text}</p>
                  </div>
                </div>
              ))}
            </div>
          ))}
        </section>

        <aside className="pj-side">
          <section className="card">
            <h3 className="section-title">Key levels</h3>
            <dl className="kv">
              {r.resistance.slice().reverse().map((x) => (
                <div key={`r${x.price}`}><dt className="down">Resistance</dt><dd>₹{fmt(x.price)} <small className="muted">({x.dist_pct > 0 ? "+" : ""}{x.dist_pct}%)</small></dd></div>
              ))}
              <div><dt><b>Current</b></dt><dd><b>₹{fmt(r.price)}</b></dd></div>
              {r.support.map((x) => (
                <div key={`s${x.price}`}><dt className="up">Support</dt><dd>₹{fmt(x.price)} <small className="muted">({x.dist_pct}%)</small></dd></div>
              ))}
              <div><dt>View invalidated beyond</dt><dd>₹{fmt(r.invalidation)}</dd></div>
              <div><dt>ATR (14)</dt><dd>₹{fmt(r.atr)}</dd></div>
              <div><dt>Daily volatility</dt><dd>{r.daily_vol_pct}%</dd></div>
            </dl>
          </section>

          <section className="card">
            <h3 className="section-title">How reliable has this been?</h3>
            {bt.signals ? (
              <>
                <p className="pj-small">Same indicator score replayed on this stock's last ~3 years, checking the price {bt.horizon_days} trading days later.</p>
                <dl className="kv">
                  <div><dt>Overall hit rate</dt><dd><b className={bt.hit_rate >= 55 ? "up" : bt.hit_rate < 50 ? "down" : "mid"}>{bt.hit_rate}%</b> of {bt.signals}</dd></div>
                  <div><dt>"Rise" calls correct</dt><dd>{bt.bull_hit ?? "–"}% <small className="muted">({bt.bull_signals}, avg {bt.bull_avg_ret ?? "–"}%)</small></dd></div>
                  <div><dt>"Fall" calls correct</dt><dd>{bt.bear_hit ?? "–"}% <small className="muted">({bt.bear_signals}, avg {bt.bear_avg_ret ?? "–"}%)</small></dd></div>
                  <div><dt>Stock rose anyway</dt><dd>{bt.base_up_rate}% of months</dd></div>
                </dl>
                <p className="pj-small muted">A hit rate near 50% means the chart signal has had little edge on this stock; trust it less.</p>
              </>
            ) : <p className="muted">Not enough history to back-test.</p>}
          </section>
        </aside>
      </div>

      <p className="pj-disclaimer muted">
        Technical projection from past price and volume only. Ranges are statistical estimates, not guarantees; news, results and
        market moves can override any chart pattern. Not investment advice.
      </p>
    </div>
  );
}
