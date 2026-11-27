"""
WACC estimate and ROIC-vs-WACC spread.

WACC = E/(D+E) x Ke + D/(D+E) x Kd x (1 - t)
Ke   = Risk-free rate + Beta x Equity risk premium      (CAPM)
Kd   = Interest expense / Average interest-bearing debt (pre-tax)
E    = market capitalisation; D = book value of borrowings (proxy for market value)

All assumptions come from config.ASSUMPTIONS and are listed in the report.
WACC is an ESTIMATE: beta, risk premium and market value of debt are not directly observable.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from analysis.fundamental_ratios import FINANCIAL_CLASSES
from config import ASSUMPTIONS
from data_providers.models import CompanyData
from utils.financial_utils import (ESTIMATE, Metric, is_num, not_meaningful, num, safe_div, unavailable)


def compute_beta(prices: pd.DataFrame, bench: pd.Series, years: int = ASSUMPTIONS.beta_lookback_years) -> Optional[dict]:
    if prices is None or prices.empty or bench is None or bench.empty:
        return None
    s = prices["Close"]
    start = s.index[-1] - pd.DateOffset(years=years)
    df = pd.concat([s.loc[s.index >= start].rename("stock"), bench.loc[bench.index >= start].rename("index")],
                   axis=1, join="inner").dropna()
    if len(df) < 120:
        return None
    wk = df.resample("W-FRI").last().pct_change().dropna()
    if len(wk) < 52:
        return None
    var = wk["index"].var()
    if not var or not np.isfinite(var):
        return None
    beta = wk["stock"].cov(wk["index"]) / var
    return {"beta": float(beta), "observations": int(len(wk)),
            "basis": f"Weekly returns vs NIFTY 50, {wk.index[0].date()} – {wk.index[-1].date()}"}


def analyse_roic_wacc(data: CompanyData, at: pd.DataFrame, ratios: dict) -> dict:
    a = ASSUMPTIONS
    out: dict = {"assumptions": a.as_dict(), "warnings": []}
    is_fin = data.identity.sector_class in FINANCIAL_CLASSES

    # ---- Beta
    b = compute_beta(data.price_history, data.benchmark_history)
    if b and -0.5 < b["beta"] < 3.5:
        beta, beta_src = b["beta"], f"Computed: {b['basis']} ({b['observations']} weeks)"
    elif is_num(data.quote.get("beta")):
        beta, beta_src = float(data.quote["beta"]), "Yahoo Finance published beta"
    else:
        beta, beta_src = a.default_beta, "ASSUMPTION: default beta (could not compute)"
        out["warnings"].append("Beta could not be computed – default beta of %.2f used." % a.default_beta)
    out["beta"] = Metric("Beta", beta, "", "Cov(stock, NIFTY) / Var(NIFTY)", "", {}, beta_src, ESTIMATE)

    ke = a.risk_free_rate + beta * a.equity_risk_premium
    out["cost_of_equity"] = Metric("Cost of equity", ke * 100, "%", "Risk-free + Beta x Equity risk premium", "",
                                   {"Risk-free %": a.risk_free_rate * 100, "Beta": beta,
                                    "ERP %": a.equity_risk_premium * 100}, "CAPM (assumptions in config.py)", ESTIMATE)

    last = at.iloc[-1] if at is not None and not at.empty else pd.Series(dtype=object)
    # ---- Tax
    t = num(last.get("tax_rate"))
    t = t / 100 if is_num(t) else a.statutory_tax_rate
    t_basis = last.get("tax_rate_basis", "Statutory") if len(last) else "Statutory"
    out["tax_rate"] = Metric("Tax rate", t * 100, "%", "Tax / Profit before tax", str(at.index[-1]) if len(last) else "",
                             {}, "Financial statements" if t_basis == "Actual" else "ASSUMPTION (statutory rate)",
                             ESTIMATE, "" if t_basis == "Actual" else str(t_basis))

    if is_fin:
        roe = ratios.get("roe")
        out["wacc"] = not_meaningful("WACC", "For banks/NBFCs/insurers, deposits and borrowings are operating "
                                     "liabilities. Compare ROE with the cost of equity instead.", "%")
        out["roic"] = ratios.get("roic")
        if roe is not None and roe.available:
            spread = roe.value - ke * 100
            out["spread"] = Metric("ROE − Cost of equity", spread, "%", "ROE - Cost of equity", roe.period,
                                   {"ROE %": roe.value, "Ke %": ke * 100}, "Derived", ESTIMATE,
                                   "Financial company: equity spread used instead of ROIC-WACC")
        else:
            out["spread"] = unavailable("ROE − Cost of equity", "ROE unavailable", "%")
        out["spread_kind"] = "ROE vs Cost of equity"
        hist = []
        if at is not None and "roe" in at:
            for fy, r in at["roe"].items():
                hist.append({"FY": fy, "Return %": r, "Cost of capital %": ke * 100,
                             "Spread %": (r - ke * 100) if is_num(r) else None})
        out["history"] = pd.DataFrame(hist)
        out["verdict"] = _verdict(out["spread"], "ROE", "cost of equity")
        return out

    # ---- Cost of debt
    kd = num(last.get("cost_of_debt"))
    kd_src = "Interest expense / Average borrowings (latest FY)"
    if is_num(kd):
        kd = kd / 100
        if not (a.min_reliable_cost_of_debt <= kd <= a.max_reliable_cost_of_debt):
            out["warnings"].append(f"Derived cost of debt {kd*100:.1f}% is outside the reliable band "
                                   f"({a.min_reliable_cost_of_debt*100:.0f}–{a.max_reliable_cost_of_debt*100:.0f}%); "
                                   f"default {a.default_cost_of_debt*100:.1f}% used. (Finance cost may include "
                                   "lease/other charges, or debt changed sharply during the year.)")
            kd, kd_src = a.default_cost_of_debt, "ASSUMPTION: default cost of debt"
    else:
        kd, kd_src = a.default_cost_of_debt, "ASSUMPTION: default cost of debt (could not derive)"
    out["cost_of_debt"] = Metric("Cost of debt (pre-tax)", kd * 100, "%", "Interest / Average debt", "", {},
                                 kd_src, ESTIMATE)

    E = num(data.quote.get("market_cap_cr"))
    D = num(last.get("debt"))
    if not is_num(E):
        out["wacc"] = unavailable("WACC", "Market capitalisation unavailable", "%")
        out["spread"] = unavailable("ROIC − WACC", "WACC unavailable", "%")
        out["history"] = pd.DataFrame()
        out["verdict"] = "WACC could not be estimated because market capitalisation is unavailable."
        return out
    if not is_num(D):
        D = 0.0
        out["warnings"].append("Debt figure unavailable – WACC computed assuming zero debt (equity-only).")
    we, wd = E / (E + D), D / (E + D)
    wacc = we * ke + wd * kd * (1 - t)
    out["equity_weight"] = Metric("Equity weight", we * 100, "%", "E / (D + E)", "", {"E (₹ Cr)": E, "D (₹ Cr)": D},
                                  "Market cap + book debt", ESTIMATE)
    out["debt_weight"] = Metric("Debt weight", wd * 100, "%", "D / (D + E)", "", {"E (₹ Cr)": E, "D (₹ Cr)": D},
                                "Market cap + book debt", ESTIMATE, "Book value of debt used as proxy for market value")
    out["wacc"] = Metric("WACC (estimate)", wacc * 100, "%",
                         "E/(D+E) x Ke + D/(D+E) x Kd x (1 - t)", "Current",
                         {"Ke %": ke * 100, "Kd %": kd * 100, "t %": t * 100, "We %": we * 100, "Wd %": wd * 100},
                         "Estimate from config assumptions + market data", ESTIMATE)
    roic = ratios.get("roic")
    out["roic"] = roic
    if roic is not None and roic.available:
        out["spread"] = Metric("ROIC − WACC", roic.value - wacc * 100, "%", "ROIC - WACC", roic.period,
                               {"ROIC %": roic.value, "WACC %": wacc * 100}, "Derived", ESTIMATE)
    else:
        out["spread"] = unavailable("ROIC − WACC", "ROIC unavailable", "%")
    out["spread_kind"] = "ROIC vs WACC"
    hist = []
    if at is not None and "roic" in at:
        for fy, r in at["roic"].items():
            hist.append({"FY": fy, "Return %": r, "Cost of capital %": wacc * 100,
                         "Spread %": (r - wacc * 100) if is_num(r) else None})
    out["history"] = pd.DataFrame(hist)
    out["history_note"] = ("Historical spread compares each year's actual ROIC with TODAY's WACC estimate "
                           "(historical market inputs are not reconstructed).")
    out["verdict"] = _verdict(out["spread"], "ROIC", "WACC")
    return out


def _verdict(spread: Metric, ret: str, cost: str) -> str:
    if spread is None or not spread.available:
        return f"{ret} vs {cost} could not be assessed due to missing data."
    s = spread.value
    if s > 1:
        return (f"{ret} exceeds the estimated {cost} by {s:.1f} percentage points – the company is generally "
                "creating economic value (earning more than its capital costs).")
    if s >= -1:
        return (f"{ret} is roughly equal to the estimated {cost} (spread {s:+.1f} pp) – the company is approximately "
                "covering its cost of capital, but not creating much extra value.")
    return (f"{ret} is below the estimated {cost} by {abs(s):.1f} percentage points – the company may be destroying "
            "economic value (earning less than investors and lenders require).")
