import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, companyToQuery } from "../api.js";

const RECENT_KEY = "isa.recent";

function loadRecent() {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY)) || [];
  } catch {
    return [];
  }
}

function saveRecent(c) {
  try {
    const key = (x) => x.nse_symbol || x.bse_code || x.name;
    const list = [c, ...loadRecent().filter((x) => key(x) !== key(c))].slice(0, 6);
    localStorage.setItem(RECENT_KEY, JSON.stringify(list));
  } catch { /* storage unavailable */ }
}

function Highlight({ text, q }) {
  const i = text.toLowerCase().indexOf(q.toLowerCase());
  if (!q || i < 0) return text;
  return (
    <>
      {text.slice(0, i)}
      <mark>{text.slice(i, i + q.length)}</mark>
      {text.slice(i + q.length)}
    </>
  );
}

export default function SearchBox({ compact = false, autoFocus = false, onPick, placeholder }) {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [active, setActive] = useState(-1);
  const [recent, setRecent] = useState(loadRecent);
  const boxRef = useRef(null);
  const inputRef = useRef(null);

  // Debounced, cancellable suggestions
  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) {
      setItems([]);
      setLoading(false);
      return;
    }
    const ctl = new AbortController();
    setLoading(true);
    const t = setTimeout(() => {
      api
        .search(term, ctl.signal)
        .then((r) => {
          setItems(r.results);
          setActive(r.results.length ? 0 : -1);
          setLoading(false);
        })
        .catch((e) => {
          if (e.name !== "AbortError") setLoading(false);
        });
    }, 220);
    return () => {
      clearTimeout(t);
      ctl.abort();
    };
  }, [q]);

  // Close on outside click; "/" focuses search
  useEffect(() => {
    const onDown = (e) => boxRef.current && !boxRef.current.contains(e.target) && setOpen(false);
    const onKey = (e) => {
      if (e.key === "/" && document.activeElement?.tagName !== "INPUT") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  const showingRecent = q.trim().length < 2;
  const list = showingRecent ? recent : items;

  function pick(c) {
    saveRecent(c);
    setRecent(loadRecent());
    setOpen(false);
    setQ("");
    inputRef.current?.blur();
    if (onPick) onPick(c);
    else nav(`/report?${companyToQuery(c)}`);
  }

  function onKeyDown(e) {
    if (!open) setOpen(true);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, list.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (list[active]) pick(list[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
      inputRef.current?.blur();
    }
  }

  return (
    <div className={`search ${compact ? "compact" : ""}`} ref={boxRef}>
      <div className="search-field">
        <svg className="search-icon" viewBox="0 0 24 24" width="20" height="20" aria-hidden>
          <circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" strokeWidth="2" />
          <path d="M20 20l-4-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <input
          ref={inputRef}
          value={q}
          autoFocus={autoFocus}
          placeholder={placeholder || (compact ? "Search another stock…" : "Search a company or NSE symbol, e.g. Reliance, TCS, HDFC Bank")}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
            setActive(-1);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          role="combobox"
          aria-expanded={open}
          aria-autocomplete="list"
        />
        {loading ? <span className="spinner small" /> : !compact && <kbd>/</kbd>}
      </div>
      {open && (list.length > 0 || (!showingRecent && !loading)) && (
        <ul className="suggestions" role="listbox">
          {showingRecent && <li className="sugg-head">Recent</li>}
          {list.map((c, i) => (
            <li
              key={`${c.nse_symbol || c.bse_code || c.yahoo_ticker}-${i}`}
              className={i === active ? "active" : ""}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => {
                e.preventDefault();
                pick(c);
              }}
              role="option"
              aria-selected={i === active}
            >
              <span className="sugg-name">
                <Highlight text={c.name} q={q.trim()} />
                {c.demo && <em className="tag">synthetic</em>}
              </span>
              <span className="sugg-codes">
                {c.nse_symbol && <span className="chip nse">NSE · {c.nse_symbol}</span>}
                {c.bse_code && <span className="chip bse">BSE · {c.bse_code}</span>}
              </span>
            </li>
          ))}
          {!showingRecent && !loading && list.length === 0 && (
            <li className="sugg-empty">No listed Indian company matches “{q.trim()}”.</li>
          )}
        </ul>
      )}
    </div>
  );
}
