import { Fragment, useCallback, useEffect, useState } from "react";
import AdSlot from "../components/AdSlot.jsx";
import { Link, useSearchParams } from "react-router-dom";
import { abbr, api, companyFromTicker, companyToQuery, fmt, fmtChg, fmtPct, marketStatus, tickerOf, tone } from "../api.js";
import SearchBox from "../components/SearchBox.jsx";
import { useConfig } from "../config.js";

const num = (v) => (v === "" || v == null ? null : Number(v));
const sym = (tk) => tk.split(".")[0];
const reportLink = (tk, name) => `/report?${companyToQuery(companyFromTicker(tk, name))}`;

function usePoll(load) {
  useEffect(() => {
    load();
    let t;
    const next = () => {
      t = setTimeout(() => { if (document.visibilityState === "visible") load(); next(); },
        marketStatus().open ? 30_000 : 120_000);
    };
    next();
    return () => clearTimeout(t);
  }, [load]);
}

function Picker({ picked, onPick, placeholder }) {
  return picked ? (
    <div className="picked">
      <b>{picked.name}</b> <span className="chip nse">{sym(tickerOf(picked))}</span>
      <button type="button" className="link-btn" onClick={() => onPick(null)}>Change</button>
    </div>
  ) : (
    <SearchBox compact onPick={onPick} placeholder={placeholder} />
  );
}

// ---------------------------------------------------------------- holdings
function AddHolding({ onAdded }) {
  const [picked, setPicked] = useState(null);
  const [qty, setQty] = useState("");
  const [price, setPrice] = useState("");
  const [date, setDate] = useState("");
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setErr(null);
    if (!picked) return setErr("Pick a stock first");
    if (picked.demo) return setErr("The synthetic demo company can't be added");
    setBusy(true);
    try {
      await api.addHolding({ symbol: tickerOf(picked), name: picked.name, qty: num(qty), avg_price: num(price), buy_date: date || null });
      setPicked(null); setQty(""); setPrice(""); setDate("");
      onAdded();
    } catch (ex) {
      setErr(ex.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card pf-form" onSubmit={submit}>
      <h3>Add a buy</h3>
      <Picker picked={picked} onPick={setPicked} placeholder="Search the stock you bought…" />
      <div className="pf-fields">
        <label>Quantity<input type="number" min="0" step="any" required value={qty} onChange={(e) => setQty(e.target.value)} /></label>
        <label>Buy price (₹)<input type="number" min="0" step="any" required value={price} onChange={(e) => setPrice(e.target.value)} /></label>
        <label>Buy date<input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
        <button className="btn" disabled={busy}>{busy ? "Adding…" : "Add"}</button>
      </div>
      {err && <div className="error-box">{err}</div>}
      <p className="note">Several buys of the same stock are combined at their average price.</p>
    </form>
  );
}

function Holdings() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [open, setOpen] = useState(null);
  const load = useCallback(() => api.portfolio().then((d) => { setData(d); setErr(null); }).catch((e) => setErr(e.message)), []);
  usePoll(load);

  const t = data?.totals;
  const remove = async (id) => { await api.deleteHolding(id); load(); };

  return (
    <>
      {t && data.positions.length > 0 && (
        <div className="pf-summary">
          <div className="card stat"><span>Invested</span><b>{abbr(t.invested, { rupee: true })}</b></div>
          <div className="card stat"><span>Current value</span><b>{abbr(t.value, { rupee: true })}</b></div>
          <div className="card stat"><span>Total P&amp;L</span>
            <b className={tone(t.pnl)}>{fmtChg(t.pnl)}</b><small className={tone(t.pnl)}>{fmtPct(t.pnl_pct)}</small></div>
          <div className="card stat"><span>Today</span><b className={tone(t.day_pnl)}>{fmtChg(t.day_pnl)}</b></div>
        </div>
      )}
      {t && !t.complete && <p className="note">Some prices could not be fetched. P&amp;L counts only stocks with a live price.</p>}
      {err && <div className="error-box">{err}</div>}

      <section className="card pf-table">
        {!data ? <div className="empty"><span className="spinner small" /> Loading…</div>
          : data.positions.length === 0 ? <div className="empty">No holdings yet. Add your first buy below.</div> : (
            <table>
              <thead><tr>
                <th>Stock</th><th className="num">Qty</th><th className="num">Avg (₹)</th><th className="num">LTP (₹)</th>
                <th className="num">Today</th><th className="num">Value</th><th className="num">P&amp;L</th><th className="num">Weight</th><th />
              </tr></thead>
              <tbody>
                {data.positions.map((p) => (
                  <Fragment key={p.symbol}>
                    <tr>
                      <td><Link to={reportLink(p.symbol, p.name)} className="sym">{sym(p.symbol)}</Link><div className="sub">{p.name}</div></td>
                      <td className="num">{p.qty.toLocaleString("en-IN")}</td>
                      <td className="num">{fmt(p.avg_price)}</td>
                      <td className="num">{fmt(p.ltp)}</td>
                      <td className={`num ${tone(p.day_pct)}`}>{fmtPct(p.day_pct)}</td>
                      <td className="num">{abbr(p.value, { rupee: true })}</td>
                      <td className={`num ${tone(p.pnl)}`}>{fmtChg(p.pnl)}<div className="sub">{fmtPct(p.pnl_pct)}</div></td>
                      <td className="num"><span className="weight"><i style={{ width: `${p.weight || 0}%` }} /></span>{p.weight != null ? `${p.weight.toFixed(1)}%` : "–"}</td>
                      <td className="num"><button className="link-btn" onClick={() => setOpen(open === p.symbol ? null : p.symbol)}>
                        {p.lots.length} buy{p.lots.length > 1 ? "s" : ""}</button></td>
                    </tr>
                    {open === p.symbol && p.lots.map((l) => (
                      <tr key={l.id} className="lot">
                        <td className="sub">{l.buy_date || "No date"}</td>
                        <td className="num">{l.qty.toLocaleString("en-IN")}</td>
                        <td className="num">{fmt(l.avg_price)}</td>
                        <td colSpan={5} />
                        <td className="num"><button className="link-btn danger" onClick={() => remove(l.id)}>Delete</button></td>
                      </tr>
                    ))}
                  </Fragment>
                ))}
              </tbody>
            </table>
          )}
      </section>
      <AddHolding onAdded={load} />
    </>
  );
}

