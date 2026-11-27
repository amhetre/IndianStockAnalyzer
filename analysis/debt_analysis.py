"""Debt structure, trend and serviceability."""
from __future__ import annotations

import pandas as pd

from analysis.fundamental_ratios import FINANCIAL_CLASSES
from data_providers.models import CompanyData
from utils.financial_utils import fmt_cr, fmt_x, is_num, num, pct_change, safe_div


def analyse_debt(data: CompanyData, at: pd.DataFrame) -> dict:
    out: dict = {"is_financial": data.identity.sector_class in FINANCIAL_CLASSES, "points": []}
    if at is None or at.empty:
        out["summary"] = "Debt could not be analysed – no balance-sheet data."
        out["table"] = pd.DataFrame()
        return out
    cols = ["debt", "short_term_debt", "long_term_debt", "cash", "net_debt", "equity", "de", "ebitda", "cfo", "fcf",
            "interest"]
    tbl = at[[c for c in cols if c in at.columns]].copy()
    if "debt" in tbl and "ebitda" in tbl:
        tbl["debt_to_ebitda"] = [safe_div(d, e) if is_num(e) and e > 0 else None for d, e in zip(tbl["debt"], tbl["ebitda"])]
    if "net_debt" in tbl and "ebitda" in tbl:
        tbl["net_debt_to_ebitda"] = [safe_div(d, e) if is_num(e) and e > 0 else None
                                     for d, e in zip(tbl["net_debt"], tbl["ebitda"])]
    out["table"] = tbl
    last = at.iloc[-1]
    debt, cash, eq = num(last.get("debt")), num(last.get("cash")), num(last.get("equity"))
    out.update({"debt": debt, "cash": cash, "net_debt": num(last.get("net_debt")),
                "short_term_debt": num(last.get("short_term_debt")), "long_term_debt": num(last.get("long_term_debt")),
                "de": num(last.get("de")), "fy": at.index[-1]})
    pts = out["points"]

    if out["is_financial"]:
        dep = data.annual.loc["deposits"].dropna() if "deposits" in data.annual.index else pd.Series(dtype=float)
        pts.append("This is a financial company. Banks and NBFCs borrow (or take deposits) and lend that money at a "
                   "higher rate – borrowing is their raw material, so a high Debt-to-Equity is normal and NOT a "
                   "warning sign by itself. Asset quality (NPAs) and capital adequacy matter more.")
        if len(dep):
            pts.append(f"Deposits: {fmt_cr(dep.iloc[-1])} ({at.index[-1]}).")
        if is_num(debt):
            pts.append(f"Borrowings: {fmt_cr(debt)}.")
        out["summary"] = " ".join(pts)
        return out

    # 1. has debt?
    if not is_num(debt):
        pts.append("Borrowings figure is not available from the data source.")
    elif debt < 1:
        pts.append("The company is practically DEBT-FREE (borrowings below ₹1 crore).")
    else:
        pts.append(f"The company has borrowings of {fmt_cr(debt)} as of {at.index[-1]}"
                   + (f" (short-term {fmt_cr(out['short_term_debt'])}, long-term {fmt_cr(out['long_term_debt'])})"
                      if is_num(out["short_term_debt"]) and is_num(out["long_term_debt"]) else "") + ".")
        if is_num(cash):
            pts.append(f"Cash & equivalents are {fmt_cr(cash)}, so net debt is {fmt_cr(out['net_debt'])}"
                       + (" – it holds more cash than debt (net cash position)." if out["net_debt"] is not None and out["net_debt"] < 0 else "."))
        else:
            pts.append("Cash balance is not available, so net debt cannot be calculated.")
    pts.append("Why companies borrow: to build factories, buy equipment, fund acquisitions, or finance day-to-day "
               "working capital (inventory and customer credit). Debt is not bad by itself – it becomes risky when "
               "profits and cash flows are not enough to pay interest and repay on time.")
    # 2. trend
    ds = at["debt"].dropna() if "debt" in at else pd.Series(dtype=float)
    if len(ds) >= 2:
        n = min(3, len(ds) - 1)
        ch = pct_change(ds.iloc[-1], ds.iloc[-1 - n])
        direction = ("increased" if ds.iloc[-1] > ds.iloc[-1 - n] else "decreased")
        pts.append(f"Debt has {direction} from {fmt_cr(ds.iloc[-1 - n])} ({ds.index[-1 - n]}) to {fmt_cr(ds.iloc[-1])} "
                   f"({ds.index[-1]})" + (f", a change of {ch:+.0f}%." if ch is not None else "."))
        out["debt_trend"] = direction
        # 3. purpose evidence: capex vs debt increase
        cap = at["capex"].iloc[-n:] if "capex" in at else pd.Series(dtype=float)
        if direction == "increased" and cap.notna().all() and len(cap):
            inc = ds.iloc[-1] - ds.iloc[-1 - n]
            capsum = float(cap.sum())
            if capsum >= inc * 0.8:
                pts.append(f"Evidence of expansion use: capital expenditure over the same years was {fmt_cr(capsum)}, "
                           f"larger than the {fmt_cr(inc)} rise in debt – borrowing appears linked to investment in assets.")
            else:
                pts.append(f"Capital expenditure ({fmt_cr(capsum)}) was smaller than the rise in debt ({fmt_cr(inc)}); "
                           "part of the borrowing may be funding operations, working capital, acquisitions or "
                           "dividends. Check the annual report for details.")
        elif direction == "increased":
            pts.append("Capex data is not available, so the purpose of new borrowing cannot be inferred from the numbers.")
    # 4. manageable?
    de = out["de"]
    if is_num(de):
        level = ("low" if de < 0.5 else "moderate" if de < 1 else "high" if de < 2 else "very high")
        pts.append(f"Debt-to-Equity is {fmt_x(de)} – {level} for a non-financial company "
                   + ({"low": "(lenders' claim is small relative to owners' money).",
                       "moderate": "(manageable if profits are stable).",
                       "high": "(the company relies significantly on borrowed money).",
                       "very high": "(heavy reliance on borrowing; vulnerable if profits fall)."}[level]))
        if data.identity.sector_class in ("infrastructure", "real_estate") and de >= 1:
            pts.append("Note: infrastructure and real-estate businesses typically carry higher debt because projects "
                       "are long and capital-intensive; compare with sector peers.")
    # 5. cash flow to service
    cfo = num(last.get("cfo"))
    intr = num(last.get("interest"))
    if is_num(cfo) and is_num(intr) and intr > 0:
        cov = cfo / intr
        pts.append(f"Operating cash flow ({fmt_cr(cfo)}) covers interest ({fmt_cr(intr)}) {cov:.1f} times"
                   + (" – comfortable." if cov > 4 else " – adequate." if cov > 2 else " – tight; debt servicing depends on refinancing."))
    if is_num(debt) and is_num(cfo) and cfo > 0 and debt > 1:
        yrs = debt / cfo
        pts.append(f"At the current operating cash flow, total debt equals about {yrs:.1f} years of cash generation"
                   + (" (low)." if yrs < 2 else " (moderate)." if yrs < 4 else " (high)."))
    elif is_num(cfo) and cfo <= 0 and is_num(debt) and debt > 1:
        pts.append("Operating cash flow was negative in the latest year – debt cannot be serviced from operations "
                   "alone right now; this is a risk factor.")
    out["summary"] = " ".join(pts)
    return out
