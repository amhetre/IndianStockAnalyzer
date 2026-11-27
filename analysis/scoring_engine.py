"""
Explainable fundamental score out of 100.

Each category is made of sub-checks; each sub-check awards points on a published
scale (see RUBRIC_TEXT). A sub-check with missing data is excluded and the
category is scored on the sub-checks that exist. A category with no usable
sub-checks is excluded entirely, and the remaining category weights are scaled up
proportionately. Data coverage (% of total weight actually scored) is disclosed.

The score describes historical fundamentals. It is NOT a prediction of future
share-price performance and NOT a recommendation.
"""
from __future__ import annotations

from typing import Optional

from analysis.fundamental_ratios import FINANCIAL_CLASSES
from config import SCORE_LABELS, SCORE_WEIGHTS
from utils.financial_utils import is_num

RUBRIC_TEXT = {
    "Profitability and returns": "ROE: ≥20%→100, 15–20→80, 10–15→50, 5–10→30, <5→0. ROCE same bands "
                                 "(banks/NBFCs: ROA ≥1.5%→100, 1–1.5→70, 0.5–1→40, <0.5→10).",
    "Growth": "3Y revenue CAGR and 3Y net-profit CAGR: ≥20%→100, 12–20→80, 6–12→55, 0–6→30, <0→0.",
    "Valuation": "PEG <1→100, 1–2→70, 2–3→40, >3→10; P/E vs peer median and vs own 5Y average: ratio ≤0.8→100, "
                 "≤1.2→70, ≤1.6→40, >1.6→10. Loss-making (negative EPS)→0.",
    "Debt and financial risk": "D/E ≤0.3→100, ≤0.7→80, ≤1.5→50, ≤2.5→20, >2.5→0; interest cover (sector-adjusted): "
                               "strong→100, moderate→60, weak→25, <1→0, no interest→100. Banks: GNPA ≤2%→100, ≤4→65, "
                               "≤7→30, else 0; NNPA ≤1%→100, ≤2→65, ≤4→30, else 0.",
    "ROIC vs WACC": "Spread ≥5pp→100, 2–5→75, 0–2→45, −3–0→20, <−3→0 (banks: ROE − cost of equity).",
    "Cash flow": "Cumulative CFO/Net profit ≥1.0→100, ≥0.8→80, ≥0.5→40, <0.5→0; share of years with positive FCF × 100.",
    "Promoter and shareholder pattern": "3Y promoter change ≥−1pp→100, −1 to −5→60, −5 to −10→30, <−10→0; "
                                        "pledge 0%→100, <5%→80, <15%→40, ≥15%→0.",
}


def _band(v: float, bands: list[tuple[float, float]], else_pts: float) -> float:
    """bands: list of (threshold, points) checked in order with v >= threshold."""
    for thr, pts in bands:
        if v >= thr:
            return pts
    return else_pts


def _band_le(v: float, bands: list[tuple[float, float]], else_pts: float) -> float:
    for thr, pts in bands:
        if v <= thr:
            return pts
    return else_pts


class Category:
    def __init__(self, name: str):
        self.name = name
        self.checks: list[dict] = []

    def add(self, label: str, value, pts: Optional[float], explain: str):
        self.checks.append({"check": label, "value": value, "points": pts, "explain": explain,
                            "used": pts is not None})

    @property
    def score_pct(self) -> Optional[float]:
        used = [c["points"] for c in self.checks if c["used"]]
        return sum(used) / len(used) if used else None


