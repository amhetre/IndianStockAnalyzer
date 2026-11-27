import { useState } from "react";
import { timeAgo } from "../api.js";

// Headlines only: each item links to the publisher's own article (new tab).
function Thumb({ n }) {
  const [ok, setOk] = useState(true);
  if (!n.image || !ok) return null;
  return (
    <a className="thumb" href={n.link} target="_blank" rel="noopener noreferrer" tabIndex={-1} aria-hidden>
      <img src={n.image} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setOk(false)} />
    </a>
  );
}

export default function NewsList({ items, compact = false, showSummary = true, empty = "No news right now." }) {
  if (!items) {
    return <div className="empty"><span className="spinner small" /> Loading news…</div>;
  }
  if (!items.length) return <div className="empty">{empty}</div>;
  return (
    <ul className={`news-list ${compact ? "compact" : ""}`}>
      {items.map((n) => (
        <li key={n.link} className="news-item">
          <Thumb n={n} />
          <div className="news-body">
            <span className="news-meta"><b>{n.source}</b>{n.published ? ` · ${timeAgo(n.published)}` : ""}</span>
            <a className="news-title" href={n.link} target="_blank" rel="noopener noreferrer">{n.title}</a>
            {showSummary && n.summary && <p className="news-sum">{n.summary}</p>}
          </div>
        </li>
      ))}
    </ul>
  );
}
