"""Professionally formatted 14-sheet Excel workbook (openpyxl)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.comments import Comment
from openpyxl.formatting.rule import CellIsRule, ColorScaleRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from analysis import benchmarks as bm
from reporting import education, tables
from utils.financial_utils import fmt_cr, fmt_inr, fmt_pct, is_num

NAVY = "1F3A5F"
HEAD_FILL = PatternFill("solid", fgColor="F1F0EC")
TITLE_FONT = Font(name="Calibri", size=16, bold=True, color=NAVY)
H2_FONT = Font(name="Calibri", size=12, bold=True, color=NAVY)
HEAD_FONT = Font(name="Calibri", size=10, bold=True, color="52514E")
BODY_FONT = Font(name="Calibri", size=10)
MUTED_FONT = Font(name="Calibri", size=9, italic=True, color="898781")
WRAP = Alignment(wrap_text=True, vertical="top")
THIN = Border(bottom=Side(style="thin", color="E1E0D9"))
RED_FILL = PatternFill("solid", fgColor="FBE4E4")
GREEN_FILL = PatternFill("solid", fgColor="E2F4E2")
AMBER_FILL = PatternFill("solid", fgColor="FFF3D6")
GREY_FILL = PatternFill("solid", fgColor="EEEEEA")
DEMO_FILL = PatternFill("solid", fgColor="FFE08A")

INR_CR = '[>=10000000]##\\,##\\,##\\,##0;[>=100000]##\\,##\\,##0;##,##0;-##,##0'
FMT_PCT = '0.0"%";-0.0"%"'
FMT_X = '0.00"x"'
FMT_RS = '"₹"#,##0.00'
FMT_NUM = '#,##0.00'
SERIES_COLORS = ["2A78D6", "EB6834", "1BAF7A", "EDA100", "E87BA4", "008300"]


def _num_format(col: str) -> Optional[str]:
    c = col.lower()
    if "%" in col:
        return FMT_PCT
    if "(pp)" in c:
        return '+0.00;-0.00'
    if "(x)" in c or col in ("P/E", "P/B", "PEG", "EV/EBITDA", "Debt/Equity"):
        return FMT_X
    if "₹ cr" in c or "market cap" in c:
        return INR_CR
    if "(₹)" in col or "price" in c and "change %" not in c:
        return FMT_RS
    if "shareholders" in c:
        return INR_CR
    return None


class Sheet:
    def __init__(self, wb: Workbook, title: str, demo: bool):
        self.ws = wb.create_sheet(title[:31])
        self.row = 1
        self.ws.sheet_view.showGridLines = False
        self.ws.column_dimensions["A"].width = 30
        for i in range(2, 30):
            self.ws.column_dimensions[get_column_letter(i)].width = 15
        if demo:
            c = self.ws.cell(row=1, column=1, value="SYNTHETIC DEMO DATA – not a real company. For layout demonstration only.")
            c.font = Font(bold=True, color="5C4200")
            c.fill = DEMO_FILL
            self.ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=10)
            self.row = 2

    def title(self, text: str, sub: str = ""):
        self.ws.cell(row=self.row, column=1, value=text).font = TITLE_FONT
        self.row += 1
        if sub:
            self.ws.cell(row=self.row, column=1, value=sub).font = MUTED_FONT
            self.row += 1
        self.row += 1

    def h2(self, text: str):
        self.row += 1
        self.ws.cell(row=self.row, column=1, value=text).font = H2_FONT
        self.row += 1

    def para(self, text: str, width_cols: int = 10, height: Optional[int] = None):
        if not text:
            return
        c = self.ws.cell(row=self.row, column=1, value=text)
        c.alignment = WRAP
        c.font = BODY_FONT
        self.ws.merge_cells(start_row=self.row, start_column=1, end_row=self.row, end_column=width_cols)
        est = height or max(15, min(400, 15 * (len(text) // 140 + 1)))
        self.ws.row_dimensions[self.row].height = est
        self.row += 1

    def bullets(self, items: list[str], empty: str = "None."):
        if not items:
            self.para(empty)
        for it in items:
            self.para("• " + it)

    def kv(self, pairs: list[tuple[str, object, Optional[str]]]):
        for k, v, fmt in pairs:
            a = self.ws.cell(row=self.row, column=1, value=k)
            a.font = HEAD_FONT
            b = self.ws.cell(row=self.row, column=2, value=v if not (isinstance(v, float) and pd.isna(v)) else None)
            b.font = BODY_FONT
            if v is None:
                b.value = "N/A"
                b.font = MUTED_FONT
            elif fmt:
                b.number_format = fmt
            self.ws.merge_cells(start_row=self.row, start_column=2, end_row=self.row, end_column=4)
            self.row += 1

    def table(self, df: pd.DataFrame, index: bool = True, wrap_cols: tuple = (),
              widths: Optional[dict] = None, hints: Optional[dict] = None) -> dict:
        """Write a DataFrame. Returns positions for charts / conditional formats.

        `hints` maps a column name to the formula that is shown when the user
        hovers the header cell (Excel comment)."""
        if df is None or df.empty:
            self.ws.cell(row=self.row, column=1, value="No data available.").font = MUTED_FONT
            self.row += 2
            return {}
        d = df.reset_index() if index else df.copy()
        if index and d.columns[0] == "index":
            d = d.rename(columns={"index": ""})
        start = self.row
        for j, col in enumerate(d.columns, 1):
            c = self.ws.cell(row=start, column=j, value=str(col))
            c.font, c.fill, c.alignment = HEAD_FONT, HEAD_FILL, Alignment(wrap_text=True, vertical="center")
            hint = (hints or {}).get(str(col))
            if hint:
                cm = Comment(str(hint), "How it is calculated")
                cm.width, cm.height = 340, 110
                c.comment = cm
        self.ws.row_dimensions[start].height = 30
        for i, (_, r) in enumerate(d.iterrows(), 1):
            for j, col in enumerate(d.columns, 1):
                v = r[col]
                if isinstance(v, float) and pd.isna(v):
                    v = None
                elif hasattr(v, "item") and not isinstance(v, str):
                    try:
                        v = v.item()
                    except (ValueError, AttributeError):
                        v = str(v)
                if isinstance(v, (pd.Timestamp,)):
                    v = v.date()
                if isinstance(v, (list, dict, tuple)):
                    v = str(v)
                c = self.ws.cell(row=start + i, column=j, value=v)
                c.font, c.border = BODY_FONT, THIN
                fmt = _num_format(str(col))
                if fmt and isinstance(v, (int, float)) and not isinstance(v, bool):
                    c.number_format = fmt
                elif isinstance(v, float):
                    c.number_format = FMT_NUM
                if v is None:
                    c.value = "—"
                    c.alignment = Alignment(horizontal="center")
                    c.font = MUTED_FONT
                if str(col) in wrap_cols:
                    c.alignment = WRAP
        if widths:
            for col_name, w in widths.items():
                if col_name in list(d.columns):
                    self.ws.column_dimensions[get_column_letter(list(d.columns).index(col_name) + 1)].width = w
        end = start + len(d)
        self.row = end + 2
        return {"header_row": start, "first": start + 1, "last": end,
                "cols": {str(c): j for j, c in enumerate(d.columns, 1)}}

    def col_letter(self, pos: dict, name: str) -> Optional[str]:
        j = pos.get("cols", {}).get(name)
        return get_column_letter(j) if j else None

    def cond_scale(self, pos: dict, name: str, reverse: bool = False):
        L = self.col_letter(pos, name)
        if not L:
            return
        rng = f"{L}{pos['first']}:{L}{pos['last']}"
        lo, hi = ("F8696B", "63BE7B") if not reverse else ("63BE7B", "F8696B")
        self.ws.conditional_formatting.add(rng, ColorScaleRule(start_type="min", start_color=lo,
                                                               mid_type="percentile", mid_value=50, mid_color="FFEB84",
                                                               end_type="max", end_color=hi))

    def cond_lt(self, pos: dict, name: str, value: float, fill=RED_FILL):
        L = self.col_letter(pos, name)
        if L:
            self.ws.conditional_formatting.add(f"{L}{pos['first']}:{L}{pos['last']}",
                                               CellIsRule(operator="lessThan", formula=[str(value)], fill=fill))

    def cond_gt(self, pos: dict, name: str, value: float, fill=RED_FILL):
        L = self.col_letter(pos, name)
        if L:
            self.ws.conditional_formatting.add(f"{L}{pos['first']}:{L}{pos['last']}",
                                               CellIsRule(operator="greaterThan", formula=[str(value)], fill=fill))

    def cond_text(self, pos: dict, name: str):
        """Availability / benchmark indicator colouring on a column."""
        L = self.col_letter(pos, name)
        if not L:
            return
        rng = f"{L}{pos['first']}:{L}{pos['last']}"
        f = pos["first"]
        for word, fill in (("Below average", RED_FILL), ("Best", GREEN_FILL), ("Good", GREEN_FILL),
                           ("Average", AMBER_FILL),
                           ("Unavailable", RED_FILL), ("Not meaningful", GREY_FILL), ("Estimate", AMBER_FILL),
                           ("Derived", AMBER_FILL), ("Actual", GREEN_FILL), ("Failed", RED_FILL),
                           ("Restricted", RED_FILL), ("Partial", AMBER_FILL), ("OK", GREEN_FILL),
                           ("Excluded", GREY_FILL), ("Scored", GREEN_FILL), ("No", RED_FILL), ("Yes", GREEN_FILL)):
            self.ws.conditional_formatting.add(
                rng, FormulaRule(formula=[f'ISNUMBER(SEARCH("{word}",{L}{f}))'] if word not in ("No", "Yes", "OK")
                                 else [f'{L}{f}="{word}"'], fill=fill, stopIfTrue=True))

    def metric_comments(self, pos: dict, df: pd.DataFrame, col: str = "Metric"):
        """Hover comment (formula + inputs + benchmark bands) on each metric name cell."""
        j = pos.get("cols", {}).get(col)
        if not j or df is None or df.empty or col not in df.columns:
            return
        for i, (_, row) in enumerate(df.iterrows()):
            parts = []
            for label, key in (("Formula", "Formula"), ("Inputs", "Inputs"), ("Benchmark", "Benchmark")):
                v = row.get(key)
                if v is not None and str(v).strip() not in ("", "—", "nan", "N/A"):
                    parts.append(f"{label}: {v}")
            if not parts:
                continue
            cm = Comment("\n".join(parts), "How it is calculated")
            cm.width, cm.height = 380, 140
            self.ws.cell(row=pos["first"] + i, column=j).comment = cm

    def chart(self, kind: str, pos: dict, cats_col: str, series_cols: list[str], title: str, y_title: str,
              anchor: Optional[str] = None, width: float = 18, height: float = 8):
        if not pos:
            return
        cats_j = pos["cols"].get(cats_col)
        series = [(c, pos["cols"][c]) for c in series_cols if c in pos["cols"]]
        if not cats_j or not series:
            return
        ch = LineChart() if kind == "line" else BarChart()
        if kind == "bar":
            ch.type = "col"
            ch.gapWidth = 60
        ch.title = title
        ch.y_axis.title = y_title
        ch.height, ch.width = height, width
        ch.legend.position = "b"
        for i, (name, j) in enumerate(series):
            ref = Reference(self.ws, min_col=j, min_row=pos["header_row"], max_row=pos["last"])
            ch.add_data(ref, titles_from_data=True)
            s = ch.series[-1]
            color = SERIES_COLORS[i % len(SERIES_COLORS)]
            if kind == "line":
                s.graphicalProperties.line.solidFill = color
                s.graphicalProperties.line.width = 22000
                s.smooth = False
            else:
                s.graphicalProperties.solidFill = color
                s.graphicalProperties.line.noFill = True
        ch.set_categories(Reference(self.ws, min_col=cats_j, min_row=pos["first"], max_row=pos["last"]))
        try:
            ch.x_axis.delete = False
            ch.y_axis.delete = False
        except AttributeError:
            pass
        self.ws.add_chart(ch, anchor or f"A{self.row}")
        self.row += int(height * 2) + 2


def _render_edu_sheet(wb: Workbook, title: str, sections: list[dict], demo: bool) -> None:
    """Write a 'Learn …' sheet from the shared education content."""
    s = Sheet(wb, title, demo)
    s.title("Learning centre",
            "General financial education that accompanies every report – market basics, the three "
            "financial statements, ratios, valuation, risks and a research checklist. "
            "This is not investment advice.")
    for sec in sections:
        s.h2(sec["title"])
        for b in sec["blocks"]:
            t = b["t"]
            if t == "h3":
                s.h2(b["text"])
            elif t == "p":
                s.para(b["text"])
            elif t == "ul":
                s.bullets(b["items"])
            elif t == "ol":
                for i, it in enumerate(b["items"], 1):
                    s.para(f"{i}. {it}")
            elif t == "table":
                df = pd.DataFrame(b["rows"], columns=b["head"])
                s.table(df, index=False, wrap_cols=tuple(b["head"]),
                        widths={h: 62 for h in b["head"]})
            elif t == "formula":
                s.para("FORMULA:  " + b["text"])
                if b.get("note"):
                    s.para("          " + b["note"])
            elif t == "note":
                s.para("NOTE: " + b["text"])
            elif t == "links":
                for label, url, desc in b["items"]:
                    s.para(f"{label} – {url} – {desc}")
            elif t == "checklist":
                df = pd.DataFrame({"Stock research checklist": list(b["items"]),
                                   "Done (Y/N)": [""] * len(b["items"]),
                                   "Notes": [""] * len(b["items"])})
                s.table(df, index=False, widths={"Stock research checklist": 88, "Done (Y/N)": 12, "Notes": 40})
                s.para("Tick 'Y' in the Done column for every check you have completed before investing.")


def build_excel(res: dict, out_path: Path) -> Path:
    d = res["data"]
    ident = d.identity
    demo = d.is_demo
    wb = Workbook()
    wb.remove(wb.active)
    p, r, rw = res["price"], res["ratios"], res["roic_wacc"]
    at = res["annual_table"]
    hist = tables.history_df(at)

    # 1 Executive Summary
    s = Sheet(wb, "Executive Summary", demo)
    s.title(f"{ident.name} – Fundamental Analysis",
            f"NSE: {ident.nse_symbol or 'N/A'} | BSE: {ident.bse_code or 'N/A'} | ISIN: {ident.isin or 'N/A'} | "
            f"Generated {d.fetched_at}")
    s.kv([("Sector / Industry", f"{ident.sector or 'N/A'} / {ident.industry or 'N/A'}", None),
          ("Sector treatment", ident.sector_class.replace("_", " "), None),
          ("Exchange / Currency", f"{ident.exchange or 'N/A'} / {ident.currency}", None),
          ("Statements basis", f"{d.statement_basis} ({d.statement_source or 'none'})", None),
          ("CMP (₹)", p.get("price"), FMT_RS),
          ("Day change %", p.get("day_change_pct"), FMT_PCT),
          ("Market cap (₹ Cr)", p.get("market_cap_cr"), INR_CR),
          ("P/E (x)", r["pe"].value if r.get("pe") and r["pe"].available else None, FMT_X),
          ("ROE %", r["roe"].value if r.get("roe") and r["roe"].available else None, FMT_PCT),
          ("ROCE %", r["roce"].value if r.get("roce") and r["roce"].available else None, FMT_PCT),
          ("Debt/Equity (x)", r["de"].value if r.get("de") and r["de"].available else None, FMT_X),
          ("Overall score (/100)", res["score"]["overall"], "0.0"),
          ("Assessment", res["score"]["label"], None),
          ("Score data coverage %", res["score"]["coverage_pct"], FMT_PCT),
          ("Overall data coverage %", res["coverage"]["coverage_pct"], FMT_PCT)])
    s.h2("Overall assessment")
    s.para(res["overall_text"])
    s.h2("Valuation summary")
    s.para(res["valuation"]["summary"])
    s.h2("Strengths")
    s.bullets(res["strengths"], "None identified from available data.")
    s.h2("Weaknesses")
    s.bullets(res["weaknesses"], "None identified from available data.")
    s.h2("Financial warning signs")
    s.bullets(res["warning_signs"], "None detected.")
    s.h2("Disclaimer")
    s.para(res["disclaimer"])

    # 2 CMP and Price
    s = Sheet(wb, "CMP and Price Analysis", demo)
    s.title("CMP and price analysis", f"Source: {p.get('source', '')}. {p.get('staleness', {}).get('message', '')} {p.get('price_note', '')}")
    s.kv([("Current market price (₹)", p.get("price"), FMT_RS), ("Previous close (₹)", p.get("prev_close"), FMT_RS),
          ("Day change (₹)", p.get("day_change"), FMT_RS), ("Day change %", p.get("day_change_pct"), FMT_PCT),
          ("52-week high (₹)", p.get("high_52w"), FMT_RS), ("52-week low (₹)", p.get("low_52w"), FMT_RS),
          ("Distance from 52W high %", p.get("dist_from_high_pct"), FMT_PCT),
          ("Distance from 52W low %", p.get("dist_from_low_pct"), FMT_PCT),
          ("Market cap (₹ Cr)", p.get("market_cap_cr"), INR_CR), ("Volume", p.get("volume"), "#,##0"),
          ("50-day moving average (₹)", p.get("dma50"), FMT_RS), ("200-day moving average (₹)", p.get("dma200"), FMT_RS),
          ("RSI (14)", p.get("rsi14"), "0.0"), ("Return 3M %", p.get("ret_3m"), FMT_PCT),
          ("Return 1Y %", p.get("ret_1y"), FMT_PCT)])
    s.h2("What the price is telling us")
    for x in p.get("explanation", []):
        s.ws.cell(row=s.row, column=1, value=x["q"]).font = HEAD_FONT
        s.row += 1
        s.para(x["a"])
    ch = p.get("chart")
    if ch is not None and not ch.empty:
        s.h2("Weekly closing price (for chart)")
        wk = ch.resample("W-FRI").last().dropna(subset=["Close"])
        wk.index = wk.index.date
        wk.index.name = "Week"
        wk.columns = ["Close (₹)", "50-DMA (₹)", "200-DMA (₹)"]
        anchor_row = s.row
        pos = s.table(wk)
        s.chart("line", pos, "Week", ["Close (₹)", "50-DMA (₹)", "200-DMA (₹)"], "Share price and moving averages",
                "₹", anchor=f"F{anchor_row}", width=22, height=10)

    # 3 Fundamental Ratios
    s = Sheet(wb, "Fundamental Ratios", demo)
    s.title("Fundamental ratios",
            "Every metric keeps its inputs, formula, period, source and availability status. "
            "The Benchmark column shows where the value sits in the published bands "
            "(Best / Good / Average / Below average). Hover a metric name for its formula.")
    keys = ["ebitda", "ebitda_margin", "ebitda_growth", "eps", "eps_diluted", "ttm_eps", "eps_growth_1y", "eps_cagr_3y",
            "roe", "roa", "roce", "roic", "pe", "pe_5y_avg", "pb", "peg", "ev_ebitda", "enterprise_value", "de"]
    mdf = tables.metrics_df([r[k] for k in keys if k in r], financial=res["is_financial"]).drop(columns=["Value"])
    pos = s.table(mdf, index=False, wrap_cols=("Inputs", "Note", "Formula"),
                  widths={"Metric": 26, "Display": 16, "Benchmark": 16, "Formula": 36, "Inputs": 40,
                          "Source": 24, "Note": 40})
    s.cond_text(pos, "Status")
    s.cond_text(pos, "Benchmark")
    s.metric_comments(pos, mdf)
    s.h2("Simple-English explanation of each ratio")
    ex = pd.DataFrame(res["explanations"]).drop(columns=["Current value", "Assessment"], errors="ignore")
    pos = s.table(ex, index=False, wrap_cols=tuple(ex.columns),
                  widths={c: 34 for c in ex.columns})
    s.cond_text(pos, "Benchmark")
    for rr in range(pos.get("first", 0), pos.get("last", -1) + 1):
        s.ws.row_dimensions[rr].height = 120

    # 4 Historical Financial Performance
    s = Sheet(wb, "Historical Financials", demo)
    s.title("Historical financial performance",
            f"₹ crore unless stated. Basis: {d.statement_basis} – {d.statement_source}. "
            f"Capital employed = {at.attrs.get('ce_definition', 'N/A') if at is not None else 'N/A'}.")
    pos = s.table(hist, hints=bm.COLUMN_HINTS)
    s.cond_scale(pos, "ROE %")
    s.cond_scale(pos, "ROCE %")
    s.cond_lt(pos, "Interest cover (x)", 1.5)
    s.cond_lt(pos, "Revenue growth %", 0)
    s.cond_lt(pos, "Profit growth %", 0)
    s.chart("bar", pos, "Year", ["Revenue (₹ Cr)", "EBITDA (₹ Cr)", "Net profit (₹ Cr)"],
            "Revenue, EBITDA, Net profit", "₹ crore")
    s.h2("Quarterly results")
    qpos = s.table(tables.quarterly_df(res["quarterly_table"]), hints=bm.COLUMN_HINTS)
    s.chart("bar", qpos, "Quarter", ["Revenue (₹ Cr)", "Net profit (₹ Cr)"], "Quarterly revenue and profit", "₹ crore")

    # 5 Period analysis
    s = Sheet(wb, "3M-6M-9M-1Y-3Y-5Y Analysis", demo)
    s.title("3M / 6M / 9M / 1Y / 3Y / 5Y analysis",
            "Short periods: last k quarters vs same quarters a year earlier. 3Y/5Y: CAGR from annual statements. "
            "Historical ratios are from the statements of those years. '—' = not available (never estimated).")
    pdf = tables.period_df(res["periods"])
    pos = s.table(pdf, wrap_cols=("Financial basis", "Ratio note", "Data note"), hints=bm.COLUMN_HINTS,
                  widths={"Financial basis": 30, "Ratio note": 40, "Data note": 30})
    for c in ("Price change %", "Revenue growth %", "Net profit growth %", "EPS growth %"):
        s.cond_lt(pos, c, 0)
        s.cond_gt(pos, c, 0, GREEN_FILL)

    # 6 ROIC vs WACC
    s = Sheet(wb, "ROIC vs WACC", demo)
    s.title(rw.get("spread_kind", "ROIC vs WACC"),
            "WACC is an ESTIMATE based on the configurable assumptions listed on this sheet.")
    s.para(rw.get("verdict", ""))
    s.para("WACC in simple English: the average yearly cost of arranging money for the business – the return "
           "shareholders expect plus the after-tax interest paid to lenders, weighted by how much of each is used.")
    for w in rw.get("warnings", []):
        s.para("Note: " + w)
    mets = [rw.get(k) for k in ("beta", "cost_of_equity", "cost_of_debt", "tax_rate", "equity_weight", "debt_weight",
                                "wacc", "roic", "spread") if rw.get(k) is not None]
    mdf = tables.metrics_df(mets, financial=res["is_financial"]).drop(columns=["Value"])
    pos = s.table(mdf, index=False, wrap_cols=("Inputs", "Note", "Source"),
                  widths={"Metric": 26, "Benchmark": 16, "Inputs": 40, "Source": 34, "Note": 34, "Formula": 34})
    s.cond_text(pos, "Status")
    s.cond_text(pos, "Benchmark")
    s.metric_comments(pos, mdf)
    s.h2("Historical spread")
    if rw.get("history_note"):
        s.para(rw["history_note"])
    hpos = s.table(rw.get("history"), index=False, hints=bm.COLUMN_HINTS)
    s.cond_lt(hpos, "Spread %", 0)
    s.cond_gt(hpos, "Spread %", 0, GREEN_FILL)
    s.chart("line", hpos, "FY", ["Return %", "Cost of capital %"], rw.get("spread_kind", "ROIC vs WACC"), "%")
    s.h2("Assumptions used")
    s.table(pd.DataFrame([{"Assumption": k, "Value": v} for k, v in res["assumptions"].items()]), index=False)

    # 7 Debt
    s = Sheet(wb, "Debt Analysis", demo)
    s.title("Debt analysis", "₹ crore. Debt-to-Equity = Total borrowings / Shareholders' equity. "
            "Hover a column header for its formula.")
    for pt in res["debt"].get("points", []):
        s.para("• " + pt)
    dt = tables.debt_df(res["debt"].get("table"))
    pos = s.table(dt, hints=bm.COLUMN_HINTS)
    s.cond_gt(pos, "Debt/Equity (x)", 1.5)
    s.chart("bar", pos, "Year", ["Total borrowings (₹ Cr)", "Cash (₹ Cr)"], "Borrowings vs cash", "₹ crore")

    # 8 Interest coverage
    s = Sheet(wb, "Interest Coverage", demo)
    icr = res["interest_coverage"]
    s.title("Interest coverage ratio", "Interest coverage = EBIT / Interest expense (finance cost). Example: EBIT ₹100 Cr "
            "÷ interest ₹20 Cr = 5x → ₹5 of operating profit for every ₹1 of interest.")
    m = icr.get("metric")
    s.kv([("Interest coverage (x)", m.value if m is not None and m.available else None, FMT_X),
          ("Assessment", icr.get("label"), None), ("EBIT (₹ Cr)", icr.get("ebit"), INR_CR),
          ("Finance cost (₹ Cr)", icr.get("interest"), INR_CR),
          ("Sector thresholds (weak / moderate / strong)", " / ".join(f"{t:g}x" for t in icr.get("thresholds", ())), None)])
    for e in icr.get("explanation", []):
        s.para(e)
    s.h2("Trend by period")
    tpos = s.table(icr.get("trend"), hints=bm.COLUMN_HINTS)
    s.cond_lt(tpos, "ICR (x)", 1)
    s.h2("Annual history")
    a = icr.get("annual")
    if a is not None and not a.empty:
        a = a.rename(columns={"ebit": "EBIT (₹ Cr)", "interest": "Finance cost (₹ Cr)", "icr": "Interest cover (x)"})
        a.index.name = "Year"
    apos = s.table(a, hints=bm.COLUMN_HINTS)
    s.cond_lt(apos, "Interest cover (x)", 1)
    s.chart("line", apos, "Year", ["Interest cover (x)"], "Interest coverage trend", "times")

    # 9 Cash flow
    s = Sheet(wb, "Cash Flow Analysis", demo)
    s.title("Cash flow analysis", "₹ crore. FCF = Cash from operations – Capital expenditure. "
            "Hover a column header for its formula.")
    for pt in res["cashflow"].get("points", []):
        s.para("• " + pt)
    ct = tables.cashflow_df(res["cashflow"].get("table"))
    pos = s.table(ct, hints=bm.COLUMN_HINTS)
    s.cond_lt(pos, "Free cash flow (₹ Cr)", 0)
    s.cond_lt(pos, "CFO / Net profit (x)", 0.7)
    s.chart("bar", pos, "Year", ["Net profit (₹ Cr)", "Operating cash flow (₹ Cr)", "Free cash flow (₹ Cr)"],
            "Profit vs cash generation", "₹ crore")

    # 10 Promoter
    pr = res["promoter"]
    ptab = tables.promoter_df(pr.get("table"))
    s = Sheet(wb, "Promoter Holding - 3 Years", demo)
    s.title("Promoter holding – last 3 years",
            f"Source: {pr.get('source') or 'unavailable'}; pledge: {pr.get('pledge_source') or 'unavailable'}. "
            f"Quarters: {pr.get('first_quarter', '—')} to {pr.get('last_quarter', '—')}.")
    s.bullets(pr.get("points", []))
    cols = [c for c in ("Quarter", "Promoters %", "Promoter QoQ change (pp)", "Pledged % of promoter holding",
                        "Pledged % of total shares") if c in ptab.columns]
    pos = s.table(ptab[cols] if cols else ptab, index=False, hints=bm.COLUMN_HINTS)
    s.cond_lt(pos, "Promoter QoQ change (pp)", -1)
    s.cond_gt(pos, "Pledged % of promoter holding", 15)
    s.chart("line", pos, "Quarter", ["Promoters %"], "Promoter holding %", "%")
    s.chart("line", pos, "Quarter", ["Pledged % of promoter holding"], "Pledged shares (% of promoter holding)", "%")

    # 11 FII & DII
    s = Sheet(wb, "FII and DII Holding", demo)
    s.title("FII, DII and public holding", f"Source: {pr.get('source') or 'unavailable'}")
    cols = [c for c in ("Quarter", "FII %", "DII %", "Government %", "Public %", "Others %", "No. of shareholders")
            if c in ptab.columns]
    pos = s.table(ptab[cols] if len(cols) > 1 else pd.DataFrame(), index=False)
    s.chart("line", pos, "Quarter", ["FII %", "DII %", "Public %"], "FII / DII / Public holding", "%")

    # 12 Peers
    s = Sheet(wb, "Peer Comparison", demo)
    pe = res["peers"]
    s.title("Peer comparison", f"Peer source: {pe.get('source', '')}. Same formulas used for every company.")
    s.bullets(pe.get("points", []))
    pos = s.table(pe.get("table"), index=False, hints=bm.COLUMN_HINTS,
                  widths={"Company": 30, "Statements basis": 22, "Data source": 16})
    for c in ("ROE %", "ROCE %", "ROIC %"):
        s.cond_scale(pos, c)
    s.cond_scale(pos, "P/E", reverse=True)
    s.chart("bar", pos, "Company", ["P/E"], "P/E vs peers", "x")
    s.chart("bar", pos, "Company", ["ROE %"], "ROE vs peers", "%")

    # 13 Risk
    s = Sheet(wb, "Risk Assessment", demo)
    sc = res["score"]
    s.title("Risk assessment and scoring", sc["method"])
    s.kv([("Overall score (/100)", sc["overall"], "0.0"), ("Assessment", sc["label"], None),
          ("Score data coverage %", sc["coverage_pct"], FMT_PCT)])
    pos = s.table(pd.DataFrame(sc["table"]), index=False, wrap_cols=("Evidence", "Rubric"),
                  hints=bm.COLUMN_HINTS,
                  widths={"Category": 30, "Evidence": 60, "Rubric": 60, "Status": 22})
    s.cond_text(pos, "Status")
    s.cond_scale(pos, "Category score %")
    for rr in range(pos.get("first", 0), pos.get("last", -1) + 1):
        s.ws.row_dimensions[rr].height = 75
    s.chart("bar", pos, "Category", ["Category score %"], "Category scores (% of available points)", "%")
    s.h2("Critical flags")
    s.bullets(sc["critical_flags"], "None.")
    s.h2("Financial warning signs")
    s.bullets(res["warning_signs"], "None detected.")
    s.h2("Reasons supporting a premium valuation")
    s.bullets(res["valuation"]["premium_reasons"])
    s.h2("Reasons supporting a discount valuation")
    s.bullets(res["valuation"]["discount_reasons"])
    s.h2("Valuation risks")
    s.bullets(res["valuation"]["risks"])
    s.h2("Missing information")
    s.bullets(res["missing"])

    # 14 Sources
    s = Sheet(wb, "Data Sources and Assumptions", demo)
    s.title("Data sources and assumptions", f"Data fetched {d.fetched_at}")
    src = pd.DataFrame([x.as_dict() for x in d.sources])
    if not src.empty:
        src.columns = ["Dataset", "Source", "URL", "As of", "Status", "Note"]
    pos = s.table(src, index=False, wrap_cols=("Note", "URL"), widths={"Dataset": 34, "Source": 26, "URL": 50, "Note": 46})
    s.cond_text(pos, "Status")
    s.h2("Line-item derivations")
    s.table(pd.DataFrame([{"Item": k, "Source / derivation": v} for k, v in d.item_sources.items()]), index=False,
            widths={"Source / derivation": 70})
    s.h2("Assumptions (edit config.py or pass CLI flags)")
    s.table(pd.DataFrame([{"Assumption": k, "Value": v} for k, v in res["assumptions"].items()]), index=False)
    s.h2(f"Data coverage – {res['coverage']['coverage_pct']}%")
    pos = s.table(pd.DataFrame([{"Data item": k, "Available": "Yes" if v else "No"}
                                for k, v in res["coverage"]["items"].items()]), index=False)
    s.cond_text(pos, "Available")
    s.h2("Formulas")
    for f in ["EBITDA = EBIT + Depreciation & Amortisation (EBIT = PBT + Finance cost when not reported)",
              "EPS = Net profit attributable to shareholders / Weighted average shares (as reported)",
              "ROE = Net profit / Average shareholders' equity × 100",
              f"ROCE = EBIT / Average capital employed × 100; Capital employed = {at.attrs.get('ce_definition', 'N/A') if at is not None else 'N/A'}",
              "P/E = CMP / Trailing EPS; PEG = P/E / 3-year EPS CAGR (%)",
              "Debt-to-Equity = Total borrowings / Shareholders' equity",
              "ROIC = NOPAT / Average invested capital × 100; NOPAT = EBIT × (1 − tax); Invested capital = Equity + Debt − Excess cash",
              "WACC = E/(D+E) × Ke + D/(D+E) × Kd × (1 − t); Ke = Rf + β × ERP; Kd = Interest / Average debt",
              "Interest coverage = EBIT / Interest expense",
              "EV/EBITDA = (Market cap + Debt − Cash) / EBITDA",
              "FCF = Cash from operations − Capital expenditure; Cash conversion = CFO / Net profit"]:
        s.para("• " + f)
    s.h2("Disclaimer")
    s.para(res["disclaimer"])

    # 15-18 Learning centre (same content as the HTML "Learn" tab)
    for _title, _secs in zip(education.EXCEL_SHEET_TITLES, education.sections_for_excel()):
        _render_edu_sheet(wb, _title, _secs, demo)

    for ws in wb.worksheets:
        ws.freeze_panes = None
        ws.sheet_properties.tabColor = NAVY if ws.title == "Executive Summary" else "2A78D6"
        # Print nicely: landscape, fit all columns on one page width
        ws.page_setup.orientation = "landscape"
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
    wb.save(out_path)
    return out_path
