"""
Benchmark remarks (Best / Good / Average / Below average) and formula hints.

Every parameter shown in the reports gets:
* a BENCHMARK remark – where the value sits in the published bands, and
* a HINT (hover text) – the formula, the source values used and the bands.

The bands are indicative screening ranges for Indian listed companies. They are
not universal investment rules: a bank is not judged with the bands of a
manufacturer, and a cyclical business looks expensive at the bottom of its cycle.
"""
from __future__ import annotations

from typing import Optional

from utils.financial_utils import Metric, is_num

BEST, GOOD, AVERAGE, BELOW = "Best", "Good", "Average", "Below average"
NA_REMARK = "—"

# direction "high": higher is better (bands are >= thresholds, best first)
# direction "low" : lower  is better (bands are <= thresholds, best first)
_B: dict[str, dict] = {
    # --- profitability -------------------------------------------------------
    "EBITDA margin": dict(d="high", u="%", b=[(25, BEST), (20, GOOD), (10, AVERAGE)],
                          note="Compare within the same industry and with the company's own history."),
    "EBITDA growth (YoY)": dict(d="high", u="%", b=[(20, BEST), (12, GOOD), (5, AVERAGE)]),
    "ROE": dict(d="high", u="%", b=[(20, BEST), (15, GOOD), (10, AVERAGE)],
                fin=[(15, BEST), (12, GOOD), (8, AVERAGE)],
                note="Check whether a high ROE is driven by debt or by genuinely high profitability."),
    "ROA": dict(d="high", u="%", b=[(10, BEST), (5, GOOD), (2, AVERAGE)],
                fin=[(1.5, BEST), (1.0, GOOD), (0.5, AVERAGE)],
                note="For lenders ROA is the key efficiency measure (typically 0.5%-2%)."),
    "ROCE": dict(d="high", u="%", b=[(20, BEST), (15, GOOD), (10, AVERAGE)],
                 note="ROCE should sit above the company's cost of capital (~9-10%)."),
    "ROIC": dict(d="high", u="%", b=[(20, BEST), (15, GOOD), (9, AVERAGE)],
                 note="ROIC above WACC means the business creates value."),
    # --- growth --------------------------------------------------------------
    "EPS growth (3Y CAGR)": dict(d="high", u="%", b=[(20, BEST), (12, GOOD), (5, AVERAGE)]),
    "EPS growth (YoY)": dict(d="high", u="%", b=[(20, BEST), (12, GOOD), (5, AVERAGE)]),
    "Revenue growth %": dict(d="high", u="%", b=[(20, BEST), (12, GOOD), (5, AVERAGE)]),
    "Profit growth %": dict(d="high", u="%", b=[(20, BEST), (12, GOOD), (5, AVERAGE)]),
    # --- debt & safety -------------------------------------------------------
    "Debt-to-Equity": dict(d="low", u="x", b=[(0.3, BEST), (0.7, GOOD), (1.5, AVERAGE)],
                           note="Lower is safer for non-financial companies; banks are judged on NPAs and capital."),
    "Interest coverage": dict(d="high", u="x", b=[(5, BEST), (3, GOOD), (2, AVERAGE)],
                              note="Below 1x the operating profit does not cover the interest bill – serious risk."),
    "Debt/EBITDA": dict(d="low", u="x", b=[(1, BEST), (2, GOOD), (3, AVERAGE)]),
    "Net debt/EBITDA": dict(d="low", u="x", b=[(1, BEST), (2, GOOD), (3, AVERAGE)]),
    "Current Ratio": dict(d="high", u="x", b=[(1.5, BEST), (1.0, GOOD), (0.7, AVERAGE)],
                          note="Below 1 means short-term liabilities exceed short-term assets."),
    # --- valuation -----------------------------------------------------------
    "P/E": dict(d="low", u="x", b=[(15, BEST), (25, GOOD), (40, AVERAGE)],
                note="Always compare with growth (PEG), peers and the stock's own history – low P/E is not "
                     "automatically cheap."),
    "P/B": dict(d="low", u="x", b=[(1.5, BEST), (3, GOOD), (5, AVERAGE)],
                note="Most useful for banks and asset-heavy businesses; must be read with ROE."),
    "PEG": dict(d="low", u="x", b=[(1, BEST), (1.5, GOOD), (2, AVERAGE)],
                note="Not meaningful when EPS growth is zero or negative."),
    "EV/EBITDA": dict(d="low", u="x", b=[(10, BEST), (15, GOOD), (25, AVERAGE)],
                      note="Useful across companies with different debt levels."),
    "Price to Sales": dict(d="low", u="x", b=[(2, BEST), (4, GOOD), (8, AVERAGE)]),
    "Dividend yield": dict(d="high", u="%", b=[(3, BEST), (1.5, GOOD), (0.5, AVERAGE)],
                           note="A very high yield can mean the price has fallen because the business is weak."),
    "Earnings yield": dict(d="high", u="%", b=[(8, BEST), (5, GOOD), (3, AVERAGE)],
                           note="Inverse of P/E: EPS / CMP x 100."),
    # --- cash flow -----------------------------------------------------------
    "CFO / Net profit (cumulative)": dict(d="high", u="x", b=[(1.0, BEST), (0.8, GOOD), (0.5, AVERAGE)],
                                          note="Share of reported profit that actually arrived as cash."),
    "CFO / Net profit (x)": dict(d="high", u="x", b=[(1.0, BEST), (0.8, GOOD), (0.5, AVERAGE)]),
    "Years with positive FCF": dict(d="high", u="%", b=[(100, BEST), (80, GOOD), (50, AVERAGE)]),
    # --- value creation ------------------------------------------------------
    "ROIC − WACC": dict(d="high", u="pp", b=[(5, BEST), (2, GOOD), (0, AVERAGE)],
                        note="Positive spread = value created; negative spread = value destroyed."),
    "ROE − Cost of equity": dict(d="high", u="pp", b=[(5, BEST), (2, GOOD), (0, AVERAGE)]),
    "ROIC vs WACC spread": dict(d="high", u="pp", b=[(5, BEST), (2, GOOD), (0, AVERAGE)]),
    # --- shareholding --------------------------------------------------------
    "Promoter change (pp)": dict(d="high", u="pp", b=[(0, BEST), (-1, GOOD), (-5, AVERAGE)],
                                 note="A falling promoter stake needs a reason (OFS, dilution, regulation)."),
    "Pledge % of promoter holding": dict(d="low", u="%", b=[(0, BEST), (5, GOOD), (15, AVERAGE)],
                                         note="A high or rising pledge means promoters have borrowed against shares."),
    # --- lenders -------------------------------------------------------------
    "Gross NPA %": dict(d="low", u="%", b=[(1, BEST), (2, GOOD), (4, AVERAGE)],
                        note="Gross non-performing assets – loans that have stopped paying, before provisions."),
    "Net NPA %": dict(d="low", u="%", b=[(0.5, BEST), (1, GOOD), (2, AVERAGE)],
                      note="NPAs after subtracting the provisions held against them."),
}

