"""Display tables shared by the Excel and HTML reports (same numbers in both)."""
from __future__ import annotations

import html as _html
from typing import Optional

import pandas as pd

from analysis import benchmarks as bm
from utils.financial_utils import Metric, indian_group, is_num

HISTORY_COLS = [
    ("period_end", "Period end"), ("revenue", "Revenue (₹ Cr)"), ("ebitda", "EBITDA (₹ Cr)"),
    ("ebitda_margin", "EBITDA margin %"), ("ebit", "EBIT (₹ Cr)"), ("interest", "Finance cost (₹ Cr)"),
    ("net_income", "Net profit (₹ Cr)"), ("eps", "EPS (₹)"), ("revenue_growth", "Revenue growth %"),
    ("profit_growth", "Profit growth %"), ("eps_growth", "EPS growth %"), ("roe", "ROE %"), ("roce", "ROCE %"),
    ("roic", "ROIC %"), ("roa", "ROA %"), ("de", "Debt/Equity (x)"), ("icr", "Interest cover (x)"),
    ("debt", "Borrowings (₹ Cr)"), ("cash", "Cash (₹ Cr)"), ("net_debt", "Net debt (₹ Cr)"),
    ("equity", "Equity (₹ Cr)"), ("cfo", "Operating cash flow (₹ Cr)"), ("capex", "Capex (₹ Cr)"),
    ("fcf", "Free cash flow (₹ Cr)"), ("tax_rate", "Tax rate %"), ("fy_end_price", "FY-end price (₹)"),
    ("pe", "P/E at FY end (x)"),
]

PERIOD_COLS = [
    ("start_date", "Start date"), ("start_price", "Start price (₹)"), ("latest_price", "Latest price (₹)"),
    ("abs_change", "Price change (₹)"), ("pct_change", "Price change %"), ("price_cagr", "Price CAGR %"),
    ("basis", "Financial basis"), ("window", "Financial window"), ("revenue_growth", "Revenue growth %"),
    ("ebitda_growth", "EBITDA growth %"), ("operating_profit_growth", "Operating profit growth %"),
    ("profit_growth", "Net profit growth %"), ("eps_growth", "EPS growth %"), ("roe", "ROE %"),
    ("roce", "ROCE %"), ("roic", "ROIC %"), ("de", "Debt/Equity (x)"), ("icr", "Interest cover (x)"),
    ("pe", "P/E (x)"), ("ratio_note", "Ratio note"), ("note", "Data note"),
]

PROMOTER_COLS = [("quarter", "Quarter"), ("promoters", "Promoters %"), ("promoter_qoq_change", "Promoter QoQ change (pp)"),
                 ("fii", "FII %"), ("dii", "DII %"), ("government", "Government %"), ("public", "Public %"),
                 ("others", "Others %"), ("num_shareholders", "No. of shareholders"),
                 ("pledged_pct_of_promoter", "Pledged % of promoter holding"),
                 ("pledged_pct_of_total", "Pledged % of total shares")]


def history_df(at: pd.DataFrame) -> pd.DataFrame:
    if at is None or at.empty:
        return pd.DataFrame()
    cols = [(c, n) for c, n in HISTORY_COLS if c in at.columns and (c == "period_end" or at[c].notna().any())]
    df = at[[c for c, _ in cols]].copy()
    df.columns = [n for _, n in cols]
    if "Period end" in df:
        df["Period end"] = pd.to_datetime(df["Period end"]).dt.date
    df.index.name = "Year"
    return df


def period_df(per: pd.DataFrame) -> pd.DataFrame:
    if per is None or per.empty:
        return pd.DataFrame()
    cols = [(c, n) for c, n in PERIOD_COLS if c in per.columns]
    df = per[[c for c, _ in cols]].copy()
    df.columns = [n for _, n in cols]
    return df


def promoter_df(tbl: pd.DataFrame) -> pd.DataFrame:
    if tbl is None or tbl.empty:
        return pd.DataFrame()
    cols = [(c, n) for c, n in PROMOTER_COLS if c in tbl.columns and tbl[c].notna().any()]
    df = tbl[[c for c, _ in cols]].copy()
    df.columns = [n for _, n in cols]
    return df.reset_index(drop=True)


def metrics_df(metrics: list[Metric], financial: bool = False) -> pd.DataFrame:
    """Metric rows with a Benchmark remark (Best / Good / Average / Below average)."""
    rows = []
    for m in metrics:
        if m is None:
            continue
        row = m.to_row()
        row["Benchmark"] = bm.remark_for_metric(m, financial) or bm.NA_REMARK
        rows.append(row)
    df = pd.DataFrame(rows)
    if not df.empty:
        ordered = ["Metric", "Display", "Benchmark", "Unit", "Formula", "Period", "Inputs",
                   "Source", "Status", "Note", "Value"]
        df = df[[c for c in ordered if c in df.columns] +
                [c for c in df.columns if c not in ordered]]
    return df


def _hint_span(text: str, css: str = "hint") -> str:
    """'!' badge whose hover tooltip (native title, never clipped by scrolling
    containers) shows the formula / benchmark bands."""
    tip = _html.escape(text, quote=True)
    return f'<span class="{css}" title="{tip}">!</span>'


def _remark_span(label: str) -> str:
    if not label or label == bm.NA_REMARK:
        return f'<span class="badge b-na">{_html.escape(label or bm.NA_REMARK)}</span>'
    return (f'<span class="badge {bm.remark_badge_class(label)}">'
            f"{_html.escape(label)}</span>")


