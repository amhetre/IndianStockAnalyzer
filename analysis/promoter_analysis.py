"""Promoter / FII / DII / public holding and pledge analysis – last ~12 quarters."""
from __future__ import annotations

import pandas as pd

from data_providers.models import CompanyData
from utils.financial_utils import is_num, num


def _missing_quarters(idx: pd.DatetimeIndex) -> list[str]:
    if len(idx) < 2:
        return []
    try:
        expected = pd.date_range(idx.min(), idx.max(), freq="QE")
    except ValueError:  # pandas < 2.2
        expected = pd.date_range(idx.min(), idx.max(), freq="Q")
    have = {(d.year, d.month) for d in idx}
    return [d.strftime("%b %Y") for d in expected if (d.year, d.month) not in have]


def analyse_promoters(data: CompanyData) -> dict:
    out: dict = {"source": data.shareholding_source, "pledge_source": data.pledge_source, "points": [],
                 "missing": []}
    shp = data.shareholding
    if shp is None or shp.empty:
        out["table"] = pd.DataFrame()
        out["available"] = False
        out["points"].append("Quarterly shareholding data could not be retrieved from Screener.in or NSE. "
                             "No promoter figures are shown (none are estimated).")
        out["missing"].append("Entire shareholding history")
        return out
    shp = shp.sort_index()
    last_date = shp.index[-1]
    cutoff = last_date - pd.DateOffset(months=33)
    tbl = shp.loc[shp.index >= cutoff].copy()
    out["missing"] = _missing_quarters(tbl.index)
    tbl["quarter"] = [d.strftime("%b %Y") for d in tbl.index]
    if "promoters" in tbl:
        tbl["promoter_qoq_change"] = tbl["promoters"].diff()
    # Pledge
    pl = data.pledge
    if pl is not None and not pl.empty:
        pl = pl.sort_index()
        aligned = pl.reindex(tbl.index, method="nearest", tolerance=pd.Timedelta(days=45))
        for c in ("pledged_pct_of_promoter", "pledged_pct_of_total"):
            if c in aligned:
                tbl[c] = aligned[c].values
    out["table"] = tbl
    out["available"] = True
    out["quarters"] = len(tbl)
    out["first_quarter"], out["last_quarter"] = tbl.index[0].strftime("%b %Y"), tbl.index[-1].strftime("%b %Y")
    pts = out["points"]
    if len(tbl) < 12:
        pts.append(f"Only {len(tbl)} quarter(s) of shareholding data available (target: 12).")
    if out["missing"]:
        pts.append("Missing quarters: " + ", ".join(out["missing"]) + ".")

    if "promoters" in tbl and tbl["promoters"].notna().any():
        p = tbl["promoters"].dropna()
        start, end = float(p.iloc[0]), float(p.iloc[-1])
        out["promoter_start"], out["promoter_end"] = start, end
        out["promoter_change_3y"] = end - start
        if end == 0 and start == 0:
            out["no_promoter"] = True
            pts.append("The company has no identified promoter group (professionally managed / widely held). "
                       "Promoter-based signals do not apply; look at FII/DII trends instead.")
        else:
            ch = end - start
            direction = "increased" if ch > 0.25 else "decreased" if ch < -0.25 else "remained broadly stable"
            pts.append(f"Promoter holding has {direction}: {start:.2f}% ({out['first_quarter']}) → {end:.2f}% "
                       f"({out['last_quarter']}), a change of {ch:+.2f} percentage points.")
            big = tbl["promoter_qoq_change"].dropna()
            big = big[big.abs() >= 2]
            if len(big):
                pts.append("Large quarter-on-quarter moves: " + ", ".join(
                    f"{d.strftime('%b %Y')} ({v:+.2f} pp)" for d, v in big.items()) + ".")
            if ch <= -5:
                pts.append("This is a SIGNIFICANT reduction. It may reflect stake sales, but also QIPs/new share issues "
                           "(dilution), mergers, OFS to meet minimum public shareholding rules, or reclassification. "
                           "Check exchange filings before reading it as negative sentiment.")
            elif ch < -0.25:
                pts.append("A modest reduction. Promoter selling does not automatically mean negative sentiment – "
                           "it can be for personal needs, dilution from fundraising, or regulatory compliance.")
            elif ch > 0.25:
                pts.append("Rising promoter holding is usually read as promoters showing confidence (e.g. creeping "
                           "acquisition or buy-back), though buy-backs mechanically raise the percentage too.")
            else:
                pts.append("A stable promoter holding suggests promoters are maintaining their commitment.")
    else:
        pts.append("Promoter holding row not found in the data.")

    for col, label in (("fii", "FII (foreign institutions)"), ("dii", "DII (domestic institutions – mutual funds, insurers)"),
                       ("public", "Public / retail")):
        if col in tbl and tbl[col].notna().sum() >= 2:
            s = tbl[col].dropna()
            out[f"{col}_change_3y"] = float(s.iloc[-1] - s.iloc[0])
            pts.append(f"{label}: {s.iloc[0]:.2f}% → {s.iloc[-1]:.2f}% ({s.iloc[-1] - s.iloc[0]:+.2f} pp).")
    if "fii_change_3y" in out and "dii_change_3y" in out:
        f, d = out["fii_change_3y"], out["dii_change_3y"]
        if f > 1 and d > 1:
            pts.append("Both foreign and domestic institutions have been adding – institutional interest is rising.")
        elif f < -1 and d < -1:
            pts.append("Both foreign and domestic institutions have reduced holdings – institutional interest has cooled.")
        elif f < -1 < d:
            pts.append("Foreign investors sold while domestic institutions bought – a common pattern in Indian markets; "
                       "domestic funds have absorbed FII selling.")

    # Pledge
    if "pledged_pct_of_promoter" in tbl and tbl["pledged_pct_of_promoter"].notna().any():
        ps = tbl["pledged_pct_of_promoter"].dropna()
        out["pledge_latest"] = float(ps.iloc[-1])
        out["pledge_change"] = float(ps.iloc[-1] - ps.iloc[0]) if len(ps) >= 2 else None
        lvl = ps.iloc[-1]
        pts.append(f"Pledged shares: {lvl:.2f}% of promoter holding ({ps.index[-1].strftime('%b %Y')})"
                   + (f", changed {out['pledge_change']:+.2f} pp since {ps.index[0].strftime('%b %Y')}." if out['pledge_change'] is not None else ".")
                   + (" No pledge – a positive sign." if lvl == 0 else
                      " Low pledge." if lvl < 5 else
                      " Moderate pledge – monitor it." if lvl < 25 else
                      " HIGH pledge – if the share price falls sharply, lenders may sell pledged shares, adding "
                      "selling pressure. This is a risk factor."))
    else:
        out["pledge_latest"] = None
        pts.append("Promoter pledge data was not available (NSE pledge endpoint unreachable or restricted). "
                   "Check the 'Pledged data' section on nseindia.com.")
        out["missing"].append("Pledge data")
    out["points"] = pts
    return out
