import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { abbr, api, tickerOf, fmt, fmtChg, fmtPct, marketStatus, queryToCompany, tone } from "../api.js";
import { About, KeyStats } from "../components/StockOverview.jsx";
import ReportSection from "../components/ReportSection.jsx";
import TradingChart from "../components/TradingChart.jsx";
import Projection from "../components/Projection.jsx";
import AdSlot from "../components/AdSlot.jsx";
import NewsList from "../components/NewsList.jsx";

function CompanyNews({ name, symbol }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    if (!name) return;
    setData(null);
    api.companyNews(name, symbol).then(setData).catch((e) => setErr(e.message));
  }, [name, symbol]);
  return (
    <section className="card">
      <div className="card-head sec-head"><h2>{name} news</h2></div>
      {err ? <div className="error-box">{err}</div>
        : <NewsList items={data?.items ?? null} showSummary={false} empty={`No recent news found for ${name}.`} />}
      <p className="note" style={{ padding: "0 16px 6px" }}>Headlines via Google News (India). Open a headline to read it on the publisher's site.</p>
    </section>
  );
}

function WatchButton({ company }) {
  const tk = tickerOf(company);
  const [on, setOn] = useState(null);
  useEffect(() => {
    if (!tk) return;
    api.watchlist().then((w) => setOn(w.items.some((i) => i.symbol === tk.toUpperCase()))).catch(() => setOn(false));
  }, [tk]);
  if (!tk || company.demo || on == null) return null;
  const toggle = () => (on ? api.deleteWatch(tk) : api.saveWatch({ symbol: tk, name: company.name }))
    .then(() => setOn(!on)).catch(() => {});
  return (
    <button className={`btn small watch ${on ? "on" : ""}`} onClick={toggle} title="Watchlist and price alerts">
      {on ? "★ In watchlist" : "☆ Add to watchlist"}
    </button>
  );
}

const TABS = [
  ["chart", "Chart"], ["news", "News"], ["projection", "Projection"], ["overview", "Overview"], ["price", "Price"], ["ratios", "Ratios"], ["history", "History"],
  ["periods", "3M–5Y"], ["roic", "ROIC vs WACC"], ["debt", "Debt & Interest"], ["cash", "Cash flow"],
  ["holding", "Shareholding"], ["peers", "Peers"], ["risk", "Risk & Score"], ["explain", "Explanations"],
  ["learn", "Learn"], ["sources", "Sources"],
];

function scoreTone(s) {
  if (s == null) return "flat";
  if (s >= 65) return "up";
  if (s >= 45) return "mid";
  return "down";
}