def metrics_html(metrics: list[Metric], financial: bool = False) -> str:
    """HTML table of metrics; every metric name carries a '!' with its formula on hover."""
    head = ["Metric", "Value", "Benchmark", "Period", "Formula", "Inputs", "Source", "Status", "Note"]
    tr = ["<table class='tbl'><thead><tr>" +
          "".join(f"<th>{_html.escape(h)}</th>" for h in head) + "</tr></thead><tbody>"]
    any_row = False
    for m in metrics:
        if m is None:
            continue
        any_row = True
        row = m.to_row()
        bmk = bm.remark_for_metric(m, financial) or bm.NA_REMARK
        tip = bm.hint_for_metric(m, financial) or row.get("Formula", "")
        cells = [
            f"<td>{_html.escape(row['Metric'])} {_hint_span(tip)}</td>",
            f"<td>{_html.escape(row['Display'])}</td>",
            f"<td>{_remark_span(bmk)}</td>",
            f"<td>{_html.escape(str(row.get('Period') or '—'))}</td>",
            f"<td>{_html.escape(str(row.get('Formula') or '—'))}</td>",
            f"<td>{_html.escape(str(row.get('Inputs') or '—'))}</td>",
            f"<td>{_html.escape(str(row.get('Source') or '—'))}</td>",
            f"<td>{_html.escape(str(row.get('Status') or '—'))}</td>",
            f"<td>{_html.escape(str(row.get('Note') or '—'))}</td>",
        ]
        tr.append("<tr>" + "".join(cells) + "</tr>")
    tr.append("</tbody></table>")
    if not any_row:
        return '<p class="muted">No data available.</p>'
    return "".join(tr)


def debt_df(tbl: pd.DataFrame) -> pd.DataFrame:
    """Debt table with readable column names (shared by Excel and HTML)."""
    if tbl is None or tbl.empty:
        return pd.DataFrame()
    names = {"debt": "Total borrowings (₹ Cr)", "short_term_debt": "Short-term debt (₹ Cr)",
             "long_term_debt": "Long-term debt (₹ Cr)", "cash": "Cash (₹ Cr)", "net_debt": "Net debt (₹ Cr)",
             "equity": "Equity (₹ Cr)", "de": "Debt/Equity (x)", "ebitda": "EBITDA (₹ Cr)",
             "cfo": "Operating cash flow (₹ Cr)", "fcf": "Free cash flow (₹ Cr)", "interest": "Finance cost (₹ Cr)",
             "debt_to_ebitda": "Debt/EBITDA (x)", "net_debt_to_ebitda": "Net debt/EBITDA (x)"}
    dt = tbl.rename(columns=names)
    dt.index.name = "Year"
    return dt.loc[:, dt.notna().any()]


def cashflow_df(tbl: pd.DataFrame) -> pd.DataFrame:
    """Cash-flow table with readable column names (shared by Excel and HTML)."""
    if tbl is None or tbl.empty:
        return pd.DataFrame()
    names = {"net_income": "Net profit (₹ Cr)", "cfo": "Operating cash flow (₹ Cr)",
             "capex": "Capex (₹ Cr)", "fcf": "Free cash flow (₹ Cr)",
             "cash_conversion": "CFO / Net profit (x)"}
    ct = tbl.rename(columns=names)
    ct.index.name = "Year"
    return ct


def quarterly_df(qt: pd.DataFrame) -> pd.DataFrame:
    if qt is None or qt.empty:
        return pd.DataFrame()
    names = {"revenue": "Revenue (₹ Cr)", "operating_profit": "Operating profit (₹ Cr)", "ebitda": "EBITDA (₹ Cr)",
             "ebit": "EBIT (₹ Cr)", "depreciation": "Depreciation (₹ Cr)", "interest": "Finance cost (₹ Cr)",
             "pbt": "PBT (₹ Cr)", "net_income": "Net profit (₹ Cr)", "eps_basic": "EPS (₹)", "icr": "Interest cover (x)"}
    df = qt[[c for c in names if c in qt and qt[c].notna().any()]].rename(columns=names)
    df.index = [d.strftime("%b %Y") for d in df.index]
    df.index.name = "Quarter"
    return df


def fmt_cell(v, col: str = "") -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if not is_num(v):
            return "—"
        if "%" in col or "(pp)" in col:
            return f"{v:,.1f}%" if "(pp)" not in col else f"{v:+.2f}"
        if "(x)" in col or col in ("P/E", "P/B", "PEG", "EV/EBITDA", "Debt/Equity"):
            return f"{v:.2f}"
        if "₹ Cr" in col or "Market cap" in col:
            return indian_group(v, 0)
        if "shareholders" in col.lower():
            return indian_group(v, 0)
        if "(₹)" in col:
            return indian_group(v, 2)
        return indian_group(v, 2) if abs(v) < 1e5 else indian_group(v, 0)
    return str(v)


def to_html(df: pd.DataFrame, index: bool = True, cls: str = "tbl",
            hints: Optional[dict] = None) -> str:
    """Render a DataFrame. `hints` maps a column name to the formula shown when the
    user hovers the '!' badge in that column header."""
    if df is None or df.empty:
        return '<p class="muted">No data available.</p>'
    d = df.copy()
    for c in d.columns:
        d[c] = [fmt_cell(v, str(c)) for v in d[c]]
    out = d.to_html(index=index, classes=cls, border=0, escape=True, na_rep="—")
    if hints:
        for col, text in hints.items():
            col = str(col)
            if col not in [str(c) for c in d.columns]:
                continue
            # Escape the header exactly as pandas did, then append the badge.
            esc = _html.escape(col)
            out = out.replace(f"<th>{esc}</th>",
                              f"<th>{esc} {_hint_span(str(text))}</th>", 1)
    return out