// ---------------------------------------------------------------- watchlist
function AlertCell({ w, onSaved }) {
  const [edit, setEdit] = useState(false);
  const [above, setAbove] = useState(w.alert_above ?? "");
  const [below, setBelow] = useState(w.alert_below ?? "");
  const save = async () => {
    await api.saveWatch({ symbol: w.symbol, name: w.name, alert_above: num(above), alert_below: num(below) });
    setEdit(false); onSaved();
  };
  if (!edit)
    return (
      <span className="alert-cell">
        {w.alert_above != null && <span className="pill up">≥ ₹{fmt(w.alert_above)}</span>}
        {w.alert_below != null && <span className="pill down">≤ ₹{fmt(w.alert_below)}</span>}
        <button className="link-btn" onClick={() => setEdit(true)}>{w.alert_above ?? w.alert_below ? "Edit" : "Set alert"}</button>
      </span>
    );
  return (
    <span className="alert-edit">
      <input type="number" step="any" placeholder="Above ₹" value={above} onChange={(e) => setAbove(e.target.value)} />
      <input type="number" step="any" placeholder="Below ₹" value={below} onChange={(e) => setBelow(e.target.value)} />
      <button className="btn small" onClick={save}>Save</button>
      <button className="link-btn" onClick={() => setEdit(false)}>Cancel</button>
    </span>
  );
}

