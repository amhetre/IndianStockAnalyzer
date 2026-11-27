"""
Valuation analysis – explains WHY a share may look expensive or inexpensive,
linking every statement to retrieved numbers. Never produces buy/sell calls.
"""
from __future__ import annotations

import pandas as pd

from analysis.fundamental_ratios import FINANCIAL_CLASSES
from data_providers.models import CompanyData
from utils.financial_utils import cagr, fmt_pct, is_num


def analyse_valuation(data: CompanyData, at: pd.DataFrame, ratios: dict, peers: dict, rw: dict,
                      icr: dict, cash: dict) -> dict:
    name = data.identity.name
    is_fin = data.identity.sector_class in FINANCIAL_CLASSES
    med = peers.get("median", {}) if peers else {}
    premium, discount, risks, missing = [], [], [], []

    def val(k):
        m = ratios.get(k)
        return m.value if m is not None and m.available else None

    pe, pb, peg, eve = val("pe"), val("pb"), val("peg"), val("ev_ebitda")
    pe_hist = val("pe_5y_avg")
    roe, roce, roic, de = val("roe"), val("roce"), val("roic"), val("de")
    pe_med = med.get("P/E")
    rev_g = cagr(at["revenue"].iloc[-1], at["revenue"].iloc[-4], 3) if at is not None and len(at) >= 4 and "revenue" in at else None
    prof_g = cagr(at["net_income"].iloc[-1], at["net_income"].iloc[-4], 3) if at is not None and len(at) >= 4 and "net_income" in at else None
    eps_g = val("eps_cagr_3y")

    # ---- headline
    s = []
    pe_m = ratios.get("pe")
    if pe is not None:
        s.append(f"{name} is trading at a P/E of {pe:.1f}")
        if is_num(pe_med):
            rel = "higher than" if pe > pe_med * 1.1 else "lower than" if pe < pe_med * 0.9 else "close to"
            s[-1] += f", {rel} its peer-group median of {pe_med:.1f}"
        if is_num(pe_hist):
            rel = "above" if pe > pe_hist * 1.1 else "below" if pe < pe_hist * 0.9 else "near"
            s[-1] += f" and {rel} its own recent average of {pe_hist:.1f}"
        s[-1] += "."
        if is_num(pe_med) and pe > pe_med * 1.1:
            s.append("This indicates investors are paying a premium compared with similar companies.")
        elif is_num(pe_med) and pe < pe_med * 0.9:
            s.append("This indicates the market is valuing its earnings at a discount to similar companies.")
    elif pe_m is not None and pe_m.status == "Not meaningful":
        s.append(f"{name}'s P/E is not meaningful because trailing earnings are negative – the company is loss-making, "
                 "so earnings-based valuation cannot be used; look at P/B, revenue and cash flows instead.")
        risks.append("Company is loss-making on a trailing basis.")
    else:
        s.append(f"P/E for {name} could not be calculated ({pe_m.note if pe_m else 'data missing'}).")
        missing.append("P/E")

    # ---- growth
    if is_num(eps_g):
        (premium if eps_g >= 15 else discount if eps_g < 5 else premium if eps_g >= 10 else discount).append(
            f"EPS has grown {eps_g:.1f}% a year over 3 years" + (" – strong growth can justify a higher multiple." if eps_g >= 15
                                                                 else " – moderate growth." if eps_g >= 10
                                                                 else " – slow/negative growth argues for a lower multiple."))
    else:
        missing.append("3-year EPS growth")
    if is_num(rev_g):
        if rev_g >= 12:
            premium.append(f"Revenue has grown {rev_g:.1f}% a year over 3 years.")
        elif rev_g < 5:
            discount.append(f"Revenue growth is slow at {rev_g:.1f}% a year over 3 years.")
    if is_num(prof_g) and is_num(rev_g) and prof_g < rev_g - 5:
        risks.append(f"Profit growth ({prof_g:.1f}%) lags revenue growth ({rev_g:.1f}%) – margins are under pressure.")
    if is_num(peg):
        if peg < 1:
            premium.append(f"PEG is {peg:.2f} (below 1): the P/E looks reasonable relative to earnings growth.")
        elif peg > 2:
            discount.append(f"PEG is {peg:.2f} (above 2): the price already assumes growth well above recent history.")
            risks.append("High PEG – valuation relies on faster future growth than achieved recently.")
    # ---- returns
    if is_num(roe):
        if roe >= 18:
            premium.append(f"ROE of {roe:.1f}% shows efficient use of shareholders' money.")
        elif roe < 10:
            discount.append(f"ROE is only {roe:.1f}% – low returns on shareholders' money.")
    if not is_fin and is_num(roic):
        if roic >= 15:
            premium.append(f"ROIC of {roic:.1f}% indicates high returns on all capital invested.")
        elif roic < 8:
            discount.append(f"ROIC of {roic:.1f}% is low.")
    sp = rw.get("spread") if rw else None
    if sp is not None and sp.available:
        if sp.value > 3:
            premium.append(f"{rw.get('spread_kind')} spread is {sp.value:+.1f} pp – the business earns more than its estimated cost of capital.")
        elif sp.value < -1:
            discount.append(f"{rw.get('spread_kind')} spread is {sp.value:+.1f} pp – returns are below the estimated cost of capital.")
            risks.append("Returns below cost of capital (value destruction risk).")
    # ---- balance sheet
    if not is_fin:
        if is_num(de):
            if de < 0.3:
                premium.append(f"Low debt (Debt-to-Equity {de:.2f}) reduces financial risk.")
            elif de > 1.5:
                discount.append(f"High debt (Debt-to-Equity {de:.2f}) increases risk to shareholders.")
                risks.append("High leverage.")
        im = icr.get("metric") if icr else None
        if im is not None and im.available:
            if im.value < 2:
                discount.append(f"Interest coverage is weak at {im.value:.1f}x.")
                risks.append("Weak interest coverage.")
            elif im.value > 8:
                premium.append(f"Interest coverage is strong at {im.value:.1f}x.")
        debt_trend = None
        if at is not None and "debt" in at and at["debt"].dropna().size >= 3:
            d = at["debt"].dropna()
            debt_trend = d.iloc[-1] - d.iloc[-3]
            if debt_trend > 0 and d.iloc[-3] > 0 and d.iloc[-1] / d.iloc[-3] > 1.5:
                risks.append("Debt has risen by more than 50% in two years.")
    # ---- cash
    conv = cash.get("cum_conversion") if cash else None
    if is_num(conv) and not is_fin:
        if conv >= 0.9:
            premium.append(f"Profits convert well into cash ({conv*100:.0f}% cash conversion over {cash.get('years')} years).")
        elif conv < 0.6:
            discount.append(f"Only {conv*100:.0f}% of profits converted into operating cash over {cash.get('years')} years.")
            risks.append("Poor cash conversion – earnings quality concern.")
    # ---- multiples vs history/peers
    if is_num(pe) and is_num(pe_hist) and pe > pe_hist * 1.3:
        risks.append(f"P/E ({pe:.1f}) is more than 30% above its own recent average ({pe_hist:.1f}); a reversion to "
                     "the average would lower the price even if earnings hold.")
    if is_num(eve) and is_num(med.get("EV/EBITDA")) and eve > med["EV/EBITDA"] * 1.3:
        risks.append(f"EV/EBITDA ({eve:.1f}) is well above the peer median ({med['EV/EBITDA']:.1f}).")
    if not peers or not peers.get("n_peers"):
        missing.append("Peer valuation (no peer data)")
    if not is_num(pe_hist):
        missing.append("Own historical P/E")
    if data.statement_source == "Yahoo Finance":
        missing.append("Long financial history (Yahoo provides ~4 years)")

    # ---- conclusion paragraph
    if premium and len(premium) >= len(discount):
        lead = "However, several" if (is_num(pe_med) and is_num(pe) and pe > pe_med * 1.1) else "Several"
        s.append(f"{lead} fundamentals may partly justify the valuation: "
                 + "; ".join(x.rstrip(".") for x in premium[:3]) + ".")
        s.append("Investors should still judge whether this performance can continue.")
    elif discount:
        if is_num(pe) and is_num(pe_med) and pe < pe_med:
            s.append("The lower valuation may reflect genuine business concerns rather than an attractive opportunity: "
                     + "; ".join(x.rstrip(".") for x in discount[:3]) + ".")
        else:
            s.append("Points that argue against a premium: " + "; ".join(x.rstrip(".") for x in discount[:3]) + ".")
    s.append("A low P/E does not automatically mean a stock is cheap, and a high P/E does not automatically mean it is "
             "expensive – the multiple must be judged against growth, returns, debt and cash flow.")
    return {
        "summary": " ".join(x for x in s if x),
        "premium_reasons": premium, "discount_reasons": discount, "risks": risks, "missing": missing,
        "metrics": {"P/E": pe, "Peer median P/E": pe_med, "Own 5Y avg P/E": pe_hist, "P/B": pb, "PEG": peg,
                    "EV/EBITDA": eve, "Peer median EV/EBITDA": med.get("EV/EBITDA"),
                    "EPS CAGR 3Y %": eps_g, "Revenue CAGR 3Y %": rev_g, "Profit CAGR 3Y %": prof_g},
    }