# Alternative spellings used across modules -> canonical key
_ALIASES = {
    "Debt-to-Equity": "Debt-to-Equity",
    "Debt/Equity": "Debt-to-Equity",
    "Interest coverage": "Interest coverage",
    "Interest cover": "Interest coverage",
    "ROIC − WACC": "ROIC − WACC",
    "ROIC - WACC": "ROIC − WACC",
    "ROE − Cost of equity": "ROE − Cost of equity",
    "ROE - Cost of equity": "ROE − Cost of equity",
    "Cash conversion": "CFO / Net profit (cumulative)",
    "Promoter change": "Promoter change (pp)",
    "Pledge %": "Pledge % of promoter holding",
    "ROE %": "ROE",
    "ROCE %": "ROCE",
    "ROIC %": "ROIC",
    "ROA %": "ROA",
    "P/E (x)": "P/E",
    "Debt/Equity (x)": "Debt-to-Equity",
    "Interest cover (x)": "Interest coverage",
    "EBITDA margin %": "EBITDA margin",
}

_UNIT_TEXT = {"%": "%", "x": "x", "pp": " pp", "": ""}


def _spec(key: str, financial: bool) -> Optional[dict]:
    canon = _ALIASES.get(key, key)
    s = _B.get(canon)
    if s is None:
        return None
    if financial and s.get("fin"):
        s = {**s, "b": s["fin"]}
    return s


def remark(key: str, value, financial: bool = False) -> str:
    """Best / Good / Average / Below average for a value, or '' when not assessable."""
    if not is_num(value):
        return ""
    s = _spec(key, financial)
    if s is None:
        return ""
    v = float(value)
    for thr, label in s["b"]:
        if (v >= thr if s["d"] == "high" else v <= thr):
            return label
    return BELOW


def bands_text(key: str, financial: bool = False) -> str:
    """Human-readable published bands, e.g. 'Best >= 20% | Good >= 15% | Average >= 10%'."""
    s = _spec(key, financial)
    if s is None:
        return ""
    sym = "≥" if s["d"] == "high" else "≤"
    u = _UNIT_TEXT.get(s["u"], "")
    parts = [f"{label} {sym} {thr:g}{u}" for thr, label in s["b"]]
    last_thr = s["b"][-1][0]
    lo_op = "<" if s["d"] == "high" else ">"
    parts.append(f"{BELOW} {lo_op} {last_thr:g}{u}")
    return " | ".join(parts)


def remark_for_metric(m: Optional[Metric], financial: bool = False) -> str:
    if m is None or not m.available:
        return ""
    return remark(m.name, m.value, financial)


