"""
Canonical data model shared by all providers.

All statement amounts are stored in ₹ crore. EPS is in ₹ per share.
Statements are DataFrames: index = canonical line item, columns = period-end
Timestamps (oldest -> newest). Missing values are NaN – never 0.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import pandas as pd

# Canonical line items (₹ crore unless stated)
CANONICAL_ITEMS = [
    "revenue", "operating_profit", "other_income", "depreciation", "interest", "ebit", "ebitda",
    "pbt", "tax", "net_income", "eps_basic", "eps_diluted", "dividend_payout_pct",
    "total_assets", "current_liabilities", "total_equity", "total_debt", "short_term_debt",
    "long_term_debt", "lease_liabilities", "cash", "deposits", "cfo", "cfi", "cff", "capex", "fcf",
]


@dataclass
class CompanyIdentity:
    name: str = ""
    nse_symbol: Optional[str] = None
    bse_code: Optional[str] = None
    yahoo_ticker: Optional[str] = None
    isin: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    sector_class: str = "other"   # bank / nbfc / insurance / it_services / infrastructure / real_estate / manufacturing / other
    exchange: Optional[str] = None
    currency: str = "INR"
    screener_url: Optional[str] = None
    screener_company_id: Optional[str] = None
    screener_warehouse_id: Optional[str] = None
    resolved_by: str = ""

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class SourceRecord:
    dataset: str
    source: str
    url: str = ""
    as_of: str = ""
    status: str = "OK"     # OK / Partial / Failed / Restricted / Not attempted
    note: str = ""

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class CompanyData:
    identity: CompanyIdentity
    quote: dict = field(default_factory=dict)
    price_history: pd.DataFrame = field(default_factory=pd.DataFrame)   # index Date, cols Close, Volume
    benchmark_history: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    annual: pd.DataFrame = field(default_factory=pd.DataFrame)
    quarterly: pd.DataFrame = field(default_factory=pd.DataFrame)
    statement_source: str = ""
    statement_basis: str = "Unknown"      # Consolidated / Standalone / Unknown
    item_sources: dict = field(default_factory=dict)
    ttm: dict = field(default_factory=dict)  # TTM values when the source provides them
    shareholding: pd.DataFrame = field(default_factory=pd.DataFrame)  # index quarter-end, cols categories (%)
    shareholding_source: str = ""
    pledge: pd.DataFrame = field(default_factory=pd.DataFrame)        # index date, cols pledged_pct_of_promoter, pledged_pct_of_total
    pledge_source: str = ""
    bank_metrics: pd.DataFrame = field(default_factory=pd.DataFrame)  # quarterly GNPA/NNPA etc.
    source_ratios: dict = field(default_factory=dict)  # ratios as published by the source (for cross-check)
    peers: list = field(default_factory=list)          # [{"name","symbol","source"}]
    sources: list = field(default_factory=list)        # [SourceRecord]
    warnings: list = field(default_factory=list)
    is_demo: bool = False
    fetched_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def add_source(self, dataset: str, source: str, url: str = "", as_of: Any = "",
                   status: str = "OK", note: str = "") -> None:
        self.sources.append(SourceRecord(dataset, source, url, str(as_of or ""), status, note))

    def warn(self, msg: str) -> None:
        if msg not in self.warnings:
            self.warnings.append(msg)


def empty_statement() -> pd.DataFrame:
    return pd.DataFrame(index=pd.Index([], name="item"))


def finalize_statement(df: pd.DataFrame, item_sources: dict, label: str) -> pd.DataFrame:
    """Add derived items (EBIT, EBITDA, FCF) when inputs exist, without overwriting
    reported values. Derivations are recorded in item_sources."""
    if df is None or df.empty:
        return empty_statement()
    df = df.copy()

    def has(item):
        return item in df.index and df.loc[item].notna().any()

    def ensure(item):
        if item not in df.index:
            df.loc[item] = float("nan")

    # EBIT = PBT + Interest (finance cost)
    if has("pbt") and has("interest"):
        ensure("ebit")
        derived = df.loc["pbt"] + df.loc["interest"]
        mask = df.loc["ebit"].isna() & derived.notna()
        if mask.any():
            df.loc["ebit", mask] = derived[mask]
            item_sources.setdefault(f"{label}:ebit", "Derived: EBIT = Profit before tax + Finance cost")
    # EBITDA = EBIT + Depreciation & Amortisation
    if has("ebit") and has("depreciation"):
        ensure("ebitda")
        derived = df.loc["ebit"] + df.loc["depreciation"]
        mask = df.loc["ebitda"].isna() & derived.notna()
        if mask.any():
            df.loc["ebitda", mask] = derived[mask]
            item_sources.setdefault(f"{label}:ebitda", "Derived: EBITDA = EBIT + Depreciation & Amortisation")
    # Tax from PBT when only the rate is known is handled by providers.
    # FCF = CFO - Capex
    if has("cfo") and has("capex"):
        ensure("fcf")
        derived = df.loc["cfo"] - df.loc["capex"].abs()
        mask = df.loc["fcf"].isna() & derived.notna()
        if mask.any():
            df.loc["fcf", mask] = derived[mask]
            item_sources.setdefault(f"{label}:fcf", "Derived: FCF = Cash from operations - Capital expenditure")
    # Total debt from components
    if not has("total_debt") and (has("short_term_debt") or has("long_term_debt")):
        ensure("total_debt")
        st = df.loc["short_term_debt"] if "short_term_debt" in df.index else None
        lt = df.loc["long_term_debt"] if "long_term_debt" in df.index else None
        if st is not None and lt is not None:
            df.loc["total_debt"] = st.add(lt)  # NaN if either missing
            item_sources.setdefault(f"{label}:total_debt", "Derived: Short-term + Long-term debt")
    df = df.apply(pd.to_numeric, errors="coerce")
    return df.reindex(sorted(df.columns), axis=1)
