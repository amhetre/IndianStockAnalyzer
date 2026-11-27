"""Orchestrates all analysis modules into one result dictionary used by the reports."""
from __future__ import annotations

from typing import Callable, Optional

import pandas as pd

from analysis.cashflow_analysis import analyse_cashflow
from analysis.debt_analysis import analyse_debt
from analysis.explanation_engine import explain_all
from analysis.fundamental_ratios import FINANCIAL_CLASSES, annual_ratio_table, compute_core_ratios, quarterly_table
from analysis.interest_coverage import analyse_interest_coverage
from analysis.peer_analysis import analyse_peers, company_row
from analysis.period_analysis import analyse_periods
from analysis.price_analysis import analyse_price
from analysis.promoter_analysis import analyse_promoters
from analysis.roic_wacc import analyse_roic_wacc
from analysis.scoring_engine import score
from analysis.valuation_analysis import analyse_valuation
from config import ASSUMPTIONS, DISCLAIMER
from data_providers.models import CompanyData
from utils.data_validation import coverage_summary, financials_staleness, sanity_checks
from utils.financial_utils import is_num, num
from utils.logger import get_logger

log = get_logger(__name__)


def run_analysis(data: CompanyData, periods: list[str],
                 peer_loader: Optional[Callable[[str], Optional[CompanyData]]] = None,
                 progress: Callable[[str], None] = lambda s: None) -> dict:
    is_fin = data.identity.sector_class in FINANCIAL_CLASSES
    at = annual_ratio_table(data)
    qt = quarterly_table(data)
    ratios = compute_core_ratios(data, at, qt)
    per = analyse_periods(data.price_history, at, qt, periods)

    def per_val(p, col):
        if per is not None and not per.empty and p in per.index and col in per.columns:
            return num(per.at[p, col])
        return None

    price = analyse_price(data, per_val("1Y", "profit_growth"), per_val("1Y", "revenue_growth"))
    icr = analyse_interest_coverage(data, at, qt)
    debt = analyse_debt(data, at)
    cash = analyse_cashflow(data, at)
    rw = analyse_roic_wacc(data, at, ratios) if not at.empty else {"warnings": [], "history": pd.DataFrame(),
                                                                    "verdict": "No financial statements."}
    promoter = analyse_promoters(data)

    progress("Comparing with peers ...")
    try:
        main_row = company_row(data)
    except Exception as exc:  # noqa: BLE001
        log.warning("Main row failed: %s", exc)
        main_row = {"Company": data.identity.name, "Symbol": data.identity.nse_symbol, "_sector_class": data.identity.sector_class}
    peers = analyse_peers(data, main_row, peer_loader, progress)

    bank_latest = {}
    if data.bank_metrics is not None and not data.bank_metrics.empty:
        bm = data.bank_metrics.dropna(how="all")
        if len(bm):
            bank_latest = {k: num(bm[k].dropna().iloc[-1]) if k in bm and bm[k].notna().any() else None
                           for k in ("gnpa_pct", "nnpa_pct")}
            bank_latest["as_of"] = bm.index[-1]

    valuation = analyse_valuation(data, at, ratios, peers, rw, icr, cash)

    # Warnings / critical flags
    warnings = list(data.warnings)
    warnings += sanity_checks(data.annual, data.quote)
    st = price.get("staleness", {})
    if st.get("stale"):
        warnings.append(st["message"])
    fin_st = financials_staleness(data.annual.columns[-1] if not data.annual.empty else None)
    if fin_st["stale"]:
        warnings.append(fin_st["message"])
    warnings += rw.get("warnings", [])
    critical = []
    im = icr.get("metric")
    if not is_fin and im is not None and im.available and im.value < 1:
        critical.append(f"Interest coverage is {im.value:.2f}x – operating profit does not cover interest.")
    if not at.empty and is_num(at["equity"].iloc[-1]) and at["equity"].iloc[-1] < 0:
        critical.append("Shareholders' equity is negative.")
    if not is_fin and not at.empty and "cfo" in at:
        c = at["cfo"].dropna()
        if len(c) >= 2 and (c.iloc[-2:] < 0).all():
            warnings.append("Operating cash flow has been negative for the last two years.")
    if promoter.get("pledge_latest") is not None and promoter["pledge_latest"] >= 25:
        warnings.append(f"High promoter pledge ({promoter['pledge_latest']:.1f}% of promoter holding).")
    if promoter.get("promoter_change_3y") is not None and promoter["promoter_change_3y"] <= -5:
        warnings.append(f"Promoter holding fell {abs(promoter['promoter_change_3y']):.1f} pp in ~3 years.")

    ctx = {"ratios": ratios, "annual_table": at, "sector_class": data.identity.sector_class,
           "peer_median": peers.get("median", {}), "icr": icr, "roic_wacc": rw, "cashflow": cash,
           "promoter": promoter, "bank_latest": bank_latest, "critical_flags": critical}
    sc = score(ctx)
    explanations = explain_all(ctx)

    strengths, weaknesses = [], []
    for cat in sc["table"]:
        for part in cat["Evidence"].split("; "):
            if "→" not in part:
                continue
            try:
                pts = float(part.split("→")[-1].split("/")[0])
            except ValueError:
                continue
            label = f"{cat['Category']}: {part.split(' → ')[0]}"
            if pts >= 80:
                strengths.append(label)
            elif pts <= 30:
                weaknesses.append(label)
    warning_signs = critical + valuation["risks"] + [w for w in warnings if w not in critical]

    coverage = coverage_summary({
        "Current market price": is_num(data.quote.get("price")),
        "Price history ≥ 1 year": data.price_history is not None and len(data.price_history) >= 240,
        "Price history ≥ 5 years": data.price_history is not None and len(data.price_history) >= 1200,
        "Annual statements ≥ 5 years": len(at) >= 5,
        "Quarterly results ≥ 8 quarters": len(qt) >= 8,
        "Cash balance": not at.empty and "cash" in at and at["cash"].notna().any(),
        "Cash flow statement": not at.empty and "cfo" in at and at["cfo"].notna().any(),
        "Capital expenditure": not at.empty and "capex" in at and at["capex"].notna().any(),
        "Shareholding ≥ 12 quarters": promoter.get("quarters", 0) >= 12,
        "Promoter pledge": promoter.get("pledge_latest") is not None,
        "Peer data": peers.get("n_peers", 0) > 0,
        "Beta from market data": "Computed" in (rw.get("beta").source if rw.get("beta") else ""),
    })

    missing = list(dict.fromkeys(valuation["missing"] +
                                 [m if " " not in m or not m[-4:].isdigit() else f"Shareholding quarter missing: {m}"
                                  for m in promoter.get("missing", [])] +
                                 [k for k, ok in coverage["items"].items() if not ok]))
    overall_text = _overall_text(data, sc, strengths, weaknesses, warning_signs)

    return {
        "data": data, "annual_table": at, "quarterly_table": qt, "ratios": ratios, "periods": per,
        "price": price, "interest_coverage": icr, "debt": debt, "cashflow": cash, "roic_wacc": rw,
        "promoter": promoter, "peers": peers, "valuation": valuation, "score": sc,
        "explanations": explanations, "strengths": strengths, "weaknesses": weaknesses,
        "warning_signs": list(dict.fromkeys(warning_signs)), "missing": missing, "coverage": coverage,
        "bank_latest": bank_latest, "financial_staleness": fin_st, "overall_text": overall_text,
        "assumptions": ASSUMPTIONS.as_dict(), "disclaimer": DISCLAIMER, "is_financial": is_fin,
    }


def _overall_text(data: CompanyData, sc: dict, strengths, weaknesses, warnings) -> str:
    if sc["overall"] is None:
        return ("An overall assessment could not be produced because too little financial data was retrieved. "
                "See the data coverage section.")
    t = (f"{data.identity.name} scores {sc['overall']:.0f}/100 on historical fundamentals "
         f"({sc['label']}), based on {sc['coverage_pct']:.0f}% data coverage. ")
    if strengths:
        t += "Main strengths: " + "; ".join(strengths[:3]) + ". "
    if weaknesses:
        t += "Main weaknesses: " + "; ".join(weaknesses[:3]) + ". "
    if warnings:
        t += f"There are {len(warnings)} warning sign(s) listed in the risk section. "
    t += ("This score summarises past reported numbers. It is not a forecast of share-price performance and not a "
          "buy/sell recommendation.")
    return t
