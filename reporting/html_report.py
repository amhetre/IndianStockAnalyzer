"""Interactive HTML dashboard (Jinja2 + Plotly)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from analysis import benchmarks as bm
from config import SETTINGS, TEMPLATE_DIR
from reporting import charts, education, tables
from utils.financial_utils import fmt_cr, fmt_inr, fmt_num, fmt_pct, fmt_x, is_num


def _fig_html(fig) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False,
                       config={"displaylogo": False, "responsive": True,
                               "modeBarButtonsToRemove": ["lasso2d", "select2d"]})


def _plotly_js() -> str:
    if SETTINGS.html_plotly_js == "cdn":
        return '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>'
    from plotly.offline import get_plotlyjs
    return "<script>" + get_plotlyjs() + "</script>"


def _card(label, metric, financial: bool = False) -> dict:
    if metric is None:
        return {"label": label, "value": "N/A", "sub": "", "status": "na", "hint": "", "remark": "",
                "remark_class": "b-na"}
    r = bm.remark_for_metric(metric, financial)
    return {"label": label, "value": metric.display(), "sub": metric.period or "",
            "status": "ok" if metric.available else "na", "note": metric.note,
            "hint": bm.hint_for_metric(metric, financial) if metric.available else "",
            "remark": r, "remark_class": bm.remark_badge_class(r)}


# Which charts each dashboard tab shows (keys of charts._builders; *_overview are aliases).
SECTION_FIGS = {
    "overview": ["price_overview", "financials_overview"], "price": ["price"],
    "ratios": ["margins", "eps", "returns", "pe_history"], "history": ["financials", "quarterly"],
    "periods": [], "roic": ["roic_wacc"], "debt": ["debt", "de", "icr"], "cash": ["cashflow"],
    "holding": ["promoter", "fii_dii", "pledge"], "peers": ["peer_pe", "peer_roe"], "risk": ["score"],
    "explain": [], "learn": [], "sources": [],
}
FIG_ALIAS = {"price_overview": "price", "financials_overview": "financials"}

_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=select_autoescape(["html"]))


def render_section(res: dict, section: str) -> dict:
    """Render one dashboard tab as an HTML fragment plus the Plotly JSON of its charts.

    Charts appear in the HTML as <div class="pchart" data-fig="key"></div> placeholders.
    """
    if section not in SECTION_FIGS:
        raise KeyError(section)
    keys = SECTION_FIGS[section]
    built = charts.build(res, {FIG_ALIAS.get(k, k) for k in keys})
    figs = {k: f'<div class="pchart" data-fig="{k}"></div>' for k in keys}
    html = _env.get_template(f"sections/{section}.html").render(**_context(res, figs))
    return {"section": section, "html": html,
            "figs": {k: json.loads(built[FIG_ALIAS.get(k, k)].to_json()) for k in keys}}


def build_html(res: dict, out_path: Path) -> Path:
    raw_figs = charts.build_all(res)
    figs = {k: _fig_html(v) for k, v in raw_figs.items()}
    # Charts shown twice need their own div ids
    figs["price_overview"] = _fig_html(raw_figs["price"])
    figs["financials_overview"] = _fig_html(raw_figs["financials"])
    html = _env.get_template("dashboard.html").render(plotly_js=_plotly_js(), **_context(res, figs))
    out_path.write_text(html, encoding="utf-8")
    return out_path


def _context(res: dict, figs: dict) -> dict:
    d = res["data"]
    ident = d.identity
    p = res["price"]
    r = res["ratios"]
    rw = res["roic_wacc"]
    is_fin = res.get("is_financial", False)

    cards = [
        {"label": "CMP", "value": fmt_inr(p.get("price")),
         "sub": (f"{fmt_inr(p.get('day_change'))} ({fmt_pct(p.get('day_change_pct'), signed=True)})"
                 if is_num(p.get("day_change")) else ""),
         "status": "up" if (p.get("day_change") or 0) >= 0 else "down",
         "hint": "CMP = Current Market Price – the price at which the share last traded.",
         "remark": "", "remark_class": "b-na"},
        {"label": "Market cap", "value": fmt_cr(p.get("market_cap_cr")), "sub": "", "status": "ok",
         "hint": "Market Cap = CMP × Total outstanding shares", "remark": "", "remark_class": "b-na"},
        {"label": "52-week range", "value": f"{fmt_inr(p.get('low_52w'), 0)} – {fmt_inr(p.get('high_52w'), 0)}",
         "sub": f"{fmt_pct(p.get('dist_from_high_pct'), signed=True)} from high", "status": "ok",
         "hint": "Highest and lowest trading price during the last 52 weeks.",
         "remark": "", "remark_class": "b-na"},
        {"label": "Fundamental score",
         "value": (f"{res['score']['overall']:.0f}/100" if res['score']['overall'] is not None else "N/A"),
         "sub": res["score"]["label"], "status": "ok",
         "hint": "Weighted score of 7 categories (see Risk & Score). Past fundamentals only – "
                 "not a prediction of future returns.",
         "remark": "", "remark_class": "b-na"},
    ]
    ratio_cards = [_card("P/E", r.get("pe"), is_fin), _card("P/B", r.get("pb"), is_fin),
                   _card("PEG", r.get("peg"), is_fin),
                   _card("EV/EBITDA", r.get("ev_ebitda"), is_fin), _card("ROE", r.get("roe"), is_fin),
                   _card("ROCE", r.get("roce"), is_fin), _card("ROIC", r.get("roic"), is_fin),
                   _card("Debt/Equity", r.get("de"), is_fin),
                   _card("Interest cover", res["interest_coverage"].get("metric"), is_fin),
                   _card("EBITDA margin", r.get("ebitda_margin"), is_fin),
                   _card("TTM EPS", r.get("ttm_eps"), is_fin),
                   _card("WACC (est.)", rw.get("wacc"), is_fin)]
    if res["is_financial"]:
        ratio_cards.insert(4, _card("ROA", r.get("roa"), is_fin))

    metric_keys = ["ebitda", "ebitda_margin", "ebitda_growth", "eps", "eps_diluted", "ttm_eps", "eps_growth_1y",
                   "eps_cagr_3y", "roe", "roa", "roce", "roic", "pe", "pe_5y_avg", "pb", "peg", "ev_ebitda",
                   "enterprise_value", "de"]
    ratio_metrics = [r[k] for k in metric_keys if k in r]
    rw_metrics = [rw.get(k) for k in ("beta", "cost_of_equity", "cost_of_debt", "tax_rate", "equity_weight",
                                      "debt_weight", "wacc", "roic", "spread") if rw.get(k) is not None]
    sources = pd.DataFrame([s.as_dict() for s in d.sources])
    if not sources.empty:
        sources.columns = ["Dataset", "Source", "URL", "As of", "Status", "Note"]
    item_src = pd.DataFrame([{"Item": k, "Source / derivation": v} for k, v in d.item_sources.items()])
    assumptions = pd.DataFrame([{"Assumption": k, "Value": v} for k, v in res["assumptions"].items()])
    coverage = pd.DataFrame([{"Data item": k, "Available": "Yes" if v else "No"}
                             for k, v in res["coverage"]["items"].items()])
    score_tbl = pd.DataFrame(res["score"]["table"])

    return dict(
        title=f"{ident.name} – Fundamental Analysis",
        ident=ident, d=d, res=res, p=p, cards=cards, ratio_cards=ratio_cards, figs=figs,
        generated=datetime.now().strftime("%d %b %Y, %H:%M"),
        period_tbl=tables.to_html(tables.period_df(res["periods"]), hints=bm.COLUMN_HINTS),
        history_tbl=tables.to_html(tables.history_df(res["annual_table"]), hints=bm.COLUMN_HINTS),
        quarterly_tbl=tables.to_html(tables.quarterly_df(res["quarterly_table"]), hints=bm.COLUMN_HINTS),
        ratio_tbl=tables.metrics_html(ratio_metrics, financial=is_fin),
        rw_tbl=tables.metrics_html(rw_metrics, financial=is_fin),
        rw_hist_tbl=tables.to_html(rw.get("history"), index=False, hints=bm.COLUMN_HINTS),
        debt_tbl=tables.to_html(tables.debt_df(res["debt"].get("table")), hints=bm.COLUMN_HINTS),
        icr_tbl=tables.to_html(res["interest_coverage"].get("trend"), hints=bm.COLUMN_HINTS),
        cash_tbl=tables.to_html(tables.cashflow_df(res["cashflow"].get("table")), hints=bm.COLUMN_HINTS),
        promoter_tbl=tables.to_html(tables.promoter_df(res["promoter"].get("table")), index=False,
                                    hints=bm.COLUMN_HINTS),
        peer_tbl=tables.to_html(res["peers"].get("table"), index=False, hints=bm.COLUMN_HINTS),
        score_tbl=tables.to_html(score_tbl[["Category", "Weight", "Adjusted weight", "Category score %", "Points",
                                            "Status", "Evidence"]] if not score_tbl.empty else score_tbl,
                                 index=False, hints=bm.COLUMN_HINTS),
        edu_sections=education.SECTIONS,
        remark_cls=bm.remark_badge_class,
        sources_tbl=tables.to_html(sources, index=False),
        item_src_tbl=tables.to_html(item_src, index=False),
        assumptions_tbl=tables.to_html(assumptions, index=False),
        coverage_tbl=tables.to_html(coverage, index=False),
        fmt_pct=fmt_pct, fmt_x=fmt_x, fmt_num=fmt_num, fmt_cr=fmt_cr,
    )
