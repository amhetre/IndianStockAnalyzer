"""
3M / 6M / 9M / 1Y / 3Y / 5Y analysis.

Price part: start price = last close on or before (latest date - period).
Financial part (never uses today's ratios for history):
* 3M / 6M / 9M : sum of the last k reported quarters (k = 1/2/3) vs the SAME k quarters
                 one year earlier (YoY – avoids seasonality). Interest coverage from the
                 same quarters. Balance-sheet ratios (ROE/ROCE/ROIC/D-E) are not computed
                 because quarterly balance sheets are not reported consistently in India.
* 1Y           : trailing 4 quarters vs previous 4 quarters when 8 quarters exist,
                 else latest financial year vs previous year. Ratios = latest FY.
* 3Y / 5Y      : CAGR between annual statements N years apart; ratios shown as the average
                 of the annual values over the window and the end-of-window value.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from analysis.fundamental_ratios import price_on_or_before
from utils.financial_utils import cagr, is_num, mean_of, pct_change, safe_div

PERIOD_MONTHS = {"3M": 3, "6M": 6, "9M": 9, "1Y": 12, "3Y": 36, "5Y": 60}


def _price_part(hist: pd.DataFrame, months: int) -> dict:
    out = {"start_date": None, "start_price": None, "latest_price": None, "abs_change": None,
           "pct_change": None, "price_cagr": None}
    if hist is None or hist.empty:
        return out
    last_date = hist.index[-1]
    start_target = last_date - pd.DateOffset(months=months)
    if hist.index[0] > start_target + pd.Timedelta(days=7):
        out["note"] = "Price history does not cover the full period"
        return out
    sub = hist.loc[hist.index <= start_target]
    if sub.empty:
        sub = hist.iloc[:1]
    sp = float(sub["Close"].iloc[-1])
    lp = float(hist["Close"].iloc[-1])
    out.update({"start_date": sub.index[-1].date(), "start_price": sp, "latest_price": lp,
                "abs_change": lp - sp, "pct_change": pct_change(lp, sp)})
    if months > 12:
        out["price_cagr"] = cagr(lp, sp, months / 12)
    return out


def _sum_window(qt: pd.DataFrame, col: str, start: int, k: int) -> Optional[float]:
    """Sum of k quarters ending at position len-start (0 = latest). Requires all present."""
    if qt is None or col not in qt or len(qt) < start + k:
        return None
    end = len(qt) - start
    w = qt[col].iloc[end - k:end]
    if len(w) < k or w.isna().any():
        return None
    return float(w.sum())


def _quarter_window_ok(qt: pd.DataFrame, k: int) -> bool:
    """Check that the YoY comparison quarters are exactly ~1 year apart."""
    if qt is None or len(qt) < k + 4:
        return False
    a = qt.index[-1]
    b = qt.index[-1 - 4]
    return 330 <= (a - b).days <= 400


def _quarterly_part(qt: pd.DataFrame, k: int) -> dict:
    res = {"basis": f"Last {k} quarter(s) vs same {k} quarter(s) a year earlier (YoY)"}
    if not _quarter_window_ok(qt, k):
        res["note"] = "Not enough quarterly results for a year-on-year comparison"
        return res
    res["window"] = f"{qt.index[-k].strftime('%b %Y')} – {qt.index[-1].strftime('%b %Y')}"
    for col, key in (("revenue", "revenue_growth"), ("ebitda", "ebitda_growth"),
                     ("operating_profit", "operating_profit_growth"), ("net_income", "profit_growth"),
                     ("eps_basic", "eps_growth")):
        cur = _sum_window(qt, col, 0, k)
        prev = _sum_window(qt, col, 4, k)
        res[key] = pct_change(cur, prev)
    ebit, intr = _sum_window(qt, "ebit", 0, k), _sum_window(qt, "interest", 0, k)
    res["icr"] = safe_div(ebit, intr) if is_num(intr) and intr > 0 else None
    res["ratio_note"] = "ROE/ROCE/ROIC/D-E need balance sheets, which are reported annually – see 1Y/3Y/5Y."
    return res


def _annual_window(at: pd.DataFrame, years: int) -> dict:
    res = {"basis": f"Annual statements: {years}-year CAGR"}
    if at is None or len(at) < years + 1:
        res["note"] = f"Needs {years + 1} years of annual statements; only {0 if at is None else len(at)} available"
        if at is not None and len(at) >= 2:
            res["note"] += " (incomplete period)"
        return res
    end, start = at.iloc[-1], at.iloc[-1 - years]
    res["window"] = f"{at.index[-1 - years]} – {at.index[-1]}"
    for col, key in (("revenue", "revenue_growth"), ("ebitda", "ebitda_growth"), ("ebit", "operating_profit_growth"),
                     ("net_income", "profit_growth"), ("eps", "eps_growth")):
        res[key] = cagr(end.get(col), start.get(col), years)
        res[key + "_label"] = "CAGR"
    win = at.iloc[-years:]
    for col in ("roe", "roce", "roic", "de", "icr", "pe"):
        if col in at:
            res[col] = mean_of(win[col])
            res[col + "_end"] = end.get(col)
    res["ratio_note"] = f"Ratios are the average of the {years} annual values in the window."
    return res


def analyse_periods(hist: pd.DataFrame, at: pd.DataFrame, qt: pd.DataFrame, periods: list[str]) -> pd.DataFrame:
    rows = []
    for p in periods:
        p = p.upper().strip()
        if p not in PERIOD_MONTHS:
            continue
        months = PERIOD_MONTHS[p]
        row = {"Period": p}
        row.update(_price_part(hist, months))
        if months < 12:
            fin = _quarterly_part(qt, months // 3)
        elif months == 12:
            fin = {}
            if qt is not None and len(qt) >= 8 and _quarter_window_ok(qt, 4):
                fin = _quarterly_part(qt, 4)
                fin["basis"] = "Trailing 4 quarters vs previous 4 quarters"
            elif at is not None and len(at) >= 2:
                fin = {"basis": "Latest financial year vs previous year", "window": f"{at.index[-2]} – {at.index[-1]}"}
                last = at.iloc[-1]
                for col, key in (("revenue_growth", "revenue_growth"), ("ebitda_growth", "ebitda_growth"),
                                 ("ebit_growth", "operating_profit_growth"), ("profit_growth", "profit_growth"),
                                 ("eps_growth", "eps_growth")):
                    fin[key] = last.get(col)
            else:
                fin = {"note": "Not enough data for 1-year comparison"}
            if at is not None and len(at):
                last = at.iloc[-1]
                for col in ("roe", "roce", "roic", "de", "pe"):
                    if col in at:
                        fin[col] = last.get(col)
                if not is_num(fin.get("icr")) and "icr" in at:
                    fin["icr"] = last.get("icr")
                fin["ratio_note"] = f"Ratios for latest financial year ({at.index[-1]})."
        else:
            fin = _annual_window(at, months // 12)
        note = "; ".join(x for x in (row.pop("note", None), fin.pop("note", None)) if x)
        row.update(fin)
        row["note"] = note
        rows.append(row)
    return pd.DataFrame(rows).set_index("Period") if rows else pd.DataFrame()
