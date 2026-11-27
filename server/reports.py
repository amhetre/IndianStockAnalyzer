"""
Lazy, per-tab fundamental analysis for the web stock page.

Nothing is written to disk (no Excel / HTML files). The first time a report tab
is opened, the company's data is fetched and analysed once in the background and
kept in memory; every tab is then rendered on demand from that result.
The Peers tab is the expensive one (it loads every peer company), so peers are
only fetched when that tab is opened.
"""
from __future__ import annotations

import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from config import SETTINGS
from utils.logger import get_logger

log = get_logger("server.reports")

KEEP_SECONDS = 6 * 3600
SECTIONS = ["overview", "price", "ratios", "history", "periods", "roic", "debt", "cash", "holding",
            "peers", "risk", "explain", "learn", "sources"]


@dataclass
class Task:
    status: str = "running"          # running | done | error
    steps: list[str] = field(default_factory=list)
    error: Optional[str] = None
    value: Any = None
    finished: Optional[float] = None


@dataclass
class Entry:
    analysis: Task
    peers: Optional[Task] = None
    created: float = field(default_factory=time.time)
    rendered: dict = field(default_factory=dict)


_entries: dict[str, Entry] = {}
_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="analysis")


def key_for(c: dict) -> str:
    if c.get("demo"):
        return "DEMO"
    return (c.get("nse_symbol") or c.get("bse_code") or c.get("yahoo_ticker") or c.get("name") or "").upper()


def _submit(task: Task, fn: Callable[[Task], Any]) -> None:
    def run():
        try:
            task.value = fn(task)
            task.status = "done"
        except Exception as exc:  # noqa: BLE001
            log.error("Analysis task failed: %s\n%s", exc, traceback.format_exc())
            task.error = str(exc) or type(exc).__name__
            task.status = "error"
        finally:
            task.finished = time.time()
    _pool.submit(run)


def _entry(c: dict, refresh: bool) -> Entry:
    key = key_for(c)
    if not key:
        raise ValueError("Pick a company from the search suggestions")
    with _lock:
        e = _entries.get(key)
        stale = e and (e.analysis.status == "error" or time.time() - e.created > KEEP_SECONDS)
        if e and not refresh and not stale:
            return e
        e = Entry(analysis=Task())
        _entries[key] = e
    _submit(e.analysis, lambda t: _analyse(c, t))
    return e


def _analyse(c: dict, task: Task) -> dict:
    from analysis.runner import run_analysis
    say = task.steps.append
    if c.get("demo"):
        from data_providers.demo_provider import demo_peer_loader, make_demo_company
        say("Loading synthetic demo company")
        data = make_demo_company()
        data.peers = data.peers[: SETTINGS.max_peers]
        peer_loader = demo_peer_loader
    else:
        from data_providers.provider_manager import ProviderManager
        pm = ProviderManager()
        say(f"Resolving {c.get('name') or key_for(c)}")
        ident = pm._identity_from_candidate(c, "Web search selection")
        say("Retrieving statements, shareholding and price history")
        data = pm.load(ident, with_peers=True)
        peer_loader = pm.load_peer
        if data.annual.empty and not data.quote.get("price"):
            raise RuntimeError("No market or financial data could be retrieved for this company. "
                               "The data sources may be unreachable – see logs/analyzer.log.")
    for s in data.sources:
        if s.status != "OK":
            say(f"! {s.dataset}: {s.status} – {s.note}")
    say("Calculating metrics")
    res = run_analysis(data, list(SETTINGS.default_periods), None, progress=say)  # peers: on demand
    res["_peer_loader"] = peer_loader
    say("Done")
    return res


def _load_peers(res: dict, task: Task) -> dict:
    from analysis.peer_analysis import analyse_peers, company_row
    data = res["data"]
    task.steps.append(f"Loading {len(data.peers)} peer companies")
    try:
        main_row = company_row(data)
    except Exception:  # noqa: BLE001
        main_row = {"Company": data.identity.name, "Symbol": data.identity.nse_symbol,
                    "_sector_class": data.identity.sector_class}
    return analyse_peers(data, main_row, res["_peer_loader"], task.steps.append)


def _pending(task: Task) -> dict:
    if task.status == "error":
        return {"status": "error", "error": task.error, "steps": task.steps}
    return {"status": "loading", "steps": task.steps[-6:]}


def summary(c: dict, refresh: bool = False) -> dict:
    """Header info (score etc.). Starts the analysis if needed but never waits for it."""
    e = _entry(c, refresh)
    if e.analysis.status != "done":
        return _pending(e.analysis)
    res = e.analysis.value
    ident, sc = res["data"].identity, res["score"]
    return {"status": "done", "name": ident.name, "nse_symbol": ident.nse_symbol, "bse_code": ident.bse_code,
            "sector": ident.sector, "industry": ident.industry, "is_demo": res["data"].is_demo,
            "price": res["price"].get("price"), "score": sc.get("overall"), "score_label": sc.get("label"),
            "coverage_pct": res["coverage"].get("coverage_pct"),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(e.created))}


def section(c: dict, name: str) -> dict:
    """One report tab: {status: loading|error|done, html, figs}. Data is fetched on first request."""
    from reporting.html_report import render_section
    if name not in SECTIONS:
        raise KeyError(name)
    e = _entry(c, False)
    if e.analysis.status != "done":
        return _pending(e.analysis)
    res = e.analysis.value
    if name == "peers":
        with _lock:
            if e.peers is None or e.peers.status == "error" and e.peers.finished \
                    and time.time() - e.peers.finished > 60:
                e.peers = Task()
                e.rendered.pop("peers", None)
                _submit(e.peers, lambda t: _load_peers(res, t))
        if e.peers.status != "done":
            return _pending(e.peers)
        res = dict(res, peers=e.peers.value)
    if name not in e.rendered:
        e.rendered[name] = {"status": "done", **render_section(res, name)}
    return e.rendered[name]
