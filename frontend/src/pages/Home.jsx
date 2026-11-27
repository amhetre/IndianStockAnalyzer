import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { api, companyToQuery, fmt, fmtPct, marketStatus, tone } from "../api.js";
import AdSlot from "../components/AdSlot.jsx";
import IndexCard from "../components/IndexCard.jsx";
import NewsList from "../components/NewsList.jsx";
import SearchBox from "../components/SearchBox.jsx";

const POPULAR = [
  { name: "Reliance Industries Ltd", nse_symbol: "RELIANCE" },
  { name: "Tata Consultancy Services Ltd", nse_symbol: "TCS" },
  { name: "HDFC Bank Ltd", nse_symbol: "HDFCBANK" },
  { name: "Infosys Ltd", nse_symbol: "INFY" },
  { name: "ITC Ltd", nse_symbol: "ITC" },
  { name: "Larsen & Toubro Ltd", nse_symbol: "LT" },
  { name: "Demo Industries Ltd (SYNTHETIC)", nse_symbol: "DEMOIND", demo: true, label: "Demo" },
];

const REFRESH_MS = 60_000;

function MiniMovers({ title, rows, to }) {
  const nav = useNavigate();
  return (
    <section className="card">
      <div className="card-head sec-head"><h2>{title}</h2><Link to={to}>More ›</Link></div>
      {!rows ? <div className="empty"><span className="spinner small" /></div> : rows.length === 0 ? <div className="empty">No data</div> : (
        <table className="mini-table">
          <thead><tr><th>Symbol</th><th className="num">Price (₹)</th><th className="num">Change</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.symbol} title={r.name}
                onClick={() => nav(`/report?${companyToQuery({ name: r.name, nse_symbol: r.symbol, yahoo_ticker: `${r.symbol}.NS` })}`)}>
                <td><span className="sym">{r.symbol}</span>{r.name !== r.symbol && <div className="sub">{r.name}</div>}</td>
                <td className="num">{fmt(r.last)}</td>
                <td className="num"><span className={`pill-chg ${tone(r.pct)}`}>{fmtPct(r.pct)}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function MiniIpos({ data }) {
  const nav = useNavigate();
  const rows = data ? [...(data.current || []), ...(data.upcoming || [])].slice(0, 6) : null;
  return (
    <section className="card">
      <div className="card-head sec-head"><h2>Current &amp; upcoming IPOs</h2><Link to="/ipos">More ›</Link></div>
      {!rows ? <div className="empty"><span className="spinner small" /></div> : rows.length === 0 ? <div className="empty">No open or upcoming IPOs right now.</div> : (
        <table className="mini-table">
          <thead><tr><th>Company</th><th className="num">Dates</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.symbol}-${r.name}`} style={r.slug ? undefined : { cursor: "default" }}
                onClick={() => r.slug && nav(`/ipo/${r.slug}`)}>
                <td><span className="sym">{r.name}</span>{r.is_sme && <span className="chip sme" style={{ marginLeft: 6 }}>SME</span>}
                  {r.price_band && <div className="sub">₹{r.price_band}</div>}</td>
                <td className="num sub-num">{r.start}{r.end ? ` – ${r.end}` : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

export default function Home() {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [indices, setIndices] = useState(null);
  const [movers, setMovers] = useState(null);
  const [news, setNews] = useState(null);
  const [ipos, setIpos] = useState(null);
  const [err, setErr] = useState({});
  const [updated, setUpdated] = useState(null);
  const [status, setStatus] = useState(marketStatus());

  const loadMarket = useCallback(() => {
    setStatus(marketStatus());
    Promise.allSettled([api.indices(), api.movers(5)]).then(([i, m]) => {
      if (i.status === "fulfilled") setIndices(i.value);
      if (m.status === "fulfilled") setMovers(m.value);
      setErr((e) => ({ ...e, indices: i.status === "rejected" ? i.reason.message : null, movers: m.status === "rejected" ? m.reason.message : null }));
      setUpdated(new Date());
    });
  }, []);

  useEffect(() => {
    document.title = "Indian Stock Analyzer · NSE & BSE stock research";
    loadMarket();
    const t = setInterval(() => document.visibilityState === "visible" && loadMarket(), REFRESH_MS);
    api.news("markets", 12).then((d) => setNews(d.items)).catch(() => setNews([]));
    api.ipos().then(setIpos).catch(() => setIpos({}));
    return () => clearInterval(t);
  }, [loadMarket]);

  if (params.get("tab") === "ipo") return <Navigate to="/ipos" replace />; // old link

  return (
    <div className="home">
      <section className="home-hero">
        <h1>Search any NSE or BSE stock to start your analysis</h1>
        <p>Ratios, valuation, cash flow, debt, promoter holding and peers, explained in plain English.</p>
        <SearchBox autoFocus />
        <div className="popular">
          <span>Popular:</span>
          {POPULAR.map((c) => (
            <button key={c.nse_symbol} className={`chip-btn ${c.demo ? "demo" : ""}`} onClick={() => nav(`/report?${companyToQuery(c)}`)}>
              {c.label || c.nse_symbol}
            </button>
          ))}
        </div>
      </section>

      <div className="status-row">
        <h2 className="section-label">Today's market</h2>
        <div className="market-status">
          <span className={`live-dot ${status.open ? "" : "off"}`} />
          {status.label}
          {updated && <span className="muted"> · updated {updated.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}</span>}
          <button className="link-btn" onClick={loadMarket}>Refresh</button>
        </div>
      </div>
      <div className="index-grid">
        {indices ? indices.map((i) => <IndexCard key={i.key} idx={i} />) : [0, 1].map((k) => <section key={k} className="card index-card skeleton" />)}
      </div>
      {err.indices && <div className="error-box">Indices: {err.indices}</div>}

      <div className="home-grid">
        <section className="card">
          <div className="card-head sec-head"><h2>Stock market news</h2><Link to="/news">More news ›</Link></div>
          <NewsList items={news} compact />
        </section>
        <div className="home-side">
          {movers && (
            <div className="breadth card">
              <span>NIFTY 50 breadth</span>
              <div className="breadth-bar">
                <span className="up" style={{ flex: movers.advances || 0.001 }} />
                <span className="flat" style={{ flex: movers.unchanged || 0.001 }} />
                <span className="down" style={{ flex: movers.declines || 0.001 }} />
              </div>
              <span className="up">{movers.advances} up</span>
              <span className="down">{movers.declines} down</span>
            </div>
          )}
          <MiniMovers title="Top gainers" rows={movers?.gainers} to="/movers" />
          <MiniMovers title="Top losers" rows={movers?.losers} to="/movers?tab=losers" />
          {err.movers && <div className="error-box">Movers: {err.movers}</div>}
          <MiniIpos data={ipos} />
        </div>
      </div>
      <AdSlot slot="home" />
    </div>
  );
}
