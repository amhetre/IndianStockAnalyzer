"""
Portfolio tracker, watchlist and price alerts.

Storage is a local SQLite file (data/portfolio.db). Alerts are user-defined
price levels — the app never suggests what to buy or sell.

Telegram notifications are optional: set the environment variables
TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID before starting the server.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

from server.market import _cached, _f, yf
from utils.logger import get_logger

log = get_logger("server.portfolio")

DB_PATH = Path(os.environ.get("ISA_DB", Path(__file__).resolve().parent.parent / "data" / "portfolio.db"))
_db_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,           -- Yahoo ticker, e.g. TCS.NS
    name TEXT,
    qty REAL NOT NULL,
    avg_price REAL NOT NULL,
    buy_date TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS watchlist (
    symbol TEXT PRIMARY KEY,
    name TEXT,
    alert_above REAL,
    alert_below REAL,
    note TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    name TEXT,
    kind TEXT NOT NULL,             -- above | below
    level REAL NOT NULL,
    price REAL NOT NULL,
    sent_telegram INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def _rows(sql: str, args: tuple = ()) -> list[dict]:
    with _db_lock, closing(_conn()) as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def _exec(sql: str, args: tuple = ()) -> int:
    with _db_lock, closing(_conn()) as c, c:   # outer: close the file, inner: commit
        cur = c.execute(sql, args)
        return cur.lastrowid or cur.rowcount


def normalize_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if not s:
        raise ValueError("Symbol is required")
    if "." not in s:
        s = f"{s}.BO" if s.isdigit() else f"{s}.NS"
    return s


# ---------------------------------------------------------------- live prices
def _price(tk: str) -> dict:
    def produce():
        out = {"price": None, "prev_close": None}
        if yf is None:
            return out
        try:
            fi = yf.Ticker(tk).fast_info
            for k, src in (("price", "lastPrice"), ("prev_close", "previousClose")):
                v = _f(fi.get(src))
                out[k] = round(v, 2) if v is not None else None
        except Exception as exc:  # noqa: BLE001
            log.info("price failed for %s: %s", tk, exc)
        return out
    return _cached(f"lp:{tk}", 30, produce)


def prices(tickers: list[str]) -> dict[str, dict]:
    uniq = sorted(set(tickers))
    if not uniq:
        return {}
    with ThreadPoolExecutor(max_workers=min(8, len(uniq))) as ex:
        return dict(zip(uniq, ex.map(_price, uniq)))


def _day(p: dict) -> tuple[Optional[float], Optional[float]]:
    if p["price"] is None or not p["prev_close"]:
        return None, None
    chg = p["price"] - p["prev_close"]
    return round(chg, 2), round(chg / p["prev_close"] * 100, 2)


# ---------------------------------------------------------------- portfolio
def add_holding(symbol: str, name: Optional[str], qty: float, avg_price: float, buy_date: Optional[str]) -> dict:
    if qty <= 0 or avg_price <= 0:
        raise ValueError("Quantity and buy price must be positive")
    tk = normalize_symbol(symbol)
    hid = _exec("INSERT INTO holdings (symbol, name, qty, avg_price, buy_date, created_at) VALUES (?,?,?,?,?,?)",
                (tk, name or tk.split(".")[0], qty, avg_price, buy_date, _now()))
    return {"id": hid}


def delete_holding(hid: int) -> bool:
    return _exec("DELETE FROM holdings WHERE id = ?", (hid,)) > 0


def get_portfolio() -> dict:
    lots = _rows("SELECT * FROM holdings ORDER BY created_at")
    px = prices([h["symbol"] for h in lots])

    # Combine lots of the same stock into one position (weighted average cost).
    pos: dict[str, dict] = {}
    for h in lots:
        p = pos.setdefault(h["symbol"], {"symbol": h["symbol"], "name": h["name"], "qty": 0.0,
                                         "invested": 0.0, "lots": []})
        p["qty"] += h["qty"]
        p["invested"] += h["qty"] * h["avg_price"]
        p["lots"].append({"id": h["id"], "qty": h["qty"], "avg_price": h["avg_price"], "buy_date": h["buy_date"]})

    total_inv = total_val = total_day = all_inv = 0.0
    priced_all = True
    out = []
    for p in pos.values():
        q = px.get(p["symbol"], {"price": None, "prev_close": None})
        ltp = q["price"]
        p["avg_price"] = round(p["invested"] / p["qty"], 2)
        p["ltp"] = ltp
        p["day_change"], p["day_pct"] = _day(q)
        if ltp is None:
            priced_all = False
            p["value"] = p["pnl"] = p["pnl_pct"] = p["day_pnl"] = None
        else:
            p["value"] = round(ltp * p["qty"], 2)
            p["pnl"] = round(p["value"] - p["invested"], 2)
            p["pnl_pct"] = round(p["pnl"] / p["invested"] * 100, 2)
            p["day_pnl"] = round(p["day_change"] * p["qty"], 2) if p["day_change"] is not None else None
            total_val += p["value"]
            total_inv += p["invested"]
            total_day += p["day_pnl"] or 0
        all_inv += p["invested"]
        p["invested"] = round(p["invested"], 2)
        out.append(p)

    for p in out:
        p["weight"] = round(p["value"] / total_val * 100, 2) if p["value"] and total_val else None
    out.sort(key=lambda p: p["value"] or 0, reverse=True)
    return {
        "positions": out,
        "totals": {
            "invested": round(all_inv, 2),
            "priced_invested": round(total_inv, 2),   # P&L is computed only over stocks with a live price
            "value": round(total_val, 2),
            "pnl": round(total_val - total_inv, 2),
            "pnl_pct": round((total_val - total_inv) / total_inv * 100, 2) if total_inv else None,
            "day_pnl": round(total_day, 2),
            "complete": priced_all,
        },
        "updated_at": _now(),
    }


# ---------------------------------------------------------------- watchlist
def add_watch(symbol: str, name: Optional[str], alert_above: Optional[float], alert_below: Optional[float],
              note: Optional[str] = None) -> dict:
    tk = normalize_symbol(symbol)
    _exec("""INSERT INTO watchlist (symbol, name, alert_above, alert_below, note, created_at) VALUES (?,?,?,?,?,?)
             ON CONFLICT(symbol) DO UPDATE SET name = COALESCE(excluded.name, watchlist.name),
                 alert_above = excluded.alert_above, alert_below = excluded.alert_below,
                 note = COALESCE(excluded.note, watchlist.note)""",
          (tk, name or tk.split(".")[0], alert_above, alert_below, note, _now()))
    return {"symbol": tk}


def delete_watch(symbol: str) -> bool:
    return _exec("DELETE FROM watchlist WHERE symbol = ?", (normalize_symbol(symbol),)) > 0


def get_watchlist() -> dict:
    items = _rows("SELECT * FROM watchlist ORDER BY created_at")
    px = prices([w["symbol"] for w in items])
    for w in items:
        q = px.get(w["symbol"], {"price": None, "prev_close": None})
        w["ltp"] = q["price"]
        w["day_change"], w["day_pct"] = _day(q)
    return {"items": items, "telegram": telegram_configured(), "updated_at": _now()}


def recent_alerts(limit: int = 30) -> list[dict]:
    return _rows("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,))


# ---------------------------------------------------------------- alerts
def telegram_configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def send_telegram(text: str) -> bool:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": text}, timeout=10)
        return r.ok
    except requests.RequestException as exc:
        log.info("telegram send failed: %s", exc)
        return False


def check_alerts() -> list[dict]:
    """Fire alerts whose level was crossed. A fired alert level is cleared so it fires once."""
    items = _rows("SELECT * FROM watchlist WHERE alert_above IS NOT NULL OR alert_below IS NOT NULL")
    px = prices([w["symbol"] for w in items])
    fired = []
    for w in items:
        ltp = px.get(w["symbol"], {}).get("price")
        if ltp is None:
            continue
        for kind, col, hit in (("above", "alert_above", lambda lv: ltp >= lv),
                               ("below", "alert_below", lambda lv: ltp <= lv)):
            level = w[col]
            if level is None or not hit(level):
                continue
            sym = w["symbol"].split(".")[0]
            msg = (f"🔔 {w['name'] or sym} ({sym}) is ₹{ltp:,.2f} — "
                   f"{'at or above' if kind == 'above' else 'at or below'} your alert level ₹{level:,.2f}.\n"
                   "Price alert you set in Stock Analyzer. Not investment advice.")
            sent = send_telegram(msg)
            _exec("INSERT INTO alerts (symbol, name, kind, level, price, sent_telegram, created_at) VALUES (?,?,?,?,?,?,?)",
                  (w["symbol"], w["name"], kind, level, ltp, int(sent), _now()))
            _exec(f"UPDATE watchlist SET {col} = NULL WHERE symbol = ?", (w["symbol"],))
            fired.append({"symbol": w["symbol"], "kind": kind, "level": level, "price": ltp, "telegram": sent})
    return fired


def start_alert_worker(interval_s: int = 120) -> None:
    """Background thread that checks alerts every couple of minutes."""
    if os.environ.get("ISA_DISABLE_ALERTS"):
        return

    def loop():
        while True:
            try:
                fired = check_alerts()
                if fired:
                    log.info("alerts fired: %s", fired)
            except Exception as exc:  # noqa: BLE001
                log.warning("alert check failed: %s", exc)
            time.sleep(interval_s)

    threading.Thread(target=loop, name="alert-worker", daemon=True).start()