export default function Report() {
  const [params, setParams] = useSearchParams();
  const companyKey = useMemo(() => { const p = new URLSearchParams(params); p.delete("tab"); return p.toString(); }, [params]);
  const company = useMemo(() => queryToCompany(new URLSearchParams(companyKey)), [companyKey]);
  const tab = TABS.some(([k]) => k === params.get("tab")) ? params.get("tab") : company.demo ? "overview" : "chart";
  const [quote, setQuote] = useState(null);
  const [quoteErr, setQuoteErr] = useState(false);
  const [summary, setSummary] = useState(null);
  const [loaded, setLoaded] = useState({});
  const [, tick] = useState(0);
  const tabsRef = useRef(null);

  const setTab = (k) => {
    const p = new URLSearchParams(params);
    p.set("tab", k);
    setParams(p, { replace: true });
  };

  useEffect(() => { setLoaded({}); setSummary(null); }, [company]);

  // Live quote: every 15 s while the market is open, every minute otherwise
  useEffect(() => {
    setQuote(null);
    setQuoteErr(false);
    if (company.demo) return;
    let alive = true, timer;
    const load = () => {
      if (document.visibilityState === "visible")
        api.quote(company)
          .then((q) => alive && (q.available ? setQuote(q) : setQuoteErr(true)))
          .catch(() => alive && setQuoteErr(true));
      timer = setTimeout(load, marketStatus().open ? 15_000 : 60_000);
    };
    load();
    return () => { alive = false; clearTimeout(timer); };
  }, [company]);

  // Re-render the market status label every 30 s
  useEffect(() => { const t = setInterval(() => tick((n) => n + 1), 30_000); return () => clearInterval(t); }, []);

  const onLoaded = useCallback((k, r) => {
    setLoaded((m) => ({ ...m, [k]: r }));
    if (!summary) api.summary(company).then((s) => s.status === "done" && setSummary(s)).catch(() => {});
  }, [company, summary]);

  const title = summary?.name || quote?.name || company.name || company.nse_symbol || company.bse_code;
  useEffect(() => { document.title = title ? `${title} · Stock Analyzer` : "Stock Analyzer"; }, [title]);

  const price = quote?.price ?? summary?.price;
  const ms = marketStatus();
  const live = ms.open && quote?.market_state !== "CLOSED";
  const tradedValue = quote?.volume && quote?.price ? quote.volume * quote.price : null;
  const lastTrade = quote?.market_time
    ? new Date(quote.market_time * 1000).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false })
    : null;

  return (
    <div className="report">
      <div className="report-head card">
        <div className="report-id">
          <h1>{title}</h1>
          <div className="codes">
            {(summary?.nse_symbol || company.nse_symbol) && <span className="chip nse">NSE · {summary?.nse_symbol || company.nse_symbol}</span>}
            {(summary?.bse_code || company.bse_code) && <span className="chip bse">BSE · {summary?.bse_code || company.bse_code}</span>}
            {(quote?.industry || summary?.industry) && <span className="chip">{quote?.industry || summary?.industry}</span>}
            {company.demo && <span className="chip sme">Synthetic demo data</span>}
          </div>
          <WatchButton company={company} />
        </div>
        <div className="report-stats">
          <div className="stat price-stat">
            <span>Share price</span>
            {price != null ? (
              <>
                <b>₹{fmt(price)}</b>
                {quote && <small className={tone(quote.change)}>{fmtChg(quote.change)} ({fmtPct(quote.pct)}) today</small>}
              </>
            ) : company.demo ? <b>–</b> : <b className="skeleton-text" />}
          </div>
          {!company.demo && (
            <div className="stat">
              <span className="vol-label">
                {live ? <><i className="live-dot" />Volume · live</> : "Day's volume"}
              </span>
              {quote ? (
                <>
                  <b>{abbr(quote.volume)}</b>
                  <small>
                    {live ? `So far today${lastTrade ? ` · ${lastTrade} IST` : ""}` : "Full-day total"}
                    {tradedValue ? ` · ≈ ${abbr(tradedValue, { rupee: true })}` : ""}
                  </small>
                </>
              ) : <b className="skeleton-text" />}
            </div>
          )}
          {!company.demo && quote?.market_cap_cr != null && (
            <div className="stat">
              <span>Market cap</span>
              <b>{abbr(quote.market_cap_cr * 1e7, { rupee: true })}</b>
              <small>{ms.label}</small>
            </div>
          )}
          {summary && (
            <div className="stat">
              <span>Fundamental score</span>
              <b className={scoreTone(summary.score)}>{summary.score != null ? `${Math.round(summary.score)}/100` : "N/A"}</b>
              <small>{summary.score_label}</small>
            </div>
          )}
        </div>
      </div>

      <nav className="detail-tabs" ref={tabsRef} role="tablist">
        {TABS.filter(([k]) => !(company.demo && (k === "chart" || k === "news"))).map(([k, l]) => (
          <button key={k} role="tab" aria-selected={k === tab} className={k === tab ? "on" : ""} onClick={() => setTab(k)}>
            {l}
            {k !== "chart" && k !== "projection" && k !== "news" && loaded[k] && <i className="tab-dot" aria-hidden />}
          </button>
        ))}
      </nav>

      {tab === "news" ? (
        company.demo ? <div className="card empty">News is not available for the synthetic demo company.</div>
          : <CompanyNews name={summary?.name || quote?.name || company.name || company.nse_symbol} symbol={company.nse_symbol} />
      ) : tab === "projection" ? (
        <Projection company={company} />
      ) : tab === "chart" ? (
        quoteErr && !quote ? (
          <div className="card error-box big"><h3>Live price unavailable</h3><p>Yahoo Finance did not return data for this symbol. The report tabs may still work.</p></div>
        ) : (
          <>
            <div className="overview-grid">
              <TradingChart company={company} prevClose={quote?.prev_close} />
              {quote ? <KeyStats q={quote} live={live} /> : <section className="card stats-card skeleton" />}
            </div>
            {quote && <About q={quote} />}
          </>
        )
      ) : (
        <ReportSection key={`${tab}:${params.get("nse") || params.get("bse") || params.get("yt") || "demo"}`}
          company={company} tab={tab} cached={loaded[tab]} onLoaded={onLoaded} />
      )}
      <AdSlot slot="report" />
    </div>
  );
}