function Watchlist() {
  const [data, setData] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [msg, setMsg] = useState(null);
  const load = useCallback(() => {
    api.watchlist().then(setData).catch((e) => setMsg({ err: true, text: e.message }));
    api.alerts().then((a) => setAlerts(a.alerts)).catch(() => {});
  }, []);
  usePoll(load);

  const add = async (c) => {
    if (!c || c.demo) return;
    await api.saveWatch({ symbol: tickerOf(c), name: c.name });
    load();
  };
  const checkNow = async () => {
    const r = await api.checkAlerts();
    setMsg({ text: r.fired.length ? `${r.fired.length} alert(s) triggered.` : "No alert levels crossed right now." });
    load();
  };
  const testTg = () => api.testTelegram().then(() => setMsg({ text: "Test message sent to Telegram." }))
    .catch((e) => setMsg({ err: true, text: e.message }));

  return (
    <>
      <div className="card pf-form">
        <h3>Add to watchlist</h3>
        <SearchBox compact onPick={add} placeholder="Search a stock to watch…" />
      </div>

      <section className="card pf-table">
        {!data ? <div className="empty"><span className="spinner small" /> Loading…</div>
          : data.items.length === 0 ? <div className="empty">Your watchlist is empty.</div> : (
            <table>
              <thead><tr><th>Stock</th><th className="num">LTP (₹)</th><th className="num">Change</th><th>Price alerts</th><th /></tr></thead>
              <tbody>
                {data.items.map((w) => (
                  <tr key={w.symbol}>
                    <td><Link to={reportLink(w.symbol, w.name)} className="sym">{sym(w.symbol)}</Link><div className="sub">{w.name}</div></td>
                    <td className="num">{fmt(w.ltp)}</td>
                    <td className={`num ${tone(w.day_pct)}`}>{fmtChg(w.day_change)} <span className={`pill ${tone(w.day_pct)}`}>{fmtPct(w.day_pct)}</span></td>
                    <td><AlertCell key={`${w.alert_above}-${w.alert_below}`} w={w} onSaved={load} /></td>
                    <td className="num"><button className="link-btn danger" onClick={() => api.deleteWatch(w.symbol).then(load)}>Remove</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </section>

      <div className="card pf-alerts">
        <div className="pf-alerts-head">
          <h3>Alert log</h3>
          <span>
            <button className="btn ghost small" onClick={checkNow}>Check now</button>
            {data?.telegram
              ? <button className="btn ghost small" onClick={testTg}>Send Telegram test</button>
              : <span className="muted small-txt">Telegram off</span>}
          </span>
        </div>
        {msg && <div className={msg.err ? "error-box" : "ok-box"}>{msg.text}</div>}
        {alerts.length === 0 ? <p className="muted">No alerts triggered yet. Prices are checked every 2 minutes while the server runs.</p> : (
          <ul className="alert-log">
            {alerts.map((a) => (
              <li key={a.id}>
                <span className={`pill ${a.kind === "above" ? "up" : "down"}`}>{a.kind === "above" ? "▲" : "▼"} {sym(a.symbol)}</span>
                ₹{fmt(a.price)} crossed {a.kind} ₹{fmt(a.level)}
                <span className="muted"> · {new Date(a.created_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}
                  {a.sent_telegram ? " · sent to Telegram" : ""}</span>
              </li>
            ))}
          </ul>
        )}
        {!data?.telegram && (
          <p className="note">To get alerts on your phone, create a bot with @BotFather, then start the server with the
            environment variables <code>TELEGRAM_BOT_TOKEN</code> and <code>TELEGRAM_CHAT_ID</code> set.</p>
        )}
      </div>
    </>
  );
}

export default function Portfolio() {
  const cfg = useConfig();
  if (cfg && !cfg.portfolio) {
    return (
      <div className="card empty" style={{ marginTop: 24, flexDirection: "column" }}>
        <h2 style={{ margin: 0 }}>Portfolio &amp; watchlist are coming soon</h2>
        <p style={{ margin: 0 }}>They will be available once accounts are launched.</p>
      </div>
    );
  }
  return <PortfolioPage />;
}

function PortfolioPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "watch" ? "watch" : "holdings";
  useEffect(() => { document.title = `${tab === "watch" ? "Watchlist" : "Portfolio"} · Stock Analyzer`; }, [tab]);
  return (
    <div className="portfolio">
      <div className="status-row">
        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === "holdings"} className={tab === "holdings" ? "on" : ""} onClick={() => setParams({}, { replace: true })}>My portfolio</button>
          <button role="tab" aria-selected={tab === "watch"} className={tab === "watch" ? "on" : ""} onClick={() => setParams({ tab: "watch" }, { replace: true })}>Watchlist &amp; alerts</button>
        </div>
        <div className="market-status"><span className={`live-dot ${marketStatus().open ? "" : "off"}`} />{marketStatus().label}</div>
      </div>
      {tab === "watch" ? <Watchlist /> : <Holdings />}
      <AdSlot slot="portfolio" />
      <p className="note">Prices from Yahoo Finance, may be delayed. Your data is stored on this computer only. Alerts are levels you set yourself. Not investment advice.</p>
    </div>
  );
}
