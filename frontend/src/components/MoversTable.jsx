import { useNavigate } from "react-router-dom";
import { companyToQuery, fmt, fmtChg, fmtPct, tone } from "../api.js";

export default function MoversTable({ title, rows, kind }) {
  const nav = useNavigate();
  const max = Math.max(...rows.map((r) => Math.abs(r.pct || 0)), 0.01);
  return (
    <section className="card movers">
      <h3 className={`movers-title ${kind}`}>
        {kind === "up" ? "▲" : "▼"} {title}
      </h3>
      {rows.length === 0 ? (
        <div className="empty">No data</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Stock</th>
              <th className="num">LTP (₹)</th>
              <th className="num">Change</th>
              <th className="num">% Chg</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr
                key={r.symbol}
                onClick={() => nav(`/report?${companyToQuery({ name: r.name, nse_symbol: r.symbol, yahoo_ticker: `${r.symbol}.NS` })}`)}
                title={`Open fundamental report for ${r.symbol}`}
              >
                <td className="rank">{i + 1}</td>
                <td>
                  <div className="sym">{r.symbol}</div>
                  {r.name !== r.symbol && <div className="sub">{r.name}</div>}
                </td>
                <td className="num">{fmt(r.last)}</td>
                <td className={`num ${tone(r.change)}`}>{fmtChg(r.change)}</td>
                <td className="num pct-cell">
                  <span className={`bar ${tone(r.pct)}`} style={{ width: `${(Math.abs(r.pct) / max) * 100}%` }} />
                  <span className={`pill ${tone(r.pct)}`}>{fmtPct(r.pct)}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
