"""Validation helpers: staleness, sanity checks and data-coverage summary."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import pandas as pd

from config import SETTINGS
from utils.financial_utils import is_num
from utils.logger import get_logger

log = get_logger(__name__)


def days_old(ts: Any, now: Optional[datetime] = None) -> Optional[int]:
    if ts is None:
        return None
    try:
        t = pd.Timestamp(ts)
    except Exception:  # noqa: BLE001
        return None
    if t.tzinfo is not None:
        t = t.tz_convert(None)
    now = now or datetime.now()
    return (pd.Timestamp(now) - t).days


def price_staleness(last_price_date: Any) -> dict:
    age = days_old(last_price_date)
    if age is None:
        return {"stale": True, "age_days": None,
                "message": "Date of the latest price is unknown; treat CMP with caution."}
    stale = age > SETTINGS.stale_price_days
    msg = (f"Latest price is {age} day(s) old – may be stale (market holiday, suspension or data delay)."
           if stale else f"Latest price is from {pd.Timestamp(last_price_date).date()} ({age} day(s) old).")
    return {"stale": stale, "age_days": age, "message": msg}


def financials_staleness(latest_period: Any) -> dict:
    age = days_old(latest_period)
    if age is None:
        return {"stale": True, "age_days": None, "message": "No dated annual financial statements found."}
    stale = age > SETTINGS.stale_financials_days
    msg = (f"Latest annual statement period ends {pd.Timestamp(latest_period).date()} ({age} days ago)"
           + (" – this is old; newer results may exist." if stale else "."))
    return {"stale": stale, "age_days": age, "message": msg}


def clean_statement(df: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Ensure numeric values, datetime columns (oldest->newest), drop empty columns."""
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out.columns = pd.to_datetime(out.columns, errors="coerce")
    out = out.loc[:, out.columns.notna()]
    out = out.apply(pd.to_numeric, errors="coerce")
    out = out.dropna(axis=1, how="all")
    out = out.loc[:, ~out.columns.duplicated()]
    return out.reindex(sorted(out.columns), axis=1)


def sanity_checks(annual: pd.DataFrame, quote: dict) -> list[str]:
    """Return human-readable warnings for suspicious data. Never modifies data."""
    warnings: list[str] = []
    if annual is None or annual.empty:
        return ["No annual financial statements available."]
    cols = sorted(annual.columns)
    latest = cols[-1]

    def g(item):
        if item in annual.index:
            v = annual.at[item, latest]
            return float(v) if is_num(v) else None
        return None

    rev, ni, eq, ta = g("revenue"), g("net_income"), g("total_equity"), g("total_assets")
    if rev is not None and rev <= 0:
        warnings.append("Latest revenue is zero or negative – check the data source.")
    if eq is not None and eq < 0:
        warnings.append("Shareholders' equity is NEGATIVE – ROE and D/E are not meaningful.")
    if ta is not None and eq is not None and eq > ta * 1.01:
        warnings.append("Equity exceeds total assets – balance-sheet data may be inconsistent.")
    if rev and ni is not None and abs(ni) > abs(rev) * 2:
        warnings.append("Net profit is more than twice revenue – possible one-off gain or data error.")
    if not is_num(quote.get("price")):
        warnings.append("Current market price is unavailable.")
    return warnings


def coverage_summary(checks: dict[str, bool]) -> dict:
    total = len(checks)
    have = sum(1 for v in checks.values() if v)
    return {
        "items": checks,
        "available": have,
        "total": total,
        "coverage_pct": round(have / total * 100.0, 1) if total else 0.0,
    }
