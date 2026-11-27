import { Link, useNavigate } from "react-router-dom";
import { fmt, fmtPct, tone } from "../api.js";

function useOpen() {
  const nav = useNavigate();
  return (r) => (r.slug ? { onClick: () => nav(`/ipo/${r.slug}`), className: "clickable", title: `View ${r.name} IPO details` } : {});
}

function NameCell({ r, sub }) {
  return (
    <td>
      <div className="sym">
        {r.slug ? <Link to={`/ipo/${r.slug}`} onClick={(e) => e.stopPropagation()}>{r.name}</Link> : r.name}
        {r.slug && <span className="go">›</span>}
      </div>
      {sub && <div className="sub">{sub}</div>}
    </td>
  );
}

function sizeLakh(shares) {
  const n = Number(shares);
  return Number.isFinite(n) && n > 0 ? `${(n / 1e5).toLocaleString("en-IN", { maximumFractionDigits: 2 })} lakh sh.` : "–";
}

function subs(x) {
  const n = Number(x);
  return x != null && Number.isFinite(n) ? `${n.toFixed(2)}×` : "–";
}

const ARROW = { up: "▲", down: "▼", flat: "" };

function Gmp({ r }) {
  if (r.gmp == null) return <span className="muted">–</span>;
  const t = tone(r.gmp);
  return (
    <div className="gmp">
      <span className={`pill-gmp ${t}`}>
        {r.gmp > 0 ? "+" : r.gmp < 0 ? "−" : ""}₹{fmt(Math.abs(r.gmp)).replace(/\.00$/, "")}
        <small>{fmtPct(r.gmp_pct)}</small>
      </span>
      {r.gmp_trend && r.gmp_trend !== "flat" && (
        <span className={`trend ${r.gmp_trend}`} title={`GMP trending ${r.gmp_trend}`}>{ARROW[r.gmp_trend]}</span>
      )}
    </div>
  );
}

function IpoTable({ rows, showSubs }) {
  const open = useOpen();
  return (
    <table className="ipo-table">
      <thead>
        <tr>
          <th>Company</th>
          <th>Type</th>
          <th>Opens</th>
          <th>Closes</th>
          <th>Price band</th>
          <th>GMP (₹ / %)</th>
          <th className="num">Est. listing</th>
          <th className="num">Issue size</th>
          {showSubs && <th className="num">Subscribed</th>}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={`${r.symbol || r.name}-${r.start}`} {...open(r)}>
            <NameCell r={r} sub={r.symbol || r.exchange || ""} />
            <td><span className={`chip ${r.is_sme ? "sme" : "main"}`}>{r.is_sme ? "SME" : "Mainboard"}</span></td>
            <td>{r.start || "–"}</td>
            <td>{r.end || "–"}</td>
            <td>{(r.price_band || "–").replace(/Rs\.\s?/g, "₹")}</td>
            <td><Gmp r={r} /></td>
            <td className="num">{r.est_listing != null ? `₹${fmt(r.est_listing).replace(/\.00$/, "")}` : "–"}</td>
            <td className="num">{sizeLakh(r.issue_size)}</td>
            {showSubs && <td className="num">{subs(r.subscription)}</td>}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ListedTable({ rows }) {
  const open = useOpen();
  return (
    <table className="ipo-table">
      <thead>
        <tr>
          <th>Company</th>
          <th>Type</th>
          <th className="num">Issue price</th>
          <th className="num">Last GMP</th>
          <th className="num">Listing price</th>
          <th className="num">Listing gain</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.name} {...open(r)}>
            <NameCell r={r} />
            <td><span className={`chip ${/main/i.test(r.type) ? "main" : "sme"}`}>{r.type}</span></td>
            <td className="num">₹{fmt(r.issue_price)}</td>
            <td className="num">{r.gmp != null ? `₹${fmt(r.gmp)}` : "–"}</td>
            <td className="num">₹{fmt(r.listing_price)}</td>
            <td className={`num ${tone(r.listing_gain_pct)}`}><b>{fmtPct(r.listing_gain_pct)}</b></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function IpoPanel({ data, error }) {
  if (error) return <div className="card empty">Could not load IPO data: {error}</div>;
  if (!data) return <div className="card empty"><span className="spinner" /> Loading IPOs…</div>;
  if (!data.available)
    return <div className="card empty">IPO data sources did not respond right now. Try again in a few minutes.</div>;
  const gmpTime = [...data.current, ...data.upcoming].find((r) => r.gmp_updated)?.gmp_updated;
  return (
    <div className="ipo-grid">
      <section className="card">
        <h3 className="section-title">
          <span className="live-dot" /> Open for subscription <span className="count">{data.current.length}</span>
        </h3>
        {data.current.length ? <IpoTable rows={data.current} showSubs /> : <div className="empty">No IPO is open today.</div>}
      </section>
      <section className="card">
        <h3 className="section-title">
          Upcoming IPOs <span className="count">{data.upcoming.length}</span>
        </h3>
        {data.upcoming.length ? (
          <IpoTable rows={data.upcoming} />
        ) : (
          <div className="empty">No upcoming IPO dates announced yet.</div>
        )}
      </section>
      {data.recently_listed?.length > 0 && (
        <section className="card">
          <h3 className="section-title">
            Recently listed <span className="count">{data.recently_listed.length}</span>
          </h3>
          <ListedTable rows={data.recently_listed} />
        </section>
      )}
      <p className="note">
        Click any IPO to see what the business does, its size, financials, debt, why it is raising money and who is
        managing the issue.{" "}
        <b>GMP (grey market premium)</b> is an unofficial, unregulated estimate of how far above the upper price band an
        IPO may list; % is GMP ÷ upper price band. Est. listing = upper band + GMP. It often changes and is not a reliable
        predictor.{" "}
        Sources: {data.source} (issues, subscription){data.gmp_source && <>, {data.gmp_source} (GMP{gmpTime ? `, updated ${gmpTime}` : ""})</>}.
        Not a recommendation to apply.
      </p>
    </div>
  );
}
