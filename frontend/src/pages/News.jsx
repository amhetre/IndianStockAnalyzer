import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import AdSlot from "../components/AdSlot.jsx";
import NewsList from "../components/NewsList.jsx";

const CATS = [
  ["markets", "Markets"],
  ["stocks", "Stocks & Companies"],
  ["ipo", "IPOs"],
  ["economy", "Economy"],
  ["all", "All"],
];
const TITLES = { markets: "Stock Market News", stocks: "Stocks & Company News", ipo: "IPO News", economy: "Economy News", all: "All News" };

export default function News() {
  const [params] = useSearchParams();
  const cat = CATS.some(([k]) => k === params.get("cat")) ? params.get("cat") : "markets";
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    document.title = `${TITLES[cat]} · Stock Analyzer`;
    let alive = true;
    const load = () => api.news(cat, 60)
      .then((d) => alive && (setData(d), setErr(null)))
      .catch((e) => alive && setErr(e.message));
    setData(null);
    load();
    const t = setInterval(() => document.visibilityState === "visible" && load(), 10 * 60_000);
    return () => { alive = false; clearInterval(t); };
  }, [cat]);

  return (
    <div className="news-page">
      <div className="page-head">
        <h1>{TITLES[cat]}</h1>
        <p>Latest headlines from Indian financial news sites. Click a headline to read it on the publisher's site.</p>
      </div>
      <nav className="pills" aria-label="News category">
        {CATS.map(([k, l]) => (
          <Link key={k} to={k === "markets" ? "/news" : `/news?cat=${k}`} className={k === cat ? "on" : undefined}>{l}</Link>
        ))}
      </nav>
      {err && <div className="error-box">{err}</div>}
      <section className="card">
        <NewsList items={data?.items ?? (err ? [] : null)} />
      </section>
      <AdSlot slot="home" />
    </div>
  );
}