def score(ctx: dict) -> dict:
    r = ctx["ratios"]
    at = ctx["annual_table"]
    sc = ctx["sector_class"]
    is_fin = sc in FINANCIAL_CLASSES

    def mv(k):
        m = r.get(k)
        return m.value if m is not None and m.available else None

    cats = {n: Category(n) for n in SCORE_WEIGHTS}

    # Profitability
    c = cats["Profitability and returns"]
    roe = mv("roe")
    roe_bands = [(20, 100), (15, 80), (10, 50), (5, 30)]
    if r.get("roe") is not None and r["roe"].status == "Not meaningful":
        c.add("ROE", None, 0, "Equity negative – ROE not meaningful, scored 0")
    else:
        c.add("ROE %", roe, _band(roe, roe_bands, 0) if is_num(roe) else None,
              "ROE missing" if not is_num(roe) else f"ROE {roe:.1f}%")
    if is_fin:
        roa = mv("roa")
        c.add("ROA %", roa, _band(roa, [(1.5, 100), (1.0, 70), (0.5, 40)], 10) if is_num(roa) else None,
              f"ROA {roa:.2f}%" if is_num(roa) else "ROA missing")
    else:
        roce = mv("roce")
        c.add("ROCE %", roce, _band(roce, roe_bands, 0) if is_num(roce) else None,
              f"ROCE {roce:.1f}%" if is_num(roce) else "ROCE missing")

    # Growth
    c = cats["Growth"]
    gb = [(20, 100), (12, 80), (6, 55), (0, 30)]
    for col, label in (("revenue", "Revenue CAGR 3Y %"), ("net_income", "Profit CAGR 3Y %")):
        g = None
        if at is not None and len(at) >= 4 and col in at:
            from utils.financial_utils import cagr
            g = cagr(at[col].iloc[-1], at[col].iloc[-4], 3)
            if g is None and is_num(at[col].iloc[-1]) and is_num(at[col].iloc[-4]) and at[col].iloc[-1] <= 0 < at[col].iloc[-4]:
                c.add(label, None, 0, "Turned loss-making over the period → 0")
                continue
        c.add(label, g, _band(g, gb, 0) if is_num(g) else None, f"{g:.1f}%" if is_num(g) else "Needs 4 years of positive values")

    # Valuation
    c = cats["Valuation"]
    pe_m = r.get("pe")
    if pe_m is not None and pe_m.status == "Not meaningful":
        c.add("P/E", None, 0, "Loss-making – earnings do not support the price → 0")
    else:
        peg = mv("peg")
        if r.get("peg") is not None and r["peg"].status == "Not meaningful":
            c.add("PEG", None, 15, "EPS growth negative – PEG not meaningful; low score")
        else:
            c.add("PEG", peg, _band_le(peg, [(1, 100), (2, 70), (3, 40)], 10) if is_num(peg) else None,
                  f"PEG {peg:.2f}" if is_num(peg) else "PEG unavailable")
        pe = mv("pe")
        pmed = ctx.get("peer_median", {}).get("P/E")
        rel = pe / pmed if is_num(pe) and is_num(pmed) and pmed > 0 else None
        c.add("P/E ÷ peer median", rel, _band_le(rel, [(0.8, 100), (1.2, 70), (1.6, 40)], 10) if is_num(rel) else None,
              f"{rel:.2f}" if is_num(rel) else "Peer P/E unavailable")
        own = mv("pe_5y_avg")
        rel2 = pe / own if is_num(pe) and is_num(own) and own > 0 else None
        c.add("P/E ÷ own 5Y average", rel2, _band_le(rel2, [(0.8, 100), (1.2, 70), (1.6, 40)], 10) if is_num(rel2) else None,
              f"{rel2:.2f}" if is_num(rel2) else "Own P/E history unavailable")

    # Debt
    c = cats["Debt and financial risk"]
    if is_fin:
        bm = ctx.get("bank_latest", {})
        g, n = bm.get("gnpa_pct"), bm.get("nnpa_pct")
        c.add("Gross NPA %", g, _band_le(g, [(2, 100), (4, 65), (7, 30)], 0) if is_num(g) else None,
              f"GNPA {g:.2f}%" if is_num(g) else "GNPA unavailable")
        c.add("Net NPA %", n, _band_le(n, [(1, 100), (2, 65), (4, 30)], 0) if is_num(n) else None,
              f"NNPA {n:.2f}%" if is_num(n) else "NNPA unavailable")
    else:
        de = mv("de")
        if r.get("de") is not None and r["de"].status == "Not meaningful":
            c.add("Debt/Equity", None, 0, "Negative equity → 0")
        else:
            c.add("Debt/Equity", de, _band_le(de, [(0.3, 100), (0.7, 80), (1.5, 50), (2.5, 20)], 0) if is_num(de) else None,
                  f"D/E {de:.2f}" if is_num(de) else "D/E unavailable")
        icr = ctx.get("icr", {})
        lbl = icr.get("label")
        pts = {"Strong": 100, "Moderate": 60, "Weak": 25, "Serious concern": 0, "Strong (no interest)": 100}.get(lbl)
        val = icr.get("metric").value if icr.get("metric") is not None else None
        c.add("Interest coverage", val, pts, lbl or "Unavailable")

    # ROIC vs WACC
    c = cats["ROIC vs WACC"]
    sp = ctx.get("roic_wacc", {}).get("spread")
    s = sp.value if sp is not None and sp.available else None
    c.add(ctx.get("roic_wacc", {}).get("spread_kind", "Spread") + " (pp)", s,
          _band(s, [(5, 100), (2, 75), (0, 45), (-3, 20)], 0) if is_num(s) else None,
          f"{s:+.1f} pp" if is_num(s) else "Spread unavailable")

    # Cash flow
    c = cats["Cash flow"]
    cf = ctx.get("cashflow", {})
    if is_fin:
        pass  # not meaningful for lenders -> category excluded
    else:
        conv = cf.get("cum_conversion")
        c.add("CFO / Net profit (cumulative)", conv,
              _band(conv, [(1.0, 100), (0.8, 80), (0.5, 40)], 0) if is_num(conv) else None,
              f"{conv:.2f}" if is_num(conv) else "Unavailable")
        if cf.get("fcf_years"):
            share = cf["fcf_positive_years"] / cf["fcf_years"]
            c.add("Years with positive FCF", share, share * 100, f"{cf['fcf_positive_years']}/{cf['fcf_years']}")
        else:
            c.add("Years with positive FCF", None, None, "FCF unavailable")

    # Promoter
    c = cats["Promoter and shareholder pattern"]
    pr = ctx.get("promoter", {})
    if pr.get("available") and not pr.get("no_promoter"):
        ch = pr.get("promoter_change_3y")
        c.add("Promoter change (pp)", ch, _band(ch, [(-1, 100), (-5, 60), (-10, 30)], 0) if is_num(ch) else None,
              f"{ch:+.2f} pp" if is_num(ch) else "Unavailable")
        pl = pr.get("pledge_latest")
        c.add("Pledge % of promoter holding", pl, _band_le(pl, [(0, 100), (4.999, 80), (14.999, 40)], 0) if is_num(pl) else None,
              f"{pl:.2f}%" if is_num(pl) else "Pledge data unavailable")

    # Aggregate
    total_w = sum(SCORE_WEIGHTS.values())
    used_w = sum(SCORE_WEIGHTS[n] for n, cat in cats.items() if cat.score_pct is not None)
    rows = []
    overall = 0.0
    for n, cat in cats.items():
        w = SCORE_WEIGHTS[n]
        pct = cat.score_pct
        adj_w = w * total_w / used_w if pct is not None and used_w else 0
        pts = pct / 100 * adj_w if pct is not None else None
        if pts is not None:
            overall += pts
        rows.append({"Category": n, "Weight": w, "Adjusted weight": round(adj_w, 2) if pct is not None else 0,
                     "Category score %": round(pct, 1) if pct is not None else None,
                     "Points": round(pts, 1) if pts is not None else None,
                     "Status": "Scored" if pct is not None else "Excluded – insufficient data",
                     "Evidence": "; ".join(f"{ch['check']}: {ch['explain']}"
                                           + (f" → {ch['points']:.0f}/100" if ch["used"] else " (not scored)")
                                           for ch in cat.checks),
                     "Rubric": RUBRIC_TEXT[n]})
    coverage = used_w / total_w * 100 if total_w else 0
    overall = round(overall, 1) if used_w else None
    label = next(lbl for thr, lbl in SCORE_LABELS if overall is not None and overall >= thr) if overall is not None else "Insufficient data"
    critical = ctx.get("critical_flags", [])
    if critical and overall is not None:
        label = "High financial risk"
    return {"overall": overall, "label": label, "coverage_pct": round(coverage, 1), "table": rows,
            "critical_flags": critical,
            "method": ("Each category is scored 0–100% from its sub-checks (rubric shown per row) and multiplied by its "
                       "weight. Categories without data are excluded and remaining weights are scaled to total 100. "
                       "Critical warning signs (operating profit not covering interest, negative equity) override "
                       "the label to 'High financial risk'.")}
