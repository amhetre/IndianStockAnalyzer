"""
Simple-English explanation engine.

For every ratio it answers the 7 required questions:
1 What does it mean?  2 Why is it important?  3 Current value?  4 Good/moderate/concerning?
5 Why might it be at this level?  6 What does it mean for investors?  7 What to check next?
Every judgement is tied to the retrieved number (or marked unavailable).
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from analysis import benchmarks as bm
from analysis.fundamental_ratios import FINANCIAL_CLASSES
from utils.financial_utils import Metric, fmt_cr, is_num

GOOD, MOD, BAD, NA = "Good", "Moderate", "Concerning", "Not assessable"

# Set by explain_all() so every entry gets the right benchmark bands
# (banks/NBFCs are judged with different bands than industrial companies).
_FIN = False


def _trend(at: pd.DataFrame, col: str, n: int = 4) -> tuple[str, str]:
    if at is None or col not in at:
        return "", ""
    s = at[col].dropna().iloc[-n:]
    if len(s) < 3:
        return "", ""
    first, last = s.iloc[0], s.iloc[-1]
    if abs(first) < 1e-9:
        return "", ""
    rel = (last - first) / abs(first)
    word = "improving" if rel > 0.08 else "declining" if rel < -0.08 else "stable"
    return word, f"{s.index[0]}: {first:.1f} → {s.index[-1]}: {last:.1f}"


def _entry(metric: str, m: Optional[Metric], what: str, why: str, assess: str, level_reason: str,
           meaning: str, nxt: str) -> dict:
    if m is None:
        current = "Not calculated"
    elif m.available:
        current = f"{m.display()} ({m.period})" if m.period else m.display()
    else:
        current = f"{m.status}: {m.note}" if m.note else m.status
    return {"Metric": metric, "Current value": current, "Assessment": assess,
            "Benchmark": bm.remark_for_metric(m, _FIN) if m is not None else "",
            "1. What does it mean?": what, "2. Why is it important?": why, "3. Current value": current,
            "4. Good / moderate / concerning?": assess, "5. Why might it be at this level?": level_reason,
            "6. What does it mean for investors?": meaning, "7. What should investors check next?": nxt}


def explain_all(ctx: dict) -> list[dict]:
    global _FIN
    r: dict = ctx["ratios"]
    at: pd.DataFrame = ctx["annual_table"]
    sc = ctx["sector_class"]
    is_fin = sc in FINANCIAL_CLASSES
    _FIN = is_fin
    peer_med = ctx.get("peer_median", {}) or {}
    out = []

    def v(k):
        m = r.get(k)
        return m.value if m is not None and m.available else None

    # ---- EBITDA
    if not is_fin:
        mg = v("ebitda_margin")
        tw, td = _trend(at, "ebitda_margin")
        assess = NA if mg is None else GOOD if mg >= 20 else MOD if mg >= 10 else BAD
        out.append(_entry(
            "EBITDA & EBITDA margin", r.get("ebitda_margin"),
            "EBITDA is profit from the core business before interest, tax, depreciation and amortisation. The margin "
            "shows how many rupees of such profit the company keeps from every ₹100 of sales.",
            "It shows the earning power of operations, independent of how the company is financed or how old its assets are.",
            f"{assess} (EBITDA {fmt_cr(v('ebitda'))}, margin {mg:.1f}%)" if mg is not None else assess,
            (f"The margin trend is {tw} ({td}). " if tw else "") +
            ("High margins usually come from pricing power, brand or low costs. " if mg and mg >= 20 else
             "Moderate margins are typical of competitive or input-cost-heavy industries. " if mg and mg >= 10 else
             "Low margins can come from intense competition, high raw-material costs or a commodity business. " if mg is not None else ""),
            "Rising EBITDA margins mean operating profitability is improving; falling margins can hurt future earnings.",
            "Compare margins with peers in the same industry and check whether changes come from prices, costs or one-offs."))

    # ---- EPS
    eps, g3 = v("ttm_eps") or v("eps"), v("eps_cagr_3y")
    assess = NA if g3 is None else GOOD if g3 >= 12 else MOD if g3 >= 0 else BAD
    tw, td = _trend(at, "eps")
    out.append(_entry(
        "EPS (Earnings per share)", r.get("ttm_eps") if r.get("ttm_eps") and r["ttm_eps"].available else r.get("eps"),
        "EPS is the profit belonging to each share – net profit divided by the number of shares.",
        "Share prices follow earnings over the long run. Growing EPS means each share is earning more.",
        f"{assess} (3-year EPS growth {g3:.1f}% a year)" if g3 is not None else assess,
        (f"EPS trend is {tw} ({td}). " if tw else "") +
        ("Consistent growth suggests the business is expanding profitably. " if g3 is not None and g3 >= 12 else
         "Slow or negative growth may reflect weak demand, rising costs, higher interest or more shares issued. " if g3 is not None else
         "Not enough history to judge consistency. "),
        "Investors pay for future earnings – consistent EPS growth usually supports the share price; erratic EPS adds risk.",
        "Check whether EPS growth came from operations or from one-time gains, and whether new shares are diluting EPS."))

    # ---- ROE
    roe = v("roe")
    assess = NA if roe is None else GOOD if roe >= 15 else MOD if roe >= 10 else BAD
    tw, td = _trend(at, "roe")
    pm = peer_med.get("ROE %")
    out.append(_entry(
        "ROE (Return on equity)", r.get("roe"),
        "ROE shows how much profit the company makes on the money shareholders have put in (equity).",
        "It measures how efficiently management uses shareholders' money.",
        f"{assess} ({roe:.1f}%" + (f"; peer median {pm:.1f}%" if is_num(pm) else "") + ")" if roe is not None else assess,
        (f"ROE trend is {tw} ({td}). " if tw else "") +
        "ROE rises with higher margins, faster asset turnover, or more debt. A high ROE with high debt is less "
        "comforting than a high ROE with little debt.",
        "Sustained ROE above ~15% usually indicates a quality business; low ROE means shareholders' money earns little.",
        "Break ROE down: is it driven by profit margins, efficiency, or borrowing? Compare with peers."))

    if is_fin:
        roa = v("roa")
        assess = NA if roa is None else GOOD if roa >= 1.5 else MOD if roa >= 0.8 else BAD
        out.append(_entry(
            "ROA (Return on assets)", r.get("roa"),
            "ROA is profit as a percentage of total assets (loans, investments etc.).",
            "For lenders, ROA is a key efficiency measure because their assets are mostly loans funded by deposits/borrowings.",
            f"{assess} ({roa:.2f}%)" if roa is not None else assess,
            "Banks typically earn ~1–2% ROA; it depends on lending margins, credit costs (bad loans) and operating costs.",
            "Higher ROA means the lender earns more from each rupee lent.",
            "Check net interest margin, credit cost and CASA ratio in the company's investor presentation."))
        bm = ctx.get("bank_latest", {})
        g, n = bm.get("gnpa_pct"), bm.get("nnpa_pct")
        assess = NA if not is_num(g) else GOOD if g <= 2 else MOD if g <= 5 else BAD
        out.append(_entry(
            "Gross / Net NPA", None,
            "NPAs (non-performing assets) are loans where the borrower has stopped paying. Gross NPA is before "
            "provisions; Net NPA is after money set aside for expected losses.",
            "Bad loans directly reduce a lender's profit and capital.",
            f"{assess} (GNPA {g:.2f}%, NNPA {n:.2f}%)" if is_num(g) and is_num(n) else "Unavailable from free sources",
            "NPA levels depend on the quality of underwriting, the economic cycle and the sectors lent to.",
            "Lower and falling NPAs mean better asset quality and lower future losses.",
            "Check provision coverage ratio, slippages, capital adequacy (CAR), CASA and NIM in the investor presentation – "
            "CAR, CASA and NIM are not available from the free data sources used here."))
        out[-1]["Current value"] = out[-1]["3. Current value"] = (
            f"GNPA {g:.2f}% / NNPA {n:.2f}%" if is_num(g) and is_num(n) else "Unavailable")

    if not is_fin:
        # ---- ROCE
        roce = v("roce")
        assess = NA if roce is None else GOOD if roce >= 15 else MOD if roce >= 10 else BAD
        tw, td = _trend(at, "roce")
        out.append(_entry(
            "ROCE (Return on capital employed)", r.get("roce"),
            "ROCE shows the operating profit (EBIT) earned on all long-term money used in the business – both "
            "shareholders' money and borrowed money.",
            "It shows whether the company earns more on its capital than that capital costs.",
            f"{assess} ({roce:.1f}%)" if roce is not None else assess,
            (f"ROCE trend is {tw} ({td}). " if tw else "") +
            "Capital-heavy businesses (steel, power) usually have lower ROCE; asset-light ones (IT, FMCG) higher.",
            "ROCE consistently above the cost of borrowing (~9–10%) means growth adds value.",
            "Check whether heavy recent capex (capital work-in-progress) is temporarily depressing ROCE."))
        # ---- ROIC
        roic = v("roic")
        assess = NA if roic is None else GOOD if roic >= 15 else MOD if roic >= 9 else BAD
        tw, td = _trend(at, "roic")
        out.append(_entry(
            "ROIC (Return on invested capital)", r.get("roic"),
            "ROIC is after-tax operating profit (NOPAT) divided by the capital actually invested in operations "
            "(equity + debt – surplus cash).",
            "It is the cleanest measure of how much profit the business generates from invested money.",
            f"{assess} ({roic:.1f}%)" if roic is not None else assess,
            (f"ROIC trend is {tw} ({td}). " if tw else "") + "It depends on margins, competition and how much capital "
            "the business needs to grow.",
            "If ROIC is above WACC, every rupee reinvested creates value for investors.",
            "Compare ROIC with WACC (next row) and with peers; check if ROIC is falling as the company expands."))
        # ---- D/E
        de = v("de")
        assess = NA if de is None else GOOD if de <= 0.5 else MOD if de <= 1.2 else BAD
        out.append(_entry(
            "Debt-to-Equity", r.get("de"),
            "Debt-to-Equity compares money borrowed with money owned by shareholders. 0.5 means ₹50 of debt for "
            "every ₹100 of shareholders' funds.",
            "Higher debt means fixed interest payments, which become risky when profits fall.",
            f"{assess} ({de:.2f}x)" if de is not None else assess,
            "Companies borrow to build capacity, for acquisitions or working capital. Capital-intensive sectors "
            "(infrastructure, real estate, metals) usually carry more debt.",
            "Low debt gives safety and flexibility; high debt magnifies both gains and losses for shareholders.",
            "Check debt trend, repayment schedule, interest coverage and whether debt funds productive assets."))
        # ---- ICR
        icr = ctx.get("icr", {})
        m = icr.get("metric")
        val = m.value if m is not None and m.available else None
        lbl = icr.get("label", NA)
        out.append(_entry(
            "Interest coverage", m,
            "Interest coverage = EBIT ÷ interest expense: how many times operating profit can pay the interest bill.",
            "It is the first test of whether debt is affordable.",
            f"{lbl} ({val:.1f}x)" if val is not None else lbl,
            "It falls when debt or interest rates rise, or when operating profit drops.",
            "Coverage below 1 means the company cannot pay interest from operating profit – a serious risk; above ~4 "
            "is generally comfortable (sector-adjusted).",
            "Check whether new borrowing is planned and how interest cost is trending vs EBIT."))
        # ---- WACC & spread
        rw = ctx.get("roic_wacc", {})
        w = rw.get("wacc")
        out.append(_entry(
            "WACC (estimate)", w,
            "WACC is the average yearly cost of the money a company uses – the return shareholders expect plus the "
            "after-tax interest paid on loans, weighted by how much of each the company uses.",
            "A business must earn more than its WACC to create value.",
            "Estimate" if w is not None and w.available else NA,
            "WACC depends on assumptions (risk-free rate, equity risk premium, beta). It is an estimate, not an "
            "observed number – see the Assumptions sheet.",
            "Use it as a hurdle rate to judge ROIC, not as a precise figure.",
            "Re-run with your own risk-free rate / ERP assumptions to see how sensitive the conclusion is."))
        sp = rw.get("spread")
        s = sp.value if sp is not None and sp.available else None
        out.append(_entry(
            "ROIC vs WACC spread", sp,
            "The spread is ROIC minus WACC – the extra return earned above the cost of capital.",
            "A positive spread means the company creates economic value; a negative spread means it destroys value "
            "even if it reports a profit.",
            (GOOD if s > 2 else MOD if s >= -1 else BAD) if s is not None else NA,
            rw.get("verdict", ""),
            "Companies with persistent positive spreads tend to compound shareholder wealth over time.",
            "Check whether the spread is stable over several years (see ROIC vs WACC sheet)."))
    else:
        rw = ctx.get("roic_wacc", {})
        sp = rw.get("spread")
        s = sp.value if sp is not None and sp.available else None
        out.append(_entry(
            "ROE vs Cost of equity", sp,
            "For banks/NBFCs, value creation is judged by ROE minus the return shareholders require (cost of equity).",
            "A lender that earns less than its cost of equity destroys shareholder value even while profitable.",
            (GOOD if s > 2 else MOD if s >= -1 else BAD) if s is not None else NA,
            rw.get("verdict", ""),
            "A positive spread supports a price above book value (P/B > 1).",
            "Check ROE sustainability: credit costs, capital raising and growth in loans."))

    # ---- P/E
    pe = v("pe")
    pmed, own = peer_med.get("P/E"), v("pe_5y_avg")
    if pe is not None:
        rel_parts = []
        if is_num(pmed):
            rel_parts.append(f"peer median {pmed:.1f}")
        if is_num(own):
            rel_parts.append(f"own 5Y average {own:.1f}")
        hi = (is_num(pmed) and pe > pmed * 1.2) or (is_num(own) and pe > own * 1.2)
        lo = (is_num(pmed) and pe < pmed * 0.8) or (is_num(own) and pe < own * 0.8)
        assess = "High vs benchmarks" if hi and not lo else "Low vs benchmarks" if lo and not hi else "In line / mixed"
        cur = f"{assess} ({pe:.1f}x" + ("; " + ", ".join(rel_parts) if rel_parts else "") + ")"
    else:
        cur = NA
    out.append(_entry(
        "P/E (Price to earnings)", r.get("pe"),
        "P/E tells you how many rupees investors pay for ₹1 of the company's yearly profit. P/E 25 = ₹25 for every ₹1 of earnings.",
        "It is the most common quick measure of how expensive a share is relative to its profits.",
        cur,
        "A high P/E usually reflects expectations of fast growth, quality or a strong brand; a low P/E can reflect slow "
        "growth, high risk, cyclical earnings or temporarily inflated profits.",
        "A low P/E does NOT automatically mean cheap and a high P/E does not automatically mean expensive – judge it "
        "against growth (PEG), returns and debt.",
        "Compare with peers and the stock's own history, and check if current earnings include one-off items."))
    peg = v("peg")
    out.append(_entry(
        "PEG ratio", r.get("peg"),
        "PEG = P/E ÷ annual EPS growth %. It adjusts the P/E for growth.",
        "A high P/E may be fine if earnings grow fast; PEG captures this trade-off.",
        (GOOD + " (below 1)" if peg < 1 else MOD + " (1–2)" if peg <= 2 else BAD + " (above 2)") if peg is not None else
        (r["peg"].status if r.get("peg") else NA),
        "PEG is not meaningful when growth is zero or negative. It uses past 3-year EPS growth, which may not continue.",
        "PEG near or below 1 suggests the price is reasonable relative to past growth.",
        "Check analysts' or management's growth outlook – PEG based on past growth can mislead."))
    pb = v("pb")
    out.append(_entry(
        "P/B (Price to book)", r.get("pb"),
        "P/B compares market value with the accounting value of shareholders' funds (book value).",
        "Especially useful for banks/NBFCs and asset-heavy businesses.",
        f"{pb:.2f}x" if pb is not None else NA,
        "A P/B well above 1 is justified only if ROE is comfortably above the cost of equity.",
        "High P/B with low ROE is a warning sign; low P/B with low ROE may simply reflect poor returns.",
        "Compare P/B with ROE and with peers."))
    if not is_fin:
        eve = v("ev_ebitda")
        out.append(_entry(
            "EV/EBITDA", r.get("ev_ebitda"),
            "EV/EBITDA compares the value of the whole business (market cap + debt − cash) with its operating profit.",
            "Unlike P/E, it accounts for debt, so it compares companies with different borrowing levels fairly.",
            f"{eve:.1f}x" + (f" (peer median {peer_med['EV/EBITDA']:.1f}x)" if is_num(peer_med.get('EV/EBITDA')) else "")
            if eve is not None else NA,
            "Higher multiples reflect expected growth or quality; lower ones reflect risk or cyclicality.",
            "Useful cross-check to P/E for leveraged companies.",
            "Compare with peers in the same industry."))
        cf = ctx.get("cashflow", {})
        conv = cf.get("cum_conversion")
        out.append(_entry(
            "Cash conversion (CFO / Net profit)", None,
            "Shows what share of reported profit actually arrived as cash from operations.",
            "Profits can be inflated by accounting; cash is harder to manipulate.",
            (GOOD if conv >= 0.9 else MOD if conv >= 0.6 else BAD) + f" ({conv*100:.0f}% over {cf.get('years')} years)"
            if is_num(conv) else NA,
            "Low conversion often comes from rising receivables (customers paying late) or inventory build-up.",
            "Persistently weak conversion is a red flag about earnings quality.",
            "Check receivable days and inventory days in the annual report."))
        out[-1]["Current value"] = out[-1]["3. Current value"] = (f"{conv*100:.0f}%" if is_num(conv) else "Unavailable")
    return out
