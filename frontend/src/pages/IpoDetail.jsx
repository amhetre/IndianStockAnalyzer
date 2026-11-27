import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api.js";

const cr = (v) => (v == null ? "–" : `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 2 })} Cr`);

function Section({ title, sub, children, id }) {
  return (
    <section className="card ipo-sec" id={id}>
      <h3 className="section-title">{title}</h3>
      {sub && <p className="muted sec-sub">{sub}</p>}
      {children}
    </section>
  );
}

function Table({ header, rows, numFrom = 1 }) {
  if (!rows?.length) return null;
  return (
    <div className="table-scroll">
      <table>
        {header && (
          <thead>
            <tr>{header.map((h, i) => <th key={i} className={i >= numFrom ? "num" : ""}>{h}</th>)}</tr>
          </thead>
        )}
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={/^total$/i.test(r[0]) ? "total-row" : ""}>
              {r.map((c, j) => <td key={j} className={j >= numFrom ? "num" : ""}>{c}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Fact({ label, value, hint }) {
  return (
    <div className="fact">
      <span>{label}</span>
      <b>{value}</b>
      {hint && <small>{hint}</small>}
    </div>
  );
}

// "Repayment of borrowings : 247.94 Cr" → { text, amount }
function splitObject(s) {
  const m = s.match(/^(.*?)\s*:\s*(?:₹\s*)?([\d,.]+)\s*Cr\.?\s*$/i);
  return m ? { text: m[1], amount: parseFloat(m[2].replace(/,/g, "")) } : { text: s.replace(/\s*:\s*-\s*Cr$/i, ""), amount: null };
}

const SERIES = [
  { key: "revenue", label: "Total income", match: ["total income", "revenue"], color: "var(--accent)" },
  { key: "pat", label: "Profit after tax", match: ["profit after tax", "pat"], color: "var(--up)" },
  { key: "borrowing", label: "Borrowings", match: ["borrowing", "debt"], color: "var(--down)" },
  { key: "networth", label: "Net worth", match: ["net worth"], color: "var(--info)" },
];

function FinancialsChart({ fin }) {
  const find = (names) => fin.rows.find((r) => names.some((n) => r.label.toLowerCase().includes(n)));
  // oldest → newest, full years only for the trend (stub quarters distort the bars)
  const idx = fin.periods.map((p, i) => i).filter((i) => /mar/i.test(fin.periods[i])).reverse();
  const data = idx.map((i) => {
    const o = { period: `FY${fin.periods[i].slice(-2)}` };
    SERIES.forEach((s) => { o[s.key] = find(s.match)?.values[i] ?? null; });
    return o;
  });
  if (data.length < 2) return null;
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barGap={2}>
        <CartesianGrid vertical={false} stroke="var(--border)" />
        <XAxis dataKey="period" tick={{ fontSize: 12, fill: "var(--muted-foreground)" }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} axisLine={false} tickLine={false} width={56}
          tickFormatter={(v) => v.toLocaleString("en-IN")} />
        <Tooltip formatter={(v) => cr(v)} contentStyle={{ background: "var(--popover)", color: "var(--foreground)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {SERIES.map((s) => <Bar key={s.key} dataKey={s.key} name={s.label} fill={s.color} radius={[4, 4, 0, 0]} />)}
      </BarChart>
    </ResponsiveContainer>
  );
}

function GmpTrend({ rows }) {
  const data = [...rows].reverse().map((r) => ({ ...r, d: r.date.split(" ")[0].slice(0, 6) }));
  if (data.length < 2) return null;
  return (
    <ResponsiveContainer width="100%" height={180}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--border)" />
        <XAxis dataKey="d" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} axisLine={false} tickLine={false} width={44} tickFormatter={(v) => `₹${v}`} />
        <Tooltip formatter={(v, n) => (n === "gmp" ? [`₹${v}`, "GMP"] : [v, n])} labelFormatter={(_, p) => p?.[0]?.payload?.date}
          contentStyle={{ background: "var(--popover)", color: "var(--foreground)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }} />
        <Line type="monotone" dataKey="gmp" stroke="var(--accent)" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

function People({ title, list }) {
  if (!list?.length) return null;
  return (
    <div className="people">
      <h4>{title}</h4>
      <ul>
        {list.map((p, i) => (
          <li key={i}>
            <b>{p.name}</b>
            {(p.phone || p.email) && <small>{[p.phone, p.email].filter(Boolean).join(" · ")}</small>}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function IpoDetail() {
  const { slug } = useParams();
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    setD(null);
    setErr(null);
    fetch(`/api/ipo/${slug}`)
      .then(async (r) => (r.ok ? r.json() : Promise.reject(new Error((await r.json()).detail || `HTTP ${r.status}`))))
      .then(setD)
      .catch((e) => setErr(e.message));
  }, [slug]);

  useEffect(() => {
    document.title = d ? `${d.name} IPO · Stock Analyzer` : "IPO · Stock Analyzer";
  }, [d]);

  if (err)
    return (
      <div className="report">
        <div className="card error-box big"><h3>Couldn't load this IPO</h3><p>{err}</p><Link className="btn" to="/?tab=ipo">Back to IPOs</Link></div>
      </div>
    );
  if (!d)
    return (
      <div className="report">
        <div className="card progress"><div className="progress-head"><span className="spinner" /><h3>Loading IPO details…</h3></div></div>
      </div>
    );

  const v = d.valuation;
  const objects = d.objects.map(splitObject);
  const objTotal = objects.reduce((s, o) => s + (o.amount || 0), 0);
  const det = d.details;
  const latestGmp = d.gmp_trend[0];
  const sizeTone = { SME: "sme", "Small cap": "bse", "Mid cap": "nse", "Large cap": "main" }[d.size.label] || "";

  return (
    <div className="report ipo-detail">
      <Link to="/?tab=ipo" className="back-link">← All IPOs</Link>

      <div className="card report-head">
        <div className="report-id">
          <h1>{d.name} <span className="muted thin">IPO</span></h1>
          <div className="codes">
            {d.status && <span className={`chip ${/open/i.test(d.status) ? "main" : ""}`}>{d.status}</span>}
            <span className={`chip ${sizeTone}`} title={d.size.note}>{d.size.label}</span>
            <span className="chip">{d.board}</span>
            {d.sector && <span className="chip nse">{d.sector}</span>}
            {d.listed_on && <span className="chip">Listing on {d.listed_on}</span>}
          </div>
        </div>
        <div className="actions">
          {d.website && <a className="btn ghost" href={d.website} target="_blank" rel="noreferrer">Company website</a>}
          {d.documents.map((doc) => (
            <a key={doc.label} className="btn ghost" href={doc.url} target="_blank" rel="noreferrer"
              title={`${doc.label} filings list on SEBI`}>{doc.label}</a>
          ))}
        </div>
      </div>

      <div className="facts-grid card">
        <Fact label="Price band" value={det["Price Band"] || det["Issue Price"] || "–"} />
        <Fact label="Issue size" value={cr(v.issue_size_cr)}
          hint={v.fresh_issue_cr != null ? `Fresh ${cr(v.fresh_issue_cr)} · OFS ${cr(v.ofs_cr || 0)}` : null} />
        <Fact label="Est. market cap" value={cr(v.market_cap_cr)} hint={v.basis} />
        <Fact label="P/E at upper band" value={v.pe != null ? `${v.pe}×` : "–"} />
        <Fact label="Total borrowings" value={cr(v.latest_borrowing_cr)} hint={d.financials.periods?.[0] ? `as of ${d.financials.periods[0]}` : null} />
        <Fact label="Net worth" value={cr(v.latest_net_worth_cr)} />
        <Fact label="Debt / Equity" value={v.debt_to_equity ?? "–"} />
        <Fact label="Lot size" value={det["Lot Size"] || "–"} hint={d.lots?.rows?.[0]?.[3] ? `Min. investment ${d.lots.rows[0][3]}` : null} />
        <Fact label="IPO dates" value={det["IPO Date"] || "–"} hint={det["Listing Date"] ? `Listing ${det["Listing Date"]}` : null} />
        {latestGmp && (
          <Fact label="Latest GMP" value={<span className={latestGmp.gmp > 0 ? "up" : latestGmp.gmp < 0 ? "down" : ""}>
            {latestGmp.gmp >= 0 ? "+" : ""}₹{latestGmp.gmp} ({latestGmp.gain_pct}%)</span>} hint={latestGmp.date} />
        )}
      </div>

      <div className="two-col">
        <Section title="What the business does">
          {d.about_company.length ? d.about_company.map((p, i) => <p key={i}>{p}</p>) : <p className="muted">No description published.</p>}
          {d.promoters && <p className="muted"><b>Promoters:</b> {d.promoters}</p>}
        </Section>
        <Section title="Size category" sub={d.size.note}>
          <div className={`size-badge ${sizeTone}`}>{d.size.label}</div>
          <p className="muted small">
            Mainboard companies are bucketed by estimated full market cap: Large ≥ ₹1,00,000 Cr, Mid ≥ ₹33,000 Cr,
            otherwise Small (approx. AMFI cut-offs). SME IPOs list on NSE Emerge / BSE SME.
          </p>
          {d.holding && <><h4>Shareholding</h4><Table header={d.holding.header} rows={d.holding.rows} /></>}
        </Section>
      </div>

      <Section title="Why they are raising money & where it will be used" sub="Objects of the issue, as stated in the offer document.">
        {objects.length ? (
          <ul className="objects">
            {objects.map((o, i) => (
              <li key={i}>
                <div className="obj-row"><span>{o.text}</span>{o.amount != null && <b>{cr(o.amount)}</b>}</div>
                {o.amount != null && objTotal > 0 && (
                  <span className="obj-bar"><span style={{ width: `${(o.amount / objTotal) * 100}%` }} /></span>
                )}
              </li>
            ))}
          </ul>
        ) : <p className="muted">Not published yet.</p>}
        {v.ofs_cr > 0 && (
          <p className="muted small">
            The Offer for Sale portion ({cr(v.ofs_cr)}) goes to the selling shareholders, not to the company.
          </p>
        )}
      </Section>

      {d.financials.rows?.length > 0 && (
        <Section title="Financial performance" sub="Restated financials from the offer document (₹ crore). Chart shows full financial years.">
          <FinancialsChart fin={d.financials} />
          <Table header={["", ...d.financials.periods]} rows={d.financials.rows.map((r) => [r.label, ...r.values.map((x) => (x == null ? "–" : x.toLocaleString("en-IN")))])} />
        </Section>
      )}

      {Object.keys(d.kpi).length > 0 && (
        <Section title="Key ratios (KPIs)">
          <div className="kpi-grid">
            {Object.entries(d.kpi).map(([k, val]) => <div key={k} className="fact"><span>{k}</span><b>{val}</b></div>)}
          </div>
        </Section>
      )}

      {d.peers && <Section title="Listed peers"><Table header={d.peers.header} rows={d.peers.rows} /></Section>}

      <div className="two-col">
        <Section title="Strengths">
          {d.strengths.length ? <ul className="bullets good">{d.strengths.map((s, i) => <li key={i}>{s}</li>)}</ul> : <p className="muted">–</p>}
        </Section>
        <Section title="Risks">
          {d.risks.length ? <ul className="bullets bad">{[...new Set(d.risks)].map((s, i) => <li key={i}>{s}</li>)}</ul> : <p className="muted">–</p>}
        </Section>
      </div>

      <Section title="Vendors, intermediaries & investors"
        sub="Who runs the issue and who has committed money. Supplier/customer concentration is disclosed in the RHP's “Our Business” and “Risk Factors” chapters.">
        <div className="people-grid">
          <People title="Book-running lead managers" list={d.lead_managers} />
          <People title="Registrar" list={d.registrar} />
          <People title="Market makers" list={d.market_makers} />
        </div>
        {d.anchors.length > 0 && (
          <>
            <h4>Anchor investors</h4>
            <Table header={["Investor", "Shares", "Allocation"]} rows={d.anchors} />
          </>
        )}
      </Section>

      <div className="two-col">
        {d.subscription && (
          <Section title="Subscription status"><Table header={d.subscription.header} rows={d.subscription.rows} /></Section>
        )}
        {d.gmp_trend.length > 1 && (
          <Section title="GMP trend" sub="Unofficial grey-market premium, day by day.">
            <GmpTrend rows={d.gmp_trend} />
          </Section>
        )}
      </div>

      <div className="two-col">
        {d.reservation && <Section title="Issue reservation"><Table header={d.reservation.header} rows={d.reservation.rows} /></Section>}
        {d.lots && <Section title="Lot size & investment"><Table header={d.lots.header} rows={d.lots.rows} /></Section>}
      </div>

      <p className="note">
        Source: <a href={d.source_url} target="_blank" rel="noreferrer">{d.source}</a> and the company's offer documents.
        Market cap and size category are estimates. Not a recommendation to apply.
      </p>
    </div>
  );
}
