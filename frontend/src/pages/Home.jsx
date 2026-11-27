import { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, companyToQuery, marketStatus } from "../api.js";
import IndexCard from "../components/IndexCard.jsx";
import IpoPanel from "../components/IpoPanel.jsx";
import MoversTable from "../components/MoversTable.jsx";
import SearchBox from "../components/SearchBox.jsx";
import AdSlot from "../components/AdSlot.jsx";

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

export default function Home() {
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "ipo" ? "ipo" : "market";
  const setTab = (t) => setParams(t === "ipo" ? { tab: "ipo" } : {}, { replace: true });
  const [indices, setIndices] = useState(null);
  const [movers, setMovers] = useState(null);
  const [ipos, setIpos] = useState(null);
  const [err, setErr] = useState({});
  const [updated, setUpdated] = useState(null);
  const [status, setStatus] = useState(marketStatus());

  const loadMarket = useCallback(() => {
    setStatus(marketStatus());
    Promise.allSettled([api.indices(), api.movers()]).then(([i, m]) => {
      if (i.status === "fulfilled") setIndices(i.value);
      if (m.status === "fulfilled") setMovers(m.value);
      setErr((e) => ({
        ...e,
        indices: i.status === "rejected" ? i.reason.message : null,
        movers: m.status === "rejected" ? m.reason.message : null,
      }));
      setUpdated(new Date());
    });
  }, []);

  useEffect(() => {
    loadMarket();
    const t = setInterval(() => document.visibilityState === "visible" && loadMarket(), REFRESH_MS);
    return () => clearInterval(t);
  }, [loadMarket]);

  useEffect(() => {
    if (tab === "ipo" && !ipos)
      api.ipos().then(setIpos).catch((e) => setErr((x) => ({ ...x, ipos: e.message })));
  }, [tab, ipos]);

  return (
    <div className="home">
      <section className="hero">
        <h1>Fundamental analysis for any NSE / BSE stock</h1>
        <p>Search a company to get ratios, valuation, cash flow, debt, promoter holding and peers — explained in plain English.</p>
        <SearchBox autoFocus />
        <div className="popular">
          <span>Popular:</span>
          {POPULAR.map((c) => (
            <button key={c.nse_symbol} className={`chip-btn ${c.demo ? "demo" : ""}`}
              onClick={() => nav(`/report?${companyToQuery(c)}`)}>
              {c.label || c.nse_symbol}
            </button>
          ))}
        </div>
      </section>

      <div className="status-row">
        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === "market"} className={tab === "market" ? "on" : ""}
            onClick={() => setTab("market")}>Today's market</button>
          <button role="tab" aria-selected={tab === "ipo"} className={tab === "ipo" ? "on" : ""}
            onClick={() => setTab("ipo")}>IPOs</button>
        </div>
        <div className="market-status">
          <span className={`live-dot ${status.open ? "" : "off"}`} />
          {status.label}
          {updated && tab === "market" && (
            <span className="muted"> · updated {updated.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span>
          )}
          {tab === "market" && <button className="link-btn" onClick={loadMarket}>Refresh</button>}
        </div>
      </div>

      {tab === "market" ? (
        <>
          <div className="index-grid">
            {indices
              ? indices.map((i) => <IndexCard key={i.key} idx={i} />)
              : [0, 1].map((k) => <section key={k} className="card index-card skeleton" />)}
          </div>
          {err.indices && <div className="error-box">Indices: {err.indices}</div>}

          {movers && (
            <div className="breadth card">
              <span>NIFTY 50 breadth</span>
              <div className="breadth-bar">
                <span className="up" style={{ flex: movers.advances || 0.001 }} />
                <span className="flat" style={{ flex: movers.unchanged || 0.001 }} />
                <span className="down" style={{ flex: movers.declines || 0.001 }} />
              </div>
              <span className="up">{movers.advances} advances</span>
              <span className="down">{movers.declines} declines</span>
            </div>
          )}

          <div className="movers-grid">
            {movers ? (
              <>
                <MoversTable title="NIFTY 50 · Top 10 gainers" rows={movers.gainers} kind="up" />
                <MoversTable title="NIFTY 50 · Top 10 losers" rows={movers.losers} kind="down" />
              </>
            ) : (
              [0, 1].map((k) => <section key={k} className="card movers skeleton" />)
            )}
          </div>
          {err.movers && <div className="error-box">Movers: {err.movers}</div>}
          {movers && <p className="note">Movers source: {movers.source}. Click any stock to open its full report. Auto-refreshes every minute.</p>}
        </>
      ) : (
        <IpoPanel data={ipos} error={err.ipos} />
      )}
      <AdSlot slot="home" />
    </div>
  );
}
