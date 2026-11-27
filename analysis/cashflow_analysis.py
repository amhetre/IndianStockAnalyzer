"""Cash flow quality: CFO, capex, FCF, cash conversion."""
from __future__ import annotations

import pandas as pd

from analysis.fundamental_ratios import FINANCIAL_CLASSES
from data_providers.models import CompanyData
from utils.financial_utils import fmt_cr, is_num, safe_div


def analyse_cashflow(data: CompanyData, at: pd.DataFrame) -> dict:
    out: dict = {"points": [], "is_financial": data.identity.sector_class in FINANCIAL_CLASSES}
    if at is None or at.empty or "cfo" not in at or at["cfo"].dropna().empty:
        out["table"] = pd.DataFrame()
        out["summary"] = "Cash flow statements are not available from the data sources."
        return out
    tbl = at[[c for c in ("net_income", "cfo", "capex", "fcf", "cash_conversion") if c in at]].copy()
    out["table"] = tbl
    pts = out["points"]
    if out["is_financial"]:
        pts.append("For banks/NBFCs, operating cash flow swings with loan growth and deposit flows, so it is not a "
                   "reliable measure of earnings quality. The figures are shown for completeness only.")
        out["summary"] = " ".join(pts)
        return out
    n = min(5, len(tbl))
    win = tbl.iloc[-n:]
    ni_sum = win["net_income"].sum(min_count=n) if "net_income" in win else None
    cfo_sum = win["cfo"].sum(min_count=n)
    out["years"] = n
    out["cum_net_income"], out["cum_cfo"] = ni_sum, cfo_sum
    conv = safe_div(cfo_sum, ni_sum) if is_num(ni_sum) and ni_sum > 0 else None
    out["cum_conversion"] = conv
    last = tbl.iloc[-1]
    pts.append(f"Latest year ({tbl.index[-1]}): operating cash flow {fmt_cr(last.get('cfo'))} vs net profit "
               f"{fmt_cr(last.get('net_income'))}.")
    if is_num(conv):
        pts.append(f"Over the last {n} years, the company generated {fmt_cr(cfo_sum)} of operating cash against "
                   f"{fmt_cr(ni_sum)} of reported profit – a cash conversion of {conv*100:.0f}%. "
                   + ("Profits are converting well into real cash." if conv >= 1 else
                      "Most profit is converting into cash." if conv >= 0.8 else
                      "A significant part of profit is NOT turning into cash – check receivables and inventory."
                      if conv >= 0.5 else
                      "Weak – reported profits are not backed by cash flow; this is a red flag worth investigating."))
    if "fcf" in tbl and tbl["fcf"].notna().any():
        f = win["fcf"].dropna()
        pos = int((f > 0).sum())
        out["fcf_positive_years"], out["fcf_years"] = pos, len(f)
        pts.append(f"Free cash flow (operating cash minus capex) was positive in {pos} of {len(f)} years; latest FCF "
                   f"{fmt_cr(last.get('fcf'))}.")
        if len(f) >= 3:
            trend = "improving" if f.iloc[-1] > f.iloc[0] else "declining"
            pts.append(f"The free-cash-flow trend is {trend} ({fmt_cr(f.iloc[0])} → {fmt_cr(f.iloc[-1])}). Negative "
                       "FCF is acceptable during heavy expansion, but must eventually turn positive.")
    else:
        pts.append("Capital expenditure is not available, so free cash flow cannot be calculated.")
    out["summary"] = " ".join(pts)
    return out
