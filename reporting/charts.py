"""
Plotly chart builders for the HTML dashboard.

Design rules: categorical colours assigned in fixed order (never cycled), one
y-axis per chart (no dual axes), thin marks, recessive grid, hover tooltips on
every chart, legend whenever there are two or more series.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.graph_objects as go

# Validated categorical palette (light surface) – fixed order
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"


def _layout(fig: go.Figure, title: str, y_title: str = "", height: int = 360, legend: bool = True) -> go.Figure:
    fig.update_layout(
        title={"text": title, "font": {"size": 15, "color": INK}, "x": 0, "xanchor": "left"},
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE, height=height,
        margin={"l": 56, "r": 16, "t": 56, "b": 40},
        font={"family": "Inter, Segoe UI, Roboto, Arial, sans-serif", "color": INK2, "size": 12},
        hovermode="x unified", showlegend=legend,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.0, "x": 1, "xanchor": "right",
                "font": {"color": INK2}},
        bargap=0.3, bargroupgap=0.08,
    )
    fig.update_xaxes(showgrid=False, linecolor=AXIS, tickfont={"color": MUTED})
    fig.update_yaxes(gridcolor=GRID, gridwidth=1, zeroline=True, zerolinecolor=AXIS, title_text=y_title,
                     tickfont={"color": MUTED}, title_font={"color": MUTED})
    return fig


def _empty(title: str, msg: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False, font={"color": MUTED, "size": 13}, x=0.5, y=0.5,
                       xref="paper", yref="paper")
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return _layout(fig, title, height=220, legend=False)


def _has(df: Optional[pd.DataFrame], *cols: str) -> bool:
    return df is not None and not df.empty and any(c in df and df[c].notna().any() for c in cols)


def price_chart(chart: pd.DataFrame) -> go.Figure:
    if chart is None or chart.empty:
        return _empty("Share price", "Price history unavailable")
    fig = go.Figure()
    for i, (col, name) in enumerate((("Close", "Close"), ("DMA50", "50-day avg"), ("DMA200", "200-day avg"))):
        if col in chart and chart[col].notna().any():
            fig.add_trace(go.Scatter(x=chart.index, y=chart[col], name=name, mode="lines",
                                     line={"width": 2 if i == 0 else 1.5, "color": SERIES[i],
                                           "dash": "solid" if i == 0 else "dot"},
                                     hovertemplate="₹%{y:,.2f}<extra>" + name + "</extra>"))
    return _layout(fig, "Share price with 50 & 200-day moving averages", "₹ per share")


def bars(at: pd.DataFrame, cols: list[tuple[str, str]], title: str, y_title: str) -> go.Figure:
    if not _has(at, *[c for c, _ in cols]):
        return _empty(title, "Data unavailable")
    fig = go.Figure()
    for i, (col, name) in enumerate(cols):
        if col in at and at[col].notna().any():
            fig.add_trace(go.Bar(x=list(at.index), y=at[col], name=name, marker_color=SERIES[i],
                                 marker_line_width=0,
                                 hovertemplate="%{x}: %{y:,.0f}<extra>" + name + "</extra>"))
    try:  # rounded bar ends (Plotly >= 5.19)
        fig.update_traces(marker_cornerradius=4)
    except (ValueError, AttributeError):
        pass
    return _layout(fig, title, y_title, legend=len(cols) > 1)


def lines(df: pd.DataFrame, cols: list[tuple[str, str]], title: str, y_title: str,
          fmt: str = "%{y:.1f}", ref: Optional[tuple[float, str]] = None) -> go.Figure:
    if not _has(df, *[c for c, _ in cols]):
        return _empty(title, "Data unavailable")
    fig = go.Figure()
    for i, (col, name) in enumerate(cols):
        if col in df and df[col].notna().any():
            fig.add_trace(go.Scatter(x=list(df.index), y=df[col], name=name, mode="lines+markers",
                                     line={"width": 2, "color": SERIES[i]}, marker={"size": 8},
                                     connectgaps=False,
                                     hovertemplate=fmt + "<extra>" + name + "</extra>"))
    if ref is not None:
        fig.add_hline(y=ref[0], line={"color": MUTED, "width": 1, "dash": "dash"},
                      annotation_text=ref[1], annotation_font_color=MUTED)
    return _layout(fig, title, y_title, legend=len(cols) > 1)


def roic_wacc_chart(hist: pd.DataFrame, kind: str) -> go.Figure:
    if hist is None or hist.empty:
        return _empty(kind, "Data unavailable")
    h = hist.set_index("FY")
    ret_name = "ROE %" if kind.startswith("ROE") else "ROIC %"
    cost_name = "Cost of equity % (current estimate)" if kind.startswith("ROE") else "WACC % (current estimate)"
    return lines(h, [("Return %", ret_name), ("Cost of capital %", cost_name)], kind, "%")


def promoter_chart(tbl: pd.DataFrame) -> go.Figure:
    if not _has(tbl, "promoters"):
        return _empty("Promoter holding", "Shareholding data unavailable")
    t = tbl.set_index("quarter")
    return lines(t, [("promoters", "Promoters %")], "Promoter holding by quarter", "% of shares", "%{y:.2f}%")


def fii_dii_chart(tbl: pd.DataFrame) -> go.Figure:
    if not _has(tbl, "fii", "dii", "public"):
        return _empty("FII / DII / Public holding", "FII/DII data unavailable")
    t = tbl.set_index("quarter")
    return lines(t, [("fii", "FII %"), ("dii", "DII %"), ("public", "Public %")],
                 "Institutional and public holding by quarter", "% of shares", "%{y:.2f}%")


def pledge_chart(tbl: pd.DataFrame) -> go.Figure:
    if not _has(tbl, "pledged_pct_of_promoter"):
        return _empty("Promoter pledge", "Pledge data unavailable from NSE")
    t = tbl.set_index("quarter")
    return lines(t, [("pledged_pct_of_promoter", "Pledged % of promoter holding")],
                 "Promoter pledged shares", "%", "%{y:.2f}%")


def peer_bar(peer_tbl: pd.DataFrame, col: str, title: str) -> go.Figure:
    if peer_tbl is None or peer_tbl.empty or col not in peer_tbl or peer_tbl[col].notna().sum() == 0:
        return _empty(title, "Peer data unavailable")
    t = peer_tbl[peer_tbl["Company"] != "Peer median"].dropna(subset=[col])
    colors = [SERIES[0] if "(selected)" in str(c) else "#9ec5f4" for c in t["Company"]]
    fig = go.Figure(go.Bar(x=t["Company"].str.replace(" (selected)", " ★", regex=False), y=t[col],
                           marker_color=colors, marker_line_width=0,
                           hovertemplate="%{x}: %{y:.2f}<extra></extra>"))
    med = peer_tbl.loc[peer_tbl["Company"] == "Peer median", col]
    if len(med) and pd.notna(med.iloc[0]):
        fig.add_hline(y=float(med.iloc[0]), line={"color": MUTED, "width": 1, "dash": "dash"},
                      annotation_text=f"Peer median {float(med.iloc[0]):.1f}", annotation_font_color=MUTED)
    return _layout(fig, title, col, legend=False)


def score_chart(score_rows: list[dict]) -> go.Figure:
    rows = [r for r in score_rows if r["Category score %"] is not None]
    if not rows:
        return _empty("Score by category", "Insufficient data to score")
    names = [r["Category"] for r in rows][::-1]
    vals = [r["Category score %"] for r in rows][::-1]
    colors = [STATUS["good"] if v >= 70 else STATUS["warning"] if v >= 45 else STATUS["critical"] for v in vals]
    fig = go.Figure(go.Bar(x=vals, y=names, orientation="h", marker_color=colors, marker_line_width=0,
                           text=[f"{v:.0f}%" for v in vals], textposition="outside",
                           textfont={"color": INK2},
                           hovertemplate="%{y}: %{x:.0f}% of category points<extra></extra>"))
    fig.update_xaxes(range=[0, 110])
    fig = _layout(fig, "Category scores (% of available points)", "", height=320, legend=False)
    fig.update_layout(hovermode="closest")
    return fig


def _builders(res: dict) -> dict:
    at = res["annual_table"]
    qt = res["quarterly_table"]
    is_fin = res["is_financial"]
    return {
        "price": lambda: price_chart(res["price"].get("chart")),
        "financials": lambda: bars(at, [("revenue", "Revenue"), ("ebitda", "EBITDA"), ("net_income", "Net profit")],
                           "Revenue, EBITDA and net profit (₹ crore)", "₹ crore"),
        "eps": lambda: lines(at, [("eps", "EPS (₹)")], "Earnings per share", "₹ per share", "₹%{y:.2f}"),
        "margins": lambda: lines(at, [("ebitda_margin", "EBITDA margin %"), ("net_margin", "Net margin %")],
                         "Margins", "%", "%{y:.1f}%"),
        "returns": lambda: lines(at, [("roe", "ROE %")] + ([] if is_fin else [("roce", "ROCE %"), ("roic", "ROIC %")])
                         + ([("roa", "ROA %")] if is_fin else []), "Return ratios", "%", "%{y:.1f}%"),
        "pe_history": lambda: lines(at, [("pe", "P/E at FY end")], "Historical P/E (FY-end price ÷ FY EPS)", "x", "%{y:.1f}x"),
        "roic_wacc": lambda: roic_wacc_chart(res["roic_wacc"].get("history"), res["roic_wacc"].get("spread_kind", "ROIC vs WACC")),
        "debt": lambda: bars(at, [("debt", "Total borrowings"), ("cash", "Cash")], "Borrowings vs cash (₹ crore)", "₹ crore"),
        "de": lambda: lines(at, [("de", "Debt-to-Equity")], "Debt-to-Equity", "x", "%{y:.2f}x", (1.0, "1.0x")),
        "icr": lambda: lines(at, [("icr", "Interest coverage")], "Interest coverage (EBIT ÷ interest)", "times",
                     "%{y:.1f}x", (1.0, "1x – cannot cover interest")),
        "cashflow": lambda: bars(at, [("net_income", "Net profit"), ("cfo", "Operating cash flow"), ("fcf", "Free cash flow")],
                         "Profit vs cash generation (₹ crore)", "₹ crore"),
        "quarterly": lambda: bars(qt.rename(index=lambda d: d.strftime("%b %y")) if qt is not None and not qt.empty else qt,
                          [("revenue", "Revenue"), ("net_income", "Net profit")],
                          "Quarterly revenue and net profit (₹ crore)", "₹ crore"),
        "promoter": lambda: promoter_chart(res["promoter"].get("table")),
        "fii_dii": lambda: fii_dii_chart(res["promoter"].get("table")),
        "pledge": lambda: pledge_chart(res["promoter"].get("table")),
        "peer_pe": lambda: peer_bar(res["peers"].get("table"), "P/E", "P/E vs peers"),
        "peer_roe": lambda: peer_bar(res["peers"].get("table"), "ROE %", "ROE vs peers"),
        "score": lambda: score_chart(res["score"]["table"]),
    }


def build(res: dict, keys) -> dict[str, go.Figure]:
    """Build only the requested charts (used by the web app's lazy tabs)."""
    b = _builders(res)
    return {k: b[k]() for k in keys if k in b}


def build_all(res: dict) -> dict[str, go.Figure]:
    b = _builders(res)
    return {k: f() for k, f in b.items()}
