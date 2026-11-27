async function req(url, opts = {}) {
  const r = await fetch(url, opts);
  if (!r.ok) {
    let msg = `HTTP ${r.status}`;
    try {
      const j = await r.json();
      msg = j.detail || msg;
    } catch { /* not JSON */ }
    throw new Error(msg);
  }
  return r.json();
}

export const api = {
  indices: () => req("/api/market/indices"),
  movers: (n = 10) => req(`/api/market/movers?n=${n}`),
  news: (cat = "markets", limit = 40) => req(`/api/news?category=${cat}&limit=${limit}`),
  companyNews: (name, symbol) => req(`/api/news/company?name=${encodeURIComponent(name)}${symbol ? `&symbol=${encodeURIComponent(symbol)}` : ""}`),
  ipos: () => req("/api/market/ipos"),
  search: (q, signal) => req(`/api/search?q=${encodeURIComponent(q)}`, { signal }),
  summary: (c, refresh = false) => req(`/api/stock/summary?${companyQuery(c)}${refresh ? "&refresh=true" : ""}`),
  section: (c, tab) => req(`/api/stock/section/${tab}?${companyQuery(c)}`),
  quote: (c) => req(`/api/quote?${tickerQuery(c)}`),
  history: (c, range) => req(`/api/history?${tickerQuery(c)}&range=${range}`),
  projection: (c) => req(c.demo ? "/api/projection?demo=true" : `/api/projection?${tickerQuery(c)}`),
  config: () => req("/api/config"),
  portfolio: () => req("/api/portfolio"),
  addHolding: (h) => req("/api/portfolio/holdings", json("POST", h)),
  deleteHolding: (id) => req(`/api/portfolio/holdings/${id}`, { method: "DELETE" }),
  watchlist: () => req("/api/watchlist"),
  saveWatch: (w) => req("/api/watchlist", json("POST", w)),
  deleteWatch: (sym) => req(`/api/watchlist/${encodeURIComponent(sym)}`, { method: "DELETE" }),
  alerts: () => req("/api/alerts"),
  checkAlerts: () => req("/api/alerts/check", { method: "POST" }),
  testTelegram: () => req("/api/alerts/test", { method: "POST" }),
  candles: (c, range, interval) => req(`/api/candles?${tickerQuery(c)}&range=${range}&interval=${interval}`),
};

const json = (method, body) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

// Yahoo ticker for a search result / company object (TCS -> TCS.NS, 500570 -> 500570.BO)
export const tickerOf = (c) => c.yahoo_ticker || (c.nse_symbol ? `${c.nse_symbol}.NS` : c.bse_code ? `${c.bse_code}.BO` : null);

// Company object (for report links) from a stored Yahoo ticker
export function companyFromTicker(tk, name) {
  const [base, ex] = tk.split(".");
  return ex === "BO" ? { name, bse_code: base, yahoo_ticker: tk } : { name, nse_symbol: base, yahoo_ticker: tk };
}

function companyQuery(c) {
  const p = new URLSearchParams(companyToQuery(c));
  if (c.demo) { p.delete("demo"); p.set("demo", "true"); }
  return p.toString();
}

// ₹ / count abbreviations in the Indian system: K (thousand), L (lakh), Cr (crore), L Cr (lakh crore).
export function abbr(v, { rupee = false, digits = 2 } = {}) {
  if (v == null || !Number.isFinite(v)) return "–";
  const a = Math.abs(v), s = v < 0 ? "-" : "", r = rupee ? "₹" : "";
  const f = (x, u) => `${s}${r}${x.toLocaleString("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: 0 })}${u}`;
  if (a >= 1e12) return f(a / 1e12, " L Cr");
  if (a >= 1e7) return f(a / 1e7, " Cr");
  if (a >= 1e5) return f(a / 1e5, " L");
  if (a >= 1e3) return f(a / 1e3, " K");
  return f(a, "");
}
export const abbrCr = (cr, o) => (cr == null ? "–" : abbr(cr * 1e7, { rupee: true, ...o }));

function tickerQuery(c) {
  const p = new URLSearchParams();
  if (c.yahoo_ticker) p.set("yt", c.yahoo_ticker);
  else if (c.nse_symbol) p.set("nse", c.nse_symbol);
  else if (c.bse_code) p.set("bse", c.bse_code);
  return p.toString();
}

// Company <-> URL query, so a report page survives refresh and can be shared.
export function companyToQuery(c) {
  const p = new URLSearchParams();
  if (c.demo) p.set("demo", "1");
  if (c.name) p.set("name", c.name);
  if (c.nse_symbol) p.set("nse", c.nse_symbol);
  if (c.bse_code) p.set("bse", c.bse_code);
  if (c.yahoo_ticker) p.set("yt", c.yahoo_ticker);
  if (c.screener_url) p.set("scr", c.screener_url);
  return p.toString();
}

export function queryToCompany(p) {
  return {
    demo: p.get("demo") === "1",
    name: p.get("name") || undefined,
    nse_symbol: p.get("nse") || undefined,
    bse_code: p.get("bse") || undefined,
    yahoo_ticker: p.get("yt") || undefined,
    screener_url: p.get("scr") || undefined,
  };
}

const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
export const fmt = (v) => (v == null ? "–" : inr.format(v));
export const fmtPct = (v) => (v == null ? "–" : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`);
export const fmtChg = (v) => (v == null ? "–" : `${v > 0 ? "+" : ""}${inr.format(v)}`);
export const tone = (v) => (v == null || v === 0 ? "flat" : v > 0 ? "up" : "down");

export function marketStatus(now = new Date()) {
  // NSE cash market: Mon–Fri 09:15–15:30 IST (holidays not modelled)
  const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const day = ist.getDay();
  const mins = ist.getHours() * 60 + ist.getMinutes();
  if (day === 0 || day === 6) return { open: false, label: "Market closed · weekend" };
  if (mins < 9 * 60) return { open: false, label: "Pre-market" };
  if (mins < 9 * 60 + 15) return { open: false, label: "Pre-open session" };
  if (mins <= 15 * 60 + 30) return { open: true, label: "Market open" };
  return { open: false, label: "Market closed" };
}

// "5 min ago", "3 h ago", "27 Nov" for news timestamps (epoch seconds)
export function timeAgo(sec) {
  if (!sec) return "";
  const d = Date.now() / 1000 - sec;
  if (d < 60) return "just now";
  if (d < 3600) return `${Math.floor(d / 60)} min ago`;
  if (d < 86400) return `${Math.floor(d / 3600)} h ago`;
  if (d < 172800) return "yesterday";
  return new Date(sec * 1000).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}
