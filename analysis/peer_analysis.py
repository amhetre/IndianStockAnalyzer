"""Peer comparison using the SAME calculation code for every company."""
from __future__ import annotations

from typing import Callable, Optional

import pandas as pd

from analysis.fundamental_ratios import FINANCIAL_CLASSES, annual_ratio_table, compute_core_ratios, quarterly_table
from analysis.roic_wacc import analyse_roic_wacc
from data_providers.models import CompanyData
from utils.financial_utils import cagr, is_num, median_of, num
from utils.logger import get_logger

log = get_logger(__name__)

PEER_COLUMNS = ["Company", "Symbol", "CMP (₹)", "Market cap (₹ Cr)", "P/E", "P/B", "PEG", "EV/EBITDA", "ROE %",
                "ROCE %", "ROIC %", "WACC %", "Debt/Equity", "Interest cover (x)", "Revenue CAGR 3Y %",
                "Profit CAGR 3Y %", "Statements basis", "Data source"]


def company_row(data: CompanyData, benchmark: Optional[pd.Series] = None) -> dict:
    if benchmark is not None and (data.benchmark_history is None or data.benchmark_history.empty):
        data.benchmark_history = benchmark
    at = annual_ratio_table(data)
    qt = quarterly_table(data)
    r = compute_core_ratios(data, at, qt)
    rw = analyse_roic_wacc(data, at, r) if not at.empty else {}

    def mv(key):
        m = r.get(key)
        return m.value if m is not None and m.available else None

    def growth(col):
        if at is None or len(at) < 4 or col not in at:
            return None
        return cagr(at[col].iloc[-1], at[col].iloc[-4], 3)

    last = at.iloc[-1] if not at.empty else {}
    wacc = rw.get("wacc") if rw else None
    return {
        "Company": data.identity.name or data.identity.nse_symbol,
        "Symbol": data.identity.nse_symbol or data.identity.bse_code,
        "CMP (₹)": num(data.quote.get("price")),
        "Market cap (₹ Cr)": num(data.quote.get("market_cap_cr")),
        "P/E": mv("pe"), "P/B": mv("pb"), "PEG": mv("peg"), "EV/EBITDA": mv("ev_ebitda"),
        "ROE %": mv("roe"), "ROCE %": mv("roce"), "ROIC %": mv("roic"),
        "WACC %": wacc.value if wacc is not None and wacc.available else None,
        "Debt/Equity": mv("de"),
        "Interest cover (x)": num(last.get("icr")) if len(last) else None,
        "Revenue CAGR 3Y %": growth("revenue"), "Profit CAGR 3Y %": growth("net_income"),
        "Statements basis": data.statement_basis, "Data source": data.statement_source or "N/A",
        "_sector_class": data.identity.sector_class,
    }


def analyse_peers(main: CompanyData, main_row: dict, loader: Optional[Callable[[str], Optional[CompanyData]]],
                  progress: Optional[Callable[[str], None]] = None) -> dict:
    out: dict = {"peers_requested": [p["symbol"] for p in main.peers], "failed": [], "points": []}
    rows = [dict(main_row, Company=f"{main_row['Company']} (selected)")]
    if loader is not None:
        for p in main.peers:
            if progress:
                progress(f"  peer {p['symbol']} ...")
            d = loader(p["symbol"])
            if d is None:
                out["failed"].append(p["symbol"])
                continue
            if not d.identity.name or d.identity.name == d.identity.nse_symbol:
                d.identity.name = p.get("name") or p["symbol"]
            try:
                rows.append(company_row(d, main.benchmark_history))
            except Exception as exc:  # noqa: BLE001
                log.warning("Peer %s analysis failed: %s", p["symbol"], exc)
                out["failed"].append(p["symbol"])
    df = pd.DataFrame(rows)
    out["source"] = main.peers[0]["source"] if main.peers else "No peers identified"
    is_fin = main.identity.sector_class in FINANCIAL_CLASSES
    # Do not compare financial companies with non-financial ones
    mixed = df["_sector_class"].apply(lambda c: (c in FINANCIAL_CLASSES) != is_fin)
    if mixed.iloc[1:].any():
        dropped = df.loc[mixed].index.tolist()
        out["points"].append("Removed peers from a different business model (financial vs non-financial): "
                             + ", ".join(df.loc[dropped, "Symbol"].astype(str)) + ".")
        df = df.loc[~mixed]
    df = df.drop(columns=["_sector_class"]).reset_index(drop=True)
    peers_only = df.iloc[1:]
    med = {c: median_of(peers_only[c]) for c in PEER_COLUMNS
           if c not in ("Company", "Symbol", "Statements basis", "Data source")}
    out["median"] = med
    if len(peers_only):
        med_row = {"Company": "Peer median", "Symbol": "", **med, "Statements basis": "", "Data source": ""}
        df = pd.concat([df, pd.DataFrame([med_row])], ignore_index=True)
    out["table"] = df[[c for c in PEER_COLUMNS if c in df.columns]]
    out["n_peers"] = len(peers_only)
    out["points"].extend(_explain(main_row, med, len(peers_only), is_fin))
    if out["failed"]:
        out["points"].append("Data could not be retrieved for: " + ", ".join(out["failed"]) + ".")
    return out


def _explain(row: dict, med: dict, n: int, is_fin: bool) -> list[str]:
    if n == 0:
        return ["No peer data available – the company could not be compared with its sector."]
    pts = [f"Compared with {n} sector peer(s) (peer median shown):"]
    checks = [("P/E", "valuation (P/E)", False), ("P/B", "price-to-book", False), ("ROE %", "ROE", True)]
    if not is_fin:
        checks += [("ROCE %", "ROCE", True), ("ROIC %", "ROIC", True), ("Debt/Equity", "debt-to-equity", False),
                   ("EV/EBITDA", "EV/EBITDA", False)]
    checks += [("Revenue CAGR 3Y %", "3-year revenue growth", True), ("Profit CAGR 3Y %", "3-year profit growth", True)]
    for col, label, higher_better in checks:
        v, m = row.get(col), med.get(col)
        if not (is_num(v) and is_num(m)) or m == 0:
            continue
        rel = (v - m) / abs(m) * 100
        pos = "higher" if v > m else "lower"
        if abs(rel) < 10:
            pts.append(f"• {label}: {v:.1f} vs median {m:.1f} – in line with peers.")
        else:
            good = (v > m) == higher_better
            tone = ("better than" if good else "weaker than") if col not in ("P/E", "P/B", "EV/EBITDA") else \
                ("richer (more expensive) than" if v > m else "cheaper than")
            pts.append(f"• {label}: {v:.1f} vs median {m:.1f} – {abs(rel):.0f}% {pos}, {tone} peers.")
    return pts
