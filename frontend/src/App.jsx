import { useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import SearchBox from "./components/SearchBox.jsx";
import ThemeToggle from "./components/ThemeToggle.jsx";
import { useConfig } from "./config.js";

// Icons: Lucide (https://lucide.dev, ISC licence) paths, inlined.
const ICONS = {
  home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z",
  star: "m12 2 3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z",
  briefcase: "M16 20V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16M4 6h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2",
  list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  trend: "M22 7 13.5 15.5 8.5 10.5 2 17M16 7h6v6",
  rocket: "M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09zM12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2zM9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5",
  news: "M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2Zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2M18 14h-8M15 18h-5M10 6h8v4h-8z",
  flask: "M10 2v7.31L4.2 19.1A2 2 0 0 0 6 22h12a2 2 0 0 0 1.8-2.9L14 9.3V2M8.5 2h7M7 16h10",
  menu: "M4 6h16M4 12h16M4 18h16",
  chevron: "m6 9 6 6 6-6",
};
const Icon = ({ name, size = 18 }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="2"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d={ICONS[name]} /></svg>
);

// to: route; match(pathname, params) decides the active item.
const q = (p, k) => p.get(k) || "";
const NAV = [
  { label: "Home", icon: "home", to: "/", match: (path) => path === "/" },
  { label: "Watchlist", icon: "star", needs: "portfolio", to: "/portfolio?tab=watch", match: (path, p) => path === "/portfolio" && q(p, "tab") === "watch" },
  { label: "Portfolio", icon: "briefcase", needs: "portfolio", to: "/portfolio", match: (path, p) => path === "/portfolio" && q(p, "tab") !== "watch" },
  {
    label: "Stocks", icon: "list", key: "stocks", items: [
      { label: "NIFTY 50 Stocks", to: "/stocks", match: (path) => path === "/stocks" },
      { label: "Fundamental Report", to: "/report?demo=1&name=Demo+Industries+Ltd+%28SYNTHETIC%29&nse=DEMOIND&tab=overview", match: (path) => path === "/report" },
    ],
  },
  {
    label: "Market Movers", icon: "trend", key: "movers", items: [
      { label: "Top Gainers", to: "/movers", match: (path, p) => path === "/movers" && !["losers", "active"].includes(q(p, "tab")) },
      { label: "Top Losers", to: "/movers?tab=losers", match: (path, p) => path === "/movers" && q(p, "tab") === "losers" },
      { label: "Most Active", to: "/movers?tab=active", match: (path, p) => path === "/movers" && q(p, "tab") === "active" },
    ],
  },
  {
    label: "IPOs", icon: "rocket", key: "ipos", items: [
      { label: "Current & Upcoming", to: "/ipos", match: (path) => path === "/ipos" || path.startsWith("/ipo/") },
      { label: "IPO News", to: "/news?cat=ipo", match: (path, p) => path === "/news" && q(p, "cat") === "ipo" },
    ],
  },
  {
    label: "News", icon: "news", key: "news", items: [
      { label: "Market News", to: "/news", match: (path, p) => path === "/news" && ["", "markets"].includes(q(p, "cat")) },
      { label: "Stocks & Companies", to: "/news?cat=stocks", match: (path, p) => path === "/news" && q(p, "cat") === "stocks" },
      { label: "Economy", to: "/news?cat=economy", match: (path, p) => path === "/news" && q(p, "cat") === "economy" },
    ],
  },
];

const OPEN_KEY = "isa.nav.open";
function loadOpen() {
  try { return JSON.parse(localStorage.getItem(OPEN_KEY)) || { stocks: true, movers: true, ipos: true, news: true }; }
  catch { return { stocks: true, movers: true, ipos: true, news: true }; }
}

function Brand() {
  return (
    <Link to="/" className="brand">
      <span className="logo" aria-hidden>
        <svg viewBox="0 0 32 32" width="28" height="28">
          <rect width="32" height="32" rx="8" fill="var(--accent)" />
          <path d="M6 22l6-7 5 4 9-11" stroke="var(--primary-foreground)" strokeWidth="3" fill="none"
            strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
      <span>Stock<b>Analyzer</b><small>India</small></span>
    </Link>
  );
}

function Sidebar({ open, onClose }) {
  const { pathname, search } = useLocation();
  const params = new URLSearchParams(search);
  const [expanded, setExpanded] = useState(loadOpen);
  const cfg = useConfig();
  const toggle = (k) => setExpanded((e) => {
    const n = { ...e, [k]: !e[k] };
    try { localStorage.setItem(OPEN_KEY, JSON.stringify(n)); } catch { /* ignore */ }
    return n;
  });

  return (
    <>
      <aside className={`sidebar ${open ? "open" : ""}`} aria-label="Main navigation">
        <div className="sidebar-brand"><Brand /></div>
        <nav className="side-nav">
          {NAV.filter((item) => !item.needs || cfg?.[item.needs]).map((item) => {
            if (!item.items) {
              const on = item.match(pathname, params);
              return (
                <Link key={item.label} to={item.to} className={`side-link ${on ? "on" : ""}`} aria-current={on ? "page" : undefined}>
                  <Icon name={item.icon} />{item.label}
                </Link>
              );
            }
            const childOn = item.items.some((c) => c.match(pathname, params));
            const isOpen = expanded[item.key] || childOn;
            return (
              <div key={item.label} className="side-group">
                <button type="button" className={`side-link group ${childOn ? "child-on" : ""}`} aria-expanded={isOpen} onClick={() => toggle(item.key)}>
                  <Icon name={item.icon} />{item.label}
                  <span className={`chev ${isOpen ? "up" : ""}`}><Icon name="chevron" size={16} /></span>
                </button>
                {isOpen && (
                  <div className="side-sub">
                    {item.items.map((c) => {
                      const on = c.match(pathname, params);
                      return <Link key={c.label} to={c.to} className={`side-sublink ${on ? "on" : ""}`} aria-current={on ? "page" : undefined}>{c.label}</Link>;
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </nav>
        <div className="side-foot">Data: NSE, Yahoo Finance, Screener.in, ET, Mint, Business Standard. Not investment advice.</div>
      </aside>
      {open && <div className="sidebar-scrim" onClick={onClose} aria-hidden />}
    </>
  );
}

export default function App() {
  const { pathname, search } = useLocation();
  const [menu, setMenu] = useState(false);
  useEffect(() => setMenu(false), [pathname, search]); // close the mobile drawer after navigating
  useEffect(() => {
    if (!menu) return;
    const k = (e) => e.key === "Escape" && setMenu(false);
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [menu]);

  return (
    <div className="app">
      <Sidebar open={menu} onClose={() => setMenu(false)} />
      <div className="app-main">
        <header className="topbar">
          <button type="button" className="icon-btn menu-btn" onClick={() => setMenu(true)} aria-label="Open menu"><Icon name="menu" size={20} /></button>
          <div className="topbar-brand"><Brand /></div>
          <div className="topbar-search">
            {pathname !== "/" && <SearchBox compact />}
          </div>
          <ThemeToggle />
        </header>
        <main>
          <Outlet />
        </main>
        <footer className="footer">
          Data: NSE India, Yahoo Finance, Screener.in · News: Economic Times, Mint, Business Standard, Google News · Prices may be delayed · Not investment advice.
        </footer>
      </div>
    </div>
  );
}