def hint_for_metric(m: Optional[Metric], financial: bool = False) -> str:
    """Hover text: formula + source values + benchmark bands."""
    if m is None:
        return ""
    parts = []
    if m.formula:
        parts.append("Formula: " + m.formula)
    if m.inputs:
        parts.append("Inputs: " + m.inputs_text())
    b = bands_text(m.name, financial)
    if b:
        parts.append("Benchmark: " + b)
    if m.note:
        parts.append("Note: " + m.note)
    return "\n".join(parts)


def remark_badge_class(label: str) -> str:
    return {BEST: "b-best", GOOD: "b-good", AVERAGE: "b-avg", BELOW: "b-low"}.get(label, "b-na")


# ---------------------------------------------------------------------------
# Column-level hints (hover on a table header shows how the column is computed)
# ---------------------------------------------------------------------------
COLUMN_HINTS: dict[str, str] = {
    # history
    "Revenue (₹ Cr)": "Total income from sale of goods/services (as reported)",
    "EBITDA (₹ Cr)": "EBIT + Depreciation & Amortisation",
    "EBITDA margin %": "EBITDA / Revenue × 100",
    "EBIT (₹ Cr)": "Operating profit before interest and tax = PBT + finance cost",
    "Finance cost (₹ Cr)": "Interest and other borrowing costs",
    "Net profit (₹ Cr)": "Profit after tax attributable to shareholders",
    "EPS (₹)": "Net profit attributable to shareholders / Weighted average shares",
    "Revenue growth %": "(This year revenue / Last year revenue − 1) × 100",
    "Profit growth %": "(This year net profit / Last year net profit − 1) × 100",
    "EPS growth %": "(This year EPS / Last year EPS − 1) × 100",
    "ROE %": "Net profit / Average shareholders' equity × 100",
    "ROCE %": "EBIT / Average capital employed × 100",
    "ROIC %": "NOPAT / Average invested capital × 100 (NOPAT = EBIT × (1 − tax))",
    "ROA %": "Net profit / Average total assets × 100",
    "Debt/Equity (x)": "Total borrowings / Shareholders' equity",
    "Interest cover (x)": "EBIT / Finance cost",
    "Borrowings (₹ Cr)": "Short-term + long-term loans outstanding",
    "Cash (₹ Cr)": "Cash and cash equivalents",
    "Net debt (₹ Cr)": "Total borrowings − Cash and cash equivalents",
    "Equity (₹ Cr)": "Shareholders' funds (share capital + reserves)",
    "Operating cash flow (₹ Cr)": "Cash generated by normal business operations (CFO)",
    "Capex (₹ Cr)": "Cash spent on buying/creating fixed assets",
    "Free cash flow (₹ Cr)": "CFO − Capital expenditure",
    "Tax rate %": "Tax / Profit before tax × 100",
    "FY-end price (₹)": "Share price on the last trading day of that financial year",
    "P/E at FY end (x)": "FY-end price / EPS of that year",
    # period analysis
    "Start price (₹)": "Share price on the first day of the period",
    "Latest price (₹)": "Current market price (CMP)",
    "Price change (₹)": "Latest price − Start price",
    "Price change %": "(Latest price / Start price − 1) × 100",
    "Price CAGR %": "((Latest price / Start price)^(1 / years) − 1) × 100",
    "Operating profit growth %": "YoY / CAGR growth of EBIT",
    "P/E (x)": "CMP / Trailing EPS",
    # debt table
    "Total borrowings (₹ Cr)": "Short-term + long-term debt",
    "Short-term debt (₹ Cr)": "Loans due within 12 months",
    "Long-term debt (₹ Cr)": "Loans due after 12 months",
    "Debt/EBITDA (x)": "Total borrowings / EBITDA",
    "Net debt/EBITDA (x)": "(Borrowings − Cash) / EBITDA",
    # cash flow table
    "CFO / Net profit (x)": "Cumulative CFO / Cumulative net profit",
    # interest coverage
    "EBIT (₹ Cr)": "Earnings before interest and tax",
    "Interest (₹ Cr)": "Interest and finance charges for the period",
    "ICR (x)": "EBIT / Interest expense",
    # shareholding
    "Promoters %": "Promoter shares / Total shares × 100",
    "Promoter QoQ change (pp)": "This quarter's promoter % − previous quarter's (percentage points)",
    "FII %": "Foreign portfolio investor holding / Total shares × 100",
    "DII %": "Domestic institutional investor holding / Total shares × 100",
    "Government %": "Government / PSU holding / Total shares × 100",
    "Public %": "Public (retail + others) holding / Total shares × 100",
    "Pledged % of promoter holding": "Pledged promoter shares / Promoter shares × 100",
    "Pledged % of total shares": "Pledged promoter shares / Total shares × 100",
    "No. of shareholders": "Count of registered shareholders",
    # peers
    "Market cap": "CMP × Total outstanding shares",
    "WACC %": "E/(D+E) × Ke + D/(D+E) × Kd × (1 − tax); Ke = Rf + β × ERP",
    # score
    "Category score %": "Points earned / Points available for that category",
    "Weight": "Configured weight of the category (config.py SCORE_WEIGHTS)",
}
