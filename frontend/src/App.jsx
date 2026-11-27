import { Link, Outlet, useLocation } from "react-router-dom";
import SearchBox from "./components/SearchBox.jsx";
import ThemeToggle from "./components/ThemeToggle.jsx";

export default function App() {
  const { pathname, search } = useLocation();
  const watch = new URLSearchParams(search).get("tab") === "watch";
  const on = (yes) => (yes ? "on" : undefined);
  return (
    <div className="shell">
      <header className="topbar">
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
        <nav className="topnav">
          <Link to="/" className={on(pathname === "/")}>Market</Link>
          <Link to="/portfolio" className={on(pathname === "/portfolio" && !watch)}>Portfolio</Link>
          <Link to="/portfolio?tab=watch" className={on(pathname === "/portfolio" && watch)}>Watchlist</Link>
        </nav>
        {pathname !== "/" && (
          <div className="topbar-search">
            <SearchBox compact />
          </div>
        )}
        <ThemeToggle />
      </header>
      <main>
        <Outlet />
      </main>
      <footer className="footer">
        Data: NSE India, Yahoo Finance, Screener.in · Prices may be delayed · Not investment advice.
      </footer>
    </div>
  );
}
