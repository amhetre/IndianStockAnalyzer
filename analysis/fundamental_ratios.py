"""
Fundamental ratios computed from actual reported statements, year by year.

Definitions (documented and used consistently):
* EBIT              = reported EBIT, else Profit before tax + Finance cost
* EBITDA            = EBIT + Depreciation & Amortisation
* ROE               = Net profit / Average shareholders' equity x 100
* Capital Employed  = Total assets - Current liabilities   (when current liabilities are reported
                      for the company); otherwise Shareholders' equity + Total borrowings.
                      ONE definition is chosen per company and stated in the report.
* ROCE              = EBIT / Average capital employed x 100
* Effective tax     = Tax / Profit before tax (statutory rate used if outside a reliable band)
* NOPAT             = EBIT x (1 - Effective tax rate)
* Invested Capital  = Equity + Interest-bearing debt - Excess cash,
                      Excess cash = max(0, Cash - operating cash % x Revenue)
* ROIC              = NOPAT / Average invested capital x 100
* Debt-to-Equity    = Total borrowings / Shareholders' equity
* Interest coverage = EBIT / Finance cost
* P/E (historical)  = Closing price on the financial-year end date / EPS of that year
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from config import ASSUMPTIONS
from data_providers.models import CompanyData
from utils.financial_utils import (ACTUAL, DERIVED, NOT_MEANINGFUL, UNAVAILABLE, Metric, average, cagr,
                                   is_num, not_meaningful, num, pct_change, period_label, safe_div,
                                   unavailable)

FINANCIAL_CLASSES = ("bank", "nbfc", "insurance")


def _row(df: pd.DataFrame, item: str) -> pd.Series:
    if df is None or df.empty or item not in df.index:
        return pd.Series(np.nan, index=df.columns if df is not None else [], dtype=float)
    return pd.to_numeric(df.loc[item], errors="coerce")


def price_on_or_before(hist: pd.DataFrame, date) -> Optional[float]:
    if hist is None or hist.empty:
        return None
    sub = hist.loc[hist.index <= pd.Timestamp(date)]
    if sub.empty:
        return None
    # Do not use a price more than 10 days before the requested date
    if (pd.Timestamp(date) - sub.index[-1]).days > 10:
        return None
    return float(sub["Close"].iloc[-1])


def capital_employed_definition(annual: pd.DataFrame) -> str:
    cl = _row(annual, "current_liabilities")
    ta = _row(annual, "total_assets")
    both = cl.notna() & ta.notna()
    if len(annual.columns) and both.sum() >= max(2, int(0.75 * len(annual.columns))):
        return "TA-CL"
    return "EQ+DEBT"


def effective_tax_rate(tax, pbt) -> tuple[float, str]:
    r = safe_div(tax, pbt)
    if r is not None and is_num(pbt) and pbt > 0 and \
            ASSUMPTIONS.min_reliable_tax_rate <= r <= ASSUMPTIONS.max_reliable_tax_rate:
        return r, ACTUAL
    return ASSUMPTIONS.statutory_tax_rate, "Statutory (effective rate unreliable/unavailable)"


def annual_ratio_table(data: CompanyData) -> pd.DataFrame:
    """One row per financial year (oldest -> newest) with actual historical ratios."""
    a = data.annual
    if a is None or a.empty:
        return pd.DataFrame()
    cols = list(a.columns)
    is_fin = data.identity.sector_class in FINANCIAL_CLASSES
    ce_def = capital_employed_definition(a)

    rev, ebit, ebitda, dep = _row(a, "revenue"), _row(a, "ebit"), _row(a, "ebitda"), _row(a, "depreciation")
    ni, eps, eps_d = _row(a, "net_income"), _row(a, "eps_basic"), _row(a, "eps_diluted")
    eq, debt, cash = _row(a, "total_equity"), _row(a, "total_debt"), _row(a, "cash")
    ta, cl, intr = _row(a, "total_assets"), _row(a, "current_liabilities"), _row(a, "interest")
    pbt, tax = _row(a, "pbt"), _row(a, "tax")
    cfo, capex, fcf = _row(a, "cfo"), _row(a, "capex"), _row(a, "fcf")
    st_debt, lt_debt = _row(a, "short_term_debt"), _row(a, "long_term_debt")

    rows = []
    for i, c in enumerate(cols):
        p = cols[i - 1] if i > 0 else None
        r: dict = {"period_end": c, "fy": period_label(c)}
        r["revenue"] = num(rev[c])
        r["ebitda"] = num(ebitda[c])
        r["ebit"] = num(ebit[c])
        r["depreciation"] = num(dep[c])
        r["interest"] = num(intr[c])
        r["pbt"] = num(pbt[c])
        r["net_income"] = num(ni[c])
        r["eps"] = num(eps[c])
        r["eps_diluted"] = num(eps_d[c])
        r["equity"] = num(eq[c])
        r["debt"] = num(debt[c])
        r["short_term_debt"] = num(st_debt[c])
        r["long_term_debt"] = num(lt_debt[c])
        r["cash"] = num(cash[c])
        r["net_debt"] = (r["debt"] - r["cash"]) if is_num(r["debt"]) and is_num(r["cash"]) else None
        r["total_assets"] = num(ta[c])
        r["cfo"] = num(cfo[c])
        r["capex"] = num(capex[c])
        r["fcf"] = num(fcf[c])
        r["ebitda_margin"] = safe_div(r["ebitda"], r["revenue"]) * 100 if safe_div(r["ebitda"], r["revenue"]) is not None else None
        r["net_margin"] = safe_div(r["net_income"], r["revenue"]) * 100 if safe_div(r["net_income"], r["revenue"]) is not None else None
        t_rate, t_status = effective_tax_rate(num(tax[c]), r["pbt"])
        r["tax_rate"] = t_rate * 100
        r["tax_rate_basis"] = t_status

        # growth vs previous year
        if p is not None:
            for k, s in (("revenue_growth", rev), ("ebitda_growth", ebitda), ("ebit_growth", ebit),
                         ("profit_growth", ni), ("eps_growth", eps)):
                r[k] = pct_change(s[c], s[p])
        # ROE (average equity)
        eq_avg = average(eq[c], eq[p]) if p is not None else None
        r["roe_basis"] = "average equity" if eq_avg is not None else "closing equity"
        eq_base = eq_avg if eq_avg is not None else num(eq[c])
        r["roe"] = safe_div(r["net_income"], eq_base) * 100 if (is_num(eq_base) and eq_base > 0
                                                                 and is_num(r["net_income"])) else None
        # ROA
        ta_avg = average(ta[c], ta[p]) if p is not None else num(ta[c])
        r["roa"] = safe_div(r["net_income"], ta_avg) * 100 if is_num(ta_avg) and ta_avg > 0 and is_num(r["net_income"]) else None

        if not is_fin:
            # Capital employed
            def ce(col):
                if col is None:
                    return None
                if ce_def == "TA-CL":
                    return (num(ta[col]) - num(cl[col])) if is_num(ta[col]) and is_num(cl[col]) else None
                return (num(eq[col]) + num(debt[col])) if is_num(eq[col]) and is_num(debt[col]) else None
            ce_c, ce_p = ce(c), ce(p)
            r["capital_employed"] = ce_c
            ce_avg = average(ce_c, ce_p) if ce_p is not None else ce_c
            r["roce"] = safe_div(r["ebit"], ce_avg) * 100 if is_num(ce_avg) and ce_avg > 0 and is_num(r["ebit"]) else None

            # Invested capital & ROIC
            def ic(col):
                if col is None or not (is_num(eq[col]) and is_num(debt[col])):
                    return None
                base = num(eq[col]) + num(debt[col])
                if is_num(cash[col]) and is_num(rev[col]):
                    excess = max(0.0, num(cash[col]) - ASSUMPTIONS.operating_cash_pct_of_revenue * num(rev[col]))
                    return base - excess
                return base
            ic_c, ic_p = ic(c), ic(p)
            r["invested_capital"] = ic_c
            r["excess_cash_deducted"] = is_num(cash[c]) and is_num(rev[c])
            ic_avg = average(ic_c, ic_p) if ic_p is not None else ic_c
            nopat = r["ebit"] * (1 - t_rate) if is_num(r["ebit"]) else None
            r["nopat"] = nopat
            r["roic"] = safe_div(nopat, ic_avg) * 100 if is_num(ic_avg) and ic_avg > 0 and is_num(nopat) else None
            r["de"] = safe_div(r["debt"], r["equity"]) if is_num(r["equity"]) and r["equity"] > 0 else None
            r["icr"] = safe_div(r["ebit"], r["interest"]) if is_num(r["interest"]) and r["interest"] > 0 else None
            avg_debt = average(debt[c], debt[p]) if p is not None else None
            r["cost_of_debt"] = (safe_div(r["interest"], avg_debt) * 100
                                 if is_num(avg_debt) and avg_debt > 0 and is_num(r["interest"]) else None)
        r["cash_conversion"] = safe_div(r["cfo"], r["net_income"]) if is_num(r["net_income"]) and r["net_income"] > 0 else None
        # Historical P/E
        price = price_on_or_before(data.price_history, c)
        r["fy_end_price"] = price
        r["pe"] = safe_div(price, r["eps"]) if is_num(r["eps"]) and r["eps"] > 0 else None
        bvps = None
        if is_num(r["equity"]) and is_num(r["eps"]) and r["eps"] != 0 and is_num(r["net_income"]) and r["net_income"] != 0:
            shares_cr = r["net_income"] / r["eps"]  # crore shares implied
            if shares_cr > 0:
                bvps = r["equity"] / shares_cr
        r["pb"] = safe_div(price, bvps) if is_num(bvps) and bvps > 0 else None
        rows.append(r)
    df = pd.DataFrame(rows).set_index("fy")
    df.attrs["ce_definition"] = ("Total assets - Current liabilities" if ce_def == "TA-CL"
                                 else "Shareholders' equity + Total borrowings")
    return df


def quarterly_table(data: CompanyData) -> pd.DataFrame:
    q = data.quarterly
    if q is None or q.empty:
        return pd.DataFrame()
    out = pd.DataFrame(index=q.columns)
    for item in ("revenue", "operating_profit", "ebitda", "ebit", "depreciation", "interest", "pbt",
                 "net_income", "eps_basic"):
        if item in q.index:
            out[item] = pd.to_numeric(q.loc[item], errors="coerce").values
    if "ebit" in out and "interest" in out:
        out["icr"] = [safe_div(e, i) if is_num(i) and i > 0 else np.nan for e, i in zip(out["ebit"], out["interest"])]
    out.index.name = "quarter_end"
    return out.sort_index()


# ---------------------------------------------------------------------------
# Latest-value metrics
# ---------------------------------------------------------------------------
def trailing_eps(data: CompanyData, qt: pd.DataFrame) -> Metric:
    name, formula = "Trailing EPS (TTM)", "Sum of last 4 quarterly EPS"
    if qt is not None and not qt.empty and "eps_basic" in qt:
        last4 = qt["eps_basic"].dropna().iloc[-4:]
        if len(last4) == 4 and len(qt["eps_basic"].iloc[-4:].dropna()) == 4:
            span = (last4.index[-1] - last4.index[0]).days
            if 250 <= span <= 300:
                return Metric(name, float(last4.sum()), "₹", formula,
                              f"4 quarters to {last4.index[-1].date()}",
                              {f"Q{i+1}": v for i, v in enumerate(last4.values)}, data.statement_source, ACTUAL)
    ttm = data.ttm.get("eps_basic") if data.ttm else None
    if is_num(ttm):
        return Metric(name, float(ttm), "₹", "TTM EPS as published by source", "TTM", {}, data.statement_source, ACTUAL)
    te = data.quote.get("trailing_eps")
    if is_num(te):
        return Metric(name, float(te), "₹", "Trailing EPS from Yahoo Finance", "TTM", {}, "Yahoo Finance", ACTUAL)
    a = data.annual
    if a is not None and not a.empty and "eps_basic" in a.index and a.loc["eps_basic"].notna().any():
        s = a.loc["eps_basic"].dropna()
        return Metric(name, float(s.iloc[-1]), "₹", "Latest full-year EPS (TTM unavailable)",
                      period_label(s.index[-1]), {}, data.statement_source, DERIVED,
                      "Quarterly EPS not available – latest annual EPS used instead")
    return unavailable(name, "EPS not available from any source", "₹", formula)


def ttm_sum(qt: pd.DataFrame, col: str) -> Optional[float]:
    if qt is None or qt.empty or col not in qt:
        return None
    last4 = qt[col].iloc[-4:]
    if len(last4) < 4 or last4.isna().any():
        return None
    return float(last4.sum())


def compute_core_ratios(data: CompanyData, at: pd.DataFrame, qt: pd.DataFrame) -> dict[str, Metric]:
    src = data.statement_source or "N/A"
    is_fin = data.identity.sector_class in FINANCIAL_CLASSES
    m: dict[str, Metric] = {}
    price = num(data.quote.get("price"))
    mcap = num(data.quote.get("market_cap_cr"))

    if at is None or at.empty:
        for k in ("ebitda", "ebitda_margin", "eps", "roe", "roce", "roic", "pe", "pb", "peg", "de", "ev_ebitda"):
            m[k] = unavailable(k.upper(), "No financial statements available")
        return m
    last = at.iloc[-1]
    fy = at.index[-1]

    def latest(col):
        return num(last.get(col))

    # EBITDA
    if is_fin:
        m["ebitda"] = not_meaningful("EBITDA", "EBITDA is not a meaningful measure for lenders/insurers, "
                                     "because interest is their main operating cost.", "₹ Cr")
        m["ebitda_margin"] = not_meaningful("EBITDA margin", "Not meaningful for financial companies", "%")
    else:
        m["ebitda"] = Metric("EBITDA", latest("ebitda"), "₹ Cr", "EBIT + Depreciation & Amortisation", fy,
                             {"EBIT": latest("ebit"), "D&A": latest("depreciation")}, src,
                             ACTUAL if is_num(latest("ebitda")) else UNAVAILABLE,
                             data.item_sources.get("annual:ebitda", ""))
        m["ebitda_margin"] = Metric("EBITDA margin", latest("ebitda_margin"), "%", "EBITDA / Revenue x 100", fy,
                                    {"EBITDA": latest("ebitda"), "Revenue": latest("revenue")}, src,
                                    ACTUAL if is_num(latest("ebitda_margin")) else UNAVAILABLE)
        m["ebitda_growth"] = Metric("EBITDA growth (YoY)", latest("ebitda_growth"), "%",
                                    "(EBITDA this year / EBITDA last year - 1) x 100", fy, {}, src,
                                    ACTUAL if is_num(latest("ebitda_growth")) else UNAVAILABLE)

    # EPS
    m["eps"] = Metric("Basic EPS (latest FY)", latest("eps"), "₹",
                      "Net profit attributable to shareholders / Weighted average shares", fy, {}, src,
                      ACTUAL if is_num(latest("eps")) else UNAVAILABLE)
    m["eps_diluted"] = Metric("Diluted EPS (latest FY)", latest("eps_diluted"), "₹", "As reported", fy, {}, src,
                              ACTUAL if is_num(latest("eps_diluted")) else UNAVAILABLE,
                              "" if is_num(latest("eps_diluted")) else "Diluted EPS not reported by the source")
    m["ttm_eps"] = trailing_eps(data, qt)
    # EPS growth: 3Y CAGR (fallback 1Y)
    eps_s = at["eps"].dropna() if "eps" in at else pd.Series(dtype=float)
    g3 = None
    if len(at) >= 4 and is_num(at["eps"].iloc[-1]) and is_num(at["eps"].iloc[-4]):
        g3 = cagr(at["eps"].iloc[-1], at["eps"].iloc[-4], 3)
    m["eps_cagr_3y"] = Metric("EPS growth (3Y CAGR)", g3, "%", "((EPS_end / EPS_start)^(1/3) - 1) x 100",
                              f"{at.index[-4]}–{fy}" if len(at) >= 4 else "", {}, src,
                              ACTUAL if g3 is not None else UNAVAILABLE,
                              "" if g3 is not None else "Needs 4 years of positive EPS")
    m["eps_growth_1y"] = Metric("EPS growth (YoY)", latest("eps_growth"), "%", "YoY change in EPS", fy, {}, src,
                                ACTUAL if is_num(latest("eps_growth")) else UNAVAILABLE)

    # ROE
    roe = latest("roe")
    eq = latest("equity")
    if is_num(eq) and eq <= 0:
        m["roe"] = not_meaningful("ROE", "Shareholders' equity is zero or negative", "%")
    else:
        m["roe"] = Metric("ROE", roe, "%", "Net profit / Average shareholders' equity x 100", fy,
                          {"Net profit": latest("net_income"), "Equity (closing)": eq}, src,
                          ACTUAL if is_num(roe) else UNAVAILABLE,
                          f"Uses {last.get('roe_basis', 'average equity')}")
    m["roa"] = Metric("ROA", latest("roa"), "%", "Net profit / Average total assets x 100", fy,
                      {"Net profit": latest("net_income"), "Total assets": latest("total_assets")}, src,
                      ACTUAL if is_num(latest("roa")) else UNAVAILABLE)

    if is_fin:
        reason = ("For banks/NBFCs/insurers, borrowings and deposits are raw material of the business, so "
                  "ROCE, ROIC, Debt-to-Equity and interest coverage are not interpreted like industrial companies.")
        m["roce"] = not_meaningful("ROCE", reason, "%")
        m["roic"] = not_meaningful("ROIC", reason, "%")
        m["de"] = not_meaningful("Debt-to-Equity", reason, "x")
    else:
        m["roce"] = Metric("ROCE", latest("roce"), "%", "EBIT / Average capital employed x 100", fy,
                           {"EBIT": latest("ebit"), "Capital employed": latest("capital_employed")}, src,
                           ACTUAL if is_num(latest("roce")) else UNAVAILABLE,
                           f"Capital employed = {at.attrs.get('ce_definition', '')}")
        m["roic"] = Metric("ROIC", latest("roic"), "%", "NOPAT / Average invested capital x 100", fy,
                           {"NOPAT": latest("nopat"), "Invested capital": latest("invested_capital"),
                            "Tax rate %": latest("tax_rate")}, src,
                           DERIVED if is_num(latest("roic")) else UNAVAILABLE,
                           "Invested capital = Equity + Debt - Excess cash"
                           + ("" if last.get("excess_cash_deducted") else " (cash unavailable: excess cash NOT deducted)"))
        if is_num(eq) and eq <= 0:
            m["de"] = not_meaningful("Debt-to-Equity", "Equity is zero or negative", "x")
        else:
            m["de"] = Metric("Debt-to-Equity", latest("de"), "x", "Total borrowings / Shareholders' equity", fy,
                             {"Debt": latest("debt"), "Equity": eq}, src,
                             ACTUAL if is_num(latest("de")) else UNAVAILABLE)

    # P/E
    ttm = m["ttm_eps"]
    if not is_num(price):
        m["pe"] = unavailable("P/E", "CMP unavailable", "x", "CMP / Trailing EPS")
    elif not ttm.available:
        m["pe"] = unavailable("P/E", "Trailing EPS unavailable", "x", "CMP / Trailing EPS")
    elif ttm.value <= 0:
        m["pe"] = not_meaningful("P/E", "Trailing EPS is zero or negative (company is loss-making)", "x",
                                 "CMP / Trailing EPS", inputs={"CMP": price, "TTM EPS": ttm.value})
    else:
        m["pe"] = Metric("P/E", price / ttm.value, "x", "CMP / Trailing EPS", ttm.period,
                         {"CMP": price, "TTM EPS": ttm.value}, f"{data.quote.get('source', '')} + {ttm.source}",
                         ttm.status if ttm.status != ACTUAL else ACTUAL, ttm.note)
    # P/B
    if is_num(mcap) and is_num(eq) and eq > 0:
        m["pb"] = Metric("P/B", mcap / eq, "x", "Market capitalisation / Shareholders' equity (book value)", fy,
                         {"Market cap (₹ Cr)": mcap, "Equity (₹ Cr)": eq}, src, ACTUAL)
    elif is_num(eq) and eq <= 0:
        m["pb"] = not_meaningful("P/B", "Book value is zero or negative", "x")
    else:
        m["pb"] = unavailable("P/B", "Market cap or equity unavailable", "x")
    # PEG
    pe = m["pe"]
    growth = g3 if g3 is not None else latest("eps_growth")
    gbasis = "3Y EPS CAGR" if g3 is not None else "1Y EPS growth"
    if not pe.available:
        m["peg"] = not_meaningful("PEG", "P/E is not available/meaningful", "x", "P/E / EPS growth %") \
            if pe.status == NOT_MEANINGFUL else unavailable("PEG", "P/E unavailable", "x", "P/E / EPS growth %")
    elif not is_num(growth):
        m["peg"] = unavailable("PEG", "EPS growth unavailable", "x", "P/E / EPS growth %")
    elif growth <= 0:
        m["peg"] = not_meaningful("PEG", f"EPS growth ({gbasis}) is zero or negative ({growth:.1f}%)", "x",
                                  "P/E / EPS growth %", inputs={"P/E": pe.value, gbasis: growth})
    else:
        m["peg"] = Metric("PEG", pe.value / growth, "x", f"P/E / {gbasis} (%)", fy,
                          {"P/E": pe.value, f"{gbasis} %": growth}, src, DERIVED)
    # EV/EBITDA
    if is_fin:
        m["ev_ebitda"] = not_meaningful("EV/EBITDA", "Not meaningful for financial companies", "x")
    else:
        debt_l, cash_l = latest("debt"), latest("cash")
        ttm_ebitda = ttm_sum(qt, "ebitda")
        e_basis = "TTM (last 4 quarters)" if ttm_ebitda is not None else fy
        e_val = ttm_ebitda if ttm_ebitda is not None else latest("ebitda")
        if is_num(mcap) and is_num(debt_l) and is_num(e_val):
            ev = mcap + debt_l - (cash_l if is_num(cash_l) else 0.0)
            note = "" if is_num(cash_l) else "Cash unavailable – EV not reduced by cash (overstates EV)"
            if e_val <= 0:
                m["ev_ebitda"] = not_meaningful("EV/EBITDA", "EBITDA is zero or negative", "x")
            else:
                m["ev_ebitda"] = Metric("EV/EBITDA", ev / e_val, "x",
                                        "(Market cap + Debt - Cash) / EBITDA", e_basis,
                                        {"Market cap": mcap, "Debt": debt_l, "Cash": cash_l, "EBITDA": e_val},
                                        src, ACTUAL if is_num(cash_l) else DERIVED, note)
            m["enterprise_value"] = Metric("Enterprise value", ev, "₹ Cr", "Market cap + Debt - Cash", fy,
                                           {"Market cap": mcap, "Debt": debt_l, "Cash": cash_l}, src,
                                           ACTUAL if is_num(cash_l) else DERIVED, note)
        else:
            m["ev_ebitda"] = unavailable("EV/EBITDA", "Market cap, debt or EBITDA unavailable", "x")
    # Own-history P/E
    pe_hist = at["pe"].dropna() if "pe" in at else pd.Series(dtype=float)
    pe_hist5 = pe_hist.iloc[-5:]
    m["pe_5y_avg"] = Metric("Average P/E (last 5 FY-ends)", float(pe_hist5.mean()) if len(pe_hist5) else None, "x",
                            "Mean of (FY-end price / FY EPS)", f"{len(pe_hist5)} year(s)",
                            {k: v for k, v in pe_hist5.items()}, f"{src} + price history",
                            DERIVED if len(pe_hist5) else UNAVAILABLE,
                            "" if len(pe_hist5) >= 3 else "Fewer than 3 years of P/E history")
    return m
