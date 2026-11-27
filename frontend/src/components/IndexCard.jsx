import { Area, AreaChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmt, fmtChg, fmtPct, tone } from "../api.js";

const timeFmt = (iso) =>
  new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Kolkata" });

function ChartTip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="chart-tip">
      <b>{fmt(p.v)}</b>
      <span>{timeFmt(p.t)} IST</span>
    </div>
  );
}

export default function IndexCard({ idx }) {
  const t = tone(idx.change);
  const color = t === "down" ? "var(--down)" : "var(--up)";
  const gid = `g-${idx.key}`;
  const pts = idx.points || [];
  const vals = pts.map((p) => p.v);
  const lo = Math.min(...vals, idx.prev_close ?? Infinity);
  const hi = Math.max(...vals, idx.prev_close ?? -Infinity);
  const pad = (hi - lo) * 0.08 || 1;
  const sessionDate = pts.length
    ? new Date(pts[pts.length - 1].t).toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "Asia/Kolkata" })
    : null;

  return (
    <section className="card index-card">
      <div className="index-head">
        <div>
          <h3>{idx.name}</h3>
          <div className="index-last">{fmt(idx.last)}</div>
          <div className={`delta ${t}`}>
            {fmtChg(idx.change)} ({fmtPct(idx.pct)})
          </div>
        </div>
        <dl className="ohlc">
          <div><dt>Open</dt><dd>{fmt(idx.open)}</dd></div>
          <div><dt>High</dt><dd>{fmt(idx.high)}</dd></div>
          <div><dt>Low</dt><dd>{fmt(idx.low)}</dd></div>
          <div><dt>Prev close</dt><dd>{fmt(idx.prev_close)}</dd></div>
        </dl>
      </div>
      <div className="index-chart">
        {pts.length > 1 ? (
          <ResponsiveContainer width="100%" height={190}>
            <AreaChart data={pts} margin={{ top: 6, right: 4, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.28} />
                  <stop offset="100%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="t" tickFormatter={timeFmt} minTickGap={48} tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                axisLine={false} tickLine={false} />
              <YAxis domain={[lo - pad, hi + pad]} orientation="right" width={62}
                tickFormatter={(v) => Math.round(v).toLocaleString("en-IN")}
                tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} axisLine={false} tickLine={false} />
              {idx.prev_close && (
                <ReferenceLine y={idx.prev_close} stroke="var(--muted-foreground)" strokeDasharray="3 4" strokeOpacity={0.7} />
              )}
              <Tooltip content={<ChartTip />} cursor={{ stroke: "var(--muted-foreground)", strokeDasharray: "2 3" }} />
              <Area type="monotone" dataKey="v" stroke={color} strokeWidth={2} fill={`url(#${gid})`}
                isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="empty">Intraday chart unavailable</div>
        )}
      </div>
      <div className="index-foot">
        {sessionDate && <>Intraday · {sessionDate} · dashed line = previous close</>}
      </div>
    </section>
  );
}
