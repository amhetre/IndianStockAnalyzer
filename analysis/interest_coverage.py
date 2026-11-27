"""Interest coverage ratio = EBIT / Interest expense (finance cost), with period trend."""
from __future__ import annotations

from typing import Optional

import pandas as pd

from analysis.fundamental_ratios import FINANCIAL_CLASSES
from data_providers.models import CompanyData
from utils.financial_utils import (ACTUAL, Metric, cagr, fmt_cr, is_num, not_meaningful, num, safe_div,
                                   unavailable)

# Sector-specific thresholds: (weak_below, moderate_below, strong_from)
SECTOR_THRESHOLDS = {
    "default": (2.0, 4.0, 4.0),
    "infrastructure": (1.5, 2.5, 3.0),   # regulated / annuity cash flows tolerate lower coverage
    "real_estate": (1.5, 3.0, 3.5),
    "it_services": (3.0, 8.0, 8.0),      # asset-light: expect very high coverage
    "manufacturing": (2.0, 4.0, 4.0),
}


def classify_icr(icr: Optional[float], sector_class: str) -> str:
    if not is_num(icr):
        return "Unavailable"
    weak, moderate, _ = SECTOR_THRESHOLDS.get(sector_class, SECTOR_THRESHOLDS["default"])
    if icr < 1:
        return "Serious concern"
    if icr < weak:
        return "Weak"
    if icr < moderate:
        return "Moderate"
    return "Strong"


def _sum_last(qt: pd.DataFrame, col: str, k: int) -> Optional[float]:
    if qt is None or qt.empty or col not in qt or len(qt) < k:
        return None
    w = qt[col].iloc[-k:]
    return None if w.isna().any() else float(w.sum())


def analyse_interest_coverage(data: CompanyData, at: pd.DataFrame, qt: pd.DataFrame) -> dict:
    sc = data.identity.sector_class
    out: dict = {"sector_class": sc, "thresholds": SECTOR_THRESHOLDS.get(sc, SECTOR_THRESHOLDS["default"])}
    if sc in FINANCIAL_CLASSES:
        out["metric"] = not_meaningful(
            "Interest coverage", "For banks/NBFCs interest paid on deposits/borrowings is their main cost of "
            "doing business; coverage is judged via net interest margin and asset quality instead.", "x",
            "EBIT / Interest expense")
        out["trend"] = pd.DataFrame()
        out["explanation"] = [out["metric"].note]
        return out
    src = data.statement_source
    if at is None or at.empty:
        out["metric"] = unavailable("Interest coverage", "No annual statements", "x", "EBIT / Interest expense")
        out["trend"] = pd.DataFrame()
        out["explanation"] = ["Interest coverage could not be calculated – no financial statements available."]
        return out
    last = at.iloc[-1]
    ebit, intr = num(last.get("ebit")), num(last.get("interest"))
    if is_num(intr) and intr == 0:
        out["metric"] = not_meaningful("Interest coverage", "No interest expense in the latest year (debt-free or "
                                       "negligible borrowing) – coverage is effectively unlimited.", "x",
                                       "EBIT / Interest expense", at.index[-1], {"EBIT": ebit, "Interest": intr}, src)
        out["no_interest"] = True
    elif is_num(ebit) and is_num(intr) and intr > 0:
        out["metric"] = Metric("Interest coverage", ebit / intr, "x", "EBIT / Interest expense", at.index[-1],
                               {"EBIT (₹ Cr)": ebit, "Interest (₹ Cr)": intr}, src, ACTUAL)
    else:
        out["metric"] = unavailable("Interest coverage", "EBIT or interest expense unavailable", "x",
                                    "EBIT / Interest expense", at.index[-1], {"EBIT": ebit, "Interest": intr}, src)
    out["ebit"], out["interest"] = ebit, intr
    out["label"] = classify_icr(out["metric"].value, sc) if out["metric"].available else (
        "Strong (no interest)" if out.get("no_interest") else "Unavailable")

    # Period trend 3M/6M/9M (quarterly sums) + 1Y/3Y/5Y (annual)
    rows = []
    for label, k in (("3M", 1), ("6M", 2), ("9M", 3)):
        e, i = _sum_last(qt, "ebit", k), _sum_last(qt, "interest", k)
        rows.append({"Period": label, "Basis": f"Last {k} quarter(s)", "EBIT (₹ Cr)": e, "Interest (₹ Cr)": i,
                     "ICR (x)": safe_div(e, i) if is_num(i) and i > 0 else None,
                     "Note": "" if is_num(e) and is_num(i) else "Quarterly EBIT/interest not available"})
    for label, n in (("1Y", 1), ("3Y", 3), ("5Y", 5)):
        if len(at) >= n:
            idx = at.index[-n]
            e, i = num(at["ebit"].iloc[-n]) if "ebit" in at else None, num(at["interest"].iloc[-n]) if "interest" in at else None
            rows.append({"Period": label, "Basis": f"FY {idx} (start of window)" if n > 1 else f"FY {idx}",
                         "EBIT (₹ Cr)": e, "Interest (₹ Cr)": i,
                         "ICR (x)": safe_div(e, i) if is_num(i) and i > 0 else None, "Note": ""})
        else:
            rows.append({"Period": label, "Basis": "", "EBIT (₹ Cr)": None, "Interest (₹ Cr)": None,
                         "ICR (x)": None, "Note": f"Fewer than {n} years of data"})
    out["trend"] = pd.DataFrame(rows).set_index("Period")
    out["annual"] = at[[c for c in ("ebit", "interest", "icr") if c in at]].copy()
    out["explanation"] = _explain(out, at)
    return out


