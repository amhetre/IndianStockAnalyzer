"""Unit tests for core financial calculations (hand-computed expected values)."""
import math
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.fundamental_ratios import annual_ratio_table, compute_core_ratios, quarterly_table  # noqa: E402
from analysis.interest_coverage import analyse_interest_coverage, classify_icr  # noqa: E402
from analysis.period_analysis import analyse_periods  # noqa: E402
from analysis.roic_wacc import analyse_roic_wacc  # noqa: E402
from analysis.scoring_engine import score  # noqa: E402
from config import ASSUMPTIONS  # noqa: E402
from data_providers.models import CompanyData, CompanyIdentity, finalize_statement  # noqa: E402
from utils.financial_utils import (NOT_MEANINGFUL, UNAVAILABLE, average, cagr, fmt_cr, indian_group,  # noqa: E402
                                   pct_change, safe_add, safe_div)


# ----------------------------------------------------------------- utils
def test_safe_div_handles_zero_and_missing():
    assert safe_div(10, 2) == 5
    assert safe_div(10, 0) is None
    assert safe_div(None, 2) is None
    assert safe_div(10, float("nan")) is None


def test_missing_is_not_zero():
    assert safe_add(1, None) is None
    assert average(10, None) is None


def test_cagr_and_pct_change():
    assert cagr(200, 100, 1) == pytest.approx(100.0)
    assert cagr(133.1, 100, 3) == pytest.approx(10.0, rel=1e-6)
    assert cagr(100, -50, 3) is None          # negative base -> not meaningful
    assert cagr(-10, 50, 3) is None
    assert pct_change(110, 100) == pytest.approx(10.0)
    assert pct_change(110, 0) is None


def test_indian_formatting():
    assert indian_group(12345678) == "1,23,45,678"
    assert fmt_cr(1234.4) == "₹1,234 Cr"
    assert fmt_cr(-50.0) == "-₹50 Cr"
    assert fmt_cr(None) == "N/A"
    assert fmt_cr(402962) == "₹4.03 L Cr"
    assert fmt_cr(0.5) == "₹50.0 L"


# ----------------------------------------------------------------- fixture company
def make_company(sector_class="manufacturing", eps=(10.0, 12.0, 14.0, 16.0), interest=(20, 20, 25, 25)) -> CompanyData:
    cols = [pd.Timestamp(f"{y}-03-31") for y in (2022, 2023, 2024, 2025)]
    df = pd.DataFrame({
        "revenue": [1000, 1100, 1200, 1300],
        "ebit": [100, 120, 150, 160],
        "depreciation": [30, 30, 30, 30],
        "interest": list(interest),
        "pbt": [80, 100, 125, 135],
        "tax": [20, 25, 31.25, 33.75],          # 25% effective
        "net_income": [60, 75, 93.75, 101.25],
        "eps_basic": list(eps),
        "total_equity": [500, 550, 600, 650],
        "total_debt": [200, 200, 250, 250],
        "cash": [50, 50, 60, 66],               # excess cash = cash - 2% revenue
        "total_assets": [900, 950, 1050, 1100],
        "current_liabilities": [200, 200, 200, 200],
        "cfo": [70, 80, 90, 100],
        "capex": [40, 40, 40, 40],
    }, index=cols).T
    ident = CompanyIdentity(name="TestCo", nse_symbol="TEST", sector_class=sector_class)
    d = CompanyData(identity=ident)
    d.annual = finalize_statement(df, d.item_sources, "annual")
    d.statement_source = "test"
    idx = pd.bdate_range("2021-01-01", "2025-06-30")
    d.price_history = pd.DataFrame({"Close": np.linspace(100, 320, len(idx))}, index=idx)
    d.quote = {"price": 320.0, "market_cap_cr": 2000.0, "trailing_eps": 16.0}
    return d


def test_derived_items():
    d = make_company()
    a = d.annual
    assert a.at["ebitda", pd.Timestamp("2025-03-31")] == 190          # EBIT + D&A
    assert a.at["fcf", pd.Timestamp("2025-03-31")] == 60               # CFO - capex


def test_roe_roce_roic_de_icr():
    d = make_company()
    at = annual_ratio_table(d)
    last = at.iloc[-1]
    # ROE = 101.25 / avg(600,650) = 16.2%
    assert last["roe"] == pytest.approx(101.25 / 625 * 100)
    # ROCE (TA-CL): CE 2025 = 900, 2024 = 850 -> avg 875 ; 160/875
    assert last["roce"] == pytest.approx(160 / 875 * 100)
    assert at.attrs["ce_definition"].startswith("Total assets")
    # ROIC: NOPAT = 160*(1-0.25)=120; IC = Eq+Debt-(cash-2%rev)
    ic25 = 650 + 250 - (66 - 0.02 * 1300)
    ic24 = 600 + 250 - (60 - 0.02 * 1200)
    assert last["roic"] == pytest.approx(120 / ((ic25 + ic24) / 2) * 100)
    assert last["de"] == pytest.approx(250 / 650)
    assert last["icr"] == pytest.approx(160 / 25)
    # Historical P/E uses FY-end price and FY EPS (not today's)
    assert last["pe"] == pytest.approx(last["fy_end_price"] / 16.0)
    assert at.iloc[0]["pe"] == pytest.approx(at.iloc[0]["fy_end_price"] / 10.0)


