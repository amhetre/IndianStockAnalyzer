"""
Safe financial arithmetic and the `Metric` record.

Rules enforced here:
* Missing values are `None` – never silently converted to 0.
* Division by zero / by missing returns None.
* Every calculated metric is a `Metric` that keeps its source values, formula,
  period, source and availability status so it can be audited in reports.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd

CRORE = 1e7
LAKH = 1e5

# Availability / confidence statuses
ACTUAL = "Actual"            # computed directly from reported data
DERIVED = "Derived"          # computed from reported data with a documented approximation
ESTIMATE = "Estimate"        # depends on assumptions (e.g. WACC)
UNAVAILABLE = "Unavailable"  # data missing
NOT_MEANINGFUL = "Not meaningful"  # e.g. PEG with negative growth, D/E for banks


def is_num(x: Any) -> bool:
    """True for real, finite numbers (not None / NaN / inf / bool)."""
    if x is None or isinstance(x, bool):
        return False
    try:
        f = float(x)
    except (TypeError, ValueError):
        return False
    return math.isfinite(f)


def num(x: Any) -> Optional[float]:
    return float(x) if is_num(x) else None


def safe_div(a: Any, b: Any) -> Optional[float]:
    """a / b, or None when either is missing or b == 0."""
    if not is_num(a) or not is_num(b):
        return None
    b = float(b)
    if b == 0:
        return None
    return float(a) / b


def safe_sub(a: Any, b: Any) -> Optional[float]:
    if not is_num(a) or not is_num(b):
        return None
    return float(a) - float(b)


def safe_add(*vals: Any) -> Optional[float]:
    """Sum only if *all* values are present."""
    if not vals or not all(is_num(v) for v in vals):
        return None
    return float(sum(float(v) for v in vals))


def safe_mul(a: Any, b: Any) -> Optional[float]:
    if not is_num(a) or not is_num(b):
        return None
    return float(a) * float(b)


def pct_change(new: Any, old: Any) -> Optional[float]:
    """Percentage change. Not meaningful when the base is <= 0 (returns None)."""
    if not is_num(new) or not is_num(old):
        return None
    old = float(old)
    if old <= 0:
        return None
    return (float(new) - old) / old * 100.0


def cagr(end: Any, start: Any, years: Any) -> Optional[float]:
    """Compound annual growth rate in %. None if start/end <= 0 or years <= 0."""
    if not (is_num(end) and is_num(start) and is_num(years)):
        return None
    end, start, years = float(end), float(start), float(years)
    if start <= 0 or end <= 0 or years <= 0:
        return None
    return ((end / start) ** (1.0 / years) - 1.0) * 100.0


def average(a: Any, b: Any) -> Optional[float]:
    """Average of opening and closing balance. Requires both."""
    if is_num(a) and is_num(b):
        return (float(a) + float(b)) / 2.0
    return None


def mean_of(values: Iterable[Any]) -> Optional[float]:
    vals = [float(v) for v in values if is_num(v)]
    return float(np.mean(vals)) if vals else None


def median_of(values: Iterable[Any]) -> Optional[float]:
    vals = [float(v) for v in values if is_num(v)]
    return float(np.median(vals)) if vals else None


def to_crore(value_in_rupees: Any) -> Optional[float]:
    v = num(value_in_rupees)
    return None if v is None else v / CRORE


# ---------------------------------------------------------------------------
# Formatting helpers (₹ crore / lakh, Indian digit grouping)
# ---------------------------------------------------------------------------
def indian_group(n: float, decimals: int = 0) -> str:
    neg = n < 0
    n = abs(n)
    s = f"{n:.{decimals}f}"
    if "." in s:
        whole, frac = s.split(".")
    else:
        whole, frac = s, ""
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    out = whole + ("." + frac if frac else "")
    return ("-" if neg else "") + out


def fmt_cr(value_cr: Any, decimals: int = 0) -> str:
    """Format a value already in ₹ crore."""
    v = num(value_cr)
    if v is None:
        return "N/A"
    sign = "-" if v < 0 else ""
    if abs(v) < 1:
        return f"{sign}₹{indian_group(abs(v) * 100, 1)} L"
    if abs(v) >= 1e5:  # 1 lakh crore and above → "₹4.03 L Cr"
        return f"{sign}₹{abs(v) / 1e5:.2f} L Cr"
    return f"{sign}₹{indian_group(abs(v), decimals)} Cr"


def fmt_inr(value: Any, decimals: int = 2) -> str:
    v = num(value)
    if v is None:
        return "N/A"
    return ("-" if v < 0 else "") + f"₹{indian_group(abs(v), decimals)}"


def fmt_pct(value: Any, decimals: int = 1, signed: bool = False) -> str:
    v = num(value)
    if v is None:
        return "N/A"
    return f"{v:+.{decimals}f}%" if signed else f"{v:.{decimals}f}%"


def fmt_x(value: Any, decimals: int = 2) -> str:
    v = num(value)
    return "N/A" if v is None else f"{v:.{decimals}f}x"


def fmt_num(value: Any, decimals: int = 2) -> str:
    v = num(value)
    return "N/A" if v is None else f"{v:,.{decimals}f}"


# ---------------------------------------------------------------------------
# Metric record
# ---------------------------------------------------------------------------
@dataclass
class Metric:
    name: str
    value: Optional[float]
    unit: str = ""                  # "%", "x", "₹", "₹ Cr", ""
    formula: str = ""
    period: str = ""
    inputs: dict = field(default_factory=dict)
    source: str = ""
    status: str = ACTUAL
    note: str = ""

    @property
    def available(self) -> bool:
        return is_num(self.value) and self.status not in (UNAVAILABLE, NOT_MEANINGFUL)

    def display(self) -> str:
        if not self.available:
            return self.status if self.status in (UNAVAILABLE, NOT_MEANINGFUL) else "N/A"
        if self.unit == "%":
            return fmt_pct(self.value)
        if self.unit == "x":
            return fmt_x(self.value)
        if self.unit == "₹ Cr":
            return fmt_cr(self.value)
        if self.unit == "₹":
            return fmt_inr(self.value)
        return fmt_num(self.value)

    def inputs_text(self) -> str:
        parts = []
        for k, v in self.inputs.items():
            if is_num(v):
                parts.append(f"{k}={float(v):,.2f}")
            else:
                parts.append(f"{k}={'missing' if v is None else v}")
        return "; ".join(parts)

    def to_row(self) -> dict:
        return {
            "Metric": self.name,
            "Value": self.value if self.available else None,
            "Display": self.display(),
            "Unit": self.unit,
            "Formula": self.formula,
            "Period": self.period,
            "Inputs": self.inputs_text(),
            "Source": self.source,
            "Status": self.status,
            "Note": self.note,
        }


def unavailable(name: str, reason: str, unit: str = "", formula: str = "", period: str = "",
                inputs: Optional[dict] = None, source: str = "") -> Metric:
    return Metric(name=name, value=None, unit=unit, formula=formula, period=period,
                  inputs=inputs or {}, source=source, status=UNAVAILABLE, note=reason)


def not_meaningful(name: str, reason: str, unit: str = "", formula: str = "", period: str = "",
                   inputs: Optional[dict] = None, source: str = "") -> Metric:
    return Metric(name=name, value=None, unit=unit, formula=formula, period=period,
                  inputs=inputs or {}, source=source, status=NOT_MEANINGFUL, note=reason)


# ---------------------------------------------------------------------------
# Statement helpers (statements: DataFrame index = line item, columns = period-end Timestamp)
# ---------------------------------------------------------------------------
def get_item(df: Optional[pd.DataFrame], item: str, col: Any) -> Optional[float]:
    if df is None or df.empty or item not in df.index or col not in df.columns:
        return None
    return num(df.at[item, col])


def series(df: Optional[pd.DataFrame], item: str) -> pd.Series:
    """Line-item series sorted oldest -> newest (NaN kept for missing)."""
    if df is None or df.empty or item not in df.index:
        return pd.Series(dtype=float)
    s = pd.to_numeric(df.loc[item], errors="coerce")
    return s.sort_index()


def sorted_cols(df: Optional[pd.DataFrame]) -> list:
    if df is None or df.empty:
        return []
    return sorted(df.columns)


def period_label(ts: Any, quarterly: bool = False) -> str:
    try:
        t = pd.Timestamp(ts)
    except Exception:  # noqa: BLE001
        return str(ts)
    return t.strftime("%b %Y") if quarterly else (f"FY{t.year % 100:02d}" if t.month <= 6
                                                   else f"FY{(t.year + 1) % 100:02d}")