def _explain(out: dict, at: pd.DataFrame) -> list[str]:
    m: Metric = out["metric"]
    ex = []
    weak, moderate, strong = out["thresholds"]
    if out.get("no_interest"):
        ex.append("1. Can it pay interest comfortably? Yes – the company reported no meaningful interest expense.")
    elif m.available:
        ex.append(f"EBIT is {fmt_cr(out['ebit'])} and interest expense is {fmt_cr(out['interest'])}, so interest "
                  f"coverage is {m.value:.1f} times. Meaning: the company earns ₹{m.value:.1f} of operating profit "
                  "for every ₹1 of interest it must pay.")
        verdict = {"Serious concern": "No – operating profit does not even cover interest. This is a serious warning.",
                   "Weak": "Only barely – a modest fall in profit could make interest hard to pay.",
                   "Moderate": "Reasonably – there is some cushion, but not a large one.",
                   "Strong": "Yes – there is a comfortable cushion."}[out["label"]]
        ex.append(f"1. Can it pay interest comfortably? {verdict} (Guide for this sector: below 1 serious, "
                  f"below {weak:g} weak, {weak:g}–{moderate:g} moderate, above {strong:g} stronger. "
                  "Thresholds are guides, not universal rules.)")
    else:
        ex.append("Interest coverage could not be calculated: " + (m.note or "data missing") + ".")
        return ex
    if "interest" in at and "ebit" in at and len(at) >= 4:
        i_s, e_s = at["interest"], at["ebit"]
        ig = cagr(i_s.iloc[-1], i_s.iloc[-4], 3)
        eg = cagr(e_s.iloc[-1], e_s.iloc[-4], 3)
        if ig is not None:
            ex.append(f"2. Is interest expense increasing? Over 3 years interest cost changed at {ig:+.1f}% a year "
                      f"({fmt_cr(i_s.iloc[-4])} → {fmt_cr(i_s.iloc[-1])}).")
        if ig is not None and eg is not None:
            faster = eg > ig
            ex.append(f"3. Is EBIT growing faster than interest? EBIT grew {eg:+.1f}% a year vs interest {ig:+.1f}% – "
                      + ("yes, operating profit is outpacing interest cost." if faster else
                         "no, interest cost is growing faster than operating profit."))
        icr_s = at["icr"].dropna() if "icr" in at else pd.Series(dtype=float)
        if len(icr_s) >= 2:
            better = icr_s.iloc[-1] > icr_s.iloc[0]
            ex.append(f"4. Becoming more or less risky? Coverage moved from {icr_s.iloc[0]:.1f}x ({icr_s.index[0]}) to "
                      f"{icr_s.iloc[-1]:.1f}x ({icr_s.index[-1]}) – the company is becoming "
                      + ("LESS financially risky." if better else "MORE financially risky on this measure."))
    else:
        ex.append("Trend questions (2–4) need at least 4 years of annual data, which is not available.")
    return ex