def test_pe_peg_and_ev():
    d = make_company()
    at, qt = annual_ratio_table(d), quarterly_table(d)
    r = compute_core_ratios(d, at, qt)
    assert r["pe"].value == pytest.approx(320 / 16)
    g = cagr(16, 10, 3)
    assert r["eps_cagr_3y"].value == pytest.approx(g)
    assert r["peg"].value == pytest.approx((320 / 16) / g)
    assert r["ev_ebitda"].value == pytest.approx((2000 + 250 - 66) / 190)
    assert r["pb"].value == pytest.approx(2000 / 650)


def test_negative_eps_makes_pe_and_peg_not_meaningful():
    d = make_company(eps=(10, 8, 2, -3))
    d.quote["trailing_eps"] = -3.0
    at, qt = annual_ratio_table(d), quarterly_table(d)
    r = compute_core_ratios(d, at, qt)
    assert r["pe"].status == NOT_MEANINGFUL
    assert r["peg"].status == NOT_MEANINGFUL


def test_negative_growth_peg_not_meaningful():
    d = make_company(eps=(16, 14, 12, 10))
    d.quote["trailing_eps"] = 10.0
    r = compute_core_ratios(d, annual_ratio_table(d), quarterly_table(d))
    assert r["peg"].status == NOT_MEANINGFUL


def test_negative_equity_handled():
    d = make_company()
    d.annual.loc["total_equity", pd.Timestamp("2025-03-31")] = -100
    at = annual_ratio_table(d)
    r = compute_core_ratios(d, at, quarterly_table(d))
    assert r["roe"].status == NOT_MEANINGFUL
    assert r["de"].status == NOT_MEANINGFUL


def test_missing_interest_is_unavailable_not_zero():
    d = make_company()
    d.annual.loc["interest", pd.Timestamp("2025-03-31")] = np.nan
    at = annual_ratio_table(d)
    assert pd.isna(at.iloc[-1]["icr"])
    icr = analyse_interest_coverage(d, at, quarterly_table(d))
    assert icr["metric"].status == UNAVAILABLE


def test_zero_interest_debt_free():
    d = make_company(interest=(0, 0, 0, 0))
    at = annual_ratio_table(d)
    icr = analyse_interest_coverage(d, at, quarterly_table(d))
    assert icr["metric"].status == NOT_MEANINGFUL
    assert icr["label"] == "Strong (no interest)"


def test_icr_thresholds_sector_specific():
    assert classify_icr(0.8, "manufacturing") == "Serious concern"
    assert classify_icr(1.6, "manufacturing") == "Weak"
    assert classify_icr(3.0, "manufacturing") == "Moderate"
    assert classify_icr(5.0, "manufacturing") == "Strong"
    assert classify_icr(1.6, "infrastructure") == "Moderate"
    assert classify_icr(5.0, "it_services") == "Moderate"


def test_wacc_formula():
    d = make_company()
    at = annual_ratio_table(d)
    r = compute_core_ratios(d, at, quarterly_table(d))
    rw = analyse_roic_wacc(d, at, r)          # no benchmark -> default beta
    beta = rw["beta"].value
    ke = ASSUMPTIONS.risk_free_rate + beta * ASSUMPTIONS.equity_risk_premium
    kd = 25 / 250                               # interest / avg debt (250, 250)
    E, D, t = 2000, 250, 0.25
    expected = E / (E + D) * ke + D / (E + D) * kd * (1 - t)
    assert rw["wacc"].value == pytest.approx(expected * 100)
    assert rw["spread"].value == pytest.approx(r["roic"].value - expected * 100)
    assert rw["wacc"].status == "Estimate"


def test_bank_treatment():
    d = make_company(sector_class="bank")
    at = annual_ratio_table(d)
    r = compute_core_ratios(d, at, quarterly_table(d))
    assert r["de"].status == NOT_MEANINGFUL
    assert r["roic"].status == NOT_MEANINGFUL
    assert analyse_interest_coverage(d, at, quarterly_table(d))["metric"].status == NOT_MEANINGFUL
    rw = analyse_roic_wacc(d, at, r)
    assert rw["spread_kind"] == "ROE vs Cost of equity"


def test_period_analysis_marks_incomplete():
    d = make_company()
    at = annual_ratio_table(d)
    per = analyse_periods(d.price_history, at, quarterly_table(d), ["3M", "1Y", "3Y", "5Y"])
    assert per.loc["3Y", "revenue_growth"] == pytest.approx(cagr(1300, 1000, 3))
    assert pd.isna(per.loc["5Y"].get("revenue_growth", np.nan))      # only 4 years available
    assert "Needs 6 years" in per.loc["5Y", "note"]
    assert "quarterly" in per.loc["3M", "note"].lower()             # no quarterly data


def test_score_renormalises_missing_categories():
    d = make_company()
    at = annual_ratio_table(d)
    r = compute_core_ratios(d, at, quarterly_table(d))
    ctx = {"ratios": r, "annual_table": at, "sector_class": "manufacturing", "peer_median": {},
           "icr": analyse_interest_coverage(d, at, quarterly_table(d)),
           "roic_wacc": analyse_roic_wacc(d, at, r), "cashflow": {}, "promoter": {}, "bank_latest": {},
           "critical_flags": []}
    s = score(ctx)
    excluded = [row for row in s["table"] if row["Status"].startswith("Excluded")]
    assert {row["Category"] for row in excluded} == {"Cash flow", "Promoter and shareholder pattern"}
    assert s["coverage_pct"] == pytest.approx(80.0)
    assert sum(row["Adjusted weight"] for row in s["table"]) == pytest.approx(100.0)
    assert 0 <= s["overall"] <= 100
    ctx["critical_flags"] = ["ICR < 1"]
    assert score(ctx)["label"] == "High financial risk"
