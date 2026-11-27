import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { abbr, api, companyToQuery, fmt, fmtChg, fmtPct, marketStatus, tone } from "../api.js";
import AdSlot from "../components/AdSlot.jsx";

const open = (nav, r) => nav(`/report?${companyToQuery({ name: r.name, nse_symbol: r.symbol, yahoo_ticker: `${r.symbol}.NS` })}`);

function usePollMovers() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    let alive = true;
    const load = () => api.movers(25).then((d) => alive && (setData(d), setErr(null))).catch((e) => alive && setErr(e.message));
    load();
    const t = setInterval(() => document.visibilityState === "visible" && marketStatus().open && load(), 60_000);
    return () => { alive = false; clearInterval(t); };
  }, []);
  return [data, err];
}

// ---------------------------------------------------------------- NIFTY 50 list
const COLS = [
  ["symbol", "Symbol", false], ["name", "Company", false], ["last", "Price (₹)", true],
  ["pct", "% Change", true], ["change", "Change", true], ["volume", "Volume", true], ["value", "Traded value", true],
];

export function Stocks() {
  const nav = useNavigate();
  const [data, err] = usePollMovers();
  const [sort, setSort] = useState({ key: "symbol", dir: 1 });
  const [filter, setFilter] = useState("");
  useEffect(() => { document.title = "NIFTY 50 Stocks · Stock Analyzer"; }, []);

  const rows = useMemo(() => {
    const f = filter.trim().toLowerCase();
    const list = (data?.all || []).filter((r) => !f || r.symbol.toLowerCase().includes(f) || (r.name || "").toLowerCase().includes(f));
    const v = (r) => r[sort.key] ?? (typeof r[sort.key] === "string" ? "" : -Infinity);
    return [...list].sort((a, b) => (v(a) > v(b) ? 1 : v(a) < v(b) ? -1 : 0) * sort.dir);
  }, [data, sort, filter]);

  const by = (key, numeric) => setSort((s) => (s.key === key ? { key, dir: -s.dir } : { key, dir: numeric ? -1 : 1 }));

  return (
    <div>
      <div className="page-head">
        <h1>NIFTY 50 Stocks</h1>
        <p>All 50 companies in India's benchmark index, with today's price move. Click a stock for its full analysis.</p>
      </div>
      {err && <div className="error-box">{err}</div>}
      <section className="card" style={{ marginTop: 14 }}>
        <div className="table-tools">
          <input type="search" placeholder="Filter by symbol or name…" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter stocks" />
          {data && <span className="muted small-txt">{rows.length} stocks · {data.advances} up, {data.declines} down · {data.source}</span>}
        </div>
        {!data ? <div className="empty"><span className="spinner small" /> Loading…</div> : (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead><tr>
                <th className="rank">#</th>
                {COLS.map(([k, l, numeric]) => (
                  <th key={k} className={numeric ? "num" : undefined} aria-sort={sort.key === k ? (sort.dir > 0 ? "ascending" : "descending") : undefined}>
                    <button type="button" className={sort.key === k ? "on" : undefined} onClick={() => by(k, numeric)}>
                      {l}{sort.key === k ? (sort.dir > 0 ? " ▲" : " ▼") : ""}
                    </button>
                  </th>
                ))}
              </tr></thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={r.symbol} onClick={() => open(nav, r)}>
                    <td className="rank">{i + 1}</td>
                    <td className="sym">{r.symbol}</td>
                    <td className="name">{r.name !== r.symbol ? r.name : ""}</td>
                    <td className="num">{fmt(r.last)}</td>
                    <td className={`num ${tone(r.pct)}`}>{fmtPct(r.pct)}</td>
                    <td className={`num ${tone(r.change)}`}>{fmtChg(r.change)}</td>
                    <td className="num">{abbr(r.volume)}</td>
                    <td className="num">{abbr(r.value, { rupee: true })}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <AdSlot slot="home" />
    </div>
  );
}

// ---------------------------------------------------------------- market movers
const MOVER_TABS = [
  ["gainers", "Top Gainers", "NIFTY 50 stocks with the biggest rise today."],
  ["losers", "Top Losers", "NIFTY 50 stocks with the biggest fall today."],
  ["active", "Most Active", "NIFTY 50 stocks with the highest traded value today."],
];

export function Movers() {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const tab = MOVER_TABS.find(([k]) => k === params.get("tab"))?.[0] || "gainers";
  const [, title, desc] = MOVER_TABS.find(([k]) => k === tab);
  const [data, err] = usePollMovers();
  useEffect(() => { document.title = `${title} · Stock Analyzer`; }, [title]);
  const rows = data?.[tab] || [];

  return (
    <div>
      <div className="page-head">
        <h1>{title}</h1>
        <p>{desc} <span className="muted">{marketStatus().label}.</span></p>
      </div>
      <nav className="pills" aria-label="Movers">
        {MOVER_TABS.map(([k, l]) => (
          <button key={k} type="button" className={k === tab ? "on" : undefined}
            onClick={() => nav(k === "gainers" ? "/movers" : `/movers?tab=${k}`, { replace: true })}>{l}</button>
        ))}
      </nav>
      {err && <div className="error-box">{err}</div>}
      <section className="card">
        {!data ? <div className="empty"><span className="spinner small" /> Loading…</div>
          : rows.length === 0 ? <div className="empty">No data</div> : (
            <div className="data-table-wrap">
              <table className="data-table">
                <thead><tr>
                  <th className="rank">#</th><th>Symbol</th><th>Company</th><th className="num">Price (₹)</th>
                  <th className="num">% Change</th><th className="num">Change</th><th className="num">Volume</th><th className="num">Traded value</th>
                </tr></thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={r.symbol} onClick={() => open(nav, r)}>
                      <td className="rank">{i + 1}</td>
                      <td className="sym">{r.symbol}</td>
                      <td className="name">{r.name !== r.symbol ? r.name : ""}</td>
                      <td className="num">{fmt(r.last)}</td>
                      <td className="num"><span className={`pill-chg ${tone(r.pct)}`}>{fmtPct(r.pct)}</span></td>
                      <td className={`num ${tone(r.change)}`}>{fmtChg(r.change)}</td>
                      <td className="num">{abbr(r.volume)}</td>
                      <td className="num">{abbr(r.value, { rupee: true })}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </section>
      {data && <p className="note">Source: {data.source}. Updates every minute while the market is open.</p>}
      <AdSlot slot="home" />
    </div>
  );
}
